from __future__ import annotations

from collections import defaultdict
from typing import Callable, Dict, Iterable, List

ANALYTICS_VERSION = "Performance Analytics v20.8.1"
CURRENT_ALLOWED_DECISIONS = {"🟢 可分批布局", "🔵 突破確認後布局"}
FACTOR_FIELDS = ("trend_score", "momentum_score", "volume_score", "risk_score", "position_score", "technical_score")


def _number(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _score_bucket(score: float) -> str:
    score = _number(score)
    if score >= 90: return "90+"
    if score >= 85: return "85-89"
    if score >= 80: return "80-84"
    if score >= 75: return "75-79"
    return "<75"


def _summarize(rows: Iterable[dict], return_field: str) -> Dict:
    values = [_number(r.get(return_field)) for r in (rows or []) if r.get(return_field) is not None]
    if not values:
        return {"count": 0, "wins": 0, "losses": 0, "win_rate": 0.0, "avg_return": 0.0, "best_return": None, "worst_return": None}
    wins = sum(v > 0 for v in values); losses = sum(v < 0 for v in values); count = len(values)
    return {"count": count, "wins": wins, "losses": losses, "win_rate": round(wins/count*100, 2),
            "avg_return": round(sum(values)/count, 3), "best_return": round(max(values), 3), "worst_return": round(min(values), 3)}


def _group_stats(rows: List[dict], key_func: Callable[[dict], str], return_field: str) -> Dict[str, Dict]:
    groups = defaultdict(list)
    for row in rows or []: groups[str(key_func(row))].append(row)
    return {k: _summarize(v, return_field) for k, v in groups.items()}


def _is_current_strategy(row: dict) -> bool:
    """現行 Top5 樣本：必須是 v20.6+ Entry Filter 允許的正式進場決策，且 Base Score 有效。"""
    decision = str(row.get("decision") or "").strip()
    return decision in CURRENT_ALLOWED_DECISIONS and _number(row.get("base_score")) > 0


def _is_clean_learning(row: dict) -> bool:
    """v20.9 可使用的乾淨樣本：現行策略 + Day5 完成 + 六因子欄位完整。"""
    if not _is_current_strategy(row) or row.get("day5_return") is None:
        return False
    return all(row.get(field) is not None for field in FACTOR_FIELDS)


def _factor_correlation_proxy(rows: List[dict]) -> Dict[str, Dict]:
    fields = {"trend":"trend_score", "momentum":"momentum_score", "volume":"volume_score", "risk":"risk_score", "position":"position_score", "technical":"technical_score"}
    result = {}; completed = [r for r in rows or [] if r.get("day5_return") is not None]
    for label, field in fields.items():
        values = [_number(r.get(field)) for r in completed if r.get(field) is not None]
        if len(values) < 4:
            result[label] = {"sample_count": len(values), "status": "insufficient"}; continue
        median = sorted(values)[len(values)//2]
        high = [r for r in completed if r.get(field) is not None and _number(r.get(field)) >= median]
        low = [r for r in completed if r.get(field) is not None and _number(r.get(field)) < median]
        hs, ls = _summarize(high,"day5_return"), _summarize(low,"day5_return")
        result[label] = {"sample_count":len(values), "split_value":median, "high":hs, "low":ls,
                         "avg_return_edge":round(hs["avg_return"]-ls["avg_return"],3), "win_rate_edge":round(hs["win_rate"]-ls["win_rate"],2)}
    return result


def _worst(rows: List[dict]) -> List[dict]:
    cases = sorted([r for r in rows if r.get("day5_return") is not None and _number(r.get("day5_return")) < 0], key=lambda r:_number(r.get("day5_return")))[:5]
    return [{"scan_date":r.get("scan_date"), "symbol":r.get("symbol"), "name":r.get("name"), "rank":int(r.get("rank") or 0),
             "base_score":int(r.get("base_score") or 0), "ai_score":int(r.get("ai_score") or 0), "decision":r.get("decision") or "",
             "day5_return":round(_number(r.get("day5_return")),3)} for r in cases]


def _analytics_for(rows: List[dict]) -> Dict:
    d1=[r for r in rows if r.get("day1_return") is not None]; d5=[r for r in rows if r.get("day5_return") is not None]
    return {"total_count":len(rows), "day1":_summarize(d1,"day1_return"), "day5":_summarize(d5,"day5_return"),
            "score_buckets":_group_stats(d5, lambda r:_score_bucket(r.get("base_score",0)), "day5_return"),
            "rank_buckets":_group_stats(d5, lambda r:f"Top{int(r.get('rank') or 0)}", "day5_return"),
            "decision_buckets":_group_stats(d5, lambda r:r.get("decision") or "unknown", "day5_return")}


def build_performance_analytics(rows: List[dict]) -> Dict:
    rows = rows or []
    current = [r for r in rows if _is_current_strategy(r)]
    clean = [r for r in rows if _is_clean_learning(r)]
    legacy = [r for r in rows if not _is_current_strategy(r)]
    all_stats = _analytics_for(rows); current_stats = _analytics_for(current)
    return {
        "analytics_version": ANALYTICS_VERSION,
        "total_history_count": len(rows),
        "current_strategy_count": len(current), "clean_learning_count": len(clean), "legacy_count": len(legacy),
        "day1": all_stats["day1"], "day5": all_stats["day5"],
        "score_buckets": all_stats["score_buckets"], "rank_buckets": all_stats["rank_buckets"], "decision_buckets": all_stats["decision_buckets"],
        "all_history": all_stats,
        "current_strategy": {**current_stats, "worst_cases": _worst(current)},
        "clean_learning": {**_analytics_for(clean), "factor_effectiveness": _factor_correlation_proxy(clean), "ready_for_auto_weight": len(clean) >= 30},
        "legacy": {"total_count":len(legacy), "reason":"非現行 Entry Filter 決策或 Base Score 無效；僅供歷史參考，不可用於自動調權重。"},
        "factor_effectiveness": _factor_correlation_proxy(clean),
        "worst_cases": _worst(current),
    }
