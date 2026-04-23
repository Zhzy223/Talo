import json
import os
import sys
from typing import Dict, Any, List

import requests


CORPORA_URL = "https://raw.githubusercontent.com/dariusk/corpora/master/data/divination/tarot_interpretations.json"


MAJOR_ARCANA_CN = {
	"The Fool": "愚者",
	"The Magician": "魔术师",
	"The High Priestess": "女祭司",
	"The Empress": "女皇",
	"The Emperor": "皇帝",
	"The Hierophant": "教皇",
	"The Lovers": "恋人",
	"The Chariot": "战车",
	"Strength": "力量",
	"The Hermit": "隐士",
	"Wheel of Fortune": "命运之轮",
	"Justice": "正义",
	"The Hanged Man": "倒吊人",
	"Death": "死神",
	"Temperance": "节制",
	"The Devil": "恶魔",
	"The Tower": "高塔",
	"The Star": "星星",
	"The Moon": "月亮",
	"The Sun": "太阳",
	"Judgement": "审判",
	"The World": "世界",
}


def ensure_dirs():
	root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
	data_dir = os.path.join(root, "data")
	os.makedirs(data_dir, exist_ok=True)
	return data_dir


def load_corpora() -> Dict[str, Any]:
	resp = requests.get(CORPORA_URL, timeout=30)
	resp.raise_for_status()
	return resp.json()


def normalize_cards(data: Dict[str, Any]) -> List[Dict[str, Any]]:
	# corpora layout
	cards = data.get("tarot_interpretations")
	if not cards:
		# fallback: try common key 'cards'
		cards = data.get("cards", [])
	normalized: List[Dict[str, Any]] = []
	for c in cards:
		name = c.get("name") or c.get("arcana") or ""
		mean = c.get("meanings", {})
		upright = mean.get("light") or mean.get("upright") or []
		reversed = mean.get("shadow") or mean.get("reversed") or []
		entry = {
			"name": name,
			"cn": MAJOR_ARCANA_CN.get(name, ""),
			"suit": c.get("suit"),
			"rank": c.get("rank"),
			"meanings": {
				"upright": upright,
				"reversed": reversed,
			},
		}
		normalized.append(entry)
	return normalized


def main() -> int:
	data_dir = ensure_dirs()
	print("Downloading tarot meanings ...")
	try:
		data = load_corpora()
	except Exception as e:
		print(f"下载牌义数据失败: {e}")
		return 1

	cards = normalize_cards(data)
	out_path = os.path.join(data_dir, "cards_en.json")
	with open(out_path, "w", encoding="utf-8") as f:
		json.dump(cards, f, ensure_ascii=False, indent=2)
	print(f"已生成 {out_path}，共 {len(cards)} 张卡。")
	return 0


if __name__ == "__main__":
	sys.exit(main())



