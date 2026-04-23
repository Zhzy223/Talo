"""零外部依赖的占卜结果导出器。"""
from core.calculator import SlotResult


SPREAD_NAME_MAP = {
    "single": "单张牌",
    "three_card": "三张牌阵",
    "celtic_cross": "凯尔特十字",
}


def _format_spread_name(spread_name: str) -> str:
    return SPREAD_NAME_MAP.get(spread_name, spread_name)


def _format_card_rows(results: list[SlotResult]) -> list[str]:
    """将牌阵结果格式化为 Markdown 表格行列表。"""
    rows: list[str] = []
    for r in results:
        orient = "逆位" if r.reversed else "正位"
        top3 = ", ".join(r.top_dimensions[:3]) if r.top_dimensions else "-"
        rows.append(
            f"| {r.position_name} | {r.card.name} | {orient} | {top3} |"
        )
    return rows


def export_markdown(
    question: str,
    spread_name: str,
    results: list[SlotResult],
    interpretation: str,
) -> str:
    """返回 Markdown 格式的占卜报告。"""
    rows = _format_card_rows(results)
    return "\n".join(
        [
            f"# {question}",
            "",
            f"## 牌阵：{_format_spread_name(spread_name)}",
            "",
            "## 牌面",
            "",
            "| 位置 | 牌名 | 正逆位 | Top-3 维度 |",
            "|------|------|--------|------------|",
            *rows,
            "",
            "## 解读",
            "",
            interpretation,
        ]
    )


def export_plaintext(
    question: str,
    spread_name: str,
    results: list[SlotResult],
    interpretation: str,
) -> str:
    """返回纯文本格式的占卜报告。"""
    card_lines = [
        f"  {i}. [{r.position_name}] {r.card.name} ({'逆位' if r.reversed else '正位'}) — Top-3: {', '.join(r.top_dimensions[:3]) if r.top_dimensions else '-'}"
        for i, r in enumerate(results, 1)
    ]
    return "\n".join(
        [
            f"问题：{question}",
            "",
            f"牌阵：{_format_spread_name(spread_name)}",
            "",
            "牌面：",
            *card_lines,
            "",
            "解读：",
            interpretation,
        ]
    )
