from typing import Dict, List

SCORE_VERSION = "AI Score 3.0"
TECH_VERSION = "Technical Engine v19.2"


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

    score = int(data.get("score", score_stock(data)) or 0)
    label = trend_label(score)
    reasons = "、".join(reason_lines(data)[:3])

    if score >= 90:
        advice = "量價與技術訊號一致，但仍應依支撐與停損控管部位。"
    elif score >= 80:
        advice = "整體訊號偏多，可觀察量價延續及短期均線是否守穩。"
    elif score >= 70:
        advice = "偏多因子較多，但仍需等待更理想的進場位置。"
    elif score >= 55:
        advice = "訊號中性，建議等待趨勢或量能更明確。"
    elif score >= 40:
        advice = "量價與技術因子偏弱，宜保守觀察。"
    else:
        advice = "弱勢因子較多，避免急著進場。"

    return f"{label}。{reasons}。{advice}"
