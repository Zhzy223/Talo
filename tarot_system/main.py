import argparse
import json
import pathlib
import threading
import time
from typing import Dict, Any, List, Tuple

from engine.entropy import EntropyPool, SecureRNG
from engine.deck import Deck
from engine.history import HistoryLogger, DrawRecord
from core.calculator import SpreadCalculator, SlotResult
from core.interpreter import TemplateEngine
from tarot_system.paths import resource_path


DATA_DIR = resource_path("data")


def load_spread(name: str) -> Dict[str, Any]:
    path = resource_path("data/spreads.json")
    with path.open("r", encoding="utf-8") as f:
        spreads = json.load(f)
    return spreads[name]


def load_interactions() -> Dict[Tuple[int, int], float]:
    path = resource_path("data/interactions.json")
    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    result: Dict[Tuple[int, int], float] = {}
    for k, v in raw.items():
        a_str, b_str = k.split(",")
        a, b = int(a_str.strip()), int(b_str.strip())
        result[(a, b)] = v
    return result


def collect_timings() -> List[int]:
    print("请按回车键3次以收集随机熵（每次间隔尽量不同）...")
    timings: List[int] = []
    last = time.perf_counter_ns()
    for i in range(3):
        input(f"  第 {i + 1} 次按回车...")
        now = time.perf_counter_ns()
        timings.append(now - last)
        last = now
    return timings


def _interactive_shuffle(deck: Deck) -> Tuple[int, int]:
    """CLI 交互式持续洗牌。返回 (duration_ms, shuffle_count)。"""
    print("按回车开始洗牌，再次按回车停止（洗得越久，逆位越多）...")
    input("  [准备就绪，按回车开始]...")

    stop_event = threading.Event()

    def _loop():
        while not stop_event.is_set():
            deck._shuffle_step()  # noqa: SLF001
            stop_event.wait(deck.shuffle_interval_ms / 1000.0)

    thread = threading.Thread(target=_loop, daemon=True)
    thread.start()
    start = time.perf_counter_ns()
    input("  [正在洗牌... 再次按回车停止]...")
    stop_event.set()
    thread.join(timeout=1.0)

    duration_ms = int((time.perf_counter_ns() - start) / 1_000_000)

    # 零间隔保底 3 次交换
    while deck.shuffle_count < 3:
        deck._shuffle_step()  # noqa: SLF001

    return duration_ms, deck.shuffle_count


def _prepare_reading(
    question: str,
    deck: Deck,
    deterministic: bool = False,
    use_physical: bool = False,
) -> None:
    """准备占卜：收集熵、交互式洗牌、设置 RNG。"""
    pool = EntropyPool(question, deterministic=deterministic)
    if not deterministic:
        for t in collect_timings():
            pool.add_timing(t)

    deck.reset()
    duration_ms, shuffle_count = _interactive_shuffle(deck)

    if use_physical:
        pool.collect(
            use_physical=True,
            shuffle_duration_ms=duration_ms,
            shuffle_count=shuffle_count,
        )
    else:
        pool.collect(shuffle_duration_ms=duration_ms, shuffle_count=shuffle_count)

    rng = SecureRNG(pool.get_seed())
    deck.set_rng(rng)


def run_single(
    question: str,
    deck: Deck,
    assoc: Dict[Tuple[int, int], float] | None = None,
    deterministic: bool = False,
    use_physical: bool = False,
) -> List[SlotResult]:
    _prepare_reading(question, deck, deterministic, use_physical)
    draws = deck.draw(1)
    spread = {
        "positions": [
            {
                "name": "启示",
                "weights": [0.125] * 8,
            }
        ]
    }
    calc = SpreadCalculator(spread, association_matrix=assoc)
    return calc.compute(draws)


def run_spread(
    spread_name: str,
    question: str,
    deck: Deck,
    assoc: Dict[Tuple[int, int], float] | None = None,
    deterministic: bool = False,
    use_physical: bool = False,
) -> List[SlotResult]:
    _prepare_reading(question, deck, deterministic, use_physical)
    spread = load_spread(spread_name)
    n = len(spread["positions"])
    if n > len(deck):
        raise ValueError(
            f"牌阵需要 {n} 张牌，但牌库仅有 {len(deck)} 张。"
        )
    draws = deck.draw(n)
    calc = SpreadCalculator(spread, association_matrix=assoc)
    return calc.compute(draws)


def _save_reading(
    logger: HistoryLogger,
    question: str,
    spread_name: str,
    results: List[SlotResult],
    interpretation: str,
) -> None:
    draw_records = [
        DrawRecord(
            uid=r.card.uid,
            name=r.card.name,
            reversed=r.reversed,
            position=r.position_name,
            final_score=r.score,
            top_dimensions=r.top_dimensions,
        )
        for r in results
    ]
    logger.log(question, spread_name, draw_records, interpretation)
    print("\n[本次占卜已保存到历史记录]\n")


def _show_history(logger: HistoryLogger) -> None:
    records = logger.list_history(limit=10)
    if not records:
        print("暂无历史记录。")
        return
    print("\n" + "=" * 40)
    print("  最近占卜记录")
    print("=" * 40)
    for idx, rec in enumerate(records, 1):
        print(f"{idx}. [{rec['timestamp'][:19]}] {rec['spread_name']}")
        print(f"   问题: {rec['question']}")
        cards = ", ".join(
            f"{d['name']}{'(逆)' if d['reversed'] else ''}"
            for d in rec["draw_results"]
        )
        print(f"   牌面: {cards}")
        print()


def _show_statistics(logger: HistoryLogger) -> None:
    stats = logger.get_statistics()
    print("\n" + "=" * 40)
    print("  占卜主题统计")
    print("=" * 40)
    for cat, count in stats.items():
        print(f"  {cat}: {count} 次")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="塔罗牌占卜系统")
    parser.add_argument(
        "--rng",
        choices=["csprng", "physical"],
        default="csprng",
        help="随机数生成器类型 (默认: csprng)",
    )
    args = parser.parse_args()

    use_physical = args.rng == "physical"
    logger = HistoryLogger()

    while True:
        print("=" * 40)
        print("  塔罗牌占卜系统")
        print("=" * 40)
        print("1. 单张牌")
        print("2. 三张牌阵（过去/现在/未来）")
        print("3. 凯尔特十字（10张）")
        print("4. 查看历史")
        print("5. 统计信息")
        print("0. 退出")
        choice = input("请选择 [0/1/2/3/4/5]: ").strip()

        if choice == "0":
            print("再见。")
            break

        if choice == "4":
            _show_history(logger)
            continue

        if choice == "5":
            _show_statistics(logger)
            continue

        question = input("请输入你的问题: ").strip()
        if not question:
            print("问题不能为空。")
            continue

        deck = Deck(rng_type="physical" if use_physical else "csprng")
        assoc = load_interactions()

        try:
            if choice == "1":
                spread_name = "single"
                results = run_single(
                    question, deck, assoc, use_physical=use_physical
                )
            elif choice == "2":
                spread_name = "three_card"
                results = run_spread(
                    "three_card", question, deck, assoc, use_physical=use_physical
                )
            elif choice == "3":
                if len(deck) < 10:
                    print("当前牌库仅支持单张/三张牌阵，请先补全牌库。")
                    continue
                spread_name = "celtic_cross"
                results = run_spread(
                    "celtic_cross", question, deck, assoc, use_physical=use_physical
                )
            else:
                print("无效选择。")
                continue
        except ValueError as e:
            print(f"错误: {e}")
            continue

        engine = TemplateEngine()
        interpretation = engine.render_spread(results)
        print("\n" + "=" * 40)
        print("  解读结果")
        print("=" * 40)
        print(interpretation)

        save = input("是否保存本次占卜记录？[y/N]: ").strip().lower()
        if save == "y":
            _save_reading(logger, question, spread_name, results, interpretation)


if __name__ == "__main__":
    main()
