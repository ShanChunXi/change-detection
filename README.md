# 通用变化检测工具

**第24届 SuperMap 杯高校 GIS 大赛 — 开发组**

基于 SuperMap iObjects Python 的遥感影像变化检测推理工具。支持 3 种深度学习模型，提供**图形界面**、交互菜单、命令行三种使用方式。

---

## 快速开始

### 1. 安装 SuperMap 环境

| 组件 | 说明 |
|------|------|
| SuperMap iObjects Python (GPU) | 含 `iobjectspy` 的 Python 环境 |
| SuperMap iObjects Java | JRE + Bin 目录 |
| ML 资源包 | 含预训练模型文件 |

### 2. 启动

双击 `run.bat`，首次使用会自动弹出环境配置窗口。也可以直接运行：

```bash
python change_detection.py ui       # 图形界面
python change_detection.py menu     # 交互菜单
python change_detection.py setup    # 命令行配置
python change_detection.py check    # 环境自检
```

配置保存到 `config.json`，换电脑只需重新配置一次。

---

## 图形界面（推荐）

双击 `run.bat` → 按 `7`，或 `python change_detection.py ui`。

```
┌─────────────────────────────────────────────────────────┐
│  🛰 变化检测工具                      ⚙ 环境配置  就绪  │
├───────────────┬─────────────────────────────────────────┤
│ 🔧 环境状态   │  📟 运行日志                             │
│  ● 环境就绪   │  ═══════════════════════════════════════ │
│               │  正在运行环境自检...                     │
│ 📋 检测参数   │  [OK] Python: ...                       │
│ [单次] [批量] │  [OK] JAVA_HOME: ...                    │
│               │  [OK] iObjects Bin: ...                 │
│ 模型 ▼        │  [OK] 模型文件: ...                     │
│ 前期影像 [浏览]│                                         │
│ 后期影像 [浏览]│                                         │
│ 输出路径 [浏览]│                                         │
│ GPU ▼  格式 ▼ │                                         │
│ [ 开始检测 ]  │                                         │
└───────────────┴─────────────────────────────────────────┘
```

### 主要功能

| 功能 | 说明 |
|------|------|
| 环境配置弹窗 | 4 个路径输入框 + 浏览按钮 + 实时校验 + 一键自动检测 |
| 路径失效提醒 | 启动时自动检测，路径不存在会弹窗提示重配 |
| 单次检测 | 选前后期影像 → 点开始 → 实时日志 → 完成提示 |
| 批量处理 | 切到批量模式 → 选 CSV → 点批量处理 |
| 参数记忆 | 每次成功运行后自动保存，下次打开自动回填 |
| 路径示例 | 每个配置项下方显示标准安装路径示例 |

---

## 可用模型

| 模型 | 用途 |
|------|------|
| `building` | 建筑物变化检测 — 前后影像对比，提取变化区域 |
| `building-seg` | 建筑物分割 — 单张影像提取所有建筑物 |
| `landcover` | 地物分类 — 多类别土地利用/覆盖分类 |

---

## 命令行用法

```bash
# 单次推理
python change_detection.py run \
    --before "D:/data/2020.tif" \
    --after  "D:/data/2024.tif" \
    --out    "D:/result/change.udbx" \
    --model  building --gpu 0

# 输出 GeoTIFF
python change_detection.py run \
    -b "2020.tif" -a "2024.tif" -o "change.tif" --out-format tif

# 批量处理（CSV 每行：前期影像,后期影像,输出路径）
python change_detection.py batch --csv tasks.csv

# 交互菜单
python change_detection.py menu
```

---

## 命令速查

| 命令 | 作用 |
|------|------|
| `ui` | 启动图形界面 |
| `menu` | 交互式菜单 |
| `run` | 单次变化检测推理 |
| `batch` | 从 CSV 批量推理 |
| `models` | 列出可用模型 |
| `check` | 环境自检 |
| `setup` | 配置向导 |

---

## 文件说明

| 文件 | 说明 |
|------|------|
| `change_detection.py` | 主程序，命令行 + 菜单入口 |
| `change_detection_ui.py` | 桌面 GUI（Tkinter，零依赖） |
| `config.json` | 环境路径 + 上次运行参数 |
| `run.bat` | Windows 启动器 |
| `README.md` | 本文件 |

---

## 常见问题

**Q: 双击 run.bat 闪退？**
命令行运行 `python change_detection.py menu` 查看错误信息。

**Q: 报"无法导入 iobjectspy"？**
请使用 SuperMap 自带的 Python 环境。点击 UI 顶部「⚙ 环境配置」重新设置路径。

**Q: 模型检测显示 [FAIL]？**
检查 ML 资源包路径是否正确，路径下是否有 `model/` 文件夹。

**Q: 显存不足？**
GPU 选 `-1 (CPU)` 改用 CPU 推理。

**Q: 想换模型？**
下拉框选择 `building-seg` 或 `landcover`。
