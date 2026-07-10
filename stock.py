import re
import time
import statistics
from typing import Dict, List, Optional, Tuple
import requests
import yfinance as yf

from ai import ai_comment, score_stock, score_to_stars, trend_label, reason_lines, score_factors, factor_summary, SCORE_VERSION

CACHE_SECONDS = 60 * 10
_CACHE: Dict[str, Tuple[float, Optional[Dict]]] = {}

STOCK_NAMES = {
    "0050": "元大台灣50",
    "0056": "元大高股息",
    "006208": "富邦台50",
    "00878": "國泰永續高股息",
    "00919": "群益台灣精選高息",
    "00929": "復華台灣科技優息",
    "2303": "聯電",
    "2317": "鴻海",
    "2330": "台積電",
    "2344": "華邦電",
    "2353": "宏碁",
    "2357": "華碩",
    "2382": "廣達",
    "2408": "南亞科",
    "2454": "聯發科",
    "2603": "長榮",
    "2609": "陽明",
    "2615": "萬海",
    "2881": "富邦金",
    "2882": "國泰金",
    "2884": "玉山金",
    "2885": "元大金",
    "2886": "兆豐金",
    "2891": "中信金",
    "2892": "第一金",
    "3008": "大立光",
    "3034": "聯詠",
    "3231": "緯創",
    "3661": "世芯-KY",
    "3711": "日月光投控",
    "4904": "遠傳",
    "5871": "中租-KY",
    "5880": "合庫金",
    "6505": "台塑化",
    "6669": "緯穎",
    "2379": "瑞昱",
    "2308": "台達電",
    "2327": "國巨",
    "3017": "奇鋐",
    "3443": "創意",
    "5274": "信驊",
    "6488": "環球晶",
    "2376": "技嘉",
    "2356": "英業達",
    "2345": "智邦",
    "2395": "研華",
    "2449": "京元電子",
    "2618": "長榮航",
    "2606": "裕民",
    "2610": "華航",
    "1216": "統一",
    "1301": "台塑",
    "1303": "南亞",
    "1326": "台化",
    "2002": "中鋼",
    "2207": "和泰車",
    "2301": "光寶科",
    "2412": "中華電",
    "3045": "台灣大",
    "8046": "南電",
    "8069": "元太",
    "8299": "群聯",
    "2360": "致茂",
    "6274": "台燿",
    "6239": "力成",
    "1519": "華城",
    "1605": "華新",
}

ALIASES = {
    "台灣50": "0050", "元大台灣50": "0050",
    "高股息": "0056", "元大高股息": "0056",
    "富邦台50": "006208",
    "國泰永續高股息": "00878", "878": "00878",
    "群益台灣精選高息": "00919", "919": "00919",
    "復華台灣科技優息": "00929", "929": "00929",
    "台積電": "2330", "tsmc": "2330", "台積": "2330",
    "聯電": "2303", "鴻海": "2317", "foxconn": "2317",
    "廣達": "2382", "聯發科": "2454", "mediatek": "2454",
    "緯創": "3231", "世芯": "3661", "世芯ky": "3661",
    "日月光": "3711", "日月光投控": "3711",
    "長榮": "2603", "陽明": "2609", "萬海": "2615",
    "富邦金": "2881", "國泰金": "2882", "玉山金": "2884",
    "元大金": "2885", "兆豐金": "2886", "中信金": "2891", "第一金": "2892",
}


# v16.1：TOP5 可買使用的全市場候選池。
# 先放台灣高成交值/權值/AI/半導體/電子/金融/航運等常見熱門股，
# 之後 v17 可改成自動抓上市櫃成交值排行，再動態擴大掃描。
MARKET_CANDIDATES = [
    "2330", "2317", "2454", "2382", "3231", "6669", "3661", "3034", "3711", "2303",
    "2357", "2379", "2308", "2327", "3017", "3443", "5274", "6488", "2376", "2356",
    "2345", "2395", "3008", "2408", "2344", "2449", "2618", "2603", "2609", "2615",
    "2606", "2610", "2881", "2882", "2884", "2885", "2886", "2891", "2892", "5871",
    "5880", "1216", "1301", "1303", "1326", "2002", "2207", "2301", "2412", "3045",
    "4904", "6505", "8046", "8069", "8299", "2360", "6274", "6239", "1519", "1605",
]


def resolve_symbol(symbol: str) -> str:
    raw = (symbol or "").strip()
    key = raw.lower().replace(" ", "").replace("-", "")
    if key in ALIASES:
        return ALIASES[key]
    return raw


def normalize_symbol(symbol: str) -> str:
    s = resolve_symbol(symbol).strip().upper().replace(" ", "")
    if not s:
        return ""
    s = s.replace(".TW", "").replace(".TWO", "")
    if re.fullmatch(r"\d{4,6}", s):
        return f"{s}.TW"
    return s


def display_symbol(symbol: str) -> str:
    s = normalize_symbol(symbol)
    return s.replace(".TW", "").replace(".TWO", "")


def stock_name(symbol: str) -> str:
    code = display_symbol(symbol)
    return STOCK_NAMES.get(code, "")


def stock_title(symbol: str) -> str:
    code = display_symbol(symbol)
    name = stock_name(code)
    return f"{code} {name}" if name else code


def _ma(values: List[float], days: int) -> float:
    if not values:
        return 0
    part = values[-days:] if len(values) >= days else values
    return sum(part) / len(part)


def _build_data_from_values(yf_symbol: str, closes: List[float], volumes: Optional[List[int]] = None) -> Optional[Dict]:
    closes = [float(x) for x in closes if x is not None]
    if not closes:
        return None

    price = float(closes[-1])
    prev = float(closes[-2]) if len(closes) >= 2 else price
    five_ago = float(closes[-6]) if len(closes) >= 6 else float(closes[0])

    change = price - prev
    change_pct = (change / prev * 100) if prev else 0
    five_pct = ((price - five_ago) / five_ago * 100) if five_ago else 0

    volumes = volumes or []
    volumes = [int(v or 0) for v in volumes]
    volume = volumes[-1] if volumes else 0
    prior_volumes = volumes[-6:-1] if len(volumes) >= 2 else []
    avg_volume = int(sum(prior_volumes) / len(prior_volumes)) if prior_volumes else 0
    volume_ratio = (volume / avg_volume) if avg_volume else 0

    returns = []
    for i in range(max(1, len(closes) - 20), len(closes)):
        previous = closes[i - 1]
        if previous:
            returns.append((closes[i] - previous) / previous * 100)
    volatility = statistics.pstdev(returns) if len(returns) >= 2 else 0

    recent_20 = closes[-20:] if len(closes) >= 20 else closes
    high_20 = max(recent_20) if recent_20 else price
    low_20 = min(recent_20) if recent_20 else price
    position_20d = ((price - low_20) / (high_20 - low_20) * 100) if high_20 > low_20 else 50

    ma5 = _ma(closes, 5)
    ma10 = _ma(closes, 10)
    ma20 = _ma(closes, 20)
    support = min(closes[-10:]) if len(closes) >= 10 else min(closes)
    resistance = max(closes[-10:]) if len(closes) >= 10 else max(closes)
    stop_loss = support * 0.98 if support else price * 0.95

    code = display_symbol(yf_symbol)
    data = {
        "symbol": code,
        "name": stock_name(code),
        "title": stock_title(code),
        "yf_symbol": yf_symbol,
        "price": price,
        "change": change,
        "change_pct": change_pct,
        "five_pct": five_pct,
        "volume": volume,
        "avg_volume": avg_volume,
        "volume_ratio": volume_ratio,
        "volatility": volatility,
        "high_20": high_20,
        "low_20": low_20,
        "position_20d": position_20d,
        "ma5": ma5,
        "ma10": ma10,
        "ma20": ma20,
        "support": support,
        "resistance": resistance,
        "stop_loss": stop_loss,
    }
    data["factor_scores"] = score_factors(data)
    data["score"] = score_stock(data)
    data["score_version"] = SCORE_VERSION
    data["factor_summary"] = factor_summary(data)
    data["stars"] = score_to_stars(data["score"])
    data["trend"] = trend_label(data["score"])
    data["reasons"] = reason_lines(data)
    return data


def _get_stock_data_by_yfinance(yf_symbol: str) -> Optional[Dict]:
    ticker = yf.Ticker(yf_symbol)
    hist = ticker.history(period="2mo", interval="1d", auto_adjust=False)
    if hist is None or hist.empty:
        return None
    close = hist["Close"].dropna()
    if close.empty:
        return None
    volumes = hist["Volume"].dropna().tolist() if "Volume" in hist else []
    return _build_data_from_values(yf_symbol, close.tolist(), volumes)


def _get_stock_data_by_yahoo_chart(yf_symbol: str) -> Optional[Dict]:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yf_symbol}"
    params = {"range": "2mo", "interval": "1d"}
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json,text/plain,*/*"}
    resp = requests.get(url, params=params, headers=headers, timeout=12)
    if resp.status_code != 200:
        return None
    payload = resp.json()
    result = payload.get("chart", {}).get("result") or []
    if not result:
        return None
    quote = (result[0].get("indicators", {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []
    return _build_data_from_values(yf_symbol, closes, volumes)


def get_stock_data(symbol: str, force_refresh: bool = False) -> Optional[Dict]:
    yf_symbol = normalize_symbol(symbol)
    if not yf_symbol:
        return None

    now = time.time()
    if not force_refresh:
        cached = _CACHE.get(yf_symbol)
        if cached and now - cached[0] <= CACHE_SECONDS:
            return cached[1]

    data = None
    for getter in (_get_stock_data_by_yfinance, _get_stock_data_by_yahoo_chart):
        try:
            data = getter(yf_symbol)
            if data:
                break
        except Exception:
            continue

    _CACHE[yf_symbol] = (now, data)
    return data


def analyze_stock(symbol: str) -> str:
    data = get_stock_data(symbol)
    if not data:
        return f"查不到 {symbol} 的股價資料，請確認股票代號是否正確，或稍後再試。"

    arrow = "▲" if data["change"] >= 0 else "▼"
    reasons = "\n".join([f"✔ {r}" for r in data.get("reasons", [])])
    return (
        f"📈 個股分析：{data['title']}\n"
        f"────────────\n"
        f"價格：{data['price']:.2f}\n"
        f"漲跌：{arrow} {data['change']:.2f} ({data['change_pct']:.2f}%)\n"
        f"五日：{data['five_pct']:.2f}%\n"
        f"MA5 / MA10 / MA20：{data['ma5']:.2f} / {data['ma10']:.2f} / {data['ma20']:.2f}\n"
        f"支撐：{data['support']:.2f}\n"
        f"壓力：{data['resistance']:.2f}\n"
        f"停損參考：{data['stop_loss']:.2f}\n"
        f"AI評分：{data['score']} 分 {data['stars']}（{data.get('score_version', SCORE_VERSION)}）\n"
        f"因子：{data.get('factor_summary', factor_summary(data))}\n"
        f"趨勢：{data['trend']}\n"
        f"\nAI理由：\n{reasons}\n"
        f"\nAI分析：\n{ai_comment(data)}\n"
        f"\n提醒：這是量價模型分析，不是投資建議。"
    )


def _is_top5_eligible(data: Dict) -> bool:
    """TOP5 可買的基本過濾：避免把流動性太低或短線過弱的股票排進來。"""
    if not data:
        return False

    price = data.get("price", 0) or 0
    volume = data.get("volume", 0) or 0
    change_pct = data.get("change_pct", 0) or 0
    five_pct = data.get("five_pct", 0) or 0

    if price <= 0:
        return False
    if volume and volume < 300_000:
        return False
    if change_pct <= -6:
        return False
    if five_pct <= -12:
        return False
    return True


def top5_candidates(symbols: Optional[List[str]] = None) -> List[Dict]:
    """
    TOP5 可買：v16.1 起改為「市場候選池」綜合評分，不再使用自選股。
    symbols 參數保留是為了相容舊的呼叫方式，但實際不採用使用者自選清單。
    """
    rows = []
    seen = set()

    for symbol in MARKET_CANDIDATES:
        code = display_symbol(symbol)
        if code in seen:
            continue
        seen.add(code)

        data = get_stock_data(code, force_refresh=True)
        if data and _is_top5_eligible(data):
            rows.append(data)

    return sorted(rows, key=lambda x: x.get("score", 0), reverse=True)[:5]
