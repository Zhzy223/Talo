#!/usr/bin/env python3
"""合并英文牌义数据并扩展字段到 cards.json。"""
import json
from pathlib import Path


def _suit_to_uid_base(suit: str) -> int:
    return {
        "wands": 22,
        "cups": 36,
        "swords": 50,
        "pentacles": 64,
        "coins": 64,
    }[suit]


COURT_RANKS = {
    "page": 11,
    "knight": 12,
    "queen": 13,
    "king": 14,
}


MAJOR_ELEMENTS = {
    0: "air",
    1: "air",
    2: "water",
    3: "earth",
    4: "fire",
    5: "earth",
    6: "air",
    7: "water",
    8: "fire",
    9: "earth",
    10: "fire",
    11: "air",
    12: "water",
    13: "water",
    14: "fire",
    15: "earth",
    16: "fire",
    17: "air",
    18: "water",
    19: "fire",
    20: "fire",
    21: "earth",
}

MAJOR_ASTROLOGY = {
    0: "天王星|Uranus|♅",
    1: "水星|Mercury|☿",
    2: "月亮|Moon|☽",
    3: "金星|Venus|♀",
    4: "白羊座|Aries|♈",
    5: "金牛座|Taurus|♉",
    6: "双子座|Gemini|♊",
    7: "巨蟹座|Cancer|♋",
    8: "狮子座|Leo|♌",
    9: "处女座|Virgo|♍",
    10: "木星|Jupiter|♃",
    11: "天秤座|Libra|♎",
    12: "海王星|Neptune|♆",
    13: "天蝎座|Scorpio|♏",
    14: "射手座|Sagittarius|♐",
    15: "摩羯座|Capricorn|♑",
    16: "火星|Mars|♂",
    17: "水瓶座|Aquarius|♒",
    18: "双鱼座|Pisces|♓",
    19: "太阳|Sun|☉",
    20: "冥王星|Pluto|♇",
    21: "土星|Saturn|♄",
}

SUIT_ELEMENTS = {
    "wands": "fire",
    "cups": "water",
    "swords": "air",
    "pentacles": "earth",
}


def main() -> None:
    base = Path(__file__).parent.parent
    cards_path = base / "data" / "cards.json"
    cards_en_path = base.parent / "data" / "cards_en.json"

    with cards_path.open("r", encoding="utf-8") as f:
        cards: list[dict] = json.load(f)

    with cards_en_path.open("r", encoding="utf-8") as f:
        cards_en: list[dict] = json.load(f)

    # 建立 cards_en 的查找表：uid -> en_record
    en_by_uid: dict[int, dict] = {}
    for rec in cards_en:
        suit = rec["suit"]
        rank_raw = rec["rank"]
        if suit == "major":
            uid = int(rank_raw)
        else:
            if isinstance(rank_raw, str):
                rank = COURT_RANKS[rank_raw]
            else:
                rank = int(rank_raw)
            uid = _suit_to_uid_base(suit) + (rank - 1)
        en_by_uid[uid] = rec

    # 扩展每张牌
    for card in cards:
        uid = card["uid"]
        en = en_by_uid.get(uid)
        if en is None:
            raise ValueError(f"uid {uid} 在 cards_en.json 中找不到对应记录")

        meanings = en.get("meanings", {})
        card["meanings_upright"] = meanings.get("upright", [])
        card["meanings_reversed"] = meanings.get("reversed", [])

        if card["suit"] == "major_arcana":
            card["element"] = MAJOR_ELEMENTS[uid]
            card["astrology"] = MAJOR_ASTROLOGY[uid]
            card["kabbalah_path"] = uid + 11
        else:
            card["element"] = SUIT_ELEMENTS[card["suit"]]

    with cards_path.open("w", encoding="utf-8") as f:
        json.dump(cards, f, ensure_ascii=False, indent=2)

    print(f"✅ 已合并并扩展 {len(cards)} 张牌到 {cards_path}")


if __name__ == "__main__":
    main()
