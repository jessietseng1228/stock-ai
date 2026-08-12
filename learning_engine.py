from __future__ import annotations

import os
from collections import defaultdict
from typing import Dict, Iterable, List, Tuple

LEARNING_VERSION = "Learning Engine v20.9"
CURRENT_ALLOWED_DECISIONS = {"🟢 可分批布局", "🔵 突破確認後布局"}
FACTOR_FIELDS = ("trend_score", "momentum_score", "volume_score", "risk_score", "position_score", "technical_score")
SHADOW_MIN_SAMPLES = max(5, int(os.getenv("LEARNING_SHADOW_MIN_SAMPLES", "10")))
AUTO_APPLY_MIN_SAMPLES = max(30, int(os.getenv("LEARNING_AUTO_APPLY_MIN_SAMPLES", "30")))
MAX_ADJUSTMENT = max(1.0, min(5.0, float(os.getenv("LEARNING_MAX_ADJUSTMENT", "3"))))


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _number(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _is_clean_learning(row: dict) -> bool:
    decision = str(row.get("decision") or "").strip()
    if decision not in CURRENT_ALLOWED_DECISIONS:
        return False
    if _number(row.get("base_score")) <= 0 or row.get("day5_return") is None:
        return False
    return all(row.get(field) is not None for field in FACTOR_FIELDS)


def _score_bucket(score: float) -> str:
    score = _number(score)
    if score >= 90: return "90+"
    if score >= 85: return "85-89"
    if score >= 80: return "80-84"
    if score >= 75: return "75-79"
    return "<75"


def _confidence_bucket(confidence: float) -> str:
    confidence = _number(confidence)
    if confidence >= 90: return "90+"
    if confidence >= 80: return "80-89"
    if confidence > 0: return "<80"
    return "unknown"


def _rr_bucket(rr: float) -> str:
    rr = _number(rr)
    if rr >= 2: return "2+"
    if rr >= 1.5: return "1.5-1.99"
    if rr >= 1: return "1-1.49"
    if rr > 0: return "<1"
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
    return {"count": count, "win_rate": round(wins / count * 100, 2), "avg_return": round(sum(values) / count, 3)}


def _group_stats(rows: List[dict], key_func) -> Dict[str, Dict]:
    groups: Dict[str, List[dict]] = defaultdict(list)
    for row in rows:
        groups[str(key_func(row))].append(row)
    return {key: _summarize(values) for key, values in groups.items()}


def _factor_shadow(rows: List[dict]) -> Dict[str, Dict]:
    labels = {
        "trend": "trend_score", "momentum": "momentum_score", "volume": "volume_score",
        "risk": "risk_score", "position": "position_score", "technical": "technical_score",
    }
    result = {}
    for label, field in labels.items():
        values = sorted(_number(r.get(field)) for r in rows if r.get(field) is not None)
        if len(values) < 4:
            result[label] = {"sample_count": len(values), "status": "insufficient", "suggested_bias": 0.0}
            continue
        median = values[len(values)//2]
        high = [r for r in rows if _number(r.get(field)) >= median]
        low = [r for r in rows if _number(r.get(field)) < median]
        hs, ls = _summarize(high), _summarize(low)
        win_edge = hs["win_rate"] - ls["win_rate"]
        ret_edge = hs["avg_return"] - ls["avg_return"]
        raw = (win_edge / 20.0) * 0.6 + ret_edge * 0.4
        reliability = min(1.0, len(values) / max(AUTO_APPLY_MIN_SAMPLES, 1))
        bias = round(_clamp(raw * reliability, -1.5, 1.5), 2)
        result[label] = {
            "sample_count": len(values), "status": "shadow", "split_value": median,
            "high": hs, "low": ls, "win_rate_edge": round(win_edge, 2),
            "avg_return_edge": round(ret_edge, 3), "suggested_bias": bias,
        }
    return result


def build_learning_profile(rows: List[dict]) -> Dict:
    raw_completed = [r for r in (rows or []) if r.get("day5_return") is not None]
    clean = [r for r in raw_completed if _is_clean_learning(r)]
    overall = _summarize(clean)
    clean_count = overall["count"]
    shadow_ready = clean_count >= SHADOW_MIN_SAMPLES
    auto_apply_ready = clean_count >= AUTO_APPLY_MIN_SAMPLES
    mode = "auto" if auto_apply_ready else ("shadow" if shadow_ready else "collecting")
    return {
        "version": LEARNING_VERSION,
        "mode": mode,
        "ready": auto_apply_ready,
        "shadow_ready": shadow_ready,
        "auto_apply_ready": auto_apply_ready,
        "raw_completed_count": len(raw_completed),
        "clean_sample_count": clean_count,
        "legacy_excluded_count": len(raw_completed) - clean_count,
        "shadow_min_samples": SHADOW_MIN_SAMPLES,
        "auto_apply_min_samples": AUTO_APPLY_MIN_SAMPLES,
        "max_adjustment": MAX_ADJUSTMENT,
        "overall": overall,
        "score_buckets": _group_stats(clean, lambda r: _score_bucket(r.get("base_score", 0))),
        "confidence_buckets": _group_stats(clean, lambda r: _confidence_bucket(r.get("confidence", 0))),
        "rr_buckets": _group_stats(clean, lambda r: _rr_bucket(r.get("rr", 0))),
        "pattern_buckets": _group_stats(clean, lambda r: r.get("pattern") or "unknown"),
        "decision_buckets": _group_stats(clean, lambda r: r.get("decision") or "unknown"),
        "factor_shadow": _factor_shadow(clean),
    }


def _bucket_edge(stats: Dict, baseline: Dict, weight: float) -> Tuple[float, str]:
    count = int(stats.get("count", 0) or 0)
    if count < SHADOW_MIN_SAMPLES:
        return 0.0, f"樣本{count}筆，尚未達Shadow門檻{SHADOW_MIN_SAMPLES}筆"
    win_edge = (_number(stats.get("win_rate")) - _number(baseline.get("win_rate"))) / 10.0
    return_edge = _number(stats.get("avg_return")) - _number(baseline.get("avg_return"))
    raw = win_edge * 0.65 + return_edge * 0.35
    reliability = min(1.0, count / max(AUTO_APPLY_MIN_SAMPLES, 1))
    value = _clamp(raw * reliability * weight, -weight, weight)
    reason = f"樣本{count}筆／勝率{_number(stats.get('win_rate')):.1f}%／均報酬{_number(stats.get('avg_return')):+.2f}%"
    return value, reason


def learning_adjustment(data: Dict, profile: Dict) -> Dict:
    base_score = int(data.get("score", 0) or 0)
    sample_count = int((profile.get("overall") or {}).get("count", 0) or 0)
    result = {
        "base_score": base_score,
        "learning_adjustment": 0.0,
        "shadow_adjustment": 0.0,
        "shadow_score": base_score,
        "learned_score": base_score,
        "learning_ready": bool(profile.get("auto_apply_ready", False)),
        "learning_mode": profile.get("mode", "collecting"),
        "learning_sample_count": sample_count,
        "learning_min_samples": AUTO_APPLY_MIN_SAMPLES,
        "learning_shadow_min_samples": SHADOW_MIN_SAMPLES,
        "learning_reasons": [],
        "learning_version": LEARNING_VERSION,
    }
    if not profile or not profile.get("shadow_ready"):
        result["learning_reasons"] = [f"Clean Sample {sample_count}筆；需{SHADOW_MIN_SAMPLES}筆才產生Shadow建議，{AUTO_APPLY_MIN_SAMPLES}筆才允許正式校正"]
        return result

    baseline = profile.get("overall") or {}
    components: List[Tuple[float, str]] = []
    score_key = _score_bucket(base_score)
    value, reason = _bucket_edge((profile.get("score_buckets") or {}).get(score_key, {}), baseline, 3.0)
    components.append((value, f"分數層級 {score_key}：{reason}"))

    confidence = _number(data.get("confidence", (data.get("trade_plan") or {}).get("confidence", 0)))
    conf_key = _confidence_bucket(confidence)
    if conf_key != "unknown":
        value, reason = _bucket_edge((profile.get("confidence_buckets") or {}).get(conf_key, {}), baseline, 1.0)
        components.append((value, f"信心層級 {conf_key}：{reason}"))

    rr = _number(data.get("rr", (data.get("trade_plan") or {}).get("rr", 0)))
    rr_key = _rr_bucket(rr)
    if rr_key != "unknown":
        value, reason = _bucket_edge((profile.get("rr_buckets") or {}).get(rr_key, {}), baseline, 1.0)
        components.append((value, f"RR層級 {rr_key}：{reason}"))

    shadow_adjustment = round(_clamp(sum(v for v, _ in components), -MAX_ADJUSTMENT, MAX_ADJUSTMENT), 1)
    shadow_score = int(_clamp(round(base_score + shadow_adjustment), 0, 100))
    auto_apply = bool(profile.get("auto_apply_ready", False))
    result.update({
        "shadow_adjustment": shadow_adjustment,
        "shadow_score": shadow_score,
        "learning_adjustment": shadow_adjustment if auto_apply else 0.0,
        "learned_score": shadow_score if auto_apply else base_score,
        "learning_ready": auto_apply,
        "learning_reasons": [reason for value, reason in components if abs(value) >= 0.05] or ["Clean Sample 已達Shadow門檻，但目前各分組差異不足，建議維持原分數"],
    })
    return result
