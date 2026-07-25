# -*- coding: utf-8 -*-
"""
================================================================================
 通用变化检测 — 参数化命令行工具
 第24届 SuperMap 杯高校 GIS 大赛 开发组
 负责：张硕岐
================================================================================

功能：
  基于 SuperMap iObjects Python 的遥感影像变化检测推理工具。
  通过 config.json 配置环境路径，可在不同电脑上使用。

首次使用：
  python change_detection.py setup    # 配置向导
  python change_detection.py check    # 环境自检

日常使用：
  python change_detection.py run --before 2020.tif --after 2024.tif --out result.udbx
  python change_detection.py menu     # 交互菜单
  python change_detection.py batch --csv tasks.csv
"""

import os
import sys
import json
import warnings
import argparse
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Tuple, Dict

warnings.filterwarnings("ignore")

# ============================================================================
# 0. 配置文件加载
# ============================================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")

DEFAULT_CONFIG: Dict[str, object] = {
    "java_home": "",
    "iobjects_bin": "",
    "resources_ml": "",
    "python_path": "",
    # --- 记忆功能：保存上次成功运行的参数，下次自动预填 ---
    "last_params": {
        "before": "",
        "after": "",
        "out": "result.udbx",
        "model": "building",
        "gpu": 0,
        "out_format": "udbx",
    },
}


def load_config() -> Dict[str, object]:
    """加载 config.json，不存在则返回默认空值。"""
    if not os.path.exists(CONFIG_PATH):
        return dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"[警告] 配置文件读取失败: {e}")
        return dict(DEFAULT_CONFIG)

    result = dict(DEFAULT_CONFIG)
    for key in DEFAULT_CONFIG:
        if key in cfg and not key.startswith("_"):
            # 嵌套字典（如 last_params）：深度合并，保留默认结构
            if isinstance(DEFAULT_CONFIG[key], dict) and isinstance(cfg[key], dict):
                merged = dict(DEFAULT_CONFIG[key])
                merged.update(cfg[key])
                result[key] = merged
            else:
                result[key] = cfg[key]
    return result


def save_config(cfg: Dict[str, object]) -> bool:
    """保存配置到 config.json。"""
    # 只保留 DEFAULT_CONFIG 中定义的 key
    out = {}
    for key in DEFAULT_CONFIG:
        out[key] = cfg.get(key, DEFAULT_CONFIG[key])
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=4, ensure_ascii=False)
        return True
    except IOError as e:
        print(f"[错误] 无法写入配置文件: {e}")
        return False


def _remember_last_params(before: str, after: str, out: str,
                         model: str, gpu: int, out_format: str):
    """将本次成功运行的参数写入 config.json，下次自动预填。"""
    cfg = load_config()
    cfg["last_params"] = {
        "before": before,
        "after": after,
        "out": out,
        "model": model,
        "gpu": gpu,
        "out_format": out_format,
    }
    save_config(cfg)


# ============================================================================
# 1. 环境设置
# ============================================================================

def setup_environment():
    """根据 config.json 设置 JAVA_HOME、PATH 和 iObjects Java 路径。"""
    cfg = load_config()

    java_home = cfg.get("java_home", "")
    iobjects_bin = cfg.get("iobjects_bin", "")

    if java_home:
        os.environ["JAVA_HOME"] = java_home
    if iobjects_bin:
        os.environ["PATH"] = (
            os.path.join(java_home, "bin") + ";" +
            iobjects_bin + ";" +
            os.environ.get("PATH", "")
        )
        try:
            from iobjectspy import env
            env.set_iobjects_java_path(iobjects_bin)
        except ImportError:
            pass


# 启动时自动加载配置
_config = load_config()

# -- 兼容旧版直接引用（从 config 读取） --
JAVA_HOME    = _config.get("java_home", "")
IOBJECTS_BIN = _config.get("iobjects_bin", "")
RESOURCES_ML = _config.get("resources_ml", "")
MODEL_DIR    = os.path.join(RESOURCES_ML, "model") if RESOURCES_ML else ""

# 初始化环境
if JAVA_HOME and IOBJECTS_BIN:
    setup_environment()


# ============================================================================
# 2. 可用模型注册表
# ============================================================================

AVAILABLE_MODELS = {
    "building": {
        "name": "建筑物变化检测 (SiamSFNet)",
        "filename": "general_cd_siamsfnet_building/general_cd_siamsfnet_building.sdm",
        "description": "通用建筑物变化检测模型，适用于城市扩张、违章建筑监测等场景。",
        "offset": 128,
    },
    "building-seg": {
        "name": "建筑物分割 (SegFormer)",
        "filename": "binary_cls_building_segformer/binary_cls_building_segformer.sdm",
        "description": "基于 SegFormer 的建筑物二分类分割模型，可用于单时相建筑物提取。",
        "offset": 128,
    },
    "landcover": {
        "name": "地物分类 (多类别)",
        "filename": "multi_cls_landcover/multi_cls_landcover.sdm",
        "description": "多类别土地利用/土地覆盖分类模型。",
        "offset": 128,
    },
}


def _resolve_model_path(filename: str) -> str:
    """根据 config 中的 resources_ml 动态解析模型完整路径。"""
    cfg = load_config()
    resources_ml = cfg.get("resources_ml", "")
    if not resources_ml:
        return ""
    model_dir = os.path.join(resources_ml, "model")
    return os.path.join(model_dir, filename.replace("/", os.sep))


def list_models():
    """打印所有可用模型信息。"""
    print()
    print("=" * 72)
    print("  可用模型列表")
    print("=" * 72)
    for key, info in AVAILABLE_MODELS.items():
        full_path = _resolve_model_path(info["filename"])
        exists = "[OK]" if os.path.exists(full_path) else "[MISSING]"
        print()
        print(f"  [{key}]  {info['name']}")
        print(f"         路径: {full_path}")
        print(f"         状态: {exists}")
        print(f"         说明: {info['description']}")
    print()
    print("-" * 72)
    print("  使用方式: python change_detection.py run --model <模型名> ...")
    print("  例如:     python change_detection.py run --model building ...")
    print("-" * 72)
    print()


def get_model_info(model_key: str) -> dict:
    """根据 key 获取模型信息。"""
    if model_key not in AVAILABLE_MODELS:
        print(f"\n[错误] 未知模型: '{model_key}'")
        print(f"可用模型: {', '.join(AVAILABLE_MODELS.keys())}")
        print("运行 'python change_detection.py models' 查看详情。\n")
        sys.exit(1)

    info = AVAILABLE_MODELS[model_key].copy()
    info["path"] = _resolve_model_path(info.pop("filename"))

    if not os.path.exists(info["path"]):
        print(f"\n[错误] 模型文件不存在: {info['path']}")
        print("请检查 config.json 中 resources_ml 路径是否正确。")
        print("或运行 'python change_detection.py setup' 重新配置。\n")
        sys.exit(1)
    return info


# ============================================================================
# 3. 核心推理逻辑
# ============================================================================

def _check_supermap_import() -> bool:
    """检查是否能导入 iobjectspy。"""
    try:
        from iobjectspy import env  # noqa: F401
        return True
    except ImportError:
        print("\n[错误] 无法导入 iobjectspy，请确认：")
        print("  1. 使用的是 SuperMap 自带的 Python 环境")
        print("  2. config.json 中的路径配置正确")
        print("  3. 运行 'python change_detection.py setup' 重新配置\n")
        return False


def run_single_inference(
    before_path: str,
    after_path: str,
    out_path: str,
    model_key: str = "building",
    gpu: int = 0,
    batch_size: int = 1,
    offset: int = None,
    result_type: str = "grid",
    out_dataset_name: str = "predict_change",
    out_format: str = "udbx",
) -> bool:
    """执行单次变化检测推理。"""
    # 校验输入
    if not os.path.exists(before_path):
        print(f"\n[错误] 前期影像不存在: {before_path}")
        return False
    if not os.path.exists(after_path):
        print(f"\n[错误] 后期影像不存在: {after_path}")
        return False

    model_info = get_model_info(model_key)
    if offset is None:
        offset = model_info.get("offset", 128)

    # 确保输出目录存在
    out_dir = os.path.dirname(os.path.abspath(out_path))
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    if not _check_supermap_import():
        return False

    try:
        from iobjectspy.ml.vision import ImageryInference

        # 打印信息
        print()
        print("=" * 60)
        print("  变化检测推理")
        print("=" * 60)
        print(f"  模型:       {model_info['name']}")
        print(f"  前期影像:   {before_path}")
        print(f"  后期影像:   {after_path}")
        print(f"  输出路径:   {out_path}")
        print(f"  输出格式:   {out_format}")
        print(f"  设备:       {'GPU ' + str(gpu) if gpu >= 0 else 'CPU'}")
        print(f"  Batch Size: {batch_size}")
        print(f"  Offset:     {offset}")
        print("=" * 60)
        print()

        gpus = [gpu] if gpu >= 0 else []

        print("[1/3] 正在加载模型...")
        model = ImageryInference(
            model_path=model_info["path"],
            gpus=gpus,
            batch_size=batch_size,
        )
        print("      模型加载完成。")

        print("[2/3] 正在执行变化检测推理...")
        start_time = datetime.now()

        if out_format == "tif":
            tmp_udbx = out_path.replace(".tif", ".udbx").replace(".tiff", ".udbx")
            model.general_changedet_infer(
                input_data=before_path,
                input_compare_data=after_path,
                out_data=tmp_udbx,
                out_dataset_name=out_dataset_name,
                offset=offset,
                result_type=result_type,
            )
            print("      推理完成，正在转换为 GeoTIFF...")
            from iobjectspy import conversion, DatasourceConnectionInfo, Workspace
            _ws = Workspace()
            try:
                _conn = DatasourceConnectionInfo()
                _conn.set_server(tmp_udbx)
                _ds = _ws.open_datasource(_conn)
                _dt = _ds[out_dataset_name]
                conversion.export_to_tif(_dt, out_path)
            finally:
                _ws.close()
            try:
                os.remove(tmp_udbx)
            except Exception:
                pass
        else:
            model.general_changedet_infer(
                input_data=before_path,
                input_compare_data=after_path,
                out_data=out_path,
                out_dataset_name=out_dataset_name,
                offset=offset,
                result_type=result_type,
            )

        elapsed = (datetime.now() - start_time).total_seconds()
        print(f"      推理完成，耗时: {elapsed:.1f} 秒")

        print(f"[3/3] 结果已保存至: {out_path}")
        print()
        print("=" * 60)
        print("  [OK] 变化检测完成")
        print("=" * 60)
        print()
        return True

    except RuntimeError as e:
        print(f"\n[错误] 推理运行时错误: {e}")
        print("可能原因:")
        print("  - GPU 显存不足，尝试减小 batch_size 或使用 CPU (--gpu -1)")
        print("  - 影像格式不支持或损坏")
        print("  - 影像与模型要求的波段数不匹配")
        return False
    except Exception as e:
        print(f"\n[错误] {type(e).__name__}: {e}")
        return False


# ============================================================================
# 4. 批处理
# ============================================================================

def run_batch_inference(
    csv_path: str,
    model_key: str = "building",
    gpu: int = 0,
    batch_size: int = 1,
    offset: int = None,
    result_type: str = "grid",
    out_format: str = "udbx",
) -> bool:
    """从 CSV 文件读取任务列表，批量执行变化检测。"""
    import csv

    if not os.path.exists(csv_path):
        print(f"\n[错误] CSV 文件不存在: {csv_path}")
        return False

    tasks: List[Tuple[str, ...]] = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row or row[0].startswith("#"):
                continue
            row = [c.strip() for c in row]
            if len(row) < 3:
                print(f"[警告] 跳过不完整行: {row}")
                continue
            tasks.append(tuple(row))

    if not tasks:
        print("[警告] CSV 文件中没有有效任务。")
        return False

    print()
    print("=" * 60)
    print("  批处理模式")
    print("=" * 60)
    print(f"  任务数量:   {len(tasks)}")
    print(f"  模型:       {model_key}")
    print(f"  设备:       {'GPU ' + str(gpu) if gpu >= 0 else 'CPU'}")
    print("=" * 60)
    print()

    if offset is None:
        model_info = get_model_info(model_key)
        offset = model_info.get("offset", 128)

    success_count = 0
    for i, task in enumerate(tasks, 1):
        before, after, out = task[0], task[1], task[2]
        ds_name = task[3] if len(task) >= 4 else "predict_change"

        print(f"\n--- [{i}/{len(tasks)}] ---")
        ok = run_single_inference(
            before_path=before,
            after_path=after,
            out_path=out,
            model_key=model_key,
            gpu=gpu,
            batch_size=batch_size,
            offset=offset,
            result_type=result_type,
            out_dataset_name=ds_name,
            out_format=out_format,
        )
        if ok:
            success_count += 1

    print()
    print("=" * 60)
    print(f"  批处理完成: {success_count}/{len(tasks)} 成功")
    print("=" * 60)
    print()
    return success_count == len(tasks)


# ============================================================================
# 5. 环境自检
# ============================================================================

def run_self_check() -> bool:
    """运行环境自检。"""
    cfg = load_config()

    print()
    print("=" * 60)
    print("  环境自检")
    print("=" * 60)

    checks = []

    # 1. Python
    py = sys.executable
    print(f"\n  Python: {py}")
    print(f"  版本:    {sys.version.split()[0]}")

    # 2. JAVA_HOME
    jh = cfg.get("java_home", "")
    jh_ok = os.path.isdir(jh) if jh else False
    status = "[OK]" if jh_ok else "[FAIL]"
    print(f"  JAVA_HOME: {status} {jh if jh else '(未配置)'}")
    checks.append(("JAVA_HOME", jh_ok))

    # 3. iObjects Bin
    iob = cfg.get("iobjects_bin", "")
    bin_ok = os.path.isdir(iob) if iob else False
    status = "[OK]" if bin_ok else "[FAIL]"
    print(f"  iObjects Bin: {status} {iob if iob else '(未配置)'}")
    checks.append(("iObjects Bin", bin_ok))

    # 4. 模型资源
    ml = cfg.get("resources_ml", "")
    model_dir = os.path.join(ml, "model") if ml else ""
    ml_ok = os.path.isdir(model_dir) if model_dir else False
    status = "[OK]" if ml_ok else "[FAIL]"
    print(f"  模型目录: {status} {model_dir if model_dir else '(未配置)'}")
    checks.append(("模型资源", ml_ok))

    # 5. iobjectspy
    try:
        import iobjectspy
        print(f"  iobjectspy: [OK] 版本 {iobjectspy.__version__}")
        checks.append(("iobjectspy", True))
    except ImportError:
        print(f"  iobjectspy: [FAIL] 未安装（请使用 SuperMap Python 运行此脚本）")
        checks.append(("iobjectspy", False))

    # 6. CUDA
    try:
        import torch
        try:
            cuda_ok = torch.cuda.is_available()
            gpu_count = torch.cuda.device_count() if cuda_ok else 0
            status = f"[OK] ({gpu_count} 个GPU)" if cuda_ok else "[FAIL] (仅 CPU)"
        except Exception:
            cuda_ok = False
            status = "- (CUDA 不可用)"
        print(f"  CUDA:      {status}")
        checks.append(("CUDA", cuda_ok))
    except ImportError:
        print(f"  CUDA:      - (未安装 PyTorch)")
        checks.append(("CUDA", False))

    # 7. 模型文件
    print(f"\n  模型文件检查:")
    for key, info in AVAILABLE_MODELS.items():
        full_path = _resolve_model_path(info["filename"])
        exists = os.path.exists(full_path)
        status = "[OK]" if exists else "[FAIL]"
        print(f"    [{key}] {status} {info['name']}")
        checks.append((f"模型-{key}", exists))

    # 汇总
    all_ok = all(ok for _, ok in checks)
    passed = sum(1 for _, ok in checks if ok)
    total = len(checks)
    print(f"\n  ---")
    print(f"  总计: {passed}/{total} 通过")
    if all_ok:
        print(f"  结论: [OK] 环境就绪，可以运行变化检测。")
    else:
        failed = [name for name, ok in checks if not ok]
        print(f"  结论: [FAIL] 以下项目未通过 — {', '.join(failed)}")
        print(f"  提示: 运行 'python change_detection.py setup' 重新配置。")
    print("=" * 60)
    print()
    return all_ok


# ============================================================================
# 6. 配置向导
# ============================================================================

def run_setup_wizard():
    """首次使用配置向导，引导用户设置 config.json。"""
    cfg = load_config()

    print()
    print("=" * 60)
    print("  首次使用 — 配置向导")
    print("=" * 60)
    print()
    print("  请依次输入 SuperMap 相关路径。")
    print("  直接回车保留当前值（如果有的话）。")
    print("  路径示例: F:/supermap/supermap-iobjectsjava-2026-win-all/jre1.8_x64")
    print()

    fields = [
        ("java_home", "SuperMap iObjects Java JRE 路径",
         "F:/supermap/supermap-iobjectsjava-2026-win-all/jre1.8_x64"),
        ("iobjects_bin", "SuperMap iObjects Java Bin 路径",
         "F:/supermap/supermap-iobjectsjava-2026-win-all/Bin"),
        ("resources_ml", "SuperMap ML 资源包路径 (内含 model 文件夹)",
         "F:/supermap/supermap-iobjectspy-resources_ml-2025u1/resources_ml"),
        ("python_path", "SuperMap Python 解释器路径",
         "F:/supermap/supermap-iobjectspy-env-gpu-2026-win64/conda/python.exe"),
    ]

    for key, description, example in fields:
        current = cfg.get(key, "")
        if current:
            prompt = f"  {description}\n  当前值: {current}\n  新值 (回车不变): "
        else:
            prompt = f"  {description}\n  例如: {example}\n  输入: "

        try:
            value = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  配置已取消。")
            return

        if value:
            cfg[key] = value

    print()
    print("-" * 60)

    # 检查路径是否存在
    all_ok = True
    for key in ["java_home", "iobjects_bin", "resources_ml", "python_path"]:
        v = cfg.get(key, "")
        exists = os.path.exists(v) if v else False
        status = "[OK]" if exists else "[MISSING]"
        if not exists:
            all_ok = False
        print(f"  {status} {key}: {v}")

    print("-" * 60)

    if all_ok:
        print("  所有路径验证通过！")
    else:
        print("  部分路径不存在（标记 [MISSING]），")
        print("  请确认安装路径后重新运行 setup。")

    save = input("\n  保存配置? (Y/n): ").strip().lower()
    if save != "n":
        if save_config(cfg):
            print("  配置已保存到 config.json")
            print()
            print("  接下来可以运行:")
            print("    python change_detection.py check    # 环境自检")
            print("    python change_detection.py models   # 查看模型")
            print("    python change_detection.py menu     # 交互菜单")
        else:
            print("  保存失败！")
    else:
        print("  未保存。")

    print()


# ============================================================================
# 7. 交互菜单
# ============================================================================

def interactive_menu():
    """交互式菜单，双击 bat 时进入。"""

    while True:
        print()
        print("  ╔══════════════════════════════════════════════════════╗")
        print("  ║       通用变化检测工具 — SuperMap iObjects            ║")
        print("  ║       第24届 SuperMap 杯高校 GIS 大赛                 ║")
        print("  ╚══════════════════════════════════════════════════════╝")
        print()
        print("    [1] 环境自检        检查 Python / Java / CUDA / 模型")
        print("    [2] 查看模型列表    列出所有可用的变化检测模型")
        print("    [3] 运行变化检测    输入前后期影像，执行推理")
        print("    [4] 批量处理        从 CSV 文件批量运行")
        print("    [5] 查看帮助        显示完整命令行用法")
        print("    [6] 配置向导        修改 config.json 路径")
        print("    [7] 图形界面        启动桌面 UI（推荐）")
        print("    [0] 退出")
        print()
        print("  " + "-" * 56)

        try:
            choice = input("  请输入数字 (0-7): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  已退出。")
            break

        if choice == "0":
            print("  已退出。")
            break
        elif choice == "1":
            print()
            try:
                run_self_check()
            except Exception as e:
                print(f"\n  [错误] 自检过程出现异常: {e}")
                print("  请检查 SuperMap 环境是否正确安装。")
        elif choice == "2":
            print()
            list_models()
        elif choice == "3":
            _menu_run_single()
        elif choice == "4":
            _menu_run_batch()
        elif choice == "5":
            _menu_show_help()
        elif choice == "6":
            run_setup_wizard()
        elif choice == "7":
            print("\n  正在启动图形界面...")
            from change_detection_ui import main as ui_main
            ui_main()
        else:
            print("  无效选择，请重新输入。")

        try:
            input("\n  按回车键返回菜单...")
        except (EOFError, KeyboardInterrupt):
            print("\n  已退出。")
            break


def _menu_show_help():
    """打印帮助信息。"""
    print()
    parser = build_parser()
    parser.print_help()
    print()
    print("  各子命令详细帮助:")
    print("    run    -  python change_detection.py run --help")
    print("    batch  -  python change_detection.py batch --help")
    print("    models -  python change_detection.py models")
    print("    check  -  python change_detection.py check")
    print("    setup  -  python change_detection.py setup")
    print("    menu   -  python change_detection.py menu")
    print()


def _menu_run_single():
    """交互式引导：单次变化检测（自动记忆上次参数）。"""
    cfg = load_config()
    last = cfg.get("last_params", DEFAULT_CONFIG["last_params"])

    def _hint(key: str, fallback: str) -> str:
        """生成提示文字，上次用过的值会显示在方括号中。"""
        val = last.get(key, fallback)
        if val:
            return f" [{val}]"
        return ""

    print()
    print("  " + "-" * 56)
    print("  运行变化检测 — 请输入以下参数")
    print("  （直接回车使用方括号中的默认值）")
    print("  " + "-" * 56)
    print()

    before = input(f"  前期影像路径 (T1){_hint('before', '')}: ").strip()
    if not before:
        before = last.get("before", "")
    if not before:
        print("  [错误] 前期影像路径不能为空！")
        return

    after = input(f"  后期影像路径 (T2){_hint('after', '')}: ").strip()
    if not after:
        after = last.get("after", "")
    if not after:
        print("  [错误] 后期影像路径不能为空！")
        return

    default_out = last.get("out", "result.udbx")
    out = input(f"  输出文件路径{_hint('out', 'result.udbx')}: ").strip()
    if not out:
        out = default_out

    default_model = last.get("model", "building")
    model = input(f"  模型 (building/building-seg/landcover){_hint('model', 'building')}: ").strip()
    if not model:
        model = default_model

    default_gpu = str(last.get("gpu", 0))
    gpu_str = input(f"  GPU 编号 (0/1/...，-1=CPU){_hint('gpu', '0')}: ").strip()
    try:
        gpu = int(gpu_str) if gpu_str else int(default_gpu)
    except ValueError:
        gpu = 0

    default_fmt = last.get("out_format", "udbx")
    out_format = input(f"  输出格式 (udbx/tif){_hint('out_format', 'udbx')}: ").strip()
    if not out_format:
        out_format = default_fmt

    print()
    print("  " + "-" * 56)
    print(f"    前期影像:   {before}")
    print(f"    后期影像:   {after}")
    print(f"    输出路径:   {out}")
    print(f"    模型:       {model}")
    print(f"    GPU:        {gpu}")
    print(f"    输出格式:   {out_format}")
    print("  " + "-" * 56)

    confirm = input("  确认执行? (Y/n): ").strip().lower()
    if confirm == "n":
        print("  已取消。")
        return

    print()
    print("  正在运行，请稍候...")
    print()

    ok = run_single_inference(
        before_path=before,
        after_path=after,
        out_path=out,
        model_key=model,
        gpu=gpu,
        batch_size=1,
        offset=None,
        result_type="grid",
        out_dataset_name="predict_change",
        out_format=out_format,
    )

    # 成功后自动记住参数
    if ok:
        _remember_last_params(before, after, out, model, gpu, out_format)
        print("  [记忆] 本次参数已保存，下次可直接回车使用。")


def _menu_run_batch():
    """交互式引导：批量变化检测（自动记忆上次参数）。"""
    cfg = load_config()
    last = cfg.get("last_params", DEFAULT_CONFIG["last_params"])
    # 批处理也用单次记忆的 model/gpu
    default_model = last.get("model", "building")
    default_gpu = str(last.get("gpu", 0))

    def _hint(val: str) -> str:
        return f" [{val}]" if val else ""

    print()
    print("  " + "-" * 56)
    print("  批量处理 — 请输入 CSV 文件路径")
    print("  " + "-" * 56)
    print()
    print("  CSV 格式（无表头）：")
    print("    前期影像路径,后期影像路径,输出路径")
    print()
    print("  示例：")
    print("    D:/data/t1_2020.tif,D:/data/t1_2024.tif,D:/result/t1.udbx")
    print("    D:/data/t2_2020.tif,D:/data/t2_2024.tif,D:/result/t2.udbx")
    print()

    csv = input("  CSV 文件路径: ").strip()
    if not csv:
        print("  [错误] CSV 路径不能为空！")
        return

    model = input(f"  模型 (building/building-seg/landcover){_hint(default_model)}: ").strip()
    if not model:
        model = default_model

    gpu_str = input(f"  GPU 编号{_hint(default_gpu)}: ").strip()
    try:
        gpu = int(gpu_str) if gpu_str else int(default_gpu)
    except ValueError:
        gpu = 0

    confirm = input("  确认执行? (Y/n): ").strip().lower()
    if confirm == "n":
        print("  已取消。")
        return

    print()
    print("  正在批量处理...")
    print()

    ok = run_batch_inference(
        csv_path=csv,
        model_key=model,
        gpu=gpu,
        batch_size=1,
        offset=None,
        result_type="grid",
        out_format="udbx",
    )


# ============================================================================
# 8. 命令行参数定义
# ============================================================================

def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。"""
    parser = argparse.ArgumentParser(
        prog="change_detection.py",
        description="通用变化检测工具 — 基于 SuperMap iObjects Python",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            示例:
              python change_detection.py setup         # 首次配置
              python change_detection.py check         # 环境自检
              python change_detection.py models        # 查看模型
              python change_detection.py menu          # 交互菜单
              python change_detection.py run --before 2020.tif --after 2024.tif --out result.udbx
              python change_detection.py batch --csv tasks.csv
        """),
    )

    sub = parser.add_subparsers(dest="command", title="子命令")

    # ---- run ----
    p_run = sub.add_parser("run", help="单次变化检测推理")
    p_run.add_argument("--before", "-b", type=str, required=True,
                       help="前期影像路径 (T1)")
    p_run.add_argument("--after", "-a", type=str, required=True,
                       help="后期影像路径 (T2)")
    p_run.add_argument("--out", "-o", type=str, required=True,
                       help="输出文件路径")
    p_run.add_argument("--model", "-m", type=str, default="building",
                       choices=list(AVAILABLE_MODELS.keys()),
                       help="模型选择 (默认: building)")
    p_run.add_argument("--gpu", "-g", type=int, default=0,
                       help="GPU 编号, -1 表示 CPU (默认: 0)")
    p_run.add_argument("--batch-size", type=int, default=1,
                       help="推理批大小 (默认: 1)")
    p_run.add_argument("--offset", type=int, default=None,
                       help="滑动窗口偏移量")
    p_run.add_argument("--result-type", type=str, default="grid",
                       choices=["grid", "region"],
                       help="结果类型 (默认: grid)")
    p_run.add_argument("--out-dataset-name", type=str, default="predict_change",
                       help="输出数据集名称 (默认: predict_change)")
    p_run.add_argument("--out-format", "-f", type=str, default="udbx",
                       choices=["udbx", "tif"],
                       help="输出格式 (默认: udbx)")

    # ---- batch ----
    p_batch = sub.add_parser("batch", help="批量变化检测推理")
    p_batch.add_argument("--csv", "-c", type=str, required=True,
                         help="CSV 任务文件路径")
    p_batch.add_argument("--model", "-m", type=str, default="building",
                         choices=list(AVAILABLE_MODELS.keys()),
                         help="模型选择 (默认: building)")
    p_batch.add_argument("--gpu", "-g", type=int, default=0,
                         help="GPU 编号")
    p_batch.add_argument("--batch-size", type=int, default=1,
                         help="推理批大小")
    p_batch.add_argument("--offset", type=int, default=None,
                         help="滑动窗口偏移量")
    p_batch.add_argument("--result-type", type=str, default="grid",
                         choices=["grid", "region"],
                         help="结果类型")
    p_batch.add_argument("--out-format", "-f", type=str, default="udbx",
                         choices=["udbx", "tif"],
                         help="输出格式")

    # ---- models / check / setup / menu / ui ----
    sub.add_parser("models", help="列出所有可用模型")
    sub.add_parser("check", help="运行环境自检")
    sub.add_parser("setup", help="首次使用配置向导")
    sub.add_parser("menu", help="交互式菜单模式")
    sub.add_parser("ui", help="启动图形界面")

    return parser


# ============================================================================
# 9. 主入口
# ============================================================================

def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "models":
        list_models()
    elif args.command == "check":
        ok = run_self_check()
        # 交互式终端：给用户时间查看结果，不直接闪退
        if sys.stdin.isatty():
            print()
            try:
                input("  按回车键退出...")
            except (EOFError, KeyboardInterrupt):
                pass
        sys.exit(0 if ok else 1)
    elif args.command == "ui":
        from change_detection_ui import main as ui_main
        ui_main()
    elif args.command == "setup":
        run_setup_wizard()
    elif args.command == "menu":
        interactive_menu()
    elif args.command == "run":
        offset = args.offset
        if offset is None:
            model_info = get_model_info(args.model)
            offset = model_info.get("offset", 128)

        ok = run_single_inference(
            before_path=args.before,
            after_path=args.after,
            out_path=args.out,
            model_key=args.model,
            gpu=args.gpu,
            batch_size=args.batch_size,
            offset=offset,
            result_type=args.result_type,
            out_dataset_name=args.out_dataset_name,
            out_format=args.out_format,
        )
        # 成功后自动记住参数
        if ok:
            _remember_last_params(args.before, args.after, args.out,
                                 args.model, args.gpu, args.out_format)
        sys.exit(0 if ok else 1)
    elif args.command == "batch":
        ok = run_batch_inference(
            csv_path=args.csv,
            model_key=args.model,
            gpu=args.gpu,
            batch_size=args.batch_size,
            offset=args.offset,
            result_type=args.result_type,
            out_format=args.out_format,
        )
        sys.exit(0 if ok else 1)
    else:
        parser.print_help()
        sys.exit(0)


if __name__ == "__main__":
    main()
