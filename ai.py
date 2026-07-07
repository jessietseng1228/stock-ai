from typing import Dict, List


def score_to_stars(score: int) -> str:
    """把 0~100 分轉成 1~5 顆星。"""
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


def score_stock(data: Dict) -> int:
    """簡易 AI 評分：短線漲跌、五日動能、量能。"""
    if not data:
        return 0

    score = 50
    five_pct = data.get("five_pct", 0) or 0
    change_pct = data.get("change_pct", 0) or 0
    volume = data.get("volume", 0) or 0
    avg_volume = data.get("avg_volume", 0) or 0

    # 五日動能
    if five_pct >= 8:
        score += 22
    elif five_pct >= 3:
        score += 14
    elif five_pct > 0:
        score += 7
    elif five_pct <= -8:
        score -= 20
    elif five_pct <= -3:
        score -= 12
    elif five_pct < 0:
        score -= 5

    # 今日表現
    if change_pct >= 3:
        score += 14
    elif change_pct > 0:
        score += 7
    elif change_pct <= -3:
        score -= 12
    elif change_pct < 0:
        score -= 6

    # 量能
    if avg_volume and volume > avg_volume * 1.5:
        score += 10
    elif avg_volume and volume > avg_volume * 1.1:
        score += 5
    elif avg_volume and volume < avg_volume * 0.6:
        score -= 5

    return max(0, min(100, int(score)))


def reason_lines(data: Dict) -> List[str]:
    if not data:
        return ["資料不足"]

    reasons: List[str] = []
    five_pct = data.get("five_pct", 0) or 0
    change_pct = data.get("change_pct", 0) or 0
    volume = data.get("volume", 0) or 0
    avg_volume = data.get("avg_volume", 0) or 0

    if five_pct >= 3:
        reasons.append("近五日動能偏強")
    elif five_pct > 0:
        reasons.append("近五日小幅走強")
    elif five_pct <= -3:
        reasons.append("近五日走勢偏弱")
    else:
        reasons.append("近五日變化不大")

    if change_pct > 0:
        reasons.append("今日股價收紅")
    elif change_pct < 0:
        reasons.append("今日股價回檔")
    else:
        reasons.append("今日股價持平")

    if avg_volume and volume > avg_volume * 1.5:
        reasons.append("成交量明顯放大")
    elif avg_volume and volume > avg_volume * 1.1:
        reasons.append("成交量略有增加")
    elif avg_volume and volume < avg_volume * 0.6:
        reasons.append("成交量偏低")

    return reasons[:3]


def ai_comment(data: Dict) -> str:
    if not data:
        return "資料不足，建議稍後再試。"

    score = score_stock(data)
    label = trend_label(score)
    reasons = "、".join(reason_lines(data))

    if score >= 85:
        advice = "短線動能強，但要留意追高與隔日回檔。"
    elif score >= 70:
        advice = "走勢中性偏多，可續觀察是否站穩。"
    elif score >= 55:
        advice = "目前訊號普通，建議等更明確的量價表態。"
    elif score >= 40:
        advice = "短線偏弱，建議保守觀察。"
    else:
        advice = "弱勢訊號較明顯，避免急著進場。"

    return f"{label}。{reasons}。{advice}"
