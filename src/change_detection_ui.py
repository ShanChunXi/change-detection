# -*- coding: utf-8 -*-
"""
变化检测 — 桌面图形界面
基于 Python 标准库 tkinter，零额外依赖。
双击运行或: python change_detection_ui.py
"""

import os
import sys
import json
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)

from change_detection import (
    run_self_check,
    run_single_inference,
    run_batch_inference,
    AVAILABLE_MODELS,
    load_config,
    save_config,
    _remember_last_params,
)

# ============================================================
# 线程通信
# ============================================================

_log_queue = queue.Queue()


def _emit(msg, tag="dim"):
    _log_queue.put((msg, tag))


def _run_inference_thread(before, after, out, model, gpu, out_format):
    """后台线程：执行推理，stdout 全部重定向到 UI。"""
    import io
    old_stdout = sys.stdout
    buf = io.StringIO()
    sys.stdout = buf
    ok = False
    try:
        ok = run_single_inference(
            before_path=before, after_path=after, out_path=out,
            model_key=model, gpu=gpu, batch_size=1, offset=None,
            result_type="grid", out_dataset_name="predict_change",
            out_format=out_format,
        )
        if ok:
            _remember_last_params(before, after, out, model, gpu, out_format)
    except Exception as e:
        print(f"[错误] {e}")
        ok = False
    finally:
        sys.stdout = old_stdout

    for line in buf.getvalue().split("\n"):
        t = line.strip()
        if not t:
            continue
        if "[OK]" in t or "完成" in t:
            _emit(t, "ok")
        elif "[错误]" in t or "Error" in t:
            _emit(t, "fail")
        elif t.startswith("="):
            _emit(t, "header")
        else:
            _emit(t, "dim")

    _emit("__DONE__" if ok else "__FAIL__", "signal")


# ============================================================
# 配置对话框
# ============================================================

SETUP_FIELDS = [
    ("python_path",   "SuperMap Python 路径",
     "含 iobjectspy 的 Python 解释器",
     "F:/supermap/supermap-iobjectspy-env-gpu-2026-win64/conda/python.exe"),
    ("java_home",     "iObjects Java JRE 路径",
     "SuperMap iObjects Java 的 JRE 目录",
     "F:/supermap/supermap-iobjectsjava-2026-win-all/jre1.8_x64"),
    ("iobjects_bin",  "iObjects Java Bin 路径",
     "SuperMap iObjects Java 的 Bin 目录",
     "F:/supermap/supermap-iobjectsjava-2026-win-all/Bin"),
    ("resources_ml",  "ML 资源包路径",
     "内含 model 文件夹的 resources_ml 目录",
     "F:/supermap/supermap-iobjectspy-resources_ml-2025u1/resources_ml"),
]


class SetupDialog(tk.Toplevel):
    """配置向导弹窗。"""

    def __init__(self, parent, colors, on_save_callback):
        super().__init__(parent)
        self.colors = colors
        self.on_save_callback = on_save_callback
        self.entries = {}
        self.status_labels = {}

        self.title("环境配置")
        self.geometry("660x530")
        self.resizable(False, False)
        self.configure(bg=colors["panel"])
        self.transient(parent)
        self.grab_set()

        # 居中于父窗口
        self.update_idletasks()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        w, h = 660, 530
        self.geometry(f"{w}x{h}+{px + (pw - w) // 2}+{py + (ph - h) // 2}")

        self._build()

    def _build(self):
        c = self.colors

        # 标题
        header = tk.Frame(self, bg=c["panel"], height=48)
        header.pack(fill="x", padx=20, pady=(20, 0))
        tk.Label(header, text="⚙  首次配置 — SuperMap 环境路径",
                 bg=c["panel"], fg=c["text"],
                 font=("Microsoft YaHei UI", 14, "bold")).pack(side="left")
        tk.Label(header, text="配置一次，以后自动记住",
                 bg=c["panel"], fg=c["dim"],
                 font=("Microsoft YaHei UI", 9)).pack(side="right", pady=4)

        # 分隔线
        tk.Frame(self, bg=c["border"], height=1).pack(fill="x", padx=20, pady=(10, 14))

        # 表单区域
        form = tk.Frame(self, bg=c["panel"])
        form.pack(fill="both", expand=True, padx=20)

        cfg = load_config()

        for i, (key, title, hint, example) in enumerate(SETUP_FIELDS):
            # 行容器
            row = tk.Frame(form, bg=c["panel"])
            row.pack(fill="x", pady=(0, 10))

            # 标签
            lbl_frame = tk.Frame(row, bg=c["panel"], width=160)
            lbl_frame.pack(side="left", fill="y")
            lbl_frame.pack_propagate(False)
            tk.Label(lbl_frame, text=title, bg=c["panel"], fg=c["text"],
                     font=("Microsoft YaHei UI", 10), anchor="w").pack(anchor="w")

            # 输入区
            input_frame = tk.Frame(row, bg=c["panel"])
            input_frame.pack(side="left", fill="x", expand=True, padx=(8, 0))

            entry_row = tk.Frame(input_frame, bg=c["panel"])
            entry_row.pack(fill="x")

            var = tk.StringVar(value=cfg.get(key, ""))
            self.entries[key] = var
            entry = tk.Entry(entry_row, textvariable=var,
                             bg=c["input"], fg=c["text"],
                             font=("Consolas", 9),
                             insertbackground=c["text"],
                             relief="flat", borderwidth=0)
            entry.pack(side="left", fill="x", expand=True, ipady=5)

            # 浏览按钮（python_path 选文件，其他选目录）
            is_file = (key == "python_path")
            ttk.Button(entry_row, text="浏览", style="Small.TButton",
                       command=lambda k=key, f=is_file: self._browse_path(k, f)).pack(side="left", padx=(6, 0))

            # 示例
            tk.Label(input_frame, text=f"示例: {example}", bg=c["panel"],
                     fg=c["dim"], font=("Consolas", 7),
                     anchor="w").pack(fill="x", pady=(2, 0))

            # 状态
            status_lbl = tk.Label(input_frame, text="", bg=c["panel"],
                                  font=("Microsoft YaHei UI", 8), anchor="w")
            status_lbl.pack(fill="x")
            self.status_labels[key] = status_lbl

        # 自动检测按钮
        auto_row = tk.Frame(form, bg=c["panel"])
        auto_row.pack(fill="x", pady=(4, 12))
        tk.Label(auto_row, text="💡 如果安装了标准路径的 SuperMap，可尝试自动检测",
                 bg=c["panel"], fg=c["dim"], font=("Microsoft YaHei UI", 9)).pack(side="left")
        ttk.Button(auto_row, text="自动检测", style="Small.TButton",
                   command=self._auto_detect).pack(side="left", padx=(8, 0))

        # 底部按钮
        footer = tk.Frame(self, bg=c["panel"], height=56)
        footer.pack(fill="x", padx=20, pady=(0, 16))

        ttk.Button(footer, text="取消", style="Small.TButton",
                   command=self.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(footer, text="保存并自检", style="Small.TButton",
                   command=self._save_and_check).pack(side="right")
        save_btn = ttk.Button(footer, text="💾 保存配置", style="Accent.TButton",
                              command=self._save)
        save_btn.pack(side="right", padx=(0, 8))

        # 实时路径校验
        for key in SETUP_FIELDS:
            self.entries[key[0]].trace_add("write", lambda *a, k=key[0]: self._validate_path(k))
            self._validate_path(key[0])

    def _browse_path(self, key, is_file=False):
        if is_file:
            path = filedialog.askopenfilename(
                title="选择 Python 解释器",
                filetypes=[("可执行文件", "python.exe"), ("所有文件", "*.*")]
            )
        else:
            path = filedialog.askdirectory(title="选择目录")
        if path:
            self.entries[key].set(path)

    def _validate_path(self, key):
        path = self.entries[key].get().strip()
        lbl = self.status_labels[key]
        if not path:
            lbl.configure(text="尚未填写", fg=self.colors["dim"])
        elif os.path.exists(path):
            lbl.configure(text="✓ 路径存在", fg=self.colors["green"])
        else:
            lbl.configure(text="✗ 路径不存在", fg=self.colors["red"])

    def _auto_detect(self):
        """扫描常见 SuperMap 安装路径。"""
        drives = ["F:/", "D:/", "E:/", "C:/"]
        patterns = {
            "python_path": [
                "/supermap-iobjectspy-env-gpu-2026-win64/conda/python.exe",
                "/supermap-iobjectspy-env-2026-win64/conda/python.exe",
                "/SuperMap/iObjectspy/env/conda/python.exe",
            ],
            "java_home": [
                "/supermap-iobjectsjava-2026-win-all/jre1.8_x64",
                "/SuperMap/iObjectsJava/jre1.8_x64",
            ],
            "iobjects_bin": [
                "/supermap-iobjectsjava-2026-win-all/Bin",
                "/SuperMap/iObjectsJava/Bin",
            ],
            "resources_ml": [
                "/supermap-iobjectspy-resources_ml-2025u1/resources_ml",
                "/supermap-iobjectspy-resources_ml-2026/resources_ml",
                "/SuperMap/resources_ml",
            ],
        }

        found_count = 0
        for key, subpaths in patterns.items():
            for drive in drives:
                for sub in subpaths:
                    full = os.path.join(drive, sub.replace("/", os.sep))
                    if os.path.exists(full):
                        full = full.replace("\\", "/")
                        self.entries[key].set(full)
                        found_count += 1
                        break
                if self.entries[key].get().strip():
                    break

        if found_count > 0:
            messagebox.showinfo("自动检测", f"已找到 {found_count} 个路径，请核对后保存。")
        else:
            messagebox.showinfo("自动检测", "未找到 SuperMap 标准安装路径，请手动填写。")

    def _save(self):
        cfg = load_config()
        for key, _, _, _ in SETUP_FIELDS:
            cfg[key] = self.entries[key].get().strip()

        if save_config(cfg):
            self.on_save_callback()
            messagebox.showinfo("保存成功", "配置已保存到 config.json")
            self.destroy()
        else:
            messagebox.showerror("保存失败", "无法写入 config.json，请检查文件权限。")

    def _save_and_check(self):
        self._save()
        if self.winfo_exists():
            return
        # 如果保存成功（窗口已关闭），触发回调做自检
        # 这里 _save 中 destroy 后回调已执行，父窗口可再调 check


def _run_batch_thread(csv_path, model, gpu, out_format):
    """后台线程：批量推理。"""
    import io
    old_stdout = sys.stdout
    buf = io.StringIO()
    sys.stdout = buf
    ok = False
    try:
        ok = run_batch_inference(
            csv_path=csv_path, model_key=model, gpu=gpu, batch_size=1,
            offset=None, result_type="grid", out_format=out_format,
        )
    except Exception as e:
        print(f"[错误] {e}")
        ok = False
    finally:
        sys.stdout = old_stdout

    for line in buf.getvalue().split("\n"):
        t = line.strip()
        if not t:
            continue
        if "[OK]" in t or "成功" in t or "完成" in t:
            _emit(t, "ok")
        elif "[错误]" in t or "Error" in t or "失败" in t:
            _emit(t, "fail")
        elif t.startswith("="):
            _emit(t, "header")
        else:
            _emit(t, "dim")

    _emit("__DONE__" if ok else "__FAIL__", "signal")


# ============================================================
# 主窗口
# ============================================================

class ChangeDetectionApp:
    def __init__(self, root):
        self.root = root
        self.root.title("变化检测工具 — SuperMap Cup")
        self.root.geometry("1020x660")
        self.root.minsize(860, 520)
        self._center_window()

        self.colors = {
            "bg":       "#1e1e2e",
            "panel":    "#252536",
            "input":    "#181825",
            "border":   "#3a3a50",
            "text":     "#cdd6f4",
            "dim":      "#6c7086",
            "accent":   "#89b4fa",
            "accent2":  "#cba6f7",
            "green":    "#a6e3a1",
            "red":      "#f38ba8",
            "yellow":   "#f9e2af",
            "terminal": "#11111b",
        }

        self.root.configure(bg=self.colors["bg"])
        self._setup_styles()
        self._build_ui()
        self._load_saved_params()
        self._poll_log_queue()

        # 首次使用：如果配置为空，自动弹出配置窗口
        self.root.after(500, self._auto_open_setup_if_needed)

    def _center_window(self):
        self.root.update_idletasks()
        w, h = 1020, 660
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    # ============================================================
    # Styles
    # ============================================================
    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")

        c = self.colors
        style.configure(".", background=c["bg"], foreground=c["text"],
                        font=("Microsoft YaHei UI", 10))
        style.configure("Card.TFrame", background=c["panel"])
        style.configure("Terminal.TFrame", background=c["terminal"])
        style.configure("Accent.TButton",
                        background=c["accent"], foreground=c["bg"],
                        font=("Microsoft YaHei UI", 11, "bold"),
                        borderwidth=0, padding=10)
        style.map("Accent.TButton",
                  background=[("active", "#a6c8ff"), ("disabled", c["border"])])
        style.configure("Small.TButton",
                        background=c["border"], foreground=c["text"],
                        font=("Microsoft YaHei UI", 9),
                        borderwidth=0, padding=(8, 4))
        style.map("Small.TButton",
                  background=[("active", "#5a5a78")])
        style.configure("Link.TButton",
                        background=c["panel"], foreground=c["accent"],
                        font=("Microsoft YaHei UI", 9, "underline"),
                        borderwidth=0, padding=4)
        style.map("Link.TButton",
                  foreground=[("active", c["accent2"])])

    # ============================================================
    # UI 构建
    # ============================================================
    def _build_ui(self):
        c = self.colors
        root = self.root

        # ----- 顶部标题栏 -----
        title_bar = tk.Frame(root, bg=c["panel"], height=50)
        title_bar.pack(fill="x", side="top")
        title_bar.pack_propagate(False)

        tk.Label(title_bar, text="🛰  变化检测工具",
                 bg=c["panel"], fg=c["text"],
                 font=("Microsoft YaHei UI", 13, "bold")).pack(side="left", padx=16, pady=12)

        # 配置按钮
        ttk.Button(title_bar, text="⚙  环境配置", style="Link.TButton",
                   command=self._open_setup).pack(side="right", padx=(0, 12), pady=12)

        self.status_label = tk.Label(title_bar, text="就绪",
                                     bg=c["panel"], fg=c["dim"],
                                     font=("Microsoft YaHei UI", 10))
        self.status_label.pack(side="right", padx=8, pady=12)

        # ----- 主体：左右分栏 -----
        main_frame = tk.Frame(root, bg=c["bg"])
        main_frame.pack(fill="both", expand=True, side="top")

        self._build_left_panel(main_frame)
        self._build_right_panel(main_frame)

    def _build_left_panel(self, parent):
        c = self.colors
        left = tk.Frame(parent, bg=c["panel"], width=370)
        left.pack(side="left", fill="y", padx=(0, 1))
        left.pack_propagate(False)

        canvas = tk.Canvas(left, bg=c["panel"], highlightthickness=0, width=370)
        scrollbar = tk.Scrollbar(left, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg=c["panel"])
        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw", width=370)
        canvas.configure(yscrollcommand=scrollbar.set)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # ---- 环境状态 ----
        self._section_label(scroll_frame, "🔧 环境状态")
        env_card = tk.Frame(scroll_frame, bg=c["input"], padx=12, pady=10)
        env_card.pack(fill="x", padx=14, pady=(2, 6))
        self.env_status = tk.Label(env_card, text="●  未检测", bg=c["input"], fg=c["dim"],
                                   font=("Microsoft YaHei UI", 10))
        self.env_status.pack(side="left")
        ttk.Button(env_card, text="环境自检", style="Small.TButton",
                   command=self._check_env).pack(side="right")

        # 配置提示
        self.config_hint = tk.Label(scroll_frame, text="", bg=c["panel"], fg=c["yellow"],
                                    font=("Microsoft YaHei UI", 8), wraplength=340, justify="left")
        self.config_hint.pack(fill="x", padx=14, pady=(0, 8))
        self._update_config_hint()

        # ---- 检测参数 ----
        self._section_label(scroll_frame, "📋 检测参数")

        # 模式切换：单次 / 批量
        mode_row = tk.Frame(scroll_frame, bg=c["panel"])
        mode_row.pack(fill="x", padx=14, pady=(0, 10))
        self.mode_var = tk.StringVar(value="single")
        self.mode_single_btn = ttk.Button(mode_row, text="单次检测", style="Small.TButton",
                                          command=lambda: self._switch_mode("single"))
        self.mode_single_btn.pack(side="left")
        self.mode_batch_btn = ttk.Button(mode_row, text="批量处理", style="Small.TButton",
                                         command=lambda: self._switch_mode("batch"))
        self.mode_batch_btn.pack(side="left", padx=(6, 0))
        self._update_mode_style()

        # 单次模式参数区
        self.single_frame = tk.Frame(scroll_frame, bg=c["panel"])
        self.single_frame.pack(fill="x")

        # 模型
        self._label(self.single_frame, "模型")
        self.model_var = tk.StringVar(value="building")
        model_f = tk.Frame(self.single_frame, bg=c["panel"])
        model_f.pack(fill="x", pady=(0, 10))
        model_cb = ttk.Combobox(model_f, textvariable=self.model_var,
                                values=list(AVAILABLE_MODELS.keys()),
                                state="readonly", font=("Microsoft YaHei UI", 10))
        model_cb.pack(fill="x")
        self.model_desc = tk.Label(self.single_frame, text="", bg=c["panel"], fg=c["dim"],
                                   font=("Microsoft YaHei UI", 8), wraplength=330, justify="left")
        self.model_desc.pack(fill="x", pady=(0, 10))
        model_cb.bind("<<ComboboxSelected>>", self._on_model_change)
        self._on_model_change()

        # 前期影像
        self._label(self.single_frame, "前期影像 (T1)")
        self.before_var = tk.StringVar()
        self._file_row(self.single_frame, self.before_var, is_image=True)

        # 后期影像
        self._label(self.single_frame, "后期影像 (T2)")
        self.after_var = tk.StringVar()
        self._file_row(self.single_frame, self.after_var, is_image=True)

        # 输出路径（带浏览按钮 — 保存文件）
        self._label(self.single_frame, "输出路径")
        self.out_var = tk.StringVar(value="result.udbx")
        out_row = tk.Frame(self.single_frame, bg=c["panel"])
        out_row.pack(fill="x", pady=(0, 10))
        tk.Entry(out_row, textvariable=self.out_var,
                 bg=c["input"], fg=c["text"],
                 font=("Consolas", 10),
                 insertbackground=c["text"],
                 relief="flat", borderwidth=0).pack(side="left", fill="x", expand=True, ipady=4)
        ttk.Button(out_row, text="浏览", style="Small.TButton",
                   command=self._browse_out).pack(side="left", padx=(6, 0))

        # GPU / 格式
        gpu_fmt_row = tk.Frame(self.single_frame, bg=c["panel"])
        gpu_fmt_row.pack(fill="x", pady=(0, 10))
        tk.Frame(gpu_fmt_row, bg=c["panel"]).pack(side="left", fill="x", expand=True)
        gpu_frame = tk.Frame(gpu_fmt_row, bg=c["panel"])
        gpu_frame.pack(side="left", padx=(0, 8))
        self._label(gpu_frame, "GPU", small=True)
        self.gpu_var = tk.StringVar(value="0")
        ttk.Combobox(gpu_frame, textvariable=self.gpu_var,
                     values=["0", "1", "-1 (CPU)"], width=8,
                     state="readonly", font=("Microsoft YaHei UI", 10)).pack()
        fmt_frame = tk.Frame(gpu_fmt_row, bg=c["panel"])
        fmt_frame.pack(side="left")
        self._label(fmt_frame, "格式", small=True)
        self.fmt_var = tk.StringVar(value="udbx")
        ttk.Combobox(fmt_frame, textvariable=self.fmt_var,
                     values=["udbx", "tif"], width=8,
                     state="readonly", font=("Microsoft YaHei UI", 10)).pack()

        # 批量模式参数区
        self.batch_frame = tk.Frame(scroll_frame, bg=c["panel"])

        self._label(self.batch_frame, "任务列表 (CSV)")
        tk.Label(self.batch_frame, text="每行: 前期影像,后期影像,输出路径",
                 bg=c["panel"], fg=c["dim"],
                 font=("Microsoft YaHei UI", 8), anchor="w").pack(fill="x", pady=(0, 4))
        self.csv_var = tk.StringVar()
        csv_row = tk.Frame(self.batch_frame, bg=c["panel"])
        csv_row.pack(fill="x", pady=(0, 10))
        tk.Entry(csv_row, textvariable=self.csv_var,
                 bg=c["input"], fg=c["text"],
                 font=("Consolas", 10),
                 insertbackground=c["text"],
                 relief="flat", borderwidth=0).pack(side="left", fill="x", expand=True, ipady=4)
        ttk.Button(csv_row, text="浏览", style="Small.TButton",
                   command=lambda: self._browse_file(self.csv_var, [("CSV文件", "*.csv"), ("所有文件", "*.*")])).pack(side="left", padx=(6, 0))

        self._label(self.batch_frame, "模型")
        self.batch_model_var = tk.StringVar(value="building")
        ttk.Combobox(self.batch_frame, textvariable=self.batch_model_var,
                     values=list(AVAILABLE_MODELS.keys()),
                     state="readonly", font=("Microsoft YaHei UI", 10)).pack(fill="x", pady=(0, 10))

        batch_row2 = tk.Frame(self.batch_frame, bg=c["panel"])
        batch_row2.pack(fill="x", pady=(0, 10))
        tk.Frame(batch_row2, bg=c["panel"]).pack(side="left", fill="x", expand=True)
        bg_frame = tk.Frame(batch_row2, bg=c["panel"])
        bg_frame.pack(side="left", padx=(0, 8))
        self._label(bg_frame, "GPU", small=True)
        self.batch_gpu_var = tk.StringVar(value="0")
        ttk.Combobox(bg_frame, textvariable=self.batch_gpu_var,
                     values=["0", "1", "-1 (CPU)"], width=8,
                     state="readonly", font=("Microsoft YaHei UI", 10)).pack()
        bf_frame = tk.Frame(batch_row2, bg=c["panel"])
        bf_frame.pack(side="left")
        self._label(bf_frame, "格式", small=True)
        self.batch_fmt_var = tk.StringVar(value="udbx")
        ttk.Combobox(bf_frame, textvariable=self.batch_fmt_var,
                     values=["udbx", "tif"], width=8,
                     state="readonly", font=("Microsoft YaHei UI", 10)).pack()

        # ---- 进度条 + 按钮 ----
        self.progress = ttk.Progressbar(scroll_frame, mode="indeterminate")
        self.progress.pack(fill="x", padx=14, pady=(6, 2))

        self.run_btn = ttk.Button(scroll_frame, text="▶  开始检测", style="Accent.TButton",
                                  command=self._run)
        self.run_btn.pack(fill="x", padx=14, pady=(10, 16))

    def _build_right_panel(self, parent):
        c = self.colors
        right = tk.Frame(parent, bg=c["terminal"])
        right.pack(side="left", fill="both", expand=True)

        log_header = tk.Frame(right, bg=c["panel"], height=36)
        log_header.pack(fill="x")
        log_header.pack_propagate(False)
        tk.Label(log_header, text="📟  运行日志", bg=c["panel"], fg=c["text"],
                 font=("Microsoft YaHei UI", 10, "bold")).pack(side="left", padx=14, pady=8)

        self.log_text = tk.Text(right, bg=c["terminal"], fg=c["dim"],
                                font=("Consolas", 10), wrap="word",
                                relief="flat", borderwidth=0,
                                padx=14, pady=10,
                                insertbackground=c["text"],
                                state="disabled")
        self.log_text.pack(fill="both", expand=True)

        self.log_text.tag_configure("ok", foreground=c["green"])
        self.log_text.tag_configure("fail", foreground=c["red"])
        self.log_text.tag_configure("warn", foreground=c["yellow"])
        self.log_text.tag_configure("header", foreground=c["text"],
                                    font=("Consolas", 10, "bold"))
        self.log_text.tag_configure("dim", foreground=c["dim"])
        self.log_text.tag_configure("info", foreground=c["accent"])

        self._log("欢迎使用变化检测工具", "header")
        self._log("点击顶部「⚙ 环境配置」设置路径，或直接填写检测参数。\n", "dim")

    # ============================================================
    # 辅助控件
    # ============================================================
    def _section_label(self, parent, text):
        tk.Label(parent, text=text, bg=self.colors["panel"], fg=self.colors["dim"],
                 font=("Microsoft YaHei UI", 10, "bold"),
                 anchor="w").pack(fill="x", padx=14, pady=(14, 4))

    def _label(self, parent, text, small=False):
        tk.Label(parent, text=text, bg=self.colors["panel"], fg=self.colors["dim"],
                 font=("Microsoft YaHei UI", 9 if small else 9),
                 anchor="w").pack(fill="x", padx=14, pady=(0, 2))

    def _file_row(self, parent, var, is_image=True):
        row = tk.Frame(parent, bg=self.colors["panel"])
        row.pack(fill="x", pady=(0, 10))
        tk.Entry(row, textvariable=var,
                 bg=self.colors["input"], fg=self.colors["text"],
                 font=("Consolas", 10),
                 insertbackground=self.colors["text"],
                 relief="flat", borderwidth=0).pack(side="left", fill="x", expand=True, ipady=4)
        ft = [("影像文件", "*.tif *.tiff *.img"), ("所有文件", "*.*")] if is_image else is_image
        ttk.Button(row, text="浏览", style="Small.TButton",
                   command=lambda v=var, f=ft: self._browse_file(v, f)).pack(side="left", padx=(6, 0))

    def _browse_file(self, var, filetypes=None):
        if filetypes is None:
            filetypes = [("影像文件", "*.tif *.tiff *.img"), ("所有文件", "*.*")]
        path = filedialog.askopenfilename(
            title="选择文件",
            filetypes=filetypes
        )
        if path:
            var.set(path)

    def _browse_out(self):
        path = filedialog.asksaveasfilename(
            title="保存检测结果",
            defaultextension=".udbx",
            filetypes=[("UDBX 数据源", "*.udbx"), ("GeoTIFF", "*.tif"), ("所有文件", "*.*")]
        )
        if path:
            self.out_var.set(path)

    # ============================================================
    # 日志
    # ============================================================
    def _log(self, msg, tag="dim"):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", msg + "\n", tag)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    # ============================================================
    # 配置对话框
    # ============================================================
    def _auto_open_setup_if_needed(self):
        """启动时检查配置：路径缺失或无效则自动弹窗提示。"""
        cfg = load_config()
        missing = []
        invalid = []
        for key, title, _, _ in SETUP_FIELDS:
            val = cfg.get(key, "")
            if not val:
                missing.append(title)
            elif not os.path.exists(val):
                invalid.append((title, val))

        if missing and not invalid:
            # 纯新用户，大部分没填
            if len(missing) >= 3:
                self._log("检测到首次使用，正在打开环境配置...", "info")
                self._open_setup()
        elif invalid:
            # 有配置但路径不存在 → 提醒重配
            self._log("═══════════════════════════════════════", "header")
            self._log("  ⚠ 检测到以下配置路径不存在：", "warn")
            for title, path in invalid:
                self._log(f"    • {title}", "warn")
                self._log(f"      {path}", "dim")
            self._log("", "dim")
            answer = messagebox.askyesno(
                "路径失效",
                f"检测到 {len(invalid)} 个已配置的路径不存在：\n\n" +
                "\n".join(f"  • {t}" for t, _ in invalid) +
                "\n\n是否打开环境配置窗口重新设置？"
            )
            if answer:
                self._open_setup()

    def _open_setup(self):
        SetupDialog(self.root, self.colors, self._update_config_hint)

    def _update_config_hint(self):
        cfg = load_config()
        missing = []
        invalid = []
        for key, title, _, _ in SETUP_FIELDS:
            val = cfg.get(key, "")
            if not val:
                missing.append(title)
            elif not os.path.exists(val):
                invalid.append(title)

        if not missing and not invalid:
            self.config_hint.configure(text="✓ 环境路径已全部配置", fg=self.colors["green"])
        else:
            parts = []
            if missing:
                parts.append(f"未配置：{', '.join(missing)}")
            if invalid:
                parts.append(f"路径无效：{', '.join(invalid)}")
            self.config_hint.configure(
                text=f"⚠ {' | '.join(parts)}\n点击顶部「⚙ 环境配置」重新设置",
                fg=self.colors["red"] if invalid else self.colors["yellow"])

    # ============================================================
    # 环境自检
    # ============================================================
    def _check_env(self):
        # 先检查配置是否完整
        cfg = load_config()
        missing = [k for k, _, _, _ in SETUP_FIELDS if not cfg.get(k, "")]
        if len(missing) >= 4:
            answer = messagebox.askyesno(
                "环境未配置",
                "尚未配置 SuperMap 环境路径，是否现在进行配置？\n\n"
                "配置完成后才能运行环境自检。"
            )
            if answer:
                self._open_setup()
            return

        self._log("═══════════════════════════════════════", "header")
        self._log("  正在运行环境自检...\n", "info")
        self.env_status.configure(text="●  检测中...", fg=self.colors["yellow"])
        self.root.update()

        import io
        old_stdout = sys.stdout
        buf = io.StringIO()
        sys.stdout = buf
        try:
            ok = run_self_check()
        except Exception as e:
            self._log(f"[错误] {e}", "fail")
            ok = False
        finally:
            sys.stdout = old_stdout

        for line in buf.getvalue().split("\n"):
            t = line.strip()
            if not t:
                continue
            if "[OK]" in t:
                self._log(t, "ok")
            elif "[FAIL]" in t:
                self._log(t, "fail")
            elif "[WARN]" in t:
                self._log(t, "warn")
            elif t.startswith("="):
                self._log(t, "header")
            else:
                self._log(t, "dim")

        if ok:
            self.env_status.configure(text="●  环境就绪", fg=self.colors["green"])
        else:
            self.env_status.configure(text="●  配置有误", fg=self.colors["red"])

    # ============================================================
    # 模式切换
    # ============================================================
    def _switch_mode(self, mode):
        self.mode_var.set(mode)
        self._update_mode_style()
        if mode == "single":
            self.single_frame.pack(fill="x")
            self.batch_frame.pack_forget()
            self.run_btn.configure(text="▶  开始检测")
        else:
            self.single_frame.pack_forget()
            self.batch_frame.pack(fill="x")
            self.run_btn.configure(text="▶  批量处理")

    def _update_mode_style(self):
        mode = self.mode_var.get()
        # 不能用 ttk style map 动态改，直接换文字标记
        if mode == "single":
            self.mode_single_btn.configure(text="● 单次检测")
            self.mode_batch_btn.configure(text="  批量处理")
        else:
            self.mode_single_btn.configure(text="  单次检测")
            self.mode_batch_btn.configure(text="● 批量处理")

    # ============================================================
    # 统一运行入口
    # ============================================================
    def _run(self):
        if self.mode_var.get() == "single":
            self._run_single()
        else:
            self._run_batch()

    def _run_single(self):
        before = self.before_var.get().strip()
        after = self.after_var.get().strip()
        out = self.out_var.get().strip() or "result.udbx"

        if not before:
            messagebox.showwarning("参数不完整", "请选择前期影像 (T1)")
            return
        if not after:
            messagebox.showwarning("参数不完整", "请选择后期影像 (T2)")
            return

        model = self.model_var.get()
        gpu_str = self.gpu_var.get().split()[0]
        try:
            gpu = int(gpu_str)
        except ValueError:
            gpu = 0
        out_format = self.fmt_var.get()

        self.run_btn.configure(state="disabled", text="⏳  检测中...")
        self.progress.start(10)
        self.status_label.configure(text="推理中...", fg=self.colors["accent"])

        self._log("═══════════════════════════════════════", "header")
        self._log(f"  前期影像: {before}", "dim")
        self._log(f"  后期影像: {after}", "dim")
        self._log(f"  输出路径: {out}", "dim")
        model_name = AVAILABLE_MODELS.get(model, {}).get("name", model)
        self._log(f"  模型: {model_name}", "dim")
        self._log(f"  设备: {'GPU ' + str(gpu) if gpu >= 0 else 'CPU'}  ·  格式: {out_format}\n", "dim")

        t = threading.Thread(
            target=_run_inference_thread,
            args=(before, after, out, model, gpu, out_format),
            daemon=True,
        )
        t.start()

    def _run_batch(self):
        csv_path = self.csv_var.get().strip()
        if not csv_path:
            messagebox.showwarning("参数不完整", "请选择 CSV 任务文件")
            return

        model = self.batch_model_var.get()
        gpu_str = self.batch_gpu_var.get().split()[0]
        try:
            gpu = int(gpu_str)
        except ValueError:
            gpu = 0
        out_format = self.batch_fmt_var.get()

        self.run_btn.configure(state="disabled", text="⏳  批量处理中...")
        self.progress.start(10)
        self.status_label.configure(text="推理中...", fg=self.colors["accent"])

        self._log("═══════════════════════════════════════", "header")
        self._log(f"  模式: 批量处理", "info")
        self._log(f"  CSV: {csv_path}", "dim")
        model_name = AVAILABLE_MODELS.get(model, {}).get("name", model)
        self._log(f"  模型: {model_name}", "dim")
        self._log(f"  设备: {'GPU ' + str(gpu) if gpu >= 0 else 'CPU'}  ·  格式: {out_format}\n", "dim")

        t = threading.Thread(
            target=_run_batch_thread,
            args=(csv_path, model, gpu, out_format),
            daemon=True,
        )
        t.start()

    # ============================================================
    # 轮询日志队列
    # ============================================================
    def _poll_log_queue(self):
        try:
            while True:
                msg, tag = _log_queue.get_nowait()
                if tag == "signal":
                    self.progress.stop()
                    self.run_btn.configure(state="normal", text="▶  开始检测")
                    if msg == "__DONE__":
                        self._log("\n  ✅ 变化检测完成！", "ok")
                        self.status_label.configure(text="检测完成", fg=self.colors["green"])
                    else:
                        self._log("\n  ❌ 检测失败，请查看上方日志", "fail")
                        self.status_label.configure(text="检测失败", fg=self.colors["red"])
                else:
                    self._log(msg, tag)
        except queue.Empty:
            pass
        self.root.after(200, self._poll_log_queue)

    # ============================================================
    # 加载上次参数
    # ============================================================
    def _load_saved_params(self):
        try:
            cfg = load_config()
            lp = cfg.get("last_params", {})
            if lp.get("before"):
                self.before_var.set(lp["before"])
            if lp.get("after"):
                self.after_var.set(lp["after"])
            if lp.get("out"):
                self.out_var.set(lp["out"])
            if lp.get("model"):
                self.model_var.set(lp["model"])
                self._on_model_change()
            if lp.get("gpu") is not None:
                g = lp["gpu"]
                self.gpu_var.set(str(g) if g < 0 else str(g))
            if lp.get("out_format"):
                self.fmt_var.set(lp["out_format"])
        except Exception:
            pass

    def _on_model_change(self, event=None):
        key = self.model_var.get()
        info = AVAILABLE_MODELS.get(key, {})
        self.model_desc.configure(text=info.get("description", ""))


# ============================================================
# 入口
# ============================================================

def main():
    root = tk.Tk()
    app = ChangeDetectionApp(root)  # noqa: F841
    root.mainloop()


if __name__ == "__main__":
    main()
