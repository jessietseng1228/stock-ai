from __future__ import annotations

import os
from collections import defaultdict
from typing import Dict, Iterable, List, Tuple

LEARNING_VERSION = "Learning Engine v20.5"
MIN_SAMPLES = max(5, int(os.getenv("LEARNING_MIN_SAMPLES", "10")))
MAX_ADJUSTMENT = max(1.0, min(8.0, float(os.getenv("LEARNING_MAX_ADJUSTMENT", "5"))))


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _score_bucket(score: float) -> str:
    score = float(score or 0)
    if score >= 85:
        return "85+"
    if score >= 80:
        return "80-84"
    if score >= 75:
        return "75-79"
    if score >= 70:
        return "70-74"
    return "<70"


def _confidence_bucket(confidence: float) -> str:
    confidence = float(confidence or 0)
    if confidence >= 90:
        return "90+"
    if confidence >= 80:
        return "80-89"
    if confidence > 0:
        return "<80"
    return "unknown"


def _rr_bucket(rr: float) -> str:
    rr = float(rr or 0)
    if rr >= 2:
        return "2+"
    if rr >= 1.5:
        return "1.5-1.99"
    if rr >= 1:
        return "1-1.49"
    if rr > 0:
        return "<1"
    return "unknown"


def _summarize(rows: Iterable[dict]) -> Dict:
    values: List[float] = []
    for row in rows:
        value = row.get("day5_return")
        if value is None:
            continue
        try:
            values.append(float(value))
        except (TypeError, ValueError):
            continue
    count = len(values)
    if not count:
        return {"count": 0, "win_rate": 0.0, "avg_return": 0.0}
    wins = sum(1 for value in values if value > 0)
    return {
        "count": count,
        "win_rate": round(wins / count * 100, 2),
        "avg_return": round(sum(values) / count, 3),
    }


def _group_stats(rows: List[dict], key_func) -> Dict[str, Dict]:
    groups: Dict[str, List[dict]] = defaultdict(list)
    for row in rows:
        groups[str(key_func(row))].append(row)
    return {key: _summarize(values) for key, values in groups.items()}


def build_learning_profile(rows: List[dict]) -> Dict:
    completed = [row for row in (rows or []) if row.get("day5_return") is not None]
    overall = _summarize(completed)
    return {
        "version": LEARNING_VERSION,
        "ready": overall["count"] >= MIN_SAMPLES,
        "min_samples": MIN_SAMPLES,
        "max_adjustment": MAX_ADJUSTMENT,
        "overall": overall,
        "score_buckets": _group_stats(completed, lambda r: _score_bucket(r.get("base_score", r.get("ai_score", 0)))),
        "confidence_buckets": _group_stats(completed, lambda r: _confidence_bucket(r.get("confidence", 0))),
        "rr_buckets": _group_stats(completed, lambda r: _rr_bucket(r.get("rr", 0))),
        "pattern_buckets": _group_stats(completed, lambda r: r.get("pattern") or "unknown"),
        "decision_buckets": _group_stats(completed, lambda r: r.get("decision") or "unknown"),
    }


def _bucket_edge(stats: Dict, baseline: Dict, weight: float) -> Tuple[float, str]:
    count = int(stats.get("count", 0) or 0)
    if count < MIN_SAMPLES:
        return 0.0, f"樣本{count}筆，尚未達{MIN_SAMPLES}筆"

    win_edge = (float(stats.get("win_rate", 0)) - float(baseline.get("win_rate", 0))) / 10.0
    return_edge = float(stats.get("avg_return", 0)) - float(baseline.get("avg_return", 0))
    raw = win_edge * 0.65 + return_edge * 0.35
    # 樣本愈多，可信度愈高；最高採完整權重。
    reliability = min(1.0, count / max(MIN_SAMPLES * 3, 1))
    value = _clamp(raw * reliability * weight, -weight, weight)
    reason = (
        f"樣本{count}筆／勝率{float(stats.get('win_rate', 0)):.1f}%／"
        f"均報酬{float(stats.get('avg_return', 0)):+.2f}%"
    )
    return value, reason


def learning_adjustment(data: Dict, profile: Dict) -> Dict:
    base_score = int(data.get("score", 0) or 0)
    result = {
        "base_score": base_score,
        "learning_adjustment": 0.0,
        "learned_score": base_score,
        "learning_ready": False,
        "learning_sample_count": int((profile.get("overall") or {}).get("count", 0) or 0),
        "learning_reasons": [],
        "learning_version": LEARNING_VERSION,
    }
    if not profile or not profile.get("ready"):
        result["learning_reasons"] = [
            f"累積{result['learning_sample_count']}筆Day+5資料，需{MIN_SAMPLES}筆才啟用校正"
        ]
        return result

    baseline = profile.get("overall") or {}
    components: List[Tuple[float, str]] = []

    score_key = _score_bucket(base_score)
    value, reason = _bucket_edge((profile.get("score_buckets") or {}).get(score_key, {}), baseline, 3.0)
    components.append((value, f"分數層級 {score_key}：{reason}"))

    confidence = float(data.get("confidence", (data.get("trade_plan") or {}).get("confidence", 0)) or 0)
    conf_key = _confidence_bucket(confidence)
    if conf_key != "unknown":
        value, reason = _bucket_edge((profile.get("confidence_buckets") or {}).get(conf_key, {}), baseline, 1.0)
        components.append((value, f"信心層級 {conf_key}：{reason}"))

    rr = float(data.get("rr", (data.get("trade_plan") or {}).get("rr", 0)) or 0)
    rr_key = _rr_bucket(rr)
    if rr_key != "unknown":
        value, reason = _bucket_edge((profile.get("rr_buckets") or {}).get(rr_key, {}), baseline, 1.0)
        components.append((value, f"RR層級 {rr_key}：{reason}"))

    adjustment = round(_clamp(sum(value for value, _ in components), -MAX_ADJUSTMENT, MAX_ADJUSTMENT), 1)
    learned_score = int(_clamp(round(base_score + adjustment), 0, 100))
    result.update({
        "learning_adjustment": adjustment,
        "learned_score": learned_score,
        "learning_ready": True,
        "learning_reasons": [reason for value, reason in components if abs(value) >= 0.05] or ["歷史表現接近整體平均，暫不調整"],
    })
    return result
