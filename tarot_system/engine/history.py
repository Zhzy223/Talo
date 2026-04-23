import json
import pathlib
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import List, Dict, Any

from tarot_system.paths import user_data_dir


@dataclass
class DrawRecord:
    uid: int
    name: str
    reversed: bool
    position: str
    final_score: float
    top_dimensions: List[str]


@dataclass
class ReadingRecord:
    timestamp: str
    question: str
    spread_name: str
    draw_results: List[Dict[str, Any]]
    interpretation_text: str


class HistoryLogger:
    def __init__(self, history_path: pathlib.Path | None = None) -> None:
        if history_path is None:
            history_path = user_data_dir() / "history.jsonl"
        self._path = history_path
        self._ensure_file()

    def _ensure_file(self) -> None:
        if not self._path.exists():
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.touch()

    def log(
        self,
        question: str,
        spread_name: str,
        draw_results: List[DrawRecord],
        interpretation_text: str,
    ) -> None:
        record = ReadingRecord(
            timestamp=datetime.now().isoformat(),
            question=question,
            spread_name=spread_name,
            draw_results=[asdict(r) for r in draw_results],
            interpretation_text=interpretation_text,
        )
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record.__dict__, ensure_ascii=False) + "\n")

    def list_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        records: List[Dict[str, Any]] = []
        if not self._path.exists():
            return records
        with self._path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records[-limit:]

    def delete_at(self, index_from_end: int) -> bool:
        """删除从末尾数第 index_from_end 条记录（0=最后一条）。"""
        if not self._path.exists():
            return False
        lines: list[str] = []
        with self._path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    lines.append(line)
        if not lines or index_from_end >= len(lines):
            return False
        del lines[-(index_from_end + 1)]
        with self._path.open("w", encoding="utf-8") as f:
            f.writelines(lines)
        return True

    def get_statistics(self) -> Dict[str, int]:
        categories: Dict[str, int] = {
            "感情": 0,
            "事业": 0,
            "财富": 0,
            "学业": 0,
            "灵性": 0,
            "其他": 0,
        }
        keywords_map = {
            "感情": ["感情", "爱", "恋", "婚", "桃花", "关系", "分手", "复合"],
            "事业": ["事业", "工作", "职", "业", "升职", "跳槽", "创业", "项目"],
            "财富": ["财富", "钱", "财", "投资", "收入", "亏损", "生意", "经济"],
            "学业": ["学业", "学", "考", "试", "成绩", "录取", "论文", "毕业"],
            "灵性": ["灵性", "精神", "冥想", "觉醒", "灵魂", "信仰", "修行"],
        }
        for record in self.list_history(limit=1000):
            q = record.get("question", "")
            matched = False
            for cat, words in keywords_map.items():
                if any(w in q for w in words):
                    categories[cat] += 1
                    matched = True
                    break
            if not matched:
                categories["其他"] += 1
        return categories
