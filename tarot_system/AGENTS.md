# AGENTS.md — Talo 塔罗牌占卜系统

## 1. 项目概况

- **名称**: Talo 塔罗牌占卜系统
- **路径**: `~/PycharmProjects/Talo/tarot_system/`
- **Python**: 3.13
- **平台**: macOS (开发), 跨平台支持
- **GUI 框架**: `customtkinter` 5.2.2（包豪斯极简风格，零圆角）
- **图像**: 78 张 Rider-Waite PNG（`assets/cards/0.png` ~ `77.png`）
- **测试框架**: 仅标准库 `unittest`（**pytest 未安装**）
- **核心特征**:
  - CSPRNG / 物理 RNG 双引擎
  - 8 维向量加权评分（emotion, material, conflict, change, spirit, will, intellect, time_pressure）
  - 牌间交互计算（JSON 关联矩阵 + fallback 规则）
  - 历史记录 JSONL 持久化
  - 无 emoji，使用几何符号（△▽◇□ ●○）

## 2. 文件结构

```
tarot_system/
├── gui.py                      # ~1378行，customtkinter GUI
├── main.py                     # ~270行，CLI 入口
├── AGENTS.md                   # 本文件（项目规范文档）
├── download_tarot_meanings.py  # 一次性脚本：下载英文牌义
├── scripts/
│   └── merge_cards_data.py     # 合并/扩展 cards.json 字段
├── engine/
│   ├── deck.py                 # 188行，牌组、洗牌、抽牌
│   ├── entropy.py              # 186行，熵池、SecureRNG、PhysicalRNG
│   └── history.py              # 111行，JSONL 历史记录
├── core/
│   ├── calculator.py           # 168行，8维评分计算器
│   ├── interpreter.py          # 274行，解读文本渲染引擎
│   └── exporter.py             # 78行，Markdown/纯文本导出
├── tests/
│   └── test_core.py            # 680行，34项 unittest
├── data/
│   ├── cards.json              # 78张牌（含向量、元素、占星）
│   ├── spreads.json            # 牌阵配置
│   ├── interactions.json       # 特殊牌对关联权重
│   ├── special_pairs.json      # 条件触发特殊文本
│   └── history.jsonl           # 历史记录（自动创建）
└── assets/
    └── cards/
        ├── 0.png ~ 77.png      # 78张 Rider-Waite 图像
```

## 3. 核心模块详解

### 3.1 engine/deck.py

```python
@dataclass(frozen=True)
class TarotCard:
    uid: int
    name: str
    suit: str
    upright_vec: Tuple[float, ...]
    reversed_vec: Tuple[float, ...]

class Deck:
    def __init__(self, cards_path=None, rng=None, rng_type="csprng"):
        ...
        self.shuffle_count = 0       # ← 普通 int 实例属性，非 property
        self.orientations: Dict[int, bool] = {}  # uid -> reversed
        ...
```

**关键设计**:
- `shuffle_count`: **普通 `int` 实例属性**，`_shuffle_step()` 中自增，`reset()` 清零。曾经错误改成 property 导致测试回归失败，已修复。
- `shuffle(times=None)`: 进入持续洗牌模式（后台线程）
- `draw()`: 未洗牌时自动 `shuffle(times=shuffle_times)`，从 `orientations` 读取逆位
- `_shuffle_step()`: Fisher-Yates 单步交换 + 手滑翻转(`hand_slip_prob`) + 双翻(`double_flip_prob`)

### 3.2 engine/entropy.py

```python
class EntropyPool:
    def __init__(self, question: str, deterministic: bool = False)
    def add_timing(self, ns: int)
    def collect(self, use_physical=False, ...) -> bytes  # 32字节种子

class SecureRNG:
    # 基于 64 位 LCG，与 Python random 模块完全隔离
    def shuffle(self, lst)
    def randbelow(self, n)
    def randbool(self, p=0.125)

class PhysicalRNG:
    # 硬件熵：os.getrandom(GRND_RANDOM) → os.urandom 回退
    def randbelow(self, n)
    def randbool(self, p=0.5)  # 使用字节阈值

def try_microphone_entropy(duration_ms=50) -> bytes | None
# 依赖 pyaudio 0.2.14，未安装时返回 None
```

### 3.3 core/calculator.py

```python
DIMENSIONS = [
    "emotion", "material", "conflict", "change",
    "spirit", "will", "intellect", "time_pressure",
]

@dataclass
class SlotResult:
    card: TarotCard
    reversed: bool
    position_name: str
    score: float
    top_dimensions: List[str]
    interaction_scores: Dict[int, float] = field(default_factory=dict)

class SpreadCalculator:
    def __init__(self, spread_config, association_matrix=None)

    @staticmethod
    def _fallback_assoc(uid_a, uid_b) -> float:
        # 双大阿卡纳相邻(0.30)/对宫(0.20)
        # 大小阿卡纳元素对应(0.18)
        # 双小阿卡纳同 suit(0.15)、同角色(0.12)、同数字(0.08)、相邻数字(0.04)

    def compute(self, draws) -> List[SlotResult]:
        # final_score = base_score + 0.3 * inter_sum
        # top_dimensions: 按 |vec[i]| 取前3
```

### 3.4 core/interpreter.py

```python
class TemplateEngine:
    def render(self, result: SlotResult) -> str      # 单张牌解读
    def render_spread(self, results) -> str          # 整个牌阵 + 特殊牌对
    def render_astrology(self, spread_name, results) -> str  # 占星视角
```

- **无 emoji**: 元素符号用 `△▽◇□`，正逆位用 `●○`
- 占星符号映射为中文：`♐→射手`，`☿→水星` 等
- 特殊牌对条件：`any` / `both_upright` / `mixed`
- `render()` 中过滤 `abs(score) < 0.001` 的零值交互

### 3.5 core/exporter.py

零外部依赖。`export_markdown()` / `export_plaintext()`。

### 3.6 engine/history.py

```python
@dataclass
class DrawRecord:
    uid, name, reversed, position, final_score, top_dimensions

@dataclass
class ReadingRecord:
    timestamp, question, spread_name, draw_results, interpretation_text

class HistoryLogger:
    def log(...)
    def list_history(self, limit=10)
    def delete_at(self, index_from_end)  # 0=最后一条
    def get_statistics(self) -> Dict[str, int]  # 感情/事业/财富/学业/灵性/其他
```

### 3.7 gui.py（~1378行）

**包豪斯设计规范（绝对不可违背）**:

```python
COLORS = {
    "bg": "#0D0D0D",
    "surface": "#161616",
    "surface_hover": "#1E1E1E",
    "border": "#3A3A3A",
    "text_primary": "#F0F0F0",
    "text_secondary": "#888888",
    "text_dim": "#555555",
    "accent": "#E8C547",
    "inverse": "#5B8DB8",
    "fire": "#C75B39", "water": "#4A7C8C",
    "air": "#8A8A8A", "earth": "#7A6A4E",
}
```

- **`corner_radius=0`** 所有组件
- **1px 边框**: `border_color=COLORS["border"], border_width=1`
- **按钮 hover**: 仅背景 `surface`→`surface_hover`，**文字保持白色不变**
- **不使用 bold**，强调靠尺寸/颜色
- **弹窗工厂**: `_make_dialog(title, w, h, grab)`，无系统标题栏，可拖动
- **`_configure_textbox_tags()`**: 封装 `textbox._textbox` 访问（`# noqa: SLF001`）
- **凯尔特十字**: `CTkScrollableFrame`，牌尺寸 110×180，② 挑战牌横置（rotate=90，2px 金色边框）
- **底部按钮区**: 保存/复制/导出/朗读，高度固定 220px
- **类型安全**: `settings.get()` 返回值显式 `int()`/`float()` 转换后再赋值

### 3.8 main.py（~270行）

CLI 入口，与 GUI 功能等价：
- 交互式菜单（单张/三张/凯尔特十字/历史/统计/退出）
- 按回车收集随机熵
- `_interactive_shuffle(deck)`: 直接访问 `deck._shuffle_step()`（`# noqa: SLF001`）
- `--rng csprng|physical` 参数
- `_prepare_reading()`: 提取了 `run_single` 和 `run_spread` 的公共熵收集/洗牌/RNG 设置逻辑

## 4. 测试（34项，全部通过）

```bash
cd ~/PycharmProjects/Talo/tarot_system
python -m unittest tests.test_core
```

**测试覆盖**:
- `TestEntropyAndShuffle`: 确定性洗牌复现、均匀性、randbool 分布
- `TestCalculator`: 单张牌得分、逆位得分、牌间交互
- `TestDeck`: 不放回抽取、抽完报错、reset、自定义参数
- `TestFullDeck`: 78张完整性、interactions 加载、suit 元素基线、Celtic Cross
- `TestBugFixesAndFeatures`: fallback 交互非零、shuffle 单次触发、逆位模板、特殊牌对、历史记录、导出格式、GUI 设置、合并脚本、占星字段、元素分布、GUI 占星标签、GUI 导入
- `TestPhysicalRNGAndShuffle`: PhysicalRNG 跨平台、物理洗牌熵消耗、持续洗牌模式、orientation 读取、无固定 reverse_prob、平台语音按钮、pathlib 使用

**测试子类 `CountingDeck`**:
```python
class CountingDeck(Deck):
    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._test_count = 0          # ← 独立计数器，与 Deck.shuffle_count 隔离

    def shuffle(self, times: int = 3) -> None:
        super().shuffle(times=times)
        self._test_count += 1
```

## 5. 已解决的关键问题

| 问题 | 解决方案 |
|------|----------|
| `shuffle_count` property 回归 | 移除 getter/setter，恢复为普通实例属性 |
| IDE 类型警告 (`settings.get()` 返回 `Any`) | 显式 `int()`/`float()` 转换后再赋值 |
| `_textbox` protected 访问警告 | 抽取为 `_configure_textbox_tags()` 方法，内部保留 `# noqa: SLF001` |
| `CTkButton \| None` 成员访问 | `speak_btn.configure()` 前增加 `assert self.speak_btn is not None` |
| `pyttsx3` 导入警告 | 添加 `# noqa: F401`（在 `try/except ImportError` 中） |
| `CountingDeck.__init__` 参数注解 | 添加 `*args: Any, **kwargs: Any` |
| 按钮反色 hover 导致文字消失 | 删除 `_bind_hover_invert`，改为仅背景色变化 |
| gui.py `Any` 未使用导入 | 保留用于 `selected_record: list[dict[str, Any] \| None]` 类型注解 |
| gui.py `selected_record` 类型推断 | 显式标注 `list[dict[str, Any] \| None]` |
| gui.py lambda 默认参数警告 | 改用 `functools.partial` 传递循环变量 |
| main.py `hashlib` 未使用 | 移除导入 |
| main.py `_shuffle_count` 未解析 | 改为公共属性 `shuffle_count`（2处） |
| main.py `_shuffle_step` protected 访问 | 添加 `# noqa: SLF001`（CLI 需要直接控制） |
| main.py `run_single`/`run_spread` 重复 | 提取 `_prepare_reading()` 公共函数 |
| main.py `spread_name` 未使用初始值 | 移除 `spread_name = ""` 初始化 |

## 6. 已知问题 / 限制

1. **"默认实参值可变"警告（gui.py 其他地方）**: 全面 AST 扫描后未发现任何函数使用 `[]`/`{}` 可变默认参数，判定为 PyCharm 误报
2. **"形参 'args' 未填"警告（gui.py `after` 回调）**: PyCharm 对 tkinter `after` 类型存根的不完善推断，实际代码正确，属误报
3. **拼写检查误报**: "Segoe"、"csprng"、"CSPRNG" 为合法专有名词（字体名、密码学术语），建议加入 PyCharm 项目字典
4. **`pyttsx3` 未安装**: macOS 开发环境使用 `say` 命令，Windows 依赖 `pyttsx3`
5. **macOS GUI 自动化限制**: 不依赖 `pyautogui`/`osascript`，依赖用户手动验证

## 7. 编码规范

- 全部函数使用类型注解
- `settings.get()` 返回值需显式转换后再赋值给 typed 属性
- `*args, **kwargs` 需标注 `Any` 类型
- 可选依赖使用 `try/except ImportError` + `# noqa: F401`
- 全部使用 `pathlib.Path`，禁止硬编码路径分隔符
- JSON 加载后增加 `None` 保护
- **禁止** `[]`/`{}`/`list()`/`dict()` 作为函数默认参数，使用 `None` + 内部初始化
- 循环中创建闭包时，优先使用 `functools.partial` 而非 lambda 默认参数

## 8. 数据文件规范

### cards.json
- `uid`: 0-21 大阿卡纳，22-77 小阿卡纳
- `name`: 中文牌名
- `suit`: `major_arcana` / `wands` / `cups` / `swords` / `pentacles`
- `upright_vec` / `reversed_vec`: 8 维 float 列表
- `element`: fire/water/air/earth
- `astrology`: `中文名|英文名|符号` 格式，如 `"射手座|Sagittarius|♐"`
- `kabbalah_path`: int（大阿卡纳）
- `meanings_upright` / `meanings_reversed`: 英文关键词列表

### spreads.json
键: `single`, `three_card`, `celtic_cross`
值: `{ "positions": [ { "name": "...", "weights": [8 floats] } ] }`

### interactions.json
键: `"uid_a,uid_b"`，值: float 权重

### special_pairs.json
键: `"(uid_a,uid_b)"`，值: `{ "condition": "any|both_upright|mixed", "text": "...", "priority": int }`

## 9. 运行方式

```bash
# GUI
python tarot_system/gui.py

# CLI
python tarot_system/main.py
python tarot_system/main.py --rng physical

# 测试
python -m unittest tarot_system.tests.test_core
python -m unittest tarot_system.tests.test_core -v
```

## 10. 当前状态

所有核心功能就绪，34 项测试全部通过，主要 IDE 警告已清理。项目处于阶段性收尾状态，可进入新功能开发或维护阶段。
