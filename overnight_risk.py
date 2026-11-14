"""Read-only pre-open risk observation."""

import csv
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta, timezone
from io import StringIO
from math import isfinite
import re
from threading import Lock
from time import monotonic
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup


TAIPEI = timezone(timedelta(hours=8), "Asia/Taipei")
NEW_YORK = ZoneInfo("America/New_York")
TAIFEX_URL = "https://www.taifex.com.tw/cht/3/futDailyMarketExcel?marketCode=1"
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
SOURCES = {
    "tx": ("TAIFEX TX 盤後", "最近月單式合約，期交所盤後漲跌幅（同合約盤後開盤參考價）"),
    "sp500": ("FRED SP500 正規收盤", "相對前一美股交易日正規收盤"),
    "nasdaq": ("FRED NASDAQCOM 正規收盤", "相對前一美股交易日正規收盤"),
}
# TWSE、NYSE 和 Nasdaq 公告的全日休市。超出涵蓋年份時停止判定。
TW_HOLIDAYS = {
    2026: "0101 0212 0213 0216 0217 0218 0219 0220 0227 0403 0406 0501 0619 0925 0928 1009 1026 1225",
    2027: "0101 0202 0203 0204 0205 0208 0209 0210 0301 0405 0406 0430 0609 0915 0928 1011 1025 1224 1231",
}
US_HOLIDAYS = {
    2026: "0101 0119 0216 0403 0525 0619 0703 0907 1126 1225",
    2027: "0101 0118 0215 0326 0531 0618 0705 0906 1125 1224",
}
US_EARLY_CLOSE = {date(2026, 11, 27), date(2026, 12, 24), date(2027, 11, 26)}
MEDIUM_DROP_PCT = 0.5
HIGH_DROP_PCT = 1.5
_CACHE_LOCK = Lock()
_cached = None


def _trading_day(day, holidays):
    return day.year in holidays and day.weekday() < 5 and day.strftime("%m%d") not in holidays[day.year].split()


def _previous_trading_day(day, holidays):
    day -= timedelta(days=1)
    while day.year in holidays:
        if _trading_day(day, holidays):
            return day
        day -= timedelta(days=1)
    return None


def _us_close(day):
    return datetime.combine(day, time(13 if day in US_EARLY_CLOSE else 16), NEW_YORK)


def _source(key, status="unavailable", **fields):
    name, basis = SOURCES[key]
    return {
        "source": name, "basis": basis, "status": status,
        "market_data_time": None, "value": None, "change_pct": None,
        "is_stale": status == "stale", **fields,
    }


def _number(text):
    try:
        value = float(text.strip().translate(str.maketrans("", "", ",%▲▼")))
        return value if isfinite(value) else None
    except (AttributeError, ValueError):
        return None


def _fetch_tx(day, previous, now):
    if previous is None or now < datetime.combine(previous + timedelta(days=1), time(5), TAIPEI):
        return _source("tx", detail="session_not_complete")
    response = requests.get(TAIFEX_URL, timeout=4)
    response.raise_for_status()
    page = BeautifulSoup(response.content, "html.parser", from_encoding="utf-8")
    text = page.get_text(" ", strip=True)
    attribution = re.search(r"日期[：:]\s*(\d{4}/\d{2}/\d{2})", text)
    session = re.search(r"(\d{4}/\d{2}/\d{2})\s+15:00\s*[~～]\s*次日\s*05:00\s+盤後交易時段行情表", text)
    if not attribution or not session:
        return _source("tx", detail="night_session_unverified")
    trade_date = date.fromisoformat(attribution[1].replace("/", "-"))
    start = date.fromisoformat(session[1].replace("/", "-"))
    close = datetime.combine(start + timedelta(days=1), time(5), TAIPEI)
    timestamp = {"market_data_time": close.isoformat(), "trade_date": trade_date.isoformat()}
    if trade_date > day or close > now:
        return _source("tx", detail="session_not_complete")
    if trade_date != day or start != previous:
        return _source("tx", "stale", detail="session_date_mismatch", **timestamp)

    contracts = {}
    caption = page.find(string=re.compile("盤後交易時段行情表"))
    table = caption.find_next("table") if caption else None
    if table is None:
        return _source("tx", detail="night_table_missing", **timestamp)
    for row in table.select("tr"):
        cells = [cell.get_text(strip=True) for cell in row.find_all("td", recursive=False)]
        if len(cells) == 15 and cells[0] == "TX" and re.fullmatch(r"\d{6}", cells[1]):
            contracts[cells[1]] = cells
    if not contracts:
        return _source("tx", detail="contract_missing", **timestamp)
    contract = min(contracts)
    cells = contracts[contract]
    value, change, volume = map(_number, (cells[5], cells[7], cells[8]))
    if not value or value < 0 or change is None or not volume or volume < 0 or cells[9] != "-":
        return _source("tx", detail="night_close_missing", contract=contract, **timestamp)
    return _source("tx", "ok", contract=contract, value=value, change_pct=change, **timestamp)


def _fetch_us(day, previous, now):
    opening = datetime.combine(day, time(9), TAIPEI)
    expected = _previous_trading_day(opening.astimezone(NEW_YORK).date() + timedelta(days=1), US_HOLIDAYS)
    keys = {"sp500": "SP500", "nasdaq": "NASDAQCOM"}
    if expected is None or previous is None:
        return {key: _source(key, detail="calendar_unavailable") for key in keys}
    if _us_close(expected) > min(now, opening):
        return {key: _source(key, detail="session_not_complete") for key in keys}
    prior = _previous_trading_day(expected, US_HOLIDAYS)
    if prior is None:
        return {key: _source(key, detail="calendar_unavailable") for key in keys}

    response = requests.get(FRED_URL, params={
        "id": "SP500,NASDAQCOM", "cosd": prior.isoformat(), "coed": expected.isoformat(),
    }, timeout=4)
    response.raise_for_status()
    observations = {}
    for row in csv.DictReader(StringIO(response.text)):
        observed = date.fromisoformat(row["observation_date"])
        if observed <= expected:
            observations[observed] = row

    results = {}
    for key, column in keys.items():
        latest = max((d for d, row in observations.items()
                      if _trading_day(d, US_HOLIDAYS) and (_number(row[column]) or 0) > 0), default=None)
        if latest is None:
            results[key] = _source(key, detail="close_missing")
            continue
        close = _us_close(latest)
        timestamp = {"market_data_time": close.isoformat(), "trade_date": latest.isoformat()}
        if latest != expected or close < datetime.combine(previous, time(15), TAIPEI):
            results[key] = _source(key, "stale", detail="session_date_mismatch", **timestamp)
            continue
        base = _number(observations.get(prior, {}).get(column))
        value = _number(observations[latest][column])
        results[key] = (
            _source(key, "ok", value=value, change_pct=round((value / base - 1) * 100, 3), **timestamp)
            if base and base > 0 else _source(key, detail="previous_close_missing", **timestamp)
        )
    return results


def assess_risk(sources, medium_drop=MEDIUM_DROP_PCT, high_drop=HIGH_DROP_PCT):
    """下跌幅度使用百分點。資料不齊時，保留可用資料但不判定整體風險。"""
    if not 0 < medium_drop < high_drop or not isfinite(high_drop):
        raise ValueError("Expected 0 < medium_drop < high_drop")
    missing = [item["source"] for item in sources.values() if item["status"] != "ok"]
    if missing:
        return "資料不足", [f"{name}缺少當期已完成行情" for name in missing]
    declines = [item for item in sources.values() if item["change_pct"] <= -medium_drop]
    reasons = [f"{item['source']} {item['change_pct']:+.2f}%" for item in declines]
    if len(declines) >= 2 or any(item["change_pct"] <= -high_drop for item in declines):
        return "高", reasons
    if declines:
        return "中", reasons
    return "低", ["各來源跌幅未達觀測門檻"]


def collect_overnight_risk(now):
    now = now.astimezone(TAIPEI)
    day = now.date()
    is_trading_day = _trading_day(day, TW_HOLIDAYS)
    if is_trading_day:
        previous = _previous_trading_day(day, TW_HOLIDAYS)
        # 兩個獨立來源並行，個別失敗照常呈現其他行情。
        with ThreadPoolExecutor(max_workers=2) as pool:
            tx = pool.submit(_fetch_tx, day, previous, now)
            us = pool.submit(_fetch_us, day, previous, now)
            sources = {}
            for future, keys in ((tx, ("tx",)), (us, ("sp500", "nasdaq"))):
                try:
                    result = future.result()
                    sources.update({"tx": result} if keys == ("tx",) else result)
                except (requests.RequestException, ValueError, KeyError, TypeError):
                    sources.update({key: _source(key, detail="source_error") for key in keys})
        level, reasons = assess_risk(sources)
    else:
        detail = "market_closed" if day.year in TW_HOLIDAYS else "calendar_unavailable"
        sources = {key: _source(key, detail=detail) for key in SOURCES}
        level, reasons = "資料不足", ["台股休市" if detail == "market_closed" else "台股交易日曆未涵蓋此日期"]
    return {
        "as_of": {"taipei_time": now.isoformat(timespec="seconds"),
                  "trade_date": day.isoformat() if is_trading_day else None},
        "sources": sources, "risk_level": level, "risk_reasons": reasons, "mode": "shadow",
    }


def get_overnight_risk():
    global _cached
    with _CACHE_LOCK:
        now = datetime.now(TAIPEI)
        stamp = monotonic()
        # 同一程序一分鐘內共享結果；跨日及收盤邊界重新查詢。
        bucket = (now.date(), now.hour, now.minute)
        if _cached is None or _cached[0] != bucket or stamp - _cached[1] >= 60:
            _cached = (bucket, stamp, collect_overnight_risk(now))
        return _cached[2]


def format_overnight_summary(risk):
    labels = {"tx": "台指期夜盤", "sp500": "S&P 500", "nasdaq": "Nasdaq"}
    lines = [f"隔夜市場風險｜{risk['risk_level']}"]
    for key, item in risk["sources"].items():
        market_time = item["market_data_time"]
        suffix = datetime.fromisoformat(market_time).astimezone(TAIPEI).strftime("（%m/%d %H:%M 台北）") if market_time else ""
        change = f"{item['change_pct']:+.2f}%" if item["status"] == "ok" else (
            "資料過期" if item["is_stale"] else "不可用"
        )
        contract = f" TX{item['contract']}" if item.get("contract") else ""
        lines.append(f"{labels[key]}{contract} {change}{suffix}")
    lines.append("開盤風險觀測｜非買賣訊號")
    return "\n".join(lines)
