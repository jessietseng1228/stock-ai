from typing import Dict, List

SCORE_VERSION = "AI Score 2.0"


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def score_to_stars(score: int) -> str:
    score = max(0, min(100, int(score or 0)))
    if score >= 85:
        full = 5
    elif score >= 70:
        full = 4
    elif score >= 55:
        full = 3
    elif score >= 40:
        full = 2
    else:
        full = 1
    return "★" * full + "☆" * (5 - full)


def trend_label(score: int) -> str:
    score = int(score or 0)
    if score >= 85:
        return "強勢偏多"
    if score >= 70:
        return "中性偏多"
    if score >= 55:
        return "震盪觀察"
    if score >= 40:
        return "偏弱整理"
    return "短線弱勢"


def score_factors(data: Dict) -> Dict[str, int]:
    """AI Score 2.0：五大可解釋因子，總分 100。

    Trend 30、Momentum 25、Volume 15、Risk 15、Position 15。
    v18.1 再加入法人籌碼，避免 v18.0 假裝已有不存在的資料。
    """
    if not data:
        return {"trend": 0, "momentum": 0, "volume": 0, "risk": 0, "position": 0}

    price = float(data.get("price", 0) or 0)
    ma5 = float(data.get("ma5", 0) or 0)
    ma10 = float(data.get("ma10", 0) or 0)
    ma20 = float(data.get("ma20", 0) or 0)
    five_pct = float(data.get("five_pct", 0) or 0)
    change_pct = float(data.get("change_pct", 0) or 0)
    volume_ratio = float(data.get("volume_ratio", 0) or 0)
    volatility = float(data.get("volatility", 0) or 0)
    position_20d = float(data.get("position_20d", 50) or 50)

    # 趨勢 30：價格與均線排列，不以單日暴漲取代趨勢。
    trend = 0
    trend += 10 if price >= ma20 > 0 else 2
    trend += 8 if ma5 >= ma10 > 0 else 2
    trend += 8 if ma10 >= ma20 > 0 else 2
    if ma20 > 0:
        distance = (price - ma20) / ma20 * 100
        trend += 4 if 0 <= distance <= 12 else (2 if distance > 12 else 0)

    # 動能 25：五日為主、當日為輔；過熱不給滿分。
    if five_pct >= 12:
        momentum = 19
    elif five_pct >= 6:
        momentum = 22
    elif five_pct >= 3:
        momentum = 18
    elif five_pct > 0:
        momentum = 14
    elif five_pct > -3:
        momentum = 9
    elif five_pct > -8:
        momentum = 4
    else:
        momentum = 0
    if 0 < change_pct <= 4:
        momentum += 3
    elif change_pct > 4:
        momentum += 1
    elif change_pct <= -3:
        momentum -= 3
    momentum = int(_clamp(momentum, 0, 25))

    # 量能 15：量增配合走強最佳；爆量但下跌不加分。
    if volume_ratio >= 2.0:
        volume_score = 13
    elif volume_ratio >= 1.5:
        volume_score = 15
    elif volume_ratio >= 1.1:
        volume_score = 12
    elif volume_ratio >= 0.8:
        volume_score = 8
    elif volume_ratio > 0:
        volume_score = 4
    else:
        volume_score = 6  # 無量資料時給中性分，不假設零成交。
    if change_pct < 0 and volume_ratio >= 1.5:
        volume_score -= 5
    volume_score = int(_clamp(volume_score, 0, 15))

    # 風險 15：近 20 日報酬波動率越低越穩；極端單日跌幅扣分。
    if volatility <= 1.5:
        risk = 15
    elif volatility <= 2.5:
        risk = 12
    elif volatility <= 4.0:
        risk = 8
    elif volatility <= 6.0:
        risk = 4
    else:
        risk = 1
    if change_pct <= -5:
        risk -= 3
    risk = int(_clamp(risk, 0, 15))

    # 位置 15：接近 20 日高點但不完全追高，分數最佳。
    if 70 <= position_20d <= 95:
        position = 15
    elif 50 <= position_20d < 70:
        position = 11
    elif 95 < position_20d <= 100:
        position = 10
    elif 30 <= position_20d < 50:
        position = 7
    else:
        position = 3

    return {
        "trend": int(_clamp(trend, 0, 30)),
        "momentum": momentum,
        "volume": volume_score,
        "risk": risk,
        "position": position,
    }


def score_stock(data: Dict) -> int:
    return max(0, min(100, sum(score_factors(data).values())))


def factor_summary(data: Dict) -> str:
    f = data.get("factor_scores") or score_factors(data)
    return (
        f"趨勢 {f.get('trend', 0)}/30｜動能 {f.get('momentum', 0)}/25｜"
        f"量能 {f.get('volume', 0)}/15｜風險 {f.get('risk', 0)}/15｜"
        f"位置 {f.get('position', 0)}/15"
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

    if price >= ma5 >= ma10 >= ma20 > 0:
        reasons.append("均線呈多頭排列")
    elif price >= ma20 > 0:
        reasons.append("股價站上20日均線")
    else:
        reasons.append("股價仍在20日均線下方")

    if five_pct >= 6:
        reasons.append(f"近五日上漲 {five_pct:.1f}%")
    elif five_pct > 0:
        reasons.append(f"近五日小幅走強 {five_pct:.1f}%")
    elif five_pct <= -3:
        reasons.append(f"近五日回落 {abs(five_pct):.1f}%")
    else:
        reasons.append("近五日動能持平")

    if volume_ratio >= 1.5:
        reasons.append(f"成交量為5日均量 {volume_ratio:.1f} 倍")
    elif volume_ratio >= 1.1:
        reasons.append("成交量溫和增加")
    elif volume_ratio > 0:
        reasons.append("成交量未明顯放大")

    if volatility <= 2.5:
        reasons.append("近期波動相對穩定")
    elif volatility >= 4:
        reasons.append("近期波動偏高")

    if 70 <= position_20d <= 95:
        reasons.append("位於20日區間相對強勢位置")
    elif position_20d > 95:
        reasons.append("接近20日高點，留意追高")

    return reasons[:5]


def ai_comment(data: Dict) -> str:
    if not data:
        return "資料不足，建議稍後再試。"

    score = int(data.get("score", score_stock(data)) or 0)
    label = trend_label(score)
    reasons = "、".join(reason_lines(data)[:3])

    if score >= 85:
        advice = "多因子訊號強，但仍應依支撐與停損控制追高風險。"
    elif score >= 70:
        advice = "多因子偏多，可觀察量價是否延續並守住短期均線。"
    elif score >= 55:
        advice = "訊號中性，建議等待趨勢或量能更明確。"
    elif score >= 40:
        advice = "因子偏弱，宜保守觀察。"
    else:
        advice = "弱勢因子較多，避免急著進場。"

    return f"{label}。{reasons}。{advice}"
