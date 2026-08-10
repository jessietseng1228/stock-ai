from __future__ import annotations

from collections import defaultdict
from typing import Callable, Dict, Iterable, List

ANALYTICS_VERSION = "Performance Analytics v20.8"


def _number(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _score_bucket(score: float) -> str:
    score = _number(score)
    if score >= 90:
        return "90+"
    if score >= 85:
        return "85-89"
    if score >= 80:
        return "80-84"
    if score >= 75:
        return "75-79"
    return "<75"


def _summarize(rows: Iterable[dict], return_field: str) -> Dict:
    values: List[float] = []
    for row in rows or []:
        value = row.get(return_field)
        if value is None:
            continue
        values.append(_number(value))

    count = len(values)
    if not count:
        return {
            "count": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "avg_return": 0.0,
            "best_return": None,
            "worst_return": None,
        }

    wins = sum(1 for value in values if value > 0)
    losses = sum(1 for value in values if value < 0)
    return {
        "count": count,
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / count * 100, 2),
        "avg_return": round(sum(values) / count, 3),
        "best_return": round(max(values), 3),
        "worst_return": round(min(values), 3),
    }


def _group_stats(rows: List[dict], key_func: Callable[[dict], str], return_field: str) -> Dict[str, Dict]:
    groups: Dict[str, List[dict]] = defaultdict(list)
    for row in rows or []:
        groups[str(key_func(row))].append(row)
    return {key: _summarize(group_rows, return_field) for key, group_rows in groups.items()}


def _factor_correlation_proxy(rows: List[dict]) -> Dict[str, Dict]:
    """以高/低分組 Day+5 表現差異做簡單有效性觀察，不宣稱統計因果。"""
    fields = {
        "trend": "trend_score",
        "momentum": "momentum_score",
        "volume": "volume_score",
        "risk": "risk_score",
        "position": "position_score",
        "technical": "technical_score",
    }
    result: Dict[str, Dict] = {}
    completed = [row for row in rows or [] if row.get("day5_return") is not None]

    for label, field in fields.items():
        values = [_number(row.get(field)) for row in completed if row.get(field) is not None]
        if len(values) < 4:
            result[label] = {"sample_count": len(values), "status": "insufficient"}
            continue
        sorted_values = sorted(values)
        median = sorted_values[len(sorted_values) // 2]
        high = [row for row in completed if row.get(field) is not None and _number(row.get(field)) >= median]
        low = [row for row in completed if row.get(field) is not None and _number(row.get(field)) < median]
        high_stats = _summarize(high, "day5_return")
        low_stats = _summarize(low, "day5_return")
        result[label] = {
            "sample_count": len(values),
            "split_value": median,
            "high": high_stats,
            "low": low_stats,
            "avg_return_edge": round(high_stats["avg_return"] - low_stats["avg_return"], 3),
            "win_rate_edge": round(high_stats["win_rate"] - low_stats["win_rate"], 2),
        }
    return result


def build_performance_analytics(rows: List[dict]) -> Dict:
    rows = rows or []
    day1_rows = [row for row in rows if row.get("day1_return") is not None]
    day5_rows = [row for row in rows if row.get("day5_return") is not None]

    worst_cases = sorted(
        [row for row in day5_rows if _number(row.get("day5_return")) < 0],
        key=lambda row: _number(row.get("day5_return")),
    )[:5]

    return {
        "analytics_version": ANALYTICS_VERSION,
        "total_history_count": len(rows),
        "day1": _summarize(day1_rows, "day1_return"),
        "day5": _summarize(day5_rows, "day5_return"),
        "score_buckets": _group_stats(
            day5_rows,
            lambda r: _score_bucket(r.get("base_score", r.get("ai_score", 0))),
            "day5_return",
        ),
        "rank_buckets": _group_stats(day5_rows, lambda r: f"Top{int(r.get('rank') or 0)}", "day5_return"),
        "decision_buckets": _group_stats(day5_rows, lambda r: r.get("decision") or "unknown", "day5_return"),
        "factor_effectiveness": _factor_correlation_proxy(day5_rows),
        "worst_cases": [
            {
                "scan_date": row.get("scan_date"),
                "symbol": row.get("symbol"),
                "name": row.get("name"),
                "rank": int(row.get("rank") or 0),
                "base_score": int(row.get("base_score", row.get("ai_score", 0)) or 0),
                "ai_score": int(row.get("ai_score") or 0),
                "decision": row.get("decision") or "",
                "day5_return": round(_number(row.get("day5_return")), 3),
            }
            for row in worst_cases
        ],
    }
