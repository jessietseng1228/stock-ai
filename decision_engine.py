from __future__ import annotations

from typing import Dict, List

DECISION_ENGINE_VERSION = "Decision Engine v20.7"


def _number(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def calculate_risk(data: Dict) -> Dict:
    """計算可解釋的風險扣分。分數越高代表風險越高。"""
    price = _number(data.get("price"))
    ma20 = _number(data.get("ma20"))
    rsi = _number(data.get("rsi14"), 50)
    five_pct = _number(data.get("five_pct"))
    atr_pct = _number(data.get("atr_pct"))
    stop_loss = _number(data.get("stop_loss"))
    plan = data.get("trade_plan") or {}
    rr = _number(plan.get("rr", data.get("rr")))

    distance_ma20 = ((price - ma20) / ma20 * 100) if price > 0 and ma20 > 0 else 0.0
    stop_distance = ((price - stop_loss) / price * 100) if price > 0 and stop_loss > 0 else 0.0

    points = 0
    reasons: List[str] = []

    if rsi >= 80:
        points += 3
        reasons.append(f"RSI {rsi:.0f} 極度過熱")
    elif rsi >= 75:
        points += 2
        reasons.append(f"RSI {rsi:.0f} 偏高")
    elif rsi >= 70:
        points += 1
        reasons.append(f"RSI {rsi:.0f} 接近過熱")

    if distance_ma20 >= 15:
        points += 3
        reasons.append(f"高於月線 {distance_ma20:.1f}%")
    elif distance_ma20 >= 12:
        points += 2
        reasons.append(f"高於月線 {distance_ma20:.1f}%")
    elif distance_ma20 >= 8:
        points += 1
        reasons.append(f"偏離月線 {distance_ma20:.1f}%")

    if five_pct >= 20:
        points += 3
        reasons.append(f"5日已漲 {five_pct:.1f}%")
    elif five_pct >= 15:
        points += 2
        reasons.append(f"5日已漲 {five_pct:.1f}%")
    elif five_pct >= 10:
        points += 1
        reasons.append(f"5日漲幅 {five_pct:.1f}%")

    if atr_pct >= 7:
        points += 2
        reasons.append(f"ATR 波動 {atr_pct:.1f}%")
    elif atr_pct >= 5:
        points += 1
        reasons.append(f"ATR 波動 {atr_pct:.1f}%")

    if 0 < rr < 1.5:
        points += 1
        reasons.append(f"RR 僅 {rr:.2f}")

    if stop_distance >= 12:
        points += 2
        reasons.append(f"停損距離 {stop_distance:.1f}%")
    elif stop_distance >= 10:
        points += 1
        reasons.append(f"停損距離 {stop_distance:.1f}%")

    # 風險扣分採壓縮制，避免單一指標完全蓋過原始 AI Score。
    penalty = min(8, int(round(points * 0.75)))
    if points <= 2:
        level = "低"
    elif points <= 4:
        level = "中低"
    elif points <= 6:
        level = "中"
    elif points <= 8:
        level = "偏高"
    else:
        level = "高"

    return {
        "risk_points": points,
        "risk_penalty": penalty,
        "risk_level": level,
        "risk_reasons": reasons[:4],
        "distance_ma20_pct": round(distance_ma20, 2),
        "stop_distance_pct": round(stop_distance, 2),
    }


def calculate_entry_quality(data: Dict) -> Dict:
    """針對已通過 v20.6 硬門檻的股票，評估進場品質，最高加 5 分。"""
    plan = data.get("trade_plan") or {}
    rr = _number(plan.get("rr", data.get("rr")))
    decision = str(plan.get("decision") or data.get("decision") or "")
    volume_ratio = _number(data.get("volume_ratio"))
    price = _number(data.get("price"))
    ma20 = _number(data.get("ma20"))
    ma20_slope = _number(data.get("ma20_slope_pct"))
    macd_hist = _number(data.get("macd_hist"))

    bonus = 0
    reasons: List[str] = []

    if rr >= 2.5:
        bonus += 2
        reasons.append(f"RR {rr:.2f} 優良")
    elif rr >= 2.0:
        bonus += 1
        reasons.append(f"RR {rr:.2f}")

    if volume_ratio >= 1.8:
        bonus += 1
        reasons.append(f"量能 {volume_ratio:.1f} 倍")

    if price > ma20 > 0 and ma20_slope > 0:
        bonus += 1
        reasons.append("站上上揚月線")

    if macd_hist > 0:
        bonus += 1
        reasons.append("MACD 動能為正")

    if decision == "🟢 可分批布局":
        bonus += 1
        reasons.append("可直接分批布局")

    bonus = min(5, bonus)
    return {"entry_quality_bonus": bonus, "entry_quality_reasons": reasons[:4]}


def apply_decision_engine(data: Dict) -> Dict:
    learned_score = int(round(_number(data.get("score"))))
    risk = calculate_risk(data)
    entry = calculate_entry_quality(data)
    final_score = max(0, min(100, learned_score + entry["entry_quality_bonus"] - risk["risk_penalty"]))
    return {
        "learned_score": learned_score,
        **risk,
        **entry,
        "final_score": final_score,
        "decision_engine_version": DECISION_ENGINE_VERSION,
    }
