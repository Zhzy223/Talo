import customtkinter as ctk
from PIL import Image
import json
import sys
import time
import tkinter.filedialog as filedialog
from functools import partial
from pathlib import Path
from typing import Any, List, Tuple

from engine.entropy import EntropyPool, SecureRNG
from engine.deck import Deck
from engine.history import HistoryLogger, DrawRecord
from core.calculator import SpreadCalculator, SlotResult
from core.interpreter import TemplateEngine
from core.exporter import export_markdown, export_plaintext
from tarot_system.paths import resource_path

# ------------------------------------------------------------------
# 包豪斯配色系统
# ------------------------------------------------------------------
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
    "fire": "#C75B39",
    "water": "#4A7C8C",
    "air": "#8A8A8A",
    "earth": "#7A6A4E",
}

# ------------------------------------------------------------------
# 字体系统
# ------------------------------------------------------------------
FONT_FAMILY = ("SF Pro", "Segoe UI", "PingFang SC", "Microsoft YaHei", "sans-serif")
FONT_MONO = ("SF Mono", "Consolas", "Courier New", "monospace")


def _font(size: int, bold: bool = False, mono: bool = False) -> tuple:
    family = FONT_MONO if mono else FONT_FAMILY
    if bold:
        return family, size, "bold"
    return family, size


# ------------------------------------------------------------------
# 元素与状态符号
# ------------------------------------------------------------------
ELEMENT_SYMBOLS = {
    "fire": ("△", COLORS["fire"]),
    "water": ("▽", COLORS["water"]),
    "air": ("◇", COLORS["air"]),
    "earth": ("□", COLORS["earth"]),
}


def _make_btn(
    parent,
    text: str,
    command=None,
    width: int = 80,
    height: int = 28,
) -> ctk.CTkButton:
    """工厂：扁平直角按钮，hover 背景微亮。"""
    btn = ctk.CTkButton(
        parent,
        text=text,
        font=_font(12),
        width=width,
        height=height,
        fg_color=COLORS["surface"],
        hover_color=COLORS["surface_hover"],
        text_color=COLORS["text_primary"],
        border_color=COLORS["border"],
        border_width=1,
        corner_radius=0,
        command=command,
    )
    return btn


def _make_label(
    parent,
    text: str,
    size: int = 12,
    bold: bool = False,
    color: str = "text_primary",
    mono: bool = False,
    **kwargs,
) -> ctk.CTkLabel:
    return ctk.CTkLabel(
        parent,
        text=text,
        font=_font(size, bold=bold, mono=mono),
        text_color=COLORS.get(color, color),
        **kwargs,
    )


def _sep(parent, horizontal: bool = True) -> ctk.CTkFrame:
    """1px 分隔线。"""
    if horizontal:
        return ctk.CTkFrame(parent, fg_color=COLORS["border"], height=1)
    return ctk.CTkFrame(parent, fg_color=COLORS["border"], width=1)


SPREAD_OPTIONS = ["单张牌", "三张牌阵", "凯尔特十字"]


class TarotGUI:
    def __init__(self, root: ctk.CTk):
        self.root = root
        self.root.title("塔罗牌占卜系统")
        self.root.geometry("1400x900")
        self.root.configure(fg_color=COLORS["bg"])

        self.deck = Deck()
        self.engine = TemplateEngine()
        self.logger = HistoryLogger()
        self.current_results: List[SlotResult] = []
        self.current_question = ""
        self.current_spread_name = ""
        self.settings = {
            "rng_type": "csprng",
            "reverse_prob": 0.125,
            "shuffle_times": 3,
            "hand_slip_prob": 0.08,
            "double_flip_prob": 0.02,
            "shuffle_interval_ms": 50,
            "use_microphone": False,
        }
        self._speak_process = None
        self._card_extras = self._load_card_extras()

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self._build_ui()

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------
    def _build_ui(self):
        self.top_frame = ctk.CTkFrame(
            self.root, height=56, fg_color=COLORS["bg"], corner_radius=0
        )
        self.top_frame.pack(side=ctk.TOP, fill=ctk.X, padx=0, pady=0)
        self.top_frame.pack_propagate(False)

        self.center_frame = ctk.CTkFrame(
            self.root, fg_color=COLORS["bg"], corner_radius=0
        )
        self.center_frame.pack(
            side=ctk.TOP, fill=ctk.BOTH, expand=True, padx=0, pady=0
        )

        self.bottom_frame = ctk.CTkFrame(
            self.root, height=220, fg_color=COLORS["bg"], corner_radius=0
        )
        self.bottom_frame.pack(side=ctk.BOTTOM, fill=ctk.X, padx=0, pady=0)
        self.bottom_frame.pack_propagate(False)

        self._build_top()
        self._build_bottom()

    def _build_top(self):
        self.top_frame.grid_columnconfigure(0, weight=0)
        self.top_frame.grid_columnconfigure(1, weight=0)
        self.top_frame.grid_columnconfigure(2, weight=0)
        self.top_frame.grid_columnconfigure(3, weight=1)
        self.top_frame.grid_rowconfigure(0, weight=1)

        _sep(self.top_frame).pack(side=ctk.BOTTOM, fill=ctk.X)

        # 问题输入
        self.question_entry = ctk.CTkEntry(
            self.top_frame,
            placeholder_text="输入你的问题...",
            width=400,
            height=28,
            font=_font(12),
            fg_color=COLORS["surface"],
            text_color=COLORS["text_primary"],
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=0,
        )
        self.question_entry.grid(row=0, column=0, padx=16, pady=0)

        # 牌阵选择
        self.spread_menu = ctk.CTkOptionMenu(
            self.top_frame,
            values=SPREAD_OPTIONS,
            width=140,
            height=28,
            font=_font(12),
            fg_color=COLORS["surface"],
            text_color=COLORS["text_primary"],
            button_color=COLORS["surface_hover"],
            button_hover_color=COLORS["border"],
            corner_radius=0,
            dropdown_fg_color=COLORS["surface"],
            dropdown_hover_color=COLORS["surface_hover"],
            dropdown_text_color=COLORS["text_primary"],
        )
        self.spread_menu.set("三张牌阵")
        self.spread_menu.grid(row=0, column=1, padx=8, pady=0)

        # 按钮组
        btn_frame = ctk.CTkFrame(
            self.top_frame, fg_color="transparent", corner_radius=0
        )
        btn_frame.grid(row=0, column=2, padx=8, pady=0)

        # 主操作按钮：带 accent 底线
        self.draw_container = ctk.CTkFrame(
            btn_frame, fg_color="transparent", width=80, height=30
        )
        self.draw_container.pack_propagate(False)
        self.draw_container.pack(side=ctk.LEFT, padx=4)
        self.draw_btn = _make_btn(
            self.draw_container, "抽牌", command=self._on_draw_clicked, width=80
        )
        self.draw_btn.pack()
        accent_line = ctk.CTkFrame(
            self.draw_container, fg_color=COLORS["accent"], height=2
        )
        accent_line.pack(fill=ctk.X)

        self.shuffle_hold_btn = ctk.CTkButton(
            btn_frame,
            text="按住洗牌",
            font=_font(12),
            width=100,
            height=28,
            fg_color=COLORS["surface"],
            hover_color=COLORS["surface_hover"],
            text_color=COLORS["text_primary"],
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=0,
        )
        self.shuffle_hold_btn.bind(
            "<ButtonPress-1>", lambda _e: self._start_shuffling()
        )
        self.shuffle_hold_btn.bind(
            "<ButtonRelease-1>", lambda _e: self._stop_shuffling()
        )

        _make_btn(btn_frame, "历史", command=self.show_history, width=60).pack(
            side=ctk.LEFT, padx=4
        )
        _make_btn(btn_frame, "设置", command=self.show_settings, width=60).pack(
            side=ctk.LEFT, padx=4
        )

        self._update_shuffle_button_visibility()

    def _configure_textbox_tags(self) -> None:
        """配置文本框标签样式（封装 _textbox 访问以隔离 IDE 警告）。"""
        inner = self.textbox._textbox  # noqa: SLF001
        inner.tag_config("special", foreground=COLORS["accent"])
        inner.tag_config("normal", foreground=COLORS["text_primary"])
        inner.tag_config("summary", foreground=COLORS["text_secondary"])
        inner.tag_config("astro", foreground=COLORS["text_dim"])

    def _build_bottom(self):
        _sep(self.bottom_frame).pack(side=ctk.TOP, fill=ctk.X)

        # 使用 grid 布局以便精确控制占星面板高度
        self.bottom_frame.grid_rowconfigure(0, weight=0)
        self.bottom_frame.grid_rowconfigure(1, weight=1)
        self.bottom_frame.grid_rowconfigure(2, weight=0)
        self.bottom_frame.grid_columnconfigure(0, weight=1)

        # --- 按钮行 ---
        btn_row = ctk.CTkFrame(
            self.bottom_frame, fg_color="transparent", corner_radius=0
        )
        btn_row.grid(row=0, column=0, sticky="ew", padx=16, pady=(8, 0))

        _make_btn(btn_row, "保存", command=self._save_reading, width=60).pack(
            side=ctk.LEFT, padx=4
        )
        _make_btn(btn_row, "复制", command=self._copy_text, width=60).pack(
            side=ctk.LEFT, padx=4
        )

        self.export_menu = ctk.CTkOptionMenu(
            btn_row,
            values=["导出 Markdown", "导出纯文本"],
            font=_font(11),
            width=130,
            height=28,
            fg_color=COLORS["surface"],
            text_color=COLORS["text_primary"],
            button_color=COLORS["surface_hover"],
            button_hover_color=COLORS["border"],
            corner_radius=0,
            dropdown_fg_color=COLORS["surface"],
            dropdown_hover_color=COLORS["surface_hover"],
            dropdown_text_color=COLORS["text_primary"],
        )
        self.export_menu.set("导出")
        self.export_menu.pack(side=ctk.LEFT, padx=4)
        self.export_menu.configure(command=self._on_export_selected)

        self.speak_btn: ctk.CTkButton | None = None
        if sys.platform == "darwin":
            sb = _make_btn(
                btn_row, "朗读", command=self._speak_interpretation, width=60
            )
            sb.pack(side=ctk.LEFT, padx=4)
            self.speak_btn = sb
        elif sys.platform == "win32":
            try:
                import pyttsx3  # noqa: F401
                sb = _make_btn(
                    btn_row, "朗读", command=self._speak_interpretation, width=60
                )
                sb.pack(side=ctk.LEFT, padx=4)
                self.speak_btn = sb
            except ImportError:
                pass

        self.export_status_label = _make_label(
            btn_row, "", size=11, color="accent"
        )
        self.export_status_label.pack(side=ctk.RIGHT, padx=10)

        # --- 解读文本框 ---
        self.textbox = ctk.CTkTextbox(
            self.bottom_frame,
            wrap="word",
            font=_font(12),
            fg_color=COLORS["bg"],
            text_color=COLORS["text_primary"],
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=0,
        )
        self.textbox.grid(row=1, column=0, sticky="nsew", padx=16, pady=8)

        self._configure_textbox_tags()

        # --- 占星视角面板（可折叠） ---
        self.astrology_frame = ctk.CTkFrame(
            self.bottom_frame,
            fg_color=COLORS["surface"],
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=0,
            height=32,
        )
        self.astrology_frame.grid(
            row=2, column=0, sticky="ew", padx=16, pady=(0, 8)
        )
        self.astrology_frame.grid_propagate(False)

        astro_header = ctk.CTkFrame(
            self.astrology_frame, fg_color="transparent", corner_radius=0
        )
        astro_header.pack(fill=ctk.X)
        self.astrology_title = _make_label(
            astro_header, "占星视角 >", size=11, color="text_secondary"
        )
        self.astrology_title.pack(side=ctk.LEFT, padx=10, pady=3)
        _make_btn(
            astro_header,
            "展开",
            command=self._toggle_astrology,
            width=50,
            height=20,
        ).pack(side=ctk.RIGHT, padx=10, pady=3)

        self.astrology_text = ctk.CTkTextbox(
            self.astrology_frame,
            wrap="word",
            font=_font(11),
            fg_color=COLORS["bg"],
            text_color=COLORS["text_secondary"],
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=0,
            height=120,
        )
        self._astrology_expanded = False

    # ------------------------------------------------------------------
    # 图像加载
    # ------------------------------------------------------------------
    @staticmethod
    def _load_card_image(
        uid: int, size: Tuple[int, int] = (120, 200), rotate: int = 0
    ):
        path = resource_path("assets/cards") / f"{uid}.png"
        if not path.exists():
            return None
        try:
            img = Image.open(path)
            if rotate:
                img = img.rotate(rotate, expand=True)
            img = img.resize(size, Image.Resampling.LANCZOS)
            return ctk.CTkImage(light_image=img, dark_image=img, size=size)
        except (OSError, ValueError):
            return None

    # ------------------------------------------------------------------
    # 事件处理
    # ------------------------------------------------------------------
    def _on_draw_clicked(self):
        question = self.question_entry.get().strip()
        if not question:
            self._show_alert("提示", "请先输入你的问题")
            return
        self.current_question = question
        spread_choice = self.spread_menu.get()

        def callback(timings):
            self._perform_reading(question, spread_choice, timings)

        self._collect_entropy(callback)

    def _make_dialog(self, title: str, width: int, height: int, grab: bool = True):
        """包豪斯风格弹窗：无系统标题栏，自定义标题栏 + 可拖动。"""
        win = ctk.CTkToplevel(self.root)
        win.geometry(f"{width}x{height}")
        win.transient(self.root)
        if grab:
            win.grab_set()
        win.configure(fg_color=COLORS["bg"])
        win.overrideredirect(True)

        # 居中
        self.root.update_idletasks()
        rx, ry = self.root.winfo_x(), self.root.winfo_y()
        rw, rh = self.root.winfo_width(), self.root.winfo_height()
        x = rx + (rw - width) // 2
        y = ry + (rh - height) // 2
        win.geometry(f"{width}x{height}+{x}+{y}")

        # 自定义标题栏
        title_bar = ctk.CTkFrame(
            win, fg_color=COLORS["surface"], height=32, corner_radius=0
        )
        title_bar.pack(fill=ctk.X, side=ctk.TOP)
        title_bar.pack_propagate(False)
        _make_label(title_bar, title.upper(), size=10, color="text_dim", mono=True).pack(
            side=ctk.LEFT, padx=12
        )
        close_btn = ctk.CTkButton(
            title_bar,
            text="×",
            font=_font(16),
            width=28,
            height=28,
            fg_color="transparent",
            hover_color=COLORS["fire"],
            text_color=COLORS["text_dim"],
            corner_radius=0,
            command=win.destroy,
        )
        close_btn.pack(side=ctk.RIGHT, padx=2)

        # 拖动
        def _start_drag(event):
            win._drag_x = event.x_root
            win._drag_y = event.y_root

        def _do_drag(event):
            dx = event.x_root - win._drag_x
            dy = event.y_root - win._drag_y
            win._drag_x = event.x_root
            win._drag_y = event.y_root
            win.geometry(f"+{win.winfo_x() + dx}+{win.winfo_y() + dy}")

        title_bar.bind("<Button-1>", _start_drag)
        title_bar.bind("<B1-Motion>", _do_drag)
        for w in title_bar.winfo_children():
            w.bind("<Button-1>", _start_drag)
            w.bind("<B1-Motion>", _do_drag)

        return win

    def _show_alert(self, title: str, msg: str):
        win = self._make_dialog(title, 300, 140)
        _make_label(win, msg, size=12, color="text_primary").pack(pady=24)
        _make_btn(win, "确定", command=win.destroy, width=80).pack(pady=8)

    def _collect_entropy(self, callback):
        win = self._make_dialog("收集随机熵", 400, 180)

        label = _make_label(
            win,
            "请点击下方按钮 3 次，每次间隔尽量不同",
            size=13,
        )
        label.pack(pady=24)

        timings = []
        last = time.perf_counter_ns()
        count = [0]

        def on_click():
            nonlocal last
            now = time.perf_counter_ns()
            timings.append(now - last)
            last = now
            count[0] += 1
            label.configure(text=f"已点击 {count[0]} / 3 次")
            if count[0] >= 3:
                win.destroy()
                callback(timings)

        btn = _make_btn(win, "点击", command=on_click, width=120, height=36)
        btn.pack(pady=12)

    # ------------------------------------------------------------------
    # 布局渲染
    # ------------------------------------------------------------------
    def _clear_center(self):
        for widget in self.center_frame.winfo_children():
            widget.destroy()

    def _make_card_widget(
        self,
        parent,
        result: SlotResult,
        img_size: Tuple[int, int] = (120, 200),
        rotate: int = 0,
    ):
        w, h = img_size
        card_w, card_h = w + 20, h + 120

        card = ctk.CTkFrame(
            parent,
            fg_color=COLORS["surface"],
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=0,
            width=card_w,
            height=card_h,
        )
        card.pack_propagate(False)

        # 图像区
        img = self._load_card_image(result.card.uid, img_size, rotate=rotate)
        if img:
            img_label = ctk.CTkLabel(card, image=img, text="")
        else:
            img_label = _make_label(
                card, "未加载", size=11, color="text_dim", width=w, height=h
            )
        img_label.pack(pady=(10, 0))

        _sep(card).pack(fill=ctk.X, padx=8, pady=4)

        # 牌名
        _make_label(
            card, result.card.name, size=14, color="text_primary"
        ).pack()

        # 状态行
        orient_sym = "●" if not result.reversed else "○"
        orient_color = COLORS["accent"] if not result.reversed else COLORS["inverse"]
        orient_text = "UPRIGHT" if not result.reversed else "REVERSED"
        status_frame = ctk.CTkFrame(card, fg_color="transparent", corner_radius=0)
        status_frame.pack(pady=4)
        ctk.CTkLabel(
            status_frame,
            text=orient_sym,
            font=_font(10),
            text_color=orient_color,
        ).pack(side=ctk.LEFT)
        ctk.CTkLabel(
            status_frame,
            text=f" {orient_text}",
            font=_font(10),
            text_color=orient_color,
        ).pack(side=ctk.LEFT)

        _sep(card).pack(fill=ctk.X, padx=8, pady=4)

        # Top-1 维度 + 元素符号
        extra = self._card_extras.get(result.card.uid, {})
        top1 = result.top_dimensions[0] if result.top_dimensions else "-"
        elem = extra.get("element", "")
        elem_sym = ""
        elem_color = COLORS["text_dim"]
        if elem in ELEMENT_SYMBOLS:
            elem_sym, elem_color = ELEMENT_SYMBOLS[elem]

        dim_frame = ctk.CTkFrame(card, fg_color="transparent", corner_radius=0)
        dim_frame.pack(pady=(0, 8))
        if elem_sym:
            ctk.CTkLabel(
                dim_frame,
                text=elem_sym,
                font=_font(11),
                text_color=elem_color,
            ).pack(side=ctk.LEFT)
        ctk.CTkLabel(
            dim_frame,
            text=f" {top1}",
            font=_font(11),
            text_color=COLORS["text_secondary"],
        ).pack(side=ctk.LEFT)

        return card

    def _layout_single(self, results: List[SlotResult]):
        self._clear_center()
        container = ctk.CTkFrame(
            self.center_frame, fg_color="transparent", corner_radius=0
        )
        container.pack(expand=True)
        self._make_card_widget(container, results[0], img_size=(220, 340)).pack(
            padx=20, pady=20
        )

    def _layout_three(self, results: List[SlotResult]):
        self._clear_center()
        container = ctk.CTkFrame(
            self.center_frame, fg_color="transparent", corner_radius=0
        )
        container.pack(expand=True)
        labels = ["过去", "现在", "未来"]
        for idx, r in enumerate(results):
            col = ctk.CTkFrame(
                container, fg_color="transparent", corner_radius=0
            )
            col.pack(side=ctk.LEFT, padx=24, pady=20, expand=True)
            self._make_card_widget(col, r, img_size=(160, 260)).pack()
            _make_label(
                col, labels[idx], size=10, color="text_secondary"
            ).pack(pady=4)

    def _layout_celtic(self, results: List[SlotResult]):
        self._clear_center()

        scroll = ctk.CTkScrollableFrame(
            self.center_frame,
            fg_color=COLORS["bg"],
            corner_radius=0,
            scrollbar_button_color=COLORS["surface"],
            scrollbar_button_hover_color=COLORS["surface_hover"],
        )
        scroll.pack(expand=True, fill=ctk.BOTH, padx=8, pady=8)

        inner = ctk.CTkFrame(scroll, fg_color="transparent", corner_radius=0)
        inner.pack(expand=True, fill=ctk.BOTH)

        celtic_img = (110, 180)

        # ---------- 左侧十字区 ----------
        cross = ctk.CTkFrame(inner, fg_color="transparent", corner_radius=0)
        cross.pack(side=ctk.LEFT, expand=True, fill=ctk.BOTH, padx=20, pady=20)

        for i in range(3):
            cross.grid_columnconfigure(i, weight=1)
        for i in range(4):
            cross.grid_rowconfigure(i, weight=1)

        def _place(parent, row, col, result, label, color="text_secondary",
                   img_size=celtic_img, rotate=0):
            cell = ctk.CTkFrame(parent, fg_color="transparent", corner_radius=0)
            cell.grid(row=row, column=col, sticky="nsew", padx=4, pady=4)
            card = self._make_card_widget(cell, result, img_size=img_size, rotate=rotate)
            card.pack(expand=True)
            _make_label(cell, label, size=11, color=color).pack(pady=(2, 0))
            return cell

        _place(cross, 0, 1, results[4], "⑤ 目标")
        _place(cross, 1, 0, results[3], "④ 过去")
        _place(cross, 1, 1, results[0], "① 现状", color="accent")
        _place(cross, 1, 2, results[5], "⑥ 未来")
        _place(cross, 2, 1, results[2], "③ 根基")

        # ② 挑战：横放
        cell = ctk.CTkFrame(cross, fg_color="transparent", corner_radius=0)
        cell.grid(row=3, column=1, sticky="nsew", padx=4, pady=4)
        card2 = self._make_card_widget(
            cell, results[1], img_size=(160, 100), rotate=90
        )
        card2.configure(border_color=COLORS["accent"], border_width=2)
        card2.pack(expand=True)
        _make_label(cell, "② 挑战", size=11, color="accent").pack(pady=(2, 0))

        # ---------- 右侧竖列 ----------
        staff = ctk.CTkFrame(inner, fg_color="transparent", corner_radius=0)
        staff.pack(side=ctk.RIGHT, expand=True, fill=ctk.Y, padx=20, pady=20)

        staff_pos = [
            ("⑦ 自我", results[6]),
            ("⑧ 环境", results[7]),
            ("⑨ 希望/恐惧", results[8]),
            ("⑩ 结果", results[9]),
        ]
        for label, res in staff_pos:
            cell = ctk.CTkFrame(staff, fg_color="transparent", corner_radius=0)
            cell.pack(pady=4)
            row_inner = ctk.CTkFrame(cell, fg_color="transparent", corner_radius=0)
            row_inner.pack()
            self._make_card_widget(row_inner, res, img_size=celtic_img).pack(side=ctk.LEFT)
            _make_label(row_inner, label, size=11, color="text_secondary").pack(
                side=ctk.LEFT, padx=(8, 0)
            )

    # ------------------------------------------------------------------
    # 占星面板
    # ------------------------------------------------------------------
    def _toggle_astrology(self):
        if self._astrology_expanded:
            self.astrology_text.pack_forget()
            self.astrology_frame.configure(height=32)
            self.astrology_title.configure(text="占星视角 >")
            self._astrology_expanded = False
        else:
            self.astrology_frame.configure(height=180)
            self.astrology_text.pack(
                fill=ctk.BOTH, expand=True, padx=8, pady=8
            )
            self.astrology_title.configure(text="占星视角 v")
            self._astrology_expanded = True

    # ------------------------------------------------------------------
    # 结果展示
    # ------------------------------------------------------------------
    def _display_results(self, results: List[SlotResult], spread_choice: str):
        if spread_choice == "单张牌":
            self._layout_single(results)
        elif spread_choice == "三张牌阵":
            self._layout_three(results)
        else:
            self._layout_celtic(results)

        interpretation = self.engine.render_spread(results)
        self.textbox.delete("1.0", ctk.END)

        for line in interpretation.splitlines():
            if "【" in line and "特殊牌对" in line:
                self.textbox.insert(ctk.END, line + "\n", "special")
            elif line.startswith("【") or line.startswith("  综合"):
                self.textbox.insert(ctk.END, line + "\n", "summary")
            else:
                self.textbox.insert(ctk.END, line + "\n", "normal")

        astro_text = self.engine.render_astrology(spread_choice, results)
        self.astrology_text.delete("1.0", ctk.END)
        self.astrology_text.insert(ctk.END, astro_text)

        self.draw_btn.configure(state=ctk.NORMAL)

    # ------------------------------------------------------------------
    # 核心占卜逻辑
    # ------------------------------------------------------------------
    def _perform_reading(self, question: str, spread_choice: str, timings=None):
        self.draw_btn.configure(state=ctk.DISABLED)

        pool = EntropyPool(question, deterministic=False)
        if timings:
            for t in timings:
                pool.add_timing(t)

        use_physical = self.settings.get("rng_type") == "physical"
        if use_physical:
            pool.collect(use_physical=True)

        rng = SecureRNG(pool.get_seed())
        self.deck.reset()
        self.deck.set_rng(rng)

        assoc = self._load_interactions()

        st: int = int(self.settings.get("shuffle_times", 3))
        rp: float = float(self.settings.get("reverse_prob", 0.125))

        if spread_choice == "单张牌":
            self.current_spread_name = "single"
            draws = self.deck.draw(1, shuffle_times=st, reverse_prob=rp)
            spread = {"positions": [{"name": "启示", "weights": [0.125] * 8}]}
            calc = SpreadCalculator(spread, association_matrix=assoc)
            results = calc.compute(draws)
        elif spread_choice == "三张牌阵":
            self.current_spread_name = "three_card"
            draws = self.deck.draw(3, shuffle_times=st, reverse_prob=rp)
            spread = self._load_spread("three_card")
            calc = SpreadCalculator(spread, association_matrix=assoc)
            results = calc.compute(draws)
        else:
            if len(self.deck) < 10:
                self._show_alert(
                    "错误", "当前牌库仅支持单张/三张牌阵，请先补全牌库。"
                )
                self.draw_btn.configure(state=ctk.NORMAL)
                return
            self.current_spread_name = "celtic_cross"
            draws = self.deck.draw(10, shuffle_times=st, reverse_prob=rp)
            spread = self._load_spread("celtic_cross")
            calc = SpreadCalculator(spread, association_matrix=assoc)
            results = calc.compute(draws)

        self.current_results = results
        self._display_results(results, spread_choice)

    @staticmethod
    def _load_json_data(filename: str) -> dict:
        path = resource_path("data") / filename
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
            if data is None:
                return {}
            return data

    @staticmethod
    def _load_card_extras() -> dict[int, dict]:
        path = resource_path("data/cards.json")
        with path.open("r", encoding="utf-8") as f:
            cards = json.load(f)
        return {
            c["uid"]: {
                "element": c.get("element"),
                "astrology": c.get("astrology"),
            }
            for c in cards
        }

    def _load_interactions(self) -> dict:
        raw = self._load_json_data("interactions.json")
        result: dict[tuple[int, int], float] = {}
        for k, v in raw.items():
            a, b = map(int, k.split(","))
            result[(a, b)] = v
        return result

    def _load_spread(self, name: str) -> dict:
        spreads = self._load_json_data("spreads.json")
        return spreads[name]

    # ------------------------------------------------------------------
    # 保存 / 复制 / 历史 / 设置
    # ------------------------------------------------------------------
    def _save_reading(self):
        if not self.current_results:
            self._show_alert("提示", "暂无占卜结果可保存")
            return
        draw_records = [
            DrawRecord(
                uid=r.card.uid,
                name=r.card.name,
                reversed=r.reversed,
                position=r.position_name,
                final_score=r.score,
                top_dimensions=r.top_dimensions,
            )
            for r in self.current_results
        ]
        interpretation = self.engine.render_spread(self.current_results)
        self.logger.log(
            self.current_question, self.current_spread_name, draw_records, interpretation
        )
        self._show_alert("保存成功", "本次占卜已保存到历史记录")

    def _copy_text(self):
        text = self.textbox.get("1.0", ctk.END)
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self._show_alert("复制成功", "解读文本已复制到剪贴板")

    def show_history(self):
        records = self.logger.list_history(limit=10)

        win = self._make_dialog("历史记录", 900, 600, grab=False)

        # 内容容器（grid/pack 隔离：标题栏已 pack，内容用独立 frame）
        content = ctk.CTkFrame(win, fg_color=COLORS["bg"], corner_radius=0)
        content.pack(fill=ctk.BOTH, expand=True, padx=16, pady=16)
        content.grid_columnconfigure(0, weight=1)
        content.grid_columnconfigure(1, weight=3)
        content.grid_rowconfigure(0, weight=1)

        list_frame = ctk.CTkScrollableFrame(
            content,
            fg_color=COLORS["surface"],
            width=220,
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=0,
        )
        list_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        detail_frame = ctk.CTkFrame(
            content,
            fg_color=COLORS["bg"],
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=0,
        )
        detail_frame.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        detail_frame.grid_rowconfigure(1, weight=1)
        detail_frame.grid_columnconfigure(0, weight=1)

        detail_title = _make_label(
            detail_frame, "请选择一条记录", size=14
        )
        detail_title.grid(row=0, column=0, sticky="w", padx=8, pady=(8, 0))

        detail_text = ctk.CTkTextbox(
            detail_frame,
            wrap="word",
            font=_font(12),
            fg_color=COLORS["surface"],
            text_color=COLORS["text_primary"],
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=0,
        )
        detail_text.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)

        selected_record: list[dict[str, Any] | None] = [None]

        def do_reload():
            selected = selected_record[0]
            if selected is None:
                return
            self._reload_from_history(selected)
            win.destroy()

        reload_btn = ctk.CTkButton(
            detail_frame,
            text="重新加载此牌阵",
            command=do_reload,
            state=ctk.DISABLED,
            font=_font(11),
            fg_color=COLORS["surface"],
            text_color=COLORS["text_primary"],
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=0,
            hover_color=COLORS["surface_hover"],
        )
        reload_btn.grid(row=2, column=0, pady=10)

        def on_select(record):
            selected_record[0] = record
            detail_title.configure(
                text=f"{record['question'][:40]}"
            )

            draw_lines = [
                f"  [{dr['position']}] {dr['name']} ({'逆位' if dr['reversed'] else '正位'})"
                for dr in record["draw_results"]
            ]
            lines = [
                f"时间：{record['timestamp']}",
                f"问题：{record['question']}",
                f"牌阵：{record['spread_name']}",
                "",
                "【牌阵缩略】",
                *draw_lines,
                "",
                "【解读】",
                record["interpretation_text"],
            ]

            detail_text.delete("1.0", ctk.END)
            detail_text.insert(ctk.END, "\n".join(lines))
            reload_btn.configure(state=ctk.NORMAL)

        def do_delete(rec_index: int):
            self.logger.delete_at(rec_index)
            win.destroy()
            self.show_history()

        if not records:
            _make_label(
                list_frame, "暂无历史记录", size=12, color="text_primary"
            ).pack(pady=40)
        else:
            for idx, rec in enumerate(reversed(records)):
                ts = rec["timestamp"][:16].replace("T", " ")
                q = rec["question"]
                if len(q) > 20:
                    q = q[:20] + "…"
                row = ctk.CTkFrame(
                    list_frame, fg_color="transparent", corner_radius=0
                )
                row.pack(fill=ctk.X, pady=2, padx=4)
                row.grid_columnconfigure(0, weight=1)

                btn = ctk.CTkButton(
                    row,
                    text=f"{ts}\n{q}",
                    font=_font(11),
                    anchor="w",
                    fg_color=COLORS["bg"],
                    hover_color=COLORS["surface_hover"],
                    text_color=COLORS["text_primary"],
                    border_color=COLORS["border"],
                    border_width=1,
                    corner_radius=0,
                    command=partial(on_select, rec),
                )
                btn.grid(row=0, column=0, sticky="ew")

                del_btn = ctk.CTkButton(
                    row,
                    text="×",
                    font=_font(12),
                    width=24,
                    height=24,
                    fg_color="transparent",
                    hover_color=COLORS["fire"],
                    text_color=COLORS["text_dim"],
                    corner_radius=0,
                    command=partial(do_delete, idx),
                )
                del_btn.grid(row=0, column=1, padx=(4, 0))

    def _reload_from_history(self, record: dict):
        spread_map = {
            "single": "单张牌",
            "three_card": "三张牌阵",
            "celtic_cross": "凯尔特十字",
        }
        spread_choice = spread_map.get(record["spread_name"], "三张牌阵")

        new_results: List[SlotResult] = []
        for dr in record["draw_results"]:
            card = self.deck.get_card_by_uid(dr["uid"])
            if card is None:
                continue
            new_results.append(
                SlotResult(
                    card=card,
                    reversed=dr["reversed"],
                    position_name=dr["position"],
                    score=dr["final_score"],
                    top_dimensions=dr["top_dimensions"],
                    interaction_scores={},
                )
            )

        self.current_results = new_results
        self.current_question = record["question"]
        self.current_spread_name = record["spread_name"]
        self.question_entry.delete(0, ctk.END)
        self.question_entry.insert(0, self.current_question)
        self._display_results(new_results, spread_choice)

    def show_settings(self):
        win = self._make_dialog("占卜设置", 440, 420)

        _make_label(win, "系统设置", size=16).pack(pady=(16, 12))

        # 网格容器
        grid = ctk.CTkFrame(win, fg_color="transparent", corner_radius=0)
        grid.pack(fill=ctk.X, padx=24, pady=8)
        grid.grid_columnconfigure(1, weight=1)

        row = 0

        def _label(text):
            nonlocal row
            lbl = _make_label(grid, text, size=10, color="text_secondary")
            lbl.grid(row=row, column=0, sticky="w", pady=(12, 4))
            row += 1
            return row - 1

        def _sep_row():
            nonlocal row
            s = _sep(grid)
            s.grid(row=row, column=0, columnspan=2, sticky="ew", pady=4)
            row += 1

        # 随机引擎
        _label("随机引擎")
        rng_menu = ctk.CTkOptionMenu(
            grid,
            values=["密码学安全(CSPRNG)", "物理硬件熵(Hardware)"],
            font=_font(12),
            width=280,
            fg_color=COLORS["surface"],
            text_color=COLORS["text_primary"],
            button_color=COLORS["surface_hover"],
            button_hover_color=COLORS["border"],
            corner_radius=0,
            dropdown_fg_color=COLORS["surface"],
            dropdown_hover_color=COLORS["surface_hover"],
            dropdown_text_color=COLORS["text_primary"],
        )
        rng_menu.set(
            "物理硬件熵(Hardware)"
            if self.settings.get("rng_type") == "physical"
            else "密码学安全(CSPRNG)"
        )
        rng_menu.grid(row=row - 1, column=1, sticky="e", pady=(12, 4))
        _sep_row()

        def _make_slider(parent, label_text, from_, to_, steps, default, fmt_fn):
            _label(label_text)
            slider = ctk.CTkSlider(parent, from_=from_, to=to_, number_of_steps=steps, width=200)
            slider.set(float(default))
            slider.grid(row=row - 1, column=1, sticky="e", pady=(12, 4))
            val_lbl = _make_label(parent, "", size=10, color="text_dim")
            val_lbl.grid(row=row - 1, column=1, sticky="e", pady=(12, 4), padx=(0, 210))

            def _upd(_value=None):
                val_lbl.configure(text=fmt_fn(slider.get()))

            slider.configure(command=_upd)
            _upd()
            _sep_row()
            return slider

        hand_slider = _make_slider(
            grid, "手滑概率", 0.02, 0.15, 13,
            self.settings.get("hand_slip_prob", 0.08),
            lambda v: f"{int(v * 100)}%",
        )
        dbl_slider = _make_slider(
            grid, "双翻概率", 0.0, 0.05, 5,
            self.settings.get("double_flip_prob", 0.02),
            lambda v: f"{int(v * 100)}%",
        )
        speed_slider = _make_slider(
            grid, "洗牌速度", 20, 200, 18,
            self.settings.get("shuffle_interval_ms", 50),
            lambda v: f"{int(v)}ms",
        )

        # 麦克风
        mic_available = False
        try:
            import pyaudio  # noqa: F401
            mic_available = True
        except ImportError:
            pass

        mic_var = ctk.BooleanVar(value=bool(self.settings.get("use_microphone", False)))
        mic_chk = ctk.CTkCheckBox(
            grid,
            text="麦克风噪声增强",
            variable=mic_var,
            font=_font(12),
            text_color=COLORS["text_primary"],
            checkbox_width=16,
            checkbox_height=16,
            corner_radius=0,
            border_width=1,
            border_color=COLORS["border"],
            fg_color=COLORS["surface"],
            hover_color=COLORS["surface_hover"],
        )
        if not mic_available:
            mic_chk.configure(
                state=ctk.DISABLED,
                text="麦克风噪声增强 (未安装 pyaudio)",
                text_color=COLORS["text_dim"],
            )
        mic_chk.grid(row=row, column=0, columnspan=2, sticky="w", pady=(12, 4))
        row += 1

        # 保存 / 取消
        def _save():
            self.settings["rng_type"] = (
                "physical" if "Hardware" in rng_menu.get() else "csprng"
            )
            self.settings["hand_slip_prob"] = float(hand_slider.get())
            self.settings["double_flip_prob"] = float(dbl_slider.get())
            self.settings["shuffle_interval_ms"] = int(speed_slider.get())
            self.settings["use_microphone"] = mic_var.get() if mic_available else False
            self.deck.set_rng_type(self.settings["rng_type"])
            self._update_shuffle_button_visibility()
            win.destroy()

        btn_frame = ctk.CTkFrame(win, fg_color="transparent", corner_radius=0)
        btn_frame.pack(pady=20)
        _make_btn(
            btn_frame, "应用", command=_save, width=80
        ).pack(side=ctk.LEFT, padx=8)
        _make_btn(btn_frame, "取消", command=win.destroy, width=80).pack(
            side=ctk.LEFT, padx=8
        )

    def _update_shuffle_button_visibility(self):
        if self.settings.get("rng_type") == "physical":
            self.draw_container.pack_forget()
            self.shuffle_hold_btn.pack(side=ctk.LEFT, padx=4)
        else:
            self.shuffle_hold_btn.pack_forget()
            self.draw_container.pack(side=ctk.LEFT, padx=4)

    def _start_shuffling(self):
        self.deck.reset()
        self.deck.shuffle_interval_ms = float(self.settings.get("shuffle_interval_ms", 50))
        self.deck.hand_slip_prob = float(self.settings.get("hand_slip_prob", 0.08))
        self.deck.double_flip_prob = float(self.settings.get("double_flip_prob", 0.02))
        self.deck.shuffle(times=None)

    def _stop_shuffling(self):
        self.deck.stop_shuffling()
        question = self.question_entry.get().strip()
        if not question:
            self._show_alert("提示", "请先输入问题")
            return
        spread_choice = self.spread_menu.get()
        self._perform_physical_reading(question, spread_choice)

    def _perform_physical_reading(self, question: str, spread_choice: str):
        self.draw_btn.configure(state=ctk.DISABLED)
        self.shuffle_hold_btn.configure(state=ctk.DISABLED)

        pool = EntropyPool(question, deterministic=False)
        if self.settings.get("use_microphone", False):
            pool.collect(use_physical=True, shuffle_count=self.deck.shuffle_count)
        else:
            pool.collect(shuffle_count=self.deck.shuffle_count)

        rng = SecureRNG(pool.get_seed())
        self.deck.set_rng(rng)

        assoc = self._load_interactions()

        if spread_choice == "单张牌":
            self.current_spread_name = "single"
            draws = self.deck.draw(1)
            spread = {"positions": [{"name": "启示", "weights": [0.125] * 8}]}
            calc = SpreadCalculator(spread, association_matrix=assoc)
            results = calc.compute(draws)
        elif spread_choice == "三张牌阵":
            self.current_spread_name = "three_card"
            draws = self.deck.draw(3)
            spread = self._load_spread("three_card")
            calc = SpreadCalculator(spread, association_matrix=assoc)
            results = calc.compute(draws)
        else:
            if len(self.deck) < 10:
                self._show_alert(
                    "错误", "当前牌库仅支持单张/三张牌阵，请先补全牌库。"
                )
                self.draw_btn.configure(state=ctk.NORMAL)
                self.shuffle_hold_btn.configure(state=ctk.NORMAL)
                return
            self.current_spread_name = "celtic_cross"
            draws = self.deck.draw(10)
            spread = self._load_spread("celtic_cross")
            calc = SpreadCalculator(spread, association_matrix=assoc)
            results = calc.compute(draws)

        self.current_question = question
        self.current_results = results
        self._display_results(results, spread_choice)
        self.shuffle_hold_btn.configure(state=ctk.NORMAL)

    def _on_export_selected(self, choice: str):
        self.export_menu.set("导出")
        if "Markdown" in choice:
            self._do_export("markdown")
        elif "纯文本" in choice:
            self._do_export("plaintext")

    def _do_export(self, fmt: str):
        if not self.current_results:
            self._show_alert("提示", "暂无占卜结果可导出")
            return

        ts = time.strftime("%Y%m%d_%H%M%S")
        default_name = f"tarot_{ts}.{'md' if fmt == 'markdown' else 'txt'}"

        path = filedialog.asksaveasfilename(
            defaultextension=".md" if fmt == "markdown" else ".txt",
            initialfile=default_name,
            filetypes=[
                ("Markdown", "*.md"),
                ("Text", "*.txt"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return

        interpretation = self.engine.render_spread(self.current_results)
        if fmt == "markdown":
            content = export_markdown(
                self.current_question,
                self.current_spread_name,
                self.current_results,
                interpretation,
            )
        else:
            content = export_plaintext(
                self.current_question,
                self.current_spread_name,
                self.current_results,
                interpretation,
            )

        try:
            Path(path).write_text(content, encoding="utf-8")
            filename = Path(path).name
            self.export_status_label.configure(text=f"已导出 {filename}")
            self.root.after(3000, lambda: self.export_status_label.configure(text=""))
        except (OSError, PermissionError) as e:
            self._show_alert("导出失败", str(e))

    def _speak_interpretation(self):
        import subprocess
        import threading

        if self._speak_process is not None:
            if isinstance(self._speak_process, subprocess.Popen):
                try:
                    self._speak_process.terminate()
                except (OSError, PermissionError):
                    pass
            self._speak_process = None
            if self.speak_btn is not None:
                self.speak_btn.configure(text="朗读")
            return

        if not self.current_results or self.speak_btn is None:
            return
        interpretation = self.engine.render_spread(self.current_results)
        text = interpretation[:500]

        if sys.platform == "darwin":
            assert self.speak_btn is not None
            self._speak_process = subprocess.Popen(
                ["say", text],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.speak_btn.configure(text="停止")

            def _on_finish():
                if isinstance(self._speak_process, subprocess.Popen):
                    self._speak_process.poll()
                    if self._speak_process.returncode is not None:
                        self._speak_process = None
                        assert self.speak_btn is not None
                        self.speak_btn.configure(text="朗读")
                    else:
                        self.root.after(500, _on_finish)

            self.root.after(500, _on_finish)
        elif sys.platform == "win32":
            def _speak():
                try:
                    import pyttsx3  # noqa: F401
                    engine = pyttsx3.init()
                    engine.say(text)
                    engine.runAndWait()
                except (ImportError, RuntimeError):
                    pass
                finally:
                    self._speak_process = None
                    if self.speak_btn is not None:
                        self.speak_btn.configure(text="朗读")

            self._speak_process = threading.Thread(target=_speak, daemon=True)
            self._speak_process.start()
            assert self.speak_btn is not None
            self.speak_btn.configure(text="停止")


if __name__ == "__main__":
    _root = ctk.CTk()
    _app = TarotGUI(_root)
    _root.mainloop()
