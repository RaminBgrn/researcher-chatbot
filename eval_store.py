"""ذخیره دائمی نوبت‌های گفتگو برای ارزیابی آنلاین (Online Eval).

هر نوبت چت یک رکورد است: سؤال، ابزارهای صدا زده‌شده، دلیل پایان، توکن‌ها،
این‌که گزارش ذخیره شد یا نه و فیدبک کاربر. رکوردها در یک فایل JSON کنار
پروژه نگه داشته می‌شوند تا با ری‌استارت سرور از بین نروند و خلاصه نرخ‌ها
(همان معیارهای درس Eval) از رویشان حساب شود.
"""

import json
import os
from datetime import datetime

_DEFAULT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "eval_log.json")


def _path(path=None) -> str:
    return path or os.environ.get("EVAL_LOG_PATH") or _DEFAULT_PATH


def load_records(path=None) -> list:
    file_path = _path(path)
    if not os.path.exists(file_path):
        return []
    try:
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save(records, path=None):
    with open(_path(path), "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=1)


def append_record(record: dict, path=None) -> dict:
    """یک نوبت را به لاگ اضافه می‌کند و همان رکورد کامل‌شده را برمی‌گرداند."""
    records = load_records(path)
    record = dict(record)
    record.setdefault("time", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    record.setdefault("feedback", None)
    records.append(record)
    _save(records, path)
    return record


def set_feedback(turn_id: str, rating: str, path=None) -> bool:
    """فیدبک کاربر (up/down) را روی رکورد همان نوبت می‌نشاند."""
    if rating not in ("up", "down"):
        return False
    records = load_records(path)
    for record in records:
        if record.get("id") == turn_id:
            record["feedback"] = rating
            _save(records, path)
            return True
    return False


def _pct(part: int, whole: int):
    return round(part * 100 / whole, 1) if whole else None


def summarize(records: list) -> dict:
    """نرخ‌های اصلی ارزیابی از روی همه نوبت‌های ثبت‌شده."""
    turns = len(records)
    with_finish = [r for r in records if r.get("finish_reason")]
    stopped = sum(1 for r in with_finish if r["finish_reason"] == "stop")
    tool_turns = sum(1 for r in records if r.get("used_tools"))
    saved = sum(1 for r in records if r.get("saved"))
    rated = [r for r in records if r.get("feedback") in ("up", "down")]
    ups = sum(1 for r in rated if r["feedback"] == "up")
    total_tokens = sum(r.get("total_tokens") or 0 for r in records)
    return {
        "turns": turns,
        "stop_rate": _pct(stopped, len(with_finish)),
        "tool_rate": _pct(tool_turns, turns),
        "saved_rate": _pct(saved, turns),
        "avg_total_tokens": round(total_tokens / turns) if turns else None,
        "feedback_up": ups,
        "feedback_down": len(rated) - ups,
        "positive_rate": _pct(ups, len(rated)),
        "recent": list(reversed(records[-10:])),
    }
