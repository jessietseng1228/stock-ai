from __future__ import annotations

import os
from collections import Counter, defaultdict
from typing import Dict, Iterable, List, Tuple

LEARNING_VERSION = "Dual Learning Engine v21.1"
CURRENT_ALLOWED_DECISIONS = {"🟢 可分批布局", "🔵 突破確認後布局"}
FACTOR_FIELDS = ("trend_score", "momentum_score", "volume_score", "risk_score", "position_score", "technical_score")
SHADOW_MIN_SAMPLES = max(5, int(os.getenv("LEARNING_SHADOW_MIN_SAMPLES", "10")))
AUTO_APPLY_MIN_SAMPLES = max(30, int(os.getenv("LEARNING_AUTO_APPLY_MIN_SAMPLES", "30")))
MAX_ADJUSTMENT = max(1.0, min(5.0, float(os.getenv("LEARNING_MAX_ADJUSTMENT", "3"))))
DECISION_MAX_ADJUSTMENT = max(0.5, min(MAX_ADJUSTMENT, float(os.getenv("LEARNING_DECISION_MAX_ADJUSTMENT", "2"))))
FACTOR_MAX_ADJUSTMENT = max(0.5, min(MAX_ADJUSTMENT, float(os.getenv("LEARNING_FACTOR_MAX_ADJUSTMENT", "1"))))
MAX_ABS_DAY5_RETURN = max(5.0, float(os.getenv("LEARNING_MAX_ABS_DAY5_RETURN", "20")))
GUARD_MIN_UNIQUE_DATES = max(3, int(os.getenv("LEARNING_GUARD_MIN_UNIQUE_DATES", "6")))
GUARD_MAX_SINGLE_DATE_SHARE = min(0.5, max(0.10, float(os.getenv("LEARNING_GUARD_MAX_SINGLE_DATE_SHARE", "0.25"))))
GUARD_MIN_FACTOR_SIDE = max(3, int(os.getenv("LEARNING_GUARD_MIN_FACTOR_SIDE", "5")))
GUARD_MIN_WIN_EDGE = max(0.0, float(os.getenv("LEARNING_GUARD_MIN_WIN_EDGE", "5")))
GUARD_MIN_RETURN_EDGE = max(0.0, float(os.getenv("LEARNING_GUARD_MIN_RETURN_EDGE", "0.30")))


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _number(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _sample_key(row: dict) -> str:
    return f"{str(row.get('scan_date') or '').strip()}|{str(row.get('symbol') or '').strip().upper()}"


def _deduplicate(rows: List[dict]) -> Tuple[List[dict], int]:
    seen = set(); clean: List[dict] = []; duplicates = 0
    for row in rows:
        key = _sample_key(row)
        if not key or key == "|":
            clean.append(row); continue
        if key in seen:
            duplicates += 1; continue
        seen.add(key); clean.append(row)
    return clean, duplicates


def _legacy_exclusion_reasons(row: dict) -> List[str]:
    reasons: List[str] = []
    decision = str(row.get("decision") or "").strip()
    if decision not in CURRENT_ALLOWED_DECISIONS: reasons.append("decision_not_allowed")
    if _number(row.get("base_score")) <= 0: reasons.append("missing_or_invalid_base_score")
    if row.get("day5_return") is None:
        reasons.append("missing_day5_return")
    elif abs(_number(row.get("day5_return"))) > MAX_ABS_DAY5_RETURN:
        reasons.append("day5_return_outlier")
    missing_factors = [field for field in FACTOR_FIELDS if row.get(field) is None]
    if missing_factors:
        reasons.append("missing_factor_scores")
        reasons.extend(f"missing_{field}" for field in missing_factors)
    if not str(row.get("scan_date") or "").strip(): reasons.append("missing_scan_date")
    if not str(row.get("symbol") or "").strip(): reasons.append("missing_symbol")
    return reasons


def _legacy_diagnostics(deduped: List[dict]) -> Dict:
    primary_counts = Counter(); all_counts = Counter(); preview = []
    priority = ("decision_not_allowed", "missing_or_invalid_base_score", "missing_day5_return", "day5_return_outlier", "missing_factor_scores", "missing_scan_date", "missing_symbol")
    excluded_count = 0
    for row in deduped:
        reasons = _legacy_exclusion_reasons(row)
        if not reasons: continue
        excluded_count += 1; all_counts.update(reasons)
        primary = next((r for r in priority if r in reasons), reasons[0]); primary_counts[primary] += 1
        if len(preview) < 12:
            preview.append({"scan_date": row.get("scan_date"), "symbol": row.get("symbol"), "decision": row.get("decision"), "base_score": row.get("base_score"), "day5_return": row.get("day5_return"), "reasons": reasons})
    return {"excluded_count": excluded_count, "primary_reasons": dict(primary_counts), "reason_counts": dict(all_counts), "preview": preview,
            "notes": "primary_reasons 加總等於 legacy_excluded_count；reason_counts 允許同一筆樣本同時命中多個原因。"}


def _is_clean_learning(row: dict) -> bool:
    if str(row.get("decision") or "").strip() not in CURRENT_ALLOWED_DECISIONS: return False
    if _number(row.get("base_score")) <= 0 or row.get("day5_return") is None: return False
    if abs(_number(row.get("day5_return"))) > MAX_ABS_DAY5_RETURN: return False
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
    values = []
    for row in rows:
        value = row.get("day5_return")
        if value is None: continue
        try: values.append(float(value))
        except (TypeError, ValueError): continue
    if not values: return {"count": 0, "win_rate": 0.0, "avg_return": 0.0}
    wins = sum(1 for value in values if value > 0)
    return {"count": len(values), "win_rate": round(wins / len(values) * 100, 2), "avg_return": round(sum(values) / len(values), 3)}


def _group_stats(rows: List[dict], key_func) -> Dict[str, Dict]:
    groups: Dict[str, List[dict]] = defaultdict(list)
    for row in rows: groups[str(key_func(row))].append(row)
    return {key: _summarize(values) for key, values in groups.items()}


def _factor_shadow(rows: List[dict]) -> Dict[str, Dict]:
    labels = {"trend": "trend_score", "momentum": "momentum_score", "volume": "volume_score", "risk": "risk_score", "position": "position_score", "technical": "technical_score"}
    result = {}
    for label, field in labels.items():
        values = sorted(_number(r.get(field)) for r in rows if r.get(field) is not None)
        if len(values) < 4:
            result[label] = {"sample_count": len(values), "status": "insufficient", "suggested_bias": 0.0}; continue
        median = values[len(values)//2]
        high = [r for r in rows if _number(r.get(field)) >= median]
        low = [r for r in rows if _number(r.get(field)) < median]
        hs, ls = _summarize(high), _summarize(low)
        win_edge = hs["win_rate"] - ls["win_rate"]; ret_edge = hs["avg_return"] - ls["avg_return"]
        raw = (win_edge / 20.0) * 0.6 + ret_edge * 0.4
        reliability = min(1.0, len(values) / max(AUTO_APPLY_MIN_SAMPLES, 1))
        bias = round(_clamp(raw * reliability, -1.5, 1.5), 2)
        result[label] = {"sample_count": len(values), "status": "shadow", "split_value": median, "high": hs, "low": ls,
                         "win_rate_edge": round(win_edge, 2), "avg_return_edge": round(ret_edge, 3), "suggested_bias": bias}
    return result


def _sample_distribution_guard(clean: List[dict]) -> Dict:
    dates = [str(r.get("scan_date") or "") for r in clean if r.get("scan_date")]
    counts = Counter(dates); unique_dates = len(counts); max_date_samples = max(counts.values(), default=0)
    max_date_share = (max_date_samples / len(clean)) if clean else 0.0
    checks = {"min_samples": len(clean) >= AUTO_APPLY_MIN_SAMPLES, "unique_dates": unique_dates >= GUARD_MIN_UNIQUE_DATES,
              "date_concentration": max_date_share <= GUARD_MAX_SINGLE_DATE_SHARE}
    reasons = []
    if not checks["min_samples"]: reasons.append(f"Clean Sample {len(clean)} < {AUTO_APPLY_MIN_SAMPLES}")
    if not checks["unique_dates"]: reasons.append(f"有效交易日 {unique_dates} < {GUARD_MIN_UNIQUE_DATES}")
    if not checks["date_concentration"]: reasons.append(f"單日樣本占比 {max_date_share:.1%} > {GUARD_MAX_SINGLE_DATE_SHARE:.0%}")
    return {"checks": checks, "unique_scan_dates": unique_dates, "max_single_date_share": round(max_date_share, 4), "reasons": reasons}


def _factor_guard(clean: List[dict], factor_shadow: Dict[str, Dict]) -> Dict:
    base = _sample_distribution_guard(clean); strong_factors = []
    for name, stats in factor_shadow.items():
        high, low = stats.get("high") or {}, stats.get("low") or {}
        both_sides_ok = min(int(high.get("count", 0) or 0), int(low.get("count", 0) or 0)) >= GUARD_MIN_FACTOR_SIDE
        meaningful = abs(_number(stats.get("win_rate_edge"))) >= GUARD_MIN_WIN_EDGE or abs(_number(stats.get("avg_return_edge"))) >= GUARD_MIN_RETURN_EDGE
        if both_sides_ok and meaningful: strong_factors.append(name)
    checks = {**base["checks"], "meaningful_factor_signal": bool(strong_factors)}
    reasons = list(base["reasons"])
    if not strong_factors: reasons.append("Factor Engine 尚無同時具備足夠兩側樣本且勝率/報酬差異明顯的因子")
    return {"passed": all(checks.values()), "checks": checks, "unique_scan_dates": base["unique_scan_dates"],
            "max_single_date_share": base["max_single_date_share"], "strong_factors": strong_factors, "reasons": reasons}


def _decision_signal_buckets(profile: Dict, baseline: Dict) -> List[str]:
    strong = []
    bucket_sets = {
        "score": profile.get("score_buckets") or {}, "confidence": profile.get("confidence_buckets") or {}, "rr": profile.get("rr_buckets") or {},
        "pattern": profile.get("pattern_buckets") or {}, "decision": profile.get("decision_buckets") or {}, "market_regime": profile.get("market_regime_buckets") or {},
    }
    for group_name, buckets in bucket_sets.items():
        for bucket_name, stats in buckets.items():
            count = int(stats.get("count", 0) or 0)
            if count < GUARD_MIN_FACTOR_SIDE: continue
            win_edge = _number(stats.get("win_rate")) - _number(baseline.get("win_rate"))
            ret_edge = _number(stats.get("avg_return")) - _number(baseline.get("avg_return"))
            if abs(win_edge) >= GUARD_MIN_WIN_EDGE or abs(ret_edge) >= GUARD_MIN_RETURN_EDGE:
                strong.append(f"{group_name}:{bucket_name}")
    return strong


def _decision_guard(clean: List[dict], profile: Dict) -> Dict:
    base = _sample_distribution_guard(clean); strong = _decision_signal_buckets(profile, profile.get("overall") or {})
    checks = {**base["checks"], "meaningful_decision_signal": bool(strong)}
    reasons = list(base["reasons"])
    if not strong: reasons.append("Decision Engine 尚無具足夠樣本且相對基準有明顯差異的決策分組")
    return {"passed": all(checks.values()), "checks": checks, "unique_scan_dates": base["unique_scan_dates"],
            "max_single_date_share": base["max_single_date_share"], "strong_buckets": strong[:20], "reasons": reasons}


def build_learning_profile(rows: List[dict]) -> Dict:
    raw_completed = [r for r in (rows or []) if r.get("day5_return") is not None]
    deduped, duplicate_excluded = _deduplicate(raw_completed)
    clean_before_dedup = [r for r in raw_completed if _is_clean_learning(r)]
    clean = [r for r in deduped if _is_clean_learning(r)]
    overall = _summarize(clean); clean_count = overall["count"]
    factor_shadow = _factor_shadow(clean)
    profile = {
        "overall": overall,
        "score_buckets": _group_stats(clean, lambda r: _score_bucket(r.get("base_score", 0))),
        "confidence_buckets": _group_stats(clean, lambda r: _confidence_bucket(r.get("confidence", 0))),
        "rr_buckets": _group_stats(clean, lambda r: _rr_bucket(r.get("rr", 0))),
        "pattern_buckets": _group_stats(clean, lambda r: r.get("pattern") or "unknown"),
        "decision_buckets": _group_stats(clean, lambda r: r.get("decision") or "unknown"),
        "market_regime_buckets": _group_stats(clean, lambda r: r.get("market_regime") or "UNKNOWN"),
    }
    factor_guard = _factor_guard(clean, factor_shadow)
    decision_guard = _decision_guard(clean, profile)
    dual_checks = {"decision_engine": bool(decision_guard.get("passed")), "factor_engine": bool(factor_guard.get("passed"))}
    dual_reasons = []
    if not dual_checks["decision_engine"]: dual_reasons.extend(["Decision: " + x for x in decision_guard.get("reasons", [])])
    if not dual_checks["factor_engine"]: dual_reasons.extend(["Factor: " + x for x in factor_guard.get("reasons", [])])
    dual_guard = {"passed": all(dual_checks.values()), "checks": dual_checks, "reasons": dual_reasons,
                  "policy": "v21.1 requires BOTH Decision Learning and Factor Learning guards to pass before production auto-apply."}
    shadow_ready = clean_count >= SHADOW_MIN_SAMPLES; auto_apply_ready = bool(dual_guard["passed"])
    mode = "auto" if auto_apply_ready else ("dual_shadow" if shadow_ready else "collecting")
    legacy_diag = _legacy_diagnostics(deduped)
    return {
        "version": LEARNING_VERSION, "architecture": "dual", "mode": mode, "ready": auto_apply_ready, "shadow_ready": shadow_ready,
        "auto_apply_ready": auto_apply_ready, "raw_completed_count": len(raw_completed), "clean_before_dedup_count": len(clean_before_dedup),
        "dedup_sample_count": len(deduped), "duplicate_excluded_count": duplicate_excluded, "clean_sample_count": clean_count,
        "legacy_excluded_count": len(deduped) - clean_count, "legacy_excluded_primary_reasons": legacy_diag["primary_reasons"],
        "legacy_excluded_reason_counts": legacy_diag["reason_counts"], "legacy_excluded_preview": legacy_diag["preview"],
        "legacy_diagnostics_notes": legacy_diag["notes"], "shadow_min_samples": SHADOW_MIN_SAMPLES, "auto_apply_min_samples": AUTO_APPLY_MIN_SAMPLES,
        "max_adjustment": MAX_ADJUSTMENT, "decision_max_adjustment": DECISION_MAX_ADJUSTMENT, "factor_max_adjustment": FACTOR_MAX_ADJUSTMENT,
        "learning_guard": dual_guard, "dual_learning_gate": dual_guard,
        "decision_learning": {"status": "auto" if decision_guard["passed"] else ("shadow" if shadow_ready else "collecting"), "guard": decision_guard,
                              "strong_buckets": decision_guard.get("strong_buckets", [])},
        "factor_learning": {"status": "auto" if factor_guard["passed"] else ("shadow" if shadow_ready else "collecting"), "guard": factor_guard,
                            "strong_factors": factor_guard.get("strong_factors", []), "factor_shadow": factor_shadow},
        **profile, "factor_shadow": factor_shadow,
        "criteria": {"min_samples": AUTO_APPLY_MIN_SAMPLES, "shadow_min_samples": SHADOW_MIN_SAMPLES, "min_unique_dates": GUARD_MIN_UNIQUE_DATES,
                     "max_single_date_share": GUARD_MAX_SINGLE_DATE_SHARE, "min_side_samples": GUARD_MIN_FACTOR_SIDE,
                     "min_win_rate_edge": GUARD_MIN_WIN_EDGE, "min_avg_return_edge": GUARD_MIN_RETURN_EDGE, "max_abs_day5_return": MAX_ABS_DAY5_RETURN},
    }


def _bucket_edge(stats: Dict, baseline: Dict, weight: float) -> Tuple[float, str]:
    count = int(stats.get("count", 0) or 0)
    if count < SHADOW_MIN_SAMPLES: return 0.0, f"樣本{count}筆，尚未達Shadow門檻{SHADOW_MIN_SAMPLES}筆"
    win_edge = (_number(stats.get("win_rate")) - _number(baseline.get("win_rate"))) / 10.0
    return_edge = _number(stats.get("avg_return")) - _number(baseline.get("avg_return"))
    raw = win_edge * 0.65 + return_edge * 0.35; reliability = min(1.0, count / max(AUTO_APPLY_MIN_SAMPLES, 1))
    value = _clamp(raw * reliability * weight, -weight, weight)
    return value, f"樣本{count}筆／勝率{_number(stats.get('win_rate')):.1f}%／均報酬{_number(stats.get('avg_return')):+.2f}%"


def _decision_shadow_adjustment(data: Dict, profile: Dict) -> Tuple[float, List[str]]:
    baseline = profile.get("overall") or {}; components: List[Tuple[float, str]] = []
    base_score = _number(data.get("score"))
    value, reason = _bucket_edge((profile.get("score_buckets") or {}).get(_score_bucket(base_score), {}), baseline, 1.2)
    components.append((value, f"Score {_score_bucket(base_score)}：{reason}"))
    confidence = _number(data.get("confidence", (data.get("trade_plan") or {}).get("confidence", 0)))
    if confidence > 0:
        key = _confidence_bucket(confidence); value, reason = _bucket_edge((profile.get("confidence_buckets") or {}).get(key, {}), baseline, 0.3); components.append((value, f"Confidence {key}：{reason}"))
    rr = _number(data.get("rr", (data.get("trade_plan") or {}).get("rr", 0)))
    if rr > 0:
        key = _rr_bucket(rr); value, reason = _bucket_edge((profile.get("rr_buckets") or {}).get(key, {}), baseline, 0.3); components.append((value, f"RR {key}：{reason}"))
    regime = str(data.get("market_regime") or "UNKNOWN")
    if regime != "UNKNOWN":
        value, reason = _bucket_edge((profile.get("market_regime_buckets") or {}).get(regime, {}), baseline, 0.2); components.append((value, f"Regime {regime}：{reason}"))
    total = round(_clamp(sum(v for v, _ in components), -DECISION_MAX_ADJUSTMENT, DECISION_MAX_ADJUSTMENT), 2)
    reasons = [r for v, r in components if abs(v) >= 0.05]
    return total, reasons


def _factor_shadow_adjustment(data: Dict, profile: Dict) -> Tuple[float, List[str]]:
    current = data.get("factor_scores") or {}; shadow = profile.get("factor_shadow") or {}
    pieces = []; reasons = []
    for label in ("trend", "momentum", "volume", "risk", "position", "technical"):
        stats = shadow.get(label) or {}; split = stats.get("split_value")
        if split is None or label not in current: continue
        bias = _number(stats.get("suggested_bias")); current_value = _number(current.get(label))
        # suggested_bias means historical HIGH minus LOW edge. Current sample gets same sign when on HIGH side, opposite on LOW side.
        direction = 1.0 if current_value >= _number(split) else -1.0
        contribution = bias * direction / 6.0; pieces.append(contribution)
        if abs(contribution) >= 0.03:
            side = "High" if direction > 0 else "Low"; reasons.append(f"{label} {side}({current_value:g}/{_number(split):g}) bias {bias:+.2f}")
    total = round(_clamp(sum(pieces), -FACTOR_MAX_ADJUSTMENT, FACTOR_MAX_ADJUSTMENT), 2)
    return total, reasons


def learning_adjustment(data: Dict, profile: Dict) -> Dict:
    base_score = int(data.get("score", 0) or 0); sample_count = int((profile.get("overall") or {}).get("count", 0) or 0)
    result = {"base_score": base_score, "learning_adjustment": 0.0, "shadow_adjustment": 0.0, "shadow_score": base_score, "learned_score": base_score,
              "decision_shadow_adjustment": 0.0, "factor_shadow_adjustment": 0.0, "learning_ready": bool(profile.get("auto_apply_ready", False)),
              "learning_mode": profile.get("mode", "collecting"), "learning_sample_count": sample_count, "learning_min_samples": AUTO_APPLY_MIN_SAMPLES,
              "learning_shadow_min_samples": SHADOW_MIN_SAMPLES, "learning_reasons": [], "learning_version": LEARNING_VERSION, "learning_architecture": "dual"}
    if not profile or not profile.get("shadow_ready"):
        result["learning_reasons"] = [f"Clean Sample {sample_count}筆；需{SHADOW_MIN_SAMPLES}筆才啟動Dual Shadow，且雙引擎都通過Guard才允許正式校正"]
        return result
    decision_adj, decision_reasons = _decision_shadow_adjustment(data, profile)
    factor_adj, factor_reasons = _factor_shadow_adjustment(data, profile)
    shadow_adjustment = round(_clamp(decision_adj + factor_adj, -MAX_ADJUSTMENT, MAX_ADJUSTMENT), 1)
    shadow_score = int(_clamp(round(base_score + shadow_adjustment), 0, 100)); auto_apply = bool(profile.get("auto_apply_ready", False))
    reasons = []
    if decision_reasons: reasons.append("Decision Learning：" + "；".join(decision_reasons[:4]))
    if factor_reasons: reasons.append("Factor Learning：" + "；".join(factor_reasons[:4]))
    if not reasons: reasons.append("Dual Shadow 已啟動，但目前決策層與因子層差異不足，維持原分數")
    if not auto_apply:
        gate_reasons = (profile.get("dual_learning_gate") or {}).get("reasons") or []
        if gate_reasons: reasons.append("Dual Learning Gate：" + "；".join(gate_reasons[:4]))
    result.update({"decision_shadow_adjustment": round(decision_adj, 2), "factor_shadow_adjustment": round(factor_adj, 2),
                   "shadow_adjustment": shadow_adjustment, "shadow_score": shadow_score, "learning_adjustment": shadow_adjustment if auto_apply else 0.0,
                   "learned_score": shadow_score if auto_apply else base_score, "learning_ready": auto_apply, "learning_reasons": reasons})
    return result
