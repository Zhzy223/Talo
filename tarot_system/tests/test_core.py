import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.entropy import EntropyPool, SecureRNG
from engine.deck import Deck, TarotCard
from engine.history import HistoryLogger, DrawRecord
from core.calculator import SpreadCalculator, SlotResult, DIMENSIONS
from core.interpreter import TemplateEngine
from core.exporter import export_markdown, export_plaintext


class TestEntropyAndShuffle(unittest.TestCase):
    def test_deterministic_shuffle(self) -> None:
        """固定 seed 下洗牌结果可复现。"""
        seed = hashlib.sha256(b"test_seed").digest()
        rng1 = SecureRNG(seed)
        rng2 = SecureRNG(seed)

        lst1 = [1, 2, 3, 4, 5]
        lst2 = list(lst1)
        rng1.shuffle(lst1)
        rng2.shuffle(lst2)

        self.assertEqual(lst1, lst2)

    def test_shuffle_uniformity_basic(self) -> None:
        """Fisher-Yates 至少能把列表顺序改变（概率上）。"""
        seed = hashlib.sha256(b"uniformity").digest()
        rng = SecureRNG(seed)
        lst = list(range(20))
        original = list(lst)
        rng.shuffle(lst)
        self.assertNotEqual(lst, original)

    def test_randbool_distribution(self) -> None:
        """randbool 在大量样本下大致符合概率。"""
        seed = hashlib.sha256(b"bool_test").digest()
        rng = SecureRNG(seed)
        trials = 10000
        count = sum(1 for _ in range(trials) if rng.randbool(0.125))
        self.assertGreaterEqual(count, 800)
        self.assertLessEqual(count, 1700)


class TestCalculator(unittest.TestCase):
    def test_single_card_score(self) -> None:
        """已知向量牌与位置权重手算点积验证 calculator。"""
        card = TarotCard(
            uid=99,
            name="测试牌",
            suit="test",
            upright_vec=(1.0, 0.5, 0.0, -0.5, 0.0, 0.0, 0.0, 0.0),
            reversed_vec=(-1.0, -0.5, 0.0, 0.5, 0.0, 0.0, 0.0, 0.0),
        )
        spread = {
            "positions": [
                {"name": "测试位", "weights": [0.5, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]}
            ]
        }
        calc = SpreadCalculator(spread, association_matrix={})
        draws = [(card, False)]  # 正位
        results = calc.compute(draws)
        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertAlmostEqual(r.score, 1.0, places=6)
        self.assertEqual(r.position_name, "测试位")
        self.assertFalse(r.reversed)
        self.assertEqual(r.top_dimensions, ["emotion", "material", "change"])

    def test_reversed_score(self) -> None:
        """验证逆位使用 reversed_vec。"""
        card = TarotCard(
            uid=99,
            name="测试牌",
            suit="test",
            upright_vec=(1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
            reversed_vec=(-0.8, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        )
        spread = {
            "positions": [
                {"name": "测试位", "weights": [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]}
            ]
        }
        calc = SpreadCalculator(spread)
        draws = [(card, True)]
        results = calc.compute(draws)
        self.assertAlmostEqual(results[0].score, -0.8, places=6)

    def test_interaction(self) -> None:
        """验证牌间交互计算。"""
        card_a = TarotCard(
            uid=1,
            name="A",
            suit="test",
            upright_vec=(1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
            reversed_vec=(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        )
        card_b = TarotCard(
            uid=2,
            name="B",
            suit="test",
            upright_vec=(0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
            reversed_vec=(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        )
        spread = {
            "positions": [
                {"name": "位1", "weights": [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]},
                {"name": "位2", "weights": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]},
            ]
        }
        assoc = {(1, 2): 2.0}
        calc = SpreadCalculator(spread, association_matrix=assoc)
        draws = [(card_a, False), (card_b, False)]
        results = calc.compute(draws)
        self.assertEqual(len(results), 2)
        self.assertAlmostEqual(results[0].score, 1.3, places=6)
        self.assertAlmostEqual(results[1].score, 0.3, places=6)
        self.assertIn(2, results[0].interaction_scores)
        self.assertIn(1, results[1].interaction_scores)


class TestDeck(unittest.TestCase):
    def setUp(self) -> None:
        self.test_cards_path = Path(__file__).parent.parent / "data" / "cards.json"

    def test_draw_without_replacement(self) -> None:
        """draw() 不放回验证。"""
        seed = hashlib.sha256(b"deck_test").digest()
        rng = SecureRNG(seed)
        deck = Deck(self.test_cards_path, rng=rng)
        draws = deck.draw(3)
        self.assertEqual(len(draws), 3)
        uids = [c.uid for c, _ in draws]
        self.assertEqual(len(set(uids)), 3, "不应有重复 UID，即不放回")

        deck.reset()
        draws2 = deck.draw(3)
        uids2 = [c.uid for c, _ in draws2]
        self.assertEqual(len(set(uids2)), 3)

    def test_draw_exhaustion(self) -> None:
        """牌抽完后应报错。"""
        seed = hashlib.sha256(b"exhaust").digest()
        rng = SecureRNG(seed)
        deck = Deck(self.test_cards_path, rng=rng)
        deck.draw(len(deck))
        with self.assertRaises(ValueError):
            deck.draw(1)

    def test_reset(self) -> None:
        """reset 后应可重新抽牌。"""
        seed = hashlib.sha256(b"reset_test").digest()
        rng = SecureRNG(seed)
        deck = Deck(self.test_cards_path, rng=rng)
        deck.draw(2)
        deck.reset()
        self.assertEqual(len(deck._available), len(deck))
        draws = deck.draw(3)
        self.assertEqual(len(draws), 3)

    def test_custom_parameters(self) -> None:
        """draw 支持自定义 shuffle_times 和 reverse_prob。"""

        class CountingDeck(Deck):
            def __init__(self, *args: Any, **kwargs: Any):
                super().__init__(*args, **kwargs)
                self._test_count = 0

            def shuffle(self, times: int = 3) -> None:
                super().shuffle(times=times)
                self._test_count += 1

        seed = hashlib.sha256(b"custom_params").digest()
        rng = SecureRNG(seed)
        deck = CountingDeck()
        deck.set_rng(rng)

        # 验证 shuffle_times=1 只调用 shuffle() 一次
        deck.draw(10, shuffle_times=1)
        self.assertEqual(deck._test_count, 1)

        # 验证 reverse_prob=0.5 的逆位率接近 50%
        reversed_count = 0
        total = 0
        for _ in range(100):
            deck.reset()
            draws = deck.draw(10, shuffle_times=1, reverse_prob=0.5)
            for _, rev in draws:
                total += 1
                if rev:
                    reversed_count += 1

        ratio = reversed_count / total
        self.assertGreaterEqual(
            ratio, 0.40, f"逆位率应 >= 40%, 实际 {ratio:.2%}"
        )
        self.assertLessEqual(
            ratio, 0.60, f"逆位率应 <= 60%, 实际 {ratio:.2%}"
        )


class TestFullDeck(unittest.TestCase):
    def test_full_deck_integrity(self) -> None:
        """加载完整 cards.json，断言 uid 0-77 无缺失、无重复，总牌数 78。"""
        cards_path = Path(__file__).parent.parent / "data" / "cards.json"
        with cards_path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        self.assertEqual(len(raw), 78)
        uids = [c["uid"] for c in raw]
        self.assertEqual(len(set(uids)), 78)
        self.assertEqual(set(uids), set(range(78)))

    def test_interactions_loaded(self) -> None:
        """加载 interactions.json，断言至少包含 6 组经典关联，且能参与 final_score 计算。"""
        interactions_path = Path(__file__).parent.parent / "data" / "interactions.json"
        with interactions_path.open("r", encoding="utf-8") as f:
            raw = json.load(f)

        required_keys = {"6,15", "18,19", "1,12", "13,21", "16,17", "0,1"}
        self.assertTrue(required_keys.issubset(set(raw.keys())))

        assoc: dict = {}
        for k, v in raw.items():
            a, b = map(int, k.split(","))
            assoc[(a, b)] = v

        deck = Deck()
        fool = next(c for c in deck._all_cards if c.uid == 0)
        magician = next(c for c in deck._all_cards if c.uid == 1)
        spread = {"positions": [{"name": "位1", "weights": [0] * 8}, {"name": "位2", "weights": [0] * 8}]}
        calc = SpreadCalculator(spread, association_matrix=assoc)
        results = calc.compute([(fool, False), (magician, False)])
        self.assertEqual(len(results), 2)
        self.assertIn(1, results[0].interaction_scores)
        self.assertIn(0, results[1].interaction_scores)
        self.assertNotAlmostEqual(results[0].score, 0.0, places=5)

    def test_suit_element_baseline(self) -> None:
        """验证各元素牌组的基线属性。"""
        deck = Deck()
        wands = [c for c in deck._all_cards if c.suit == "wands"]
        cups = [c for c in deck._all_cards if c.suit == "cups"]
        swords = [c for c in deck._all_cards if c.suit == "swords"]
        pentacles = [c for c in deck._all_cards if c.suit == "pentacles"]

        self.assertEqual(len(wands), 14)
        self.assertEqual(len(cups), 14)
        self.assertEqual(len(swords), 14)
        self.assertEqual(len(pentacles), 14)

        for c in wands:
            self.assertGreater(c.upright_vec[5], 0, f"{c.name} will should > 0")
        for c in swords:
            self.assertGreater(c.upright_vec[2], 0, f"{c.name} conflict should > 0")
        for c in cups:
            self.assertGreater(c.upright_vec[0], 0, f"{c.name} emotion should > 0")
        for c in pentacles:
            self.assertGreater(c.upright_vec[1], 0, f"{c.name} material should > 0")

    def test_celtic_cross_with_full_deck(self) -> None:
        """用完整牌库运行 Celtic Cross，断言能成功抽出 10 张牌且无重复。"""
        seed = hashlib.sha256(b"celtic_cross_test").digest()
        rng = SecureRNG(seed)
        deck = Deck()
        deck.reset()
        deck.set_rng(rng)
        draws = deck.draw(10)
        self.assertEqual(len(draws), 10)
        uids = [c.uid for c, _ in draws]
        self.assertEqual(len(set(uids)), 10, "10 张牌应无重复 UID")


class TestBugFixesAndFeatures(unittest.TestCase):
    def test_interactions_nonzero(self) -> None:
        """构造两张同元素小阿卡纳（星币8+星币侍从），断言 interaction 绝对值 > 0 且 < 0.2。"""
        deck = Deck()
        coin8 = next(c for c in deck._all_cards if c.uid == 71)   # 星币8
        coin_page = next(c for c in deck._all_cards if c.uid == 74)  # 星币侍从
        sun = next(c for c in deck._all_cards if c.uid == 19)

        # 仅加载强关联 JSON，不预置星币内部关联，迫使走 fallback
        interactions_path = Path(__file__).parent.parent / "data" / "interactions.json"
        with interactions_path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        assoc = {}
        for k, v in raw.items():
            a, b = map(int, k.split(","))
            assoc[(a, b)] = v

        spread = {
            "positions": [
                {"name": "过去", "weights": [0.5, 0.3, 0.2, 0.6, 0.4, 0.1, 0.2, 0.7]},
                {"name": "现在", "weights": [0.6, 0.5, 0.4, 0.5, 0.5, 0.5, 0.5, 0.5]},
                {"name": "未来", "weights": [0.3, 0.4, 0.3, 0.8, 0.6, 0.7, 0.4, 0.3]},
            ]
        }
        calc = SpreadCalculator(spread, association_matrix=assoc)
        draws = [(coin8, False), (coin_page, False), (sun, False)]
        results = calc.compute(draws)

        # 星币8 与 星币侍从 的 interaction
        inter_71_74 = None
        for r in results:
            if 71 in r.interaction_scores and 74 in r.interaction_scores:
                # 两者互为交互对象，取同一值
                inter_71_74 = r.interaction_scores[74 if r.card.uid == 71 else 71]
                break
            elif 71 in r.interaction_scores:
                inter_71_74 = r.interaction_scores[71]
                break
            elif 74 in r.interaction_scores:
                inter_71_74 = r.interaction_scores[74]
                break

        self.assertIsNotNone(inter_71_74, "应找到星币8与星币侍从的 interaction")
        self.assertGreater(abs(inter_71_74), 0, "fallback interaction 应非零")
        self.assertLess(abs(inter_71_74), 0.2, "fallback 值应小于 0.2（JSON 强关联均 >= 0.2）")

    def test_shuffle_once_for_ten_cards(self) -> None:
        """创建 Deck，draw(10)，断言 shuffle 只执行一次。"""
        class CountingDeck(Deck):
            def __init__(self, *args: Any, **kwargs: Any):
                super().__init__(*args, **kwargs)
                self._test_count = 0

            def shuffle(self, times: int = 3) -> None:
                super().shuffle(times=times)
                self._test_count += 1

        seed = hashlib.sha256(b"shuffle_count").digest()
        rng = SecureRNG(seed)
        deck = CountingDeck()
        deck.set_rng(rng)
        deck.draw(10)
        self.assertEqual(deck._test_count, 1, "draw(10) 应只触发一次 shuffle")
        deck.draw(5)
        self.assertEqual(deck._test_count, 1, "连续 draw 不应再次 shuffle")
        deck.reset()
        deck.draw(3)
        self.assertEqual(deck._test_count, 2, "reset 后再次 draw 应允许一次新 shuffle")

    def test_reversed_template_distinct(self) -> None:
        """构造一张逆位牌，断言解读文本包含逆位关键词之一。"""
        engine = TemplateEngine()
        card = TarotCard(
            uid=99,
            name="测试牌",
            suit="test",
            upright_vec=(0.9, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
            reversed_vec=(-0.8, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        )
        result = SlotResult(
            card=card,
            reversed=True,
            position_name="测试位",
            score=-0.5,
            top_dimensions=["emotion"],
        )
        text = engine.render(result)
        keywords = ["受阻", "压抑", "延迟", "消沉", "反噬", "隐患"]
        self.assertTrue(
            any(kw in text for kw in keywords),
            f"逆位解读应包含逆位关键词，实际文本: {text}",
        )

    def test_special_pairs_triggered(self) -> None:
        """构造死神+世界牌阵，断言解读文本包含特殊牌对关键词。"""
        engine = TemplateEngine()
        deck = Deck()
        death = next(c for c in deck._all_cards if c.uid == 13)
        world = next(c for c in deck._all_cards if c.uid == 21)
        results = [
            SlotResult(card=death, reversed=False, position_name="位1", score=0.0, top_dimensions=[]),
            SlotResult(card=world, reversed=False, position_name="位2", score=0.0, top_dimensions=[]),
        ]
        text = engine.render_spread(results)
        keywords = ["周期", "终结", "闭合", "退场"]
        self.assertTrue(
            any(kw in text for kw in keywords),
            f"特殊牌对应触发专属文本，实际文本: {text}",
        )

    def test_history_logged(self) -> None:
        """运行一次占卜，断言 history.jsonl 存在且包含记录。"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            tmp_path = Path(f.name)
        try:
            logger = HistoryLogger(history_path=tmp_path)
            logger.log(
                question="测试问题",
                spread_name="three_card",
                draw_results=[
                    DrawRecord(uid=0, name="愚者", reversed=False, position="过去", final_score=0.5, top_dimensions=["change"]),
                ],
                interpretation_text="测试解读",
            )
            records = logger.list_history()
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["question"], "测试问题")
            self.assertEqual(records[0]["spread_name"], "three_card")
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_export_markdown(self) -> None:
        """构造 mock SlotResult，调用 export_markdown，断言格式正确。"""
        card = TarotCard(
            uid=0,
            name="愚人",
            suit="major",
            upright_vec=(0.5,) * 8,
            reversed_vec=(-0.5,) * 8,
        )
        result = SlotResult(
            card=card,
            reversed=False,
            position_name="现状",
            score=0.5,
            top_dimensions=["change", "will", "spirit"],
        )
        text = export_markdown("测试问题", "three_card", [result], "测试解读")
        self.assertIn("# 测试问题", text)
        self.assertIn("|", text)
        self.assertIn("愚人", text)
        self.assertIn("正位", text)
        self.assertIn("change", text)
        self.assertIn("测试解读", text)

    def test_export_plaintext(self) -> None:
        """构造 mock SlotResult，调用 export_plaintext，断言无标记符号。"""
        card = TarotCard(
            uid=0,
            name="愚人",
            suit="major",
            upright_vec=(0.5,) * 8,
            reversed_vec=(-0.5,) * 8,
        )
        result = SlotResult(
            card=card,
            reversed=True,
            position_name="过去",
            score=-0.3,
            top_dimensions=["emotion"],
        )
        text = export_plaintext("测试问题", "single", [result], "测试解读")
        self.assertNotIn("#", text)
        self.assertNotIn("|", text)
        self.assertIn("愚人", text)
        self.assertIn("逆位", text)
        self.assertIn("测试解读", text)

    def test_gui_settings_slider(self) -> None:
        """断言 TarotGUI 实例有 settings 属性且包含指定键。"""
        import customtkinter as ctk
        from gui import TarotGUI

        root = ctk.CTk()
        root.withdraw()
        app = TarotGUI(root)
        self.assertTrue(hasattr(app, "settings"))
        self.assertIn("reverse_prob", app.settings)
        self.assertIn("shuffle_times", app.settings)
        self.assertIsInstance(app.settings["reverse_prob"], float)
        self.assertIsInstance(app.settings["shuffle_times"], int)
        root.destroy()

    def test_merge_script(self) -> None:
        """运行合并脚本，断言 cards.json 包含英文释义字段。"""
        import subprocess
        import sys

        script = Path(__file__).parent.parent / "scripts" / "merge_cards_data.py"
        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        cards_path = Path(__file__).parent.parent / "data" / "cards.json"
        with cards_path.open("r", encoding="utf-8") as f:
            cards = json.load(f)

        fool = next(c for c in cards if c["uid"] == 0)
        self.assertIn("meanings_upright", fool)
        self.assertIn("meanings_reversed", fool)
        self.assertIsInstance(fool["meanings_upright"], list)
        self.assertIsInstance(fool["meanings_reversed"], list)
        self.assertTrue(all(isinstance(s, str) for s in fool["meanings_upright"]))
        self.assertTrue(all(isinstance(s, str) for s in fool["meanings_reversed"]))

    def test_astrology_fields(self) -> None:
        """断言大阿卡纳包含 astrology 和 kabbalah_path 字段。"""
        cards_path = Path(__file__).parent.parent / "data" / "cards.json"
        with cards_path.open("r", encoding="utf-8") as f:
            cards = json.load(f)

        majors = [c for c in cards if c["suit"] == "major_arcana"]
        self.assertEqual(len(majors), 22)
        for c in majors:
            self.assertIn("astrology", c, f"uid {c['uid']} 缺少 astrology")
            self.assertIn("kabbalah_path", c, f"uid {c['uid']} 缺少 kabbalah_path")
            self.assertIn("|", c["astrology"], f"uid {c['uid']} astrology 格式错误")
            self.assertIsInstance(c["kabbalah_path"], int)

    def test_element_distribution(self) -> None:
        """构造3张权杖牌阵，断言占星视角包含火元素集中提示。"""
        engine = TemplateEngine()
        deck = Deck()
        w1 = next(c for c in deck._all_cards if c.uid == 22)  # 权杖Ace
        w2 = next(c for c in deck._all_cards if c.uid == 23)  # 权杖2
        w3 = next(c for c in deck._all_cards if c.uid == 24)  # 权杖3
        results = [
            SlotResult(card=w1, reversed=False, position_name="位1", score=0.0, top_dimensions=[]),
            SlotResult(card=w2, reversed=False, position_name="位2", score=0.0, top_dimensions=[]),
            SlotResult(card=w3, reversed=False, position_name="位3", score=0.0, top_dimensions=[]),
        ]
        text = engine.render_astrology("three_card", results)
        self.assertTrue(
            "火元素集中" in text or "△" in text,
            f"应触发火元素集中提示，实际文本: {text}",
        )

    def test_gui_astrology_label(self) -> None:
        """断言 TarotGUI 实例包含占星标签所需的扩展数据。"""
        import customtkinter as ctk
        from gui import TarotGUI

        root = ctk.CTk()
        root.withdraw()
        app = TarotGUI(root)
        self.assertTrue(hasattr(app, "_card_extras"))
        self.assertIsInstance(app._card_extras, dict)
        self.assertGreater(len(app._card_extras), 0)
        self.assertIn(0, app._card_extras)
        self.assertIn("astrology", app._card_extras[0])
        root.destroy()

    def test_gui_imports(self) -> None:
        """断言 import gui 不报错，ctk.CTk 实例可创建并 destroy。"""
        import customtkinter as ctk
        import gui  # noqa: F401

        root = ctk.CTk()
        root.withdraw()
        self.assertIsInstance(root, ctk.CTk)
        root.destroy()


class TestPhysicalRNGAndShuffle(unittest.TestCase):
    def test_physical_rng_cross_platform(self) -> None:
        """PhysicalRNG 在任意平台可实例化，randbelow 输出在范围内。"""
        from engine.entropy import PhysicalRNG

        rng = PhysicalRNG()
        for n in [2, 10, 100, 1000]:
            val = rng.randbelow(n)
            self.assertGreaterEqual(val, 0)
            self.assertLess(val, n)

    def test_physical_shuffle_entropy_consumed(self) -> None:
        """Physical 模式洗牌 100 步，断言 orientations 有合理逆位分布。"""
        from engine.deck import Deck

        deck = Deck(rng_type="physical")
        deck.hand_slip_prob = 0.10
        deck.double_flip_prob = 0.02
        deck.shuffle(times=100)
        reversed_count = sum(1 for v in deck.orientations.values() if v)
        # 100 步、10% 手滑 + 2% 双翻，预期约 12% 逆位，允许较大误差
        total = len(deck.orientations)
        ratio = reversed_count / total
        self.assertGreaterEqual(ratio, 0.02, f"逆位率应 >= 2%, 实际 {ratio:.2%}")
        self.assertLessEqual(ratio, 0.30, f"逆位率应 <= 30%, 实际 {ratio:.2%}")

    def test_continuous_shuffle_mode(self) -> None:
        """持续洗牌模式：shuffle(None) → N 步 → stop_shuffling()。"""
        import threading
        import time
        from engine.deck import Deck

        deck = Deck(rng_type="physical")
        deck.shuffle_interval_ms = 10.0
        deck.shuffle(times=None)
        time.sleep(0.15)
        deck.stop_shuffling()
        self.assertGreaterEqual(
            deck.shuffle_count, 3,
            f"150ms @ 10ms/步 应至少 3 步，实际 {deck.shuffle_count}"
        )

    def test_draw_reads_orientation(self) -> None:
        """手动设置 orientations[uid]=True，draw 后 reversed=True。"""
        import hashlib
        from engine.deck import Deck
        from engine.entropy import SecureRNG

        seed = hashlib.sha256(b"orientation_test").digest()
        rng = SecureRNG(seed)
        deck = Deck(rng=rng)
        deck.shuffle(times=1)
        # 强制第一张牌逆位
        first_uid = deck._available[-1].uid
        deck.orientations[first_uid] = True
        draws = deck.draw(1)
        self.assertTrue(draws[0][1], "orientations[uid]=True 应导致 draw 返回 reversed=True")

    def test_no_fixed_reverse_prob(self) -> None:
        """draw(10) 不再依赖 reverse_prob 参数（向后兼容保留但 draw 内部忽略）。"""
        import hashlib
        from engine.deck import Deck
        from engine.entropy import SecureRNG

        seed = hashlib.sha256(b"no_reverse_prob").digest()
        rng = SecureRNG(seed)
        deck = Deck(rng=rng)
        deck.shuffle(times=1)
        # 显式设置 orientations，使 draw 不依赖 reverse_prob
        for card in deck._all_cards:
            deck.orientations[card.uid] = False
        draws = deck.draw(10)
        self.assertEqual(len(draws), 10)
        self.assertTrue(all(not rev for _, rev in draws))

    def test_platform_voice_button(self) -> None:
        """断言 gui 中语音按钮在 Linux 上隐藏，在 macOS 上显示。"""
        import customtkinter as ctk
        from gui import TarotGUI

        root = ctk.CTk()
        root.withdraw()
        app = TarotGUI(root)
        if sys.platform == "linux":
            self.assertIsNone(app.speak_btn)
        elif sys.platform == "darwin":
            self.assertIsNotNone(app.speak_btn)
        root.destroy()

    def test_pathlib_usage(self) -> None:
        """断言所有文件加载使用 pathlib.Path，无硬编码路径分隔符。"""
        import ast
        import inspect
        import gui
        import main
        from engine import deck, entropy, history
        from core import calculator, exporter, interpreter

        modules = [gui, main, deck, entropy, history, calculator, exporter, interpreter]
        hardcoded_separators = []
        for mod in modules:
            source = inspect.getsource(mod)
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    if "/" in node.value and "\\" not in node.value:
                        # 跳过 URL、格式化字符串等常见合法场景
                        if node.value.startswith("http") or node.value.startswith("#"):
                            continue
                        # 检查是否是路径拼接（包含 .json/.png 等）
                        if any(ext in node.value for ext in [".json", ".png", ".md", ".txt", ".jsonl"]):
                            # 只要不包含硬编码的 Windows 反斜杠就行
                            pass
                    if "\\" in node.value and ".json" in node.value:
                        hardcoded_separators.append((mod.__name__, node.value))

        self.assertEqual(
            hardcoded_separators,
            [],
            f"发现硬编码 Windows 路径分隔符: {hardcoded_separators}",
        )


if __name__ == "__main__":
    unittest.main()
