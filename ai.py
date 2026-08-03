from typing import Dict, List

SCORE_VERSION = "AI Score 3.0"
TECH_VERSION = "Decision + Learning Engine v20.6"


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def score_to_stars(score: int) -> str:
    score = max(0, min(100, int(score or 0)))
    if score >= 90:
        full = 5
    elif score >= 80:
        full = 4
    elif score >= 70:
        full = 3
    elif score >= 55:
        full = 2
    else:
        full = 1
    return "★" * full + "☆" * (5 - full)


def trend_label(score: int) -> str:
    score = int(score or 0)
    if score >= 90:
        return "強勢偏多"
    if score >= 80:
        return "偏多觀察"
    if score >= 70:
        return "中性偏多"
    if score >= 55:
        return "震盪觀察"
    if score >= 40:
        return "偏弱整理"
    return "短線弱勢"


def technical_score(data: Dict) -> Dict[str, int]:
    """v19.2 技術指標加權，共 25 分。

    RSI 7、MACD 8、均線斜率 7、ATR 3。
    """
    rsi14 = float(data.get("rsi14", 50) or 50)
    macd = float(data.get("macd", 0) or 0)
    macd_signal = float(data.get("macd_signal", 0) or 0)
    macd_hist = float(data.get("macd_hist", 0) or 0)
    ma5_slope = float(data.get("ma5_slope_pct", 0) or 0)
    ma10_slope = float(data.get("ma10_slope_pct", 0) or 0)
    ma20_slope = float(data.get("ma20_slope_pct", 0) or 0)
    atr_pct = float(data.get("atr_pct", 0) or 0)

    # RSI：55～68 為健康偏多；過熱與偏弱都不給滿分。
    if 55 <= rsi14 <= 68:
        rsi_score = 7
    elif 50 <= rsi14 < 55 or 68 < rsi14 <= 75:
        rsi_score = 5
    elif 42 <= rsi14 < 50:
        rsi_score = 3
    elif 30 <= rsi14 < 42:
        rsi_score = 1
    else:
        rsi_score = 0

    # MACD：線上且柱狀體為正最佳；柱狀體方向代表動能。
    if macd > macd_signal and macd_hist > 0:
        macd_score = 8 if macd > 0 else 6
    elif macd > macd_signal:
        macd_score = 5
    elif macd_hist >= 0:
        macd_score = 4
    elif macd < macd_signal and macd_hist < 0:
        macd_score = 1 if macd < 0 else 2
    else:
        macd_score = 3

    # 均線斜率：短中長期同步向上最強，20 日斜率權重較高。
    slope_score = 0
    slope_score += 2 if ma5_slope > 0.10 else (1 if ma5_slope > 0 else 0)
    slope_score += 2 if ma10_slope > 0.08 else (1 if ma10_slope > 0 else 0)
    slope_score += 3 if ma20_slope > 0.05 else (1 if ma20_slope > 0 else 0)
    if ma5_slope < -0.20 and ma10_slope < -0.15 and ma20_slope < 0:
        slope_score = 0
    slope_score = int(_clamp(slope_score, 0, 7))

    # ATR：適度波動較適合短線；過高代表停損距離與風險增加。
    if 1.0 <= atr_pct <= 3.5:
        atr_score = 3
    elif 0 < atr_pct < 1.0 or 3.5 < atr_pct <= 5.0:
        atr_score = 2
    elif atr_pct > 0:
        atr_score = 0
    else:
        atr_score = 1  # 無高低價資料時給中性分。

    total = rsi_score + macd_score + slope_score + atr_score
    return {
        "rsi": rsi_score,
        "macd": macd_score,
        "slope": slope_score,
        "atr": atr_score,
        "total": int(_clamp(total, 0, 25)),
    }


def score_factors(data: Dict) -> Dict[str, int]:
    """AI Score 3.0：量價基本分 75＋技術引擎 25，總分 100。

    Trend 25、Momentum 20、Volume 10、Risk 10、Position 10、Technical 25。
    """
    if not data:
        return {"trend": 0, "momentum": 0, "volume": 0, "risk": 0, "position": 0, "technical": 0}

    price = float(data.get("price", 0) or 0)
    ma5 = float(data.get("ma5", 0) or 0)
    ma10 = float(data.get("ma10", 0) or 0)
    ma20 = float(data.get("ma20", 0) or 0)
    five_pct = float(data.get("five_pct", 0) or 0)
    change_pct = float(data.get("change_pct", 0) or 0)
    volume_ratio = float(data.get("volume_ratio", 0) or 0)
    volatility = float(data.get("volatility", 0) or 0)
    position_20d = float(data.get("position_20d", 50) or 50)

    trend = 0
    trend += 8 if price >= ma20 > 0 else 1
    trend += 6 if ma5 >= ma10 > 0 else 1
    trend += 6 if ma10 >= ma20 > 0 else 1
    if ma20 > 0:
        distance = (price - ma20) / ma20 * 100
        trend += 5 if 0 <= distance <= 10 else (2 if 10 < distance <= 18 else 0)
    trend = int(_clamp(trend, 0, 25))

    if five_pct >= 12:
        momentum = 14
    elif five_pct >= 6:
        momentum = 18
    elif five_pct >= 3:
        momentum = 15
    elif five_pct > 0:
        momentum = 11
    elif five_pct > -3:
        momentum = 7
    elif five_pct > -8:
        momentum = 3
    else:
        momentum = 0
    if 0 < change_pct <= 4:
        momentum += 2
    elif change_pct > 4:
        momentum += 1
    elif change_pct <= -3:
        momentum -= 2
    momentum = int(_clamp(momentum, 0, 20))

    if volume_ratio >= 2.0:
        volume_score = 8
    elif volume_ratio >= 1.4:
        volume_score = 10
    elif volume_ratio >= 1.1:
        volume_score = 8
    elif volume_ratio >= 0.8:
        volume_score = 5
    elif volume_ratio > 0:
        volume_score = 2
    else:
        volume_score = 4
    if change_pct < 0 and volume_ratio >= 1.5:
        volume_score -= 4
    volume_score = int(_clamp(volume_score, 0, 10))

    if volatility <= 1.5:
        risk = 10
    elif volatility <= 2.5:
        risk = 8
    elif volatility <= 4.0:
        risk = 5
    elif volatility <= 6.0:
        risk = 2
    else:
        risk = 0
    if change_pct <= -5:
        risk -= 2
    risk = int(_clamp(risk, 0, 10))

    if 70 <= position_20d <= 92:
        position = 10
    elif 50 <= position_20d < 70:
        position = 7
    elif 92 < position_20d <= 100:
        position = 5
    elif 30 <= position_20d < 50:
        position = 4
    else:
        position = 1

    tech = technical_score(data)
    return {
        "trend": trend,
        "momentum": momentum,
        "volume": volume_score,
        "risk": risk,
        "position": position,
        "technical": tech["total"],
    }


def score_stock(data: Dict) -> int:
    return max(0, min(100, sum(score_factors(data).values())))


def factor_summary(data: Dict) -> str:
    f = data.get("factor_scores") or score_factors(data)
    return (
        f"趨勢 {f.get('trend', 0)}/25｜動能 {f.get('momentum', 0)}/20｜"
        f"量能 {f.get('volume', 0)}/10｜風險 {f.get('risk', 0)}/10｜"
        f"位置 {f.get('position', 0)}/10｜技術 {f.get('technical', 0)}/25"
    )


def technical_summary(data: Dict) -> str:
    t = data.get("technical_scores") or technical_score(data)
    return (
        f"RSI {t.get('rsi', 0)}/7｜MACD {t.get('macd', 0)}/8｜"
        f"斜率 {t.get('slope', 0)}/7｜ATR {t.get('atr', 0)}/3"
    )



def _round_tick(price: float) -> float:
    """Approximate Taiwan stock price tick rounding for display/reference only."""
    price = max(0.0, float(price or 0))
    if price < 10:
        tick = 0.01
    elif price < 50:
        tick = 0.05
    elif price < 100:
        tick = 0.1
    elif price < 500:
        tick = 0.5
    elif price < 1000:
        tick = 1.0
    else:
        tick = 5.0
    return round(round(price / tick) * tick, 2)


def pattern_label(data: Dict) -> str:
    price = float(data.get("price", 0) or 0)
    ma5 = float(data.get("ma5", 0) or 0)
    ma10 = float(data.get("ma10", 0) or 0)
    ma20 = float(data.get("ma20", 0) or 0)
    s5 = float(data.get("ma5_slope_pct", 0) or 0)
    s10 = float(data.get("ma10_slope_pct", 0) or 0)
    s20 = float(data.get("ma20_slope_pct", 0) or 0)
    rsi = float(data.get("rsi14", 50) or 50)
    hist = float(data.get("macd_hist", 0) or 0)
    position = float(data.get("position_20d", 50) or 50)
    five_pct = float(data.get("five_pct", 0) or 0)

    if price >= ma5 >= ma10 >= ma20 > 0 and s5 > 0 and s10 > 0 and s20 > 0:
        if position >= 92 and hist > 0:
            return "突破／主升段"
        return "多頭趨勢"
    if ma20 > 0 and price >= ma20 and price <= max(ma5, ma10) * 1.01 and s20 > 0:
        return "多頭回檔"
    if position >= 95 and (hist < 0 or rsi >= 75):
        return "高檔震盪"
    if price < ma20 and s20 < 0 and hist < 0:
        return "空頭弱勢"
    if abs(five_pct) <= 3 and abs(s20) <= 0.08:
        return "箱型整理"
    return "震盪整理"


def confidence_score(data: Dict) -> int:
    """訊號一致度，不代表勝率。"""
    score = int(data.get("score", score_stock(data)) or 0)
    price = float(data.get("price", 0) or 0)
    ma5 = float(data.get("ma5", 0) or 0)
    ma10 = float(data.get("ma10", 0) or 0)
    ma20 = float(data.get("ma20", 0) or 0)
    rsi = float(data.get("rsi14", 50) or 50)
    macd = float(data.get("macd", 0) or 0)
    signal = float(data.get("macd_signal", 0) or 0)
    hist = float(data.get("macd_hist", 0) or 0)
    slopes = [float(data.get(k, 0) or 0) for k in ("ma5_slope_pct", "ma10_slope_pct", "ma20_slope_pct")]
    atr_pct = float(data.get("atr_pct", 0) or 0)

    bullish = 0
    bearish = 0
    tests = [
        price >= ma20 > 0,
        ma5 >= ma10 >= ma20 > 0,
        macd > signal and hist > 0,
        all(v > 0 for v in slopes),
        50 <= rsi <= 70,
        0 < atr_pct <= 4.5,
    ]
    bullish = sum(bool(x) for x in tests)
    bearish = sum(bool(x) for x in [price < ma20, macd < signal and hist < 0, all(v < 0 for v in slopes), rsi < 42])
    agreement = max(bullish / 6, bearish / 4)
    confidence = 45 + score * 0.35 + agreement * 20
    if bullish >= 4 and bearish >= 2:
        confidence -= 12
    return int(_clamp(round(confidence), 45, 97))


def trade_plan(data: Dict) -> Dict:
    price = float(data.get("price", 0) or 0)
    support = float(data.get("support", 0) or 0)
    resistance = float(data.get("resistance", 0) or 0)
    ma5 = float(data.get("ma5", price) or price)
    ma10 = float(data.get("ma10", price) or price)
    atr = float(data.get("atr14", 0) or 0) or price * 0.025
    score = int(data.get("score", score_stock(data)) or 0)
    rsi = float(data.get("rsi14", 50) or 50)
    hist = float(data.get("macd_hist", 0) or 0)
    slopes_up = all(float(data.get(k, 0) or 0) > 0 for k in ("ma5_slope_pct", "ma10_slope_pct", "ma20_slope_pct"))
    position = float(data.get("position_20d", 50) or 50)
    five_pct = float(data.get("five_pct", 0) or 0)

    pattern = pattern_label(data)
    overheated = rsi >= 75 or five_pct >= 20 or position >= 98
    near_breakout = resistance > 0 and price >= resistance * 0.985

    if score >= 84 and slopes_up and hist > 0 and not overheated:
        decision = "🟢 可分批布局"
    elif score >= 78 and near_breakout and hist > 0 and not overheated:
        decision = "🔵 突破確認後布局"
    elif overheated and score >= 65:
        decision = "🟠 避免追高"
    elif score >= 70:
        decision = "🟡 等待回檔"
    elif score >= 55:
        decision = "⚪ 持續觀察"
    else:
        decision = "🔴 不建議進場"

    # 買點採 MA5/MA10、ATR 與支撐交集，避免直接把現價當唯一進場點。
    base = min(price, max(support, min(ma5, ma10))) if price > 0 else 0
    entry_low = max(support, base - atr * 0.35) if support > 0 else base - atr * 0.35
    entry_high = min(price, base + atr * 0.15)
    if "突破確認" in decision:
        entry_low = max(price, resistance)
        entry_high = entry_low + atr * 0.25
    entry_low = _round_tick(max(0, entry_low))
    entry_high = _round_tick(max(entry_low, entry_high))

    stop = float(data.get("stop_loss", 0) or 0)
    if stop <= 0 or stop >= entry_low:
        stop = max(0, min(support * 0.98 if support else entry_low - atr * 1.2, entry_low - atr * 0.8))
    stop = _round_tick(stop)

    entry_mid = (entry_low + entry_high) / 2 if entry_high else entry_low
    target1 = max(resistance, entry_mid + atr * 1.6)
    target2 = max(target1 + atr * 0.8, entry_mid + atr * 2.6)
    target1 = _round_tick(target1)
    target2 = _round_tick(target2)
    risk = max(0.01, entry_mid - stop)
    reward = max(0, target1 - entry_mid)
    rr = round(reward / risk, 2) if risk > 0 else 0

    # 決策需同時考慮風險報酬，避免高分但買點不划算仍顯示可布局。
    if rr < 1.0 and decision in ("🟢 可分批布局", "🔵 突破確認後布局"):
        decision = "🟠 避免追高" if near_breakout else "🟡 等待回檔"
    elif rr < 1.5 and decision == "🟢 可分批布局":
        decision = "🟡 等待回檔"

    confidence = confidence_score(data)
    return {
        "decision": decision,
        "confidence": confidence,
        "pattern": pattern,
        "entry_low": entry_low,
        "entry_high": entry_high,
        "target1": target1,
        "target2": target2,
        "rr": rr,
    }


def decision_narrative(data: Dict) -> str:
    plan = data.get("trade_plan") or trade_plan(data)
    price = float(data.get("price", 0) or 0)
    ma20 = float(data.get("ma20", 0) or 0)
    rsi = float(data.get("rsi14", 50) or 50)
    hist = float(data.get("macd_hist", 0) or 0)
    volume_ratio = float(data.get("volume_ratio", 0) or 0)
    parts = []
    parts.append("股價站在20日均線之上" if ma20 > 0 and price >= ma20 else "股價仍在20日均線之下")
    parts.append("MACD動能偏多" if hist > 0 else "MACD動能仍偏弱")
    if rsi >= 75:
        parts.append(f"RSI {rsi:.1f} 已偏熱")
    elif 50 <= rsi < 70:
        parts.append(f"RSI {rsi:.1f} 位於健康區")
    else:
        parts.append(f"RSI {rsi:.1f} 尚未轉強")
    if volume_ratio >= 1.1:
        parts.append("量能有配合")
    else:
        parts.append("量能尚未明顯放大")
    return (
        "、".join(parts) + "。"
        f"目前判定為「{plan['pattern']}」，操作建議：{plan['decision']}。"
        f"參考買點 {plan['entry_low']:.2f}～{plan['entry_high']:.2f}，"
        f"停損 {float(data.get('stop_loss', 0) or 0):.2f}，第一目標 {plan['target1']:.2f}；"
        "若價格跌破停損或技術訊號轉弱，應重新評估。"
    )


def reason_lines(data: Dict) -> List[str]:
    if not data:
        return ["資料不足"]

    reasons: List[str] = []
    price = float(data.get("price", 0) or 0)
    ma5 = float(data.get("ma5", 0) or 0)
    ma10 = float(data.get("ma10", 0) or 0)
    ma20 = float(data.get("ma20", 0) or 0)
    five_pct = float(data.get("five_pct", 0) or 0)
    volume_ratio = float(data.get("volume_ratio", 0) or 0)
    volatility = float(data.get("volatility", 0) or 0)
    position_20d = float(data.get("position_20d", 50) or 50)
    rsi14 = float(data.get("rsi14", 0) or 0)
    macd = float(data.get("macd", 0) or 0)
    macd_signal = float(data.get("macd_signal", 0) or 0)
    macd_hist = float(data.get("macd_hist", 0) or 0)
    atr_pct = float(data.get("atr_pct", 0) or 0)
    ma5_slope = float(data.get("ma5_slope_pct", 0) or 0)
    ma10_slope = float(data.get("ma10_slope_pct", 0) or 0)
    ma20_slope = float(data.get("ma20_slope_pct", 0) or 0)

    if price >= ma5 >= ma10 >= ma20 > 0:
        reasons.append("股價與均線呈多頭排列")
    elif price >= ma20 > 0:
        reasons.append("股價站上20日均線")
    else:
        reasons.append("股價仍在20日均線下方")

    if ma5_slope > 0 and ma10_slope > 0 and ma20_slope > 0:
        reasons.append("短中期均線斜率同步向上")
    elif ma5_slope < 0 and ma10_slope < 0 and ma20_slope < 0:
        reasons.append("短中期均線斜率同步向下")

    if five_pct >= 6:
        reasons.append(f"近五日上漲 {five_pct:.1f}%")
    elif five_pct > 0:
        reasons.append(f"近五日小幅走強 {five_pct:.1f}%")
    elif five_pct <= -3:
        reasons.append(f"近五日回落 {abs(five_pct):.1f}%")
    else:
        reasons.append("近五日動能持平")

    if volume_ratio >= 1.4:
        reasons.append(f"成交量為5日均量 {volume_ratio:.1f} 倍")
    elif volume_ratio >= 1.1:
        reasons.append("成交量溫和增加")
    elif volume_ratio > 0:
        reasons.append("成交量未明顯放大")

    if rsi14 >= 75:
        reasons.append(f"RSI {rsi14:.1f} 過熱，追價風險提高")
    elif rsi14 >= 55:
        reasons.append(f"RSI {rsi14:.1f} 動能偏多")
    elif 0 < rsi14 < 42:
        reasons.append(f"RSI {rsi14:.1f} 動能偏弱")

    if macd > macd_signal and macd_hist > 0:
        reasons.append("MACD 多方動能成立")
    elif macd < macd_signal and macd_hist < 0:
        reasons.append("MACD 動能偏弱")

    if atr_pct >= 5:
        reasons.append(f"ATR {atr_pct:.1f}%：短線波動偏高")
    elif 0 < atr_pct <= 3.5:
        reasons.append(f"ATR {atr_pct:.1f}%：波動可控")

    if volatility <= 2.5:
        reasons.append("近期價格波動相對穩定")
    elif volatility >= 4:
        reasons.append("近期價格波動偏高")

    if 70 <= position_20d <= 92:
        reasons.append("位於20日區間強勢但未極端追高")
    elif position_20d > 92:
        reasons.append("接近20日高點，留意追高")

    return reasons[:7]


def ai_comment(data: Dict) -> str:
    if not data:
        return "資料不足，建議稍後再試。"
    return decision_narrative(data)
