# Talo - 塔罗牌占卜系统

一个基于 Python 3.13 的塔罗牌占卜应用，提供 GUI 与 CLI 两种使用方式，支持 CSPRNG/物理随机双引擎、8 维向量评分与牌间交互解读。

## 功能特性

- 双随机引擎：`csprng`（默认）与 `physical`
- 8 维向量评分：`emotion`、`material`、`conflict`、`change`、`spirit`、`will`、`intellect`、`time_pressure`
- 牌间交互：支持 `interactions.json` 关联矩阵 + fallback 规则
- 解读渲染：支持牌阵整体解读、特殊牌对文本、占星视角
- 历史记录：JSONL 持久化
- 导出：Markdown / 纯文本
- 视觉风格：customtkinter 包豪斯极简风格（零圆角）

## 项目结构

```text
Talo/
├── tarot.spec
├── data/
│   └── cards_en.json
└── tarot_system/
    ├── gui.py
    ├── main.py
    ├── paths.py
    ├── engine/
    │   ├── deck.py
    │   ├── entropy.py
    │   └── history.py
    ├── core/
    │   ├── calculator.py
    │   ├── interpreter.py
    │   └── exporter.py
    ├── tests/
    │   └── test_core.py
    ├── data/
    │   ├── cards.json
    │   ├── spreads.json
    │   ├── interactions.json
    │   └── special_pairs.json
    └── assets/
        └── cards/0.png ~ 77.png
```

## 环境要求

- Python 3.13
- macOS（开发环境）/ Windows（打包支持）
- GUI 依赖：`customtkinter==5.2.2`、Pillow
- 可选依赖：
  - `pyaudio==0.2.14`（麦克风熵增强）
  - `pyttsx3`（Windows 语音；macOS 可使用系统 `say`）

> 测试框架仅使用标准库 `unittest`，项目未安装 `pytest`。

## 快速开始

### 1) 进入项目

```bash
cd /Users/helel/PycharmProjects/Talo
```

### 2) 运行 GUI

```bash
python tarot_system/gui.py
```

### 3) 运行 CLI

```bash
python tarot_system/main.py
python tarot_system/main.py --rng physical
```

## 运行测试

```bash
python -m unittest tarot_system.tests.test_core
python -m unittest tarot_system.tests.test_core -v
```

## 数据与路径策略

项目统一通过 `tarot_system/paths.py` 管理路径：

- 只读资源：`resource_path("data/cards.json")`、`resource_path("assets/cards/0.png")`
- 可写数据：`user_data_dir()`（历史记录等）

该策略用于兼容开发环境与 PyInstaller 打包环境，避免 macOS `.app` 内只读路径写入失败。

## 打包发布

### 本地打包（macOS）

```bash
pyinstaller tarot.spec --clean
```

输出示例：`dist/塔罗牌占卜.app`

### CI/CD（GitHub Actions）

当推送 `v*` tag 时，工作流会自动：

1. 构建 macOS 产物（`.app`）
2. 构建 Windows 产物（文件夹）
3. 创建 Release 并上传压缩产物

示例：

```bash
git tag v1.0.1
git push origin v1.0.1
```

## 说明

- 当前核心模块与测试已完整，`tarot_system/tests/test_core.py` 覆盖主要功能路径。
- GUI 设计为统一风格（零圆角、1px 边框、简洁交互），如需调整样式，建议统一在 `tarot_system/gui.py` 的常量配置中修改。
- 历史记录文件 `history.jsonl` 属运行时数据，建议不纳入版本控制。

