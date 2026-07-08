import re
import time
from typing import Dict, List, Optional, Tuple
import requests
import yfinance as yf

from ai import ai_comment, score_stock, score_to_stars, trend_label, reason_lines

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
    recent_volumes = volumes[-5:] if volumes else []
    avg_volume = int(sum(recent_volumes) / len(recent_volumes)) if recent_volumes else 0

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
        "ma5": ma5,
        "ma10": ma10,
        "ma20": ma20,
        "support": support,
        "resistance": resistance,
        "stop_loss": stop_loss,
    }
    data["score"] = score_stock(data)
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
        f"AI評分：{data['score']} 分 {data['stars']}\n"
        f"趨勢：{data['trend']}\n"
        f"\nAI理由：\n{reasons}\n"
        f"\nAI分析：\n{ai_comment(data)}\n"
        f"\n提醒：這是量價模型分析，不是投資建議。"
    )


def top5_candidates(symbols: List[str]) -> List[Dict]:
    rows = []
    for symbol in symbols:
        data = get_stock_data(symbol, force_refresh=True)
        if data:
            rows.append(data)
    return sorted(rows, key=lambda x: x.get("score", 0), reverse=True)[:5]
