from dataclasses import dataclass, field
from typing import List, Tuple, Dict

from engine.deck import TarotCard


@dataclass
class SlotResult:
    card: TarotCard
    reversed: bool
    position_name: str
    score: float
    top_dimensions: List[str]
    interaction_scores: Dict[int, float] = field(default_factory=dict)


DIMENSIONS = [
    "emotion",
    "material",
    "conflict",
    "change",
    "spirit",
    "will",
    "intellect",
    "time_pressure",
]


class SpreadCalculator:
    def __init__(
        self,
        spread_config: dict,
        association_matrix: Dict[Tuple[int, int], float] | None = None,
    ) -> None:
        self._positions = spread_config["positions"]
        # 对称化关联矩阵：确保 (a,b) 和 (b,a) 都能命中
        self._association_matrix: Dict[Tuple[int, int], float] = {}
        if association_matrix:
            for (a, b), v in association_matrix.items():
                self._association_matrix[(a, b)] = v
                if (b, a) not in self._association_matrix:
                    self._association_matrix[(b, a)] = v

    @staticmethod
    def _fallback_assoc(uid_a: int, uid_b: int) -> float:
        """当 JSON 关联矩阵无记录时的 fallback 规则。

        基于塔罗牌核心原则：
        - 同元素 / 同数字 / 同宫廷角色 → 共鸣
        - 大阿卡纳相邻 / 对宫 → 深层关联
        - 大阿卡纳与小阿卡纳元素对应 → 能量呼应
        """
        major_elements = {
            0: "air", 1: "air", 2: "water", 3: "earth", 4: "fire",
            5: "earth", 6: "air", 7: "water", 8: "fire", 9: "earth",
            10: "fire", 11: "air", 12: "water", 13: "water", 14: "fire",
            15: "earth", 16: "fire", 17: "air", 18: "water", 19: "fire",
            20: "fire", 21: "earth",
        }
        minor_suit_element = {0: "fire", 1: "water", 2: "air", 3: "earth"}

        a_major = uid_a < 22
        b_major = uid_b < 22

        # ---------- 双大阿卡纳 ----------
        if a_major and b_major:
            diff = abs(uid_a - uid_b)
            if diff == 1:
                return 0.30  # 相邻牌：旅程连续
            if diff == 11:
                return 0.20  # 对宫：如魔术师1-正义11
            return 0.08

        # ---------- 大小阿卡纳元素对应 ----------
        if a_major or b_major:
            major_uid = uid_a if a_major else uid_b
            minor_uid = uid_b if a_major else uid_a
            suit = (minor_uid - 22) // 14
            if major_elements.get(major_uid) == minor_suit_element.get(suit):
                return 0.18
            return 0.05

        # ---------- 双小阿卡纳 ----------
        suit_a = (uid_a - 22) // 14
        suit_b = (uid_b - 22) // 14
        offset_a = (uid_a - 22) % 14
        offset_b = (uid_b - 22) % 14

        if suit_a == suit_b:
            return 0.15  # 同元素
        if offset_a == offset_b:
            return 0.08  # 同数字
        # 宫廷牌同角色
        court = {10: "page", 11: "knight", 12: "queen", 13: "king"}
        ra, rb = court.get(offset_a), court.get(offset_b)
        if ra and rb and ra == rb:
            return 0.12
        # 相邻数字（如3-4）
        if abs(offset_a - offset_b) == 1:
            return 0.04
        return 0.0

    def compute(
        self,
        draws: List[Tuple[TarotCard, bool]],
    ) -> List[SlotResult]:
        # 构建向量列表
        vectors: List[Tuple[float, ...]] = []
        for card, rev in draws:
            vec = card.reversed_vec if rev else card.upright_vec
            vectors.append(vec)

        n = len(draws)
        # 计算两两交互
        interactions: Dict[Tuple[int, int], float] = {}
        for i in range(n):
            for j in range(i + 1, n):
                uid_i = draws[i][0].uid
                uid_j = draws[j][0].uid
                key = (uid_i, uid_j)
                assoc = self._association_matrix.get(key, 0.0)

                # fallback：JSON 中无记录时，按 suit/number 赋予默认关联
                if assoc == 0.0:
                    assoc = self._fallback_assoc(uid_i, uid_j)

                dot = sum(a * b for a, b in zip(vectors[i], vectors[j]))
                interactions[(i, j)] = assoc * dot

        results: List[SlotResult] = []
        for idx, (card, rev) in enumerate(draws):
            weights = tuple(self._positions[idx]["weights"])
            vec = vectors[idx]
            base_score = sum(v * w for v, w in zip(vec, weights))

            # 收集该牌涉及的所有交互
            inter_sum = 0.0
            inter_dict: Dict[int, float] = {}
            for (i, j), val in interactions.items():
                if i == idx:
                    inter_sum += val
                    inter_dict[draws[j][0].uid] = val
                elif j == idx:
                    inter_sum += val
                    inter_dict[draws[i][0].uid] = val

            final_score = base_score + 0.3 * inter_sum

            # top_dimensions: 按 |vec[i]| 从大到小取前3个
            indexed = [
                (abs(vec[i]), DIMENSIONS[i], vec[i])
                for i in range(len(DIMENSIONS))
            ]
            indexed.sort(reverse=True)
            top_dims = [d for _, d, _ in indexed[:3]]

            results.append(
                SlotResult(
                    card=card,
                    reversed=rev,
                    position_name=self._positions[idx]["name"],
                    score=final_score,
                    top_dimensions=top_dims,
                    interaction_scores=inter_dict,
                )
            )

        return results
