import json
import pathlib
from dataclasses import dataclass
from typing import Dict, List

from core.calculator import SlotResult, DIMENSIONS
from tarot_system.paths import resource_path


DEFAULT_TEMPLATES = {
    # emotion
    "emotion_strong_upright": "情感层面充满积极与热忱",
    "emotion_strong_reversed": "情感压抑或过度敏感，需警惕情绪反噬",
    "emotion_moderate_upright": "情感状态总体平稳向好",
    "emotion_moderate_reversed": "情感上有些波动或阻滞",
    "emotion_weak_upright": "情感影响轻微，心态平和",
    "emotion_weak_reversed": "情感层面几乎无明显扰动",
    # material
    "material_strong_upright": "物质与资源方面收获显著",
    "material_strong_reversed": "物质层面存在明显损失或匮乏",
    "material_moderate_upright": "财务状况趋于稳定改善",
    "material_moderate_reversed": "物质流动略有阻碍",
    "material_weak_upright": "对物质生活影响甚微",
    "material_weak_reversed": "资源领域暂时平静",
    # conflict
    "conflict_strong_upright": "正面对抗激烈，冲突显性化",
    "conflict_strong_reversed": "矛盾被压抑或内化，表面平静但隐患仍在",
    "conflict_moderate_upright": "存在可调和的矛盾",
    "conflict_moderate_reversed": "矛盾暂时搁置",
    "conflict_weak_upright": "几乎没有外部冲突",
    "conflict_weak_reversed": "冲突能量极低",
    # change
    "change_strong_upright": "剧变正在发生，势不可挡",
    "change_strong_reversed": "转变延迟或被迫进行，阻力大于动力",
    "change_moderate_upright": "渐进式变化带来成长",
    "change_moderate_reversed": "变化节奏放缓",
    "change_weak_upright": "环境相对静止",
    "change_weak_reversed": "固守现状，缺乏新意",
    # spirit
    "spirit_strong_upright": "灵性觉醒，内在连接深刻",
    "spirit_strong_reversed": "精神层面迷茫或疏离",
    "spirit_moderate_upright": "内心有初步的灵性指引",
    "spirit_moderate_reversed": "信仰或价值观受到轻微质疑",
    "spirit_weak_upright": "精神生活平淡",
    "spirit_weak_reversed": "灵性层面暂时休眠",
    # will
    "will_strong_upright": "意志力坚定，行动果断",
    "will_strong_reversed": "意志消沉，行动力不足，易自我怀疑",
    "will_moderate_upright": "有一定的自驱力与目标感",
    "will_moderate_reversed": "决心偶有不坚定",
    "will_weak_upright": "意志影响微弱",
    "will_weak_reversed": "行动力不足，犹豫不决",
    # intellect
    "intellect_strong_upright": "思维清晰，洞察深刻",
    "intellect_strong_reversed": "思维受阻，判断易偏差，需暂缓决策",
    "intellect_moderate_upright": "理性判断基本准确",
    "intellect_moderate_reversed": "思路偶尔受阻",
    "intellect_weak_upright": "智力层面非主要因素",
    "intellect_weak_reversed": "思考深度有限",
    # time_pressure
    "time_pressure_strong_upright": "时间紧迫，需立刻行动",
    "time_pressure_strong_reversed": "时机延误，进度严重滞后",
    "time_pressure_moderate_upright": "有适度的紧迫感推动前进",
    "time_pressure_moderate_reversed": "时间压力轻微延迟",
    "time_pressure_weak_upright": "时间充裕，可从容规划",
    "time_pressure_weak_reversed": "无显著时间约束",
}


def _strength(value: float) -> str:
    av = abs(value)
    if av >= 0.7:
        return "strong"
    elif av >= 0.3:
        return "moderate"
    else:
        return "weak"


def _load_card_extras() -> Dict[int, dict]:
    path = pathlib.Path(__file__).parent.parent / "data" / "cards.json"
    with path.open("r", encoding="utf-8") as f:
        cards = json.load(f)
    return {
        c["uid"]: {
            "element": c.get("element"),
            "astrology": c.get("astrology"),
            "kabbalah_path": c.get("kabbalah_path"),
        }
        for c in cards
    }


def _load_special_pairs(path: pathlib.Path | None = None) -> Dict[tuple, dict]:
    if path is None:
        path = pathlib.Path(__file__).parent.parent / "data" / "special_pairs.json"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    result: Dict[tuple, dict] = {}
    for k, v in raw.items():
        inner = k.strip("()")
        a, b = map(int, inner.split(","))
        result[(a, b)] = v
    return result


class TemplateEngine:
    def __init__(
        self,
        templates: Dict[str, str] | None = None,
        special_pairs: Dict[tuple, dict] | None = None,
    ) -> None:
        self._templates = templates if templates is not None else dict(DEFAULT_TEMPLATES)
        self._special_pairs = special_pairs if special_pairs is not None else _load_special_pairs()

    def _match_special_pairs(self, results: List[SlotResult]) -> List[str]:
        """遍历所有牌对，返回触发的特殊文本列表（按 priority 降序）。"""
        matched: List[tuple] = []  # (priority, text)
        n = len(results)
        for i in range(n):
            for j in range(i + 1, n):
                uid_i = results[i].card.uid
                uid_j = results[j].card.uid
                rev_i = results[i].reversed
                rev_j = results[j].reversed
                for (a, b), config in self._special_pairs.items():
                    if {a, b} == {uid_i, uid_j}:
                        condition = config["condition"]
                        triggered = False
                        if condition == "any":
                            triggered = True
                        elif condition == "both_upright":
                            triggered = (not rev_i) and (not rev_j)
                        elif condition == "mixed":
                            triggered = rev_i != rev_j
                        if triggered:
                            matched.append((config["priority"], config["text"]))
        matched.sort(reverse=True)
        return [text for _, text in matched]

    def render(self, result: SlotResult) -> str:
        """渲染单张牌的解读。"""
        parts: List[str] = []
        parts.append(
            f"【{result.position_name}】{result.card.name} "
            f"{'逆位' if result.reversed else '正位'}"
        )
        parts.append(f"  综合得分: {result.score:.3f}")

        vec = result.card.reversed_vec if result.reversed else result.card.upright_vec
        parts.append("  8维向量: " + ", ".join(f"{v:+.2f}" for v in vec))
        dim_parts: List[str] = []
        for dim in result.top_dimensions:
            idx = DIMENSIONS.index(dim)
            val = vec[idx]
            strength = _strength(val)
            orient = "reversed" if result.reversed else "upright"
            key = f"{dim}_{strength}_{orient}"
            phrase = self._templates.get(key, f"{dim}影响待定")
            dim_parts.append(f"    - {dim}({val:+.2f}): {phrase}")
        parts.extend(dim_parts)

        non_zero_interactions = {
            uid: score for uid, score in result.interaction_scores.items()
            if abs(score) >= 0.001
        }
        if non_zero_interactions:
            parts.append("  牌间交互:")
            for uid, score in non_zero_interactions.items():
                parts.append(f"    - 与牌 UID {uid}: {score:+.3f}")

        return "\n".join(parts)

    def render_spread(self, results: List[SlotResult]) -> str:
        """渲染整个牌阵，包含特殊牌对提示。"""
        sections: List[str] = []
        special_texts = self._match_special_pairs(results)
        if special_texts:
            sections.append("【特殊牌对启示】")
            for text in special_texts:
                sections.append(text)
            sections.append("")
        for r in results:
            sections.append(self.render(r))
            sections.append("")
        return "\n".join(sections)

    def render_astrology(self, spread_name: str, results: List[SlotResult]) -> str:
        """渲染占星视角，包含元素分布与大阿卡纳星象分析。"""
        if not hasattr(self, "_card_extras"):
            self._card_extras = _load_card_extras()

        lines: List[str] = []

        element_counts = {"fire": 0, "water": 0, "air": 0, "earth": 0}
        element_symbols = {"fire": "△", "water": "▽", "air": "◇", "earth": "□"}

        # 占星符号 → 简洁文字映射（包豪斯：去装饰、纯功能）
        astro_symbol_map = {
            "♈": "白羊", "♉": "金牛", "♊": "双子", "♋": "巨蟹",
            "♌": "狮子", "♍": "处女", "♎": "天秤", "♏": "天蝎",
            "♐": "射手", "♑": "摩羯", "♒": "水瓶", "♓": "双鱼",
            "☿": "水星", "♀": "金星", "♂": "火星", "♃": "木星",
            "♄": "土星", "☉": "太阳", "☽": "月亮", "♅": "天王",
            "♆": "海王", "♇": "冥王",
        }
        element_hints = {
            "fire": "意志力与行动力主导当前局势",
            "water": "情感与直觉主导当前局势",
            "air": "沟通与思维主导当前局势",
            "earth": "物质与务实主导当前局势",
        }
        absent_hints = {
            "fire": "意志力与行动力层面需特别关注",
            "water": "情感与直觉层面需特别关注",
            "air": "沟通与思维层面需特别关注",
            "earth": "物质与务实层面需特别关注",
        }

        major_cards: list[tuple[SlotResult, dict]] = []
        for r in results:
            extra = self._card_extras.get(r.card.uid, {})
            elem = extra.get("element")
            if elem in element_counts:
                element_counts[elem] += 1
            if extra.get("astrology"):
                major_cards.append((r, extra))

        # 元素集中提示
        for elem, count in element_counts.items():
            if count >= 3:
                lines.append(
                    f"{element_symbols[elem]} {elem}元素集中（{count}张）：{element_hints[elem]}"
                )

        # 元素缺席提示
        for elem, count in element_counts.items():
            if count == 0:
                lines.append(
                    f"{element_symbols[elem]} {elem}元素缺席：{absent_hints[elem]}"
                )

        def _clean_sym(sym: str) -> str:
            return astro_symbol_map.get(sym, sym)

        # 大阿卡纳星象
        if major_cards:
            lines.append("")
            lines.append("【大阿卡纳星象】")
            for r, extra in major_cards:
                astro = extra["astrology"]
                parts = astro.split("|")
                symbol = _clean_sym(parts[2]) if len(parts) > 2 else ""
                cn_name = parts[0] if len(parts) > 0 else ""
                lines.append(f"  {symbol} {r.card.name}：{cn_name}能量")

            # 行星/星座能量重复
            astro_counts: Dict[str, int] = {}
            for _, extra in major_cards:
                astro = extra["astrology"]
                astro_counts[astro] = astro_counts.get(astro, 0) + 1

            for astro, count in astro_counts.items():
                if count >= 2:
                    parts = astro.split("|")
                    symbol = _clean_sym(parts[2]) if len(parts) > 2 else ""
                    cn_name = parts[0] if len(parts) > 0 else ""
                    lines.append(
                        f"  {symbol} {cn_name}能量重复："
                        f"该行星/星座特质被放大，需留意其极端表现"
                    )

        return "\n".join(lines)
