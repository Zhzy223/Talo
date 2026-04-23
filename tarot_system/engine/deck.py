import json
import pathlib
import threading
import time
from dataclasses import dataclass
from typing import List, Tuple, Dict, Any

from engine.entropy import SecureRNG, PhysicalRNG
from tarot_system.paths import resource_path


@dataclass(frozen=True)
class TarotCard:
    uid: int
    name: str
    suit: str
    upright_vec: Tuple[float, ...]
    reversed_vec: Tuple[float, ...]


class Deck:
    def __init__(
        self,
        cards_path: pathlib.Path | None = None,
        rng: SecureRNG | None = None,
        rng_type: str = "csprng",
    ) -> None:
        if cards_path is None:
            cards_path = resource_path("data/cards.json")
        self._cards_path = cards_path
        self._rng_type = rng_type
        self._rng = rng
        self._phys_rng: PhysicalRNG | None = None
        self._all_cards: List[TarotCard] = []
        self._available: List[TarotCard] = []
        self._shuffled = False
        self._shuffle_stop = threading.Event()
        self._shuffle_thread: threading.Thread | None = None
        self.shuffle_count = 0
        self.orientations: Dict[int, bool] = {}

        # 可配置参数
        self.shuffle_interval_ms: float = 50.0
        self.hand_slip_prob: float = 0.08
        self.double_flip_prob: float = 0.02
        self.reverse_prob: float = 0.125

        self._load()

    def _load(self) -> None:
        with self._cards_path.open("r", encoding="utf-8") as f:
            raw: List[Dict[str, Any]] = json.load(f)
        cards = []
        for item in raw:
            cards.append(
                TarotCard(
                    uid=item["uid"],
                    name=item["name"],
                    suit=item["suit"],
                    upright_vec=tuple(item["upright_vec"]),
                    reversed_vec=tuple(item["reversed_vec"]),
                )
            )
        self._all_cards = cards
        self._available = list(cards)
        self._reset_orientations()

    def _reset_orientations(self) -> None:
        self.orientations = {c.uid: False for c in self._all_cards}

    def reset(self) -> None:
        self._available = list(self._all_cards)
        self._shuffled = False
        self.shuffle_count = 0
        self._reset_orientations()
        if self._shuffle_thread is not None and self._shuffle_thread.is_alive():
            self._shuffle_stop.set()
            self._shuffle_thread.join(timeout=1.0)
        self._shuffle_thread = None

    def set_rng(self, rng: SecureRNG) -> None:
        self._rng = rng

    def set_rng_type(self, rng_type: str) -> None:
        self._rng_type = rng_type
        if rng_type != "physical":
            self._phys_rng = None

    def _get_rng(self):
        if self._rng_type == "physical":
            if self._phys_rng is None:
                self._phys_rng = PhysicalRNG()
            return self._phys_rng
        if self._rng is None:
            raise RuntimeError("RNG not set")
        return self._rng

    def shuffle(self, times: int | None = None) -> None:
        """Fisher-Yates 洗牌。times=None 时进入持续模式。"""
        if times is None:
            self._shuffle_stop.clear()
            self._shuffle_thread = threading.Thread(
                target=self._shuffle_loop, daemon=True
            )
            self._shuffle_thread.start()
            return

        if self._rng_type == "physical":
            for _ in range(times):
                self._shuffle_step()
        else:
            rng = self._get_rng()
            for _ in range(times):
                rng.shuffle(self._available)
            for card in self._all_cards:
                self.orientations[card.uid] = rng.randbool(self.reverse_prob)

        self._shuffled = True

    def _shuffle_loop(self) -> None:
        """持续洗牌循环，直到 stop_shuffling() 被调用。"""
        while not self._shuffle_stop.is_set():
            self._shuffle_step()
            self._shuffle_stop.wait(self.shuffle_interval_ms / 1000.0)

    def _shuffle_step(self) -> None:
        """执行一次 Fisher-Yates 单步交换 + 手滑翻转 + 双翻。"""
        rng = self._get_rng()
        n = len(self._available)
        if n < 2:
            return

        i = rng.randbelow(n)
        j = rng.randbelow(n)
        self._available[i], self._available[j] = (
            self._available[j],
            self._available[i],
        )
        self.shuffle_count += 1

        # 手滑翻转
        if rng.randbool(self.hand_slip_prob):
            card = self._available[i]
            self.orientations[card.uid] = not self.orientations[card.uid]

        # 双翻
        if rng.randbool(self.double_flip_prob):
            card = self._available[j]
            self.orientations[card.uid] = not self.orientations[card.uid]

        self._shuffled = True

    def stop_shuffling(self) -> None:
        """停止持续洗牌模式。"""
        self._shuffle_stop.set()
        if self._shuffle_thread is not None and self._shuffle_thread.is_alive():
            self._shuffle_thread.join(timeout=1.0)
        self._shuffle_thread = None

    def draw(
        self,
        n: int,
        shuffle_times: int = 3,
        reverse_prob: float | None = None,
    ) -> List[Tuple[TarotCard, bool]]:
        if n < 0:
            raise ValueError("n must be non-negative")
        if n > len(self._available):
            raise ValueError(
                f"Not enough cards (requested {n}, available {len(self._available)})"
            )
        if reverse_prob is not None:
            self.reverse_prob = reverse_prob

        if not self._shuffled:
            self.shuffle(times=shuffle_times)

        drawn: List[Tuple[TarotCard, bool]] = []
        for _ in range(n):
            card = self._available.pop()
            reversed_flag = self.orientations.get(card.uid, False)
            drawn.append((card, reversed_flag))
        return drawn

    def get_card_by_uid(self, uid: int) -> TarotCard | None:
        for c in self._all_cards:
            if c.uid == uid:
                return c
        return None

    def __len__(self) -> int:
        return len(self._all_cards)
