from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Dict, List
import math
import requests

from supabase_db import get_pending_ai_performance, update_ai_performance

TAIPEI_TZ = timezone(timedelta(hours=8))


def _ticker(symbol: str, market: str) -> str:
    suffix = ".TWO" if str(market or "").upper() == "TPEX" else ".TW"
    return f"{symbol}{suffix}"


def _trading_closes_after(ticker: str, scan_date: str) -> List[Dict]:
    """取得推薦日之後的實際交易日收盤價，不以曆日推算。"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    params = {"range": "1mo", "interval": "1d"}
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json,text/plain,*/*"}
    try:
        response = requests.get(url, params=params, headers=headers, timeout=12)
        response.raise_for_status()
        payload = response.json()
        result = (payload.get("chart", {}).get("result") or [])[0]
        timestamps = result.get("timestamp") or []
        quote = (result.get("indicators", {}).get("quote") or [{}])[0]
        closes = quote.get("close") or []
    except Exception:
        return []

    rows: List[Dict] = []
    for ts, close in zip(timestamps, closes):
        try:
            price = float(close)
            if not math.isfinite(price) or price <= 0:
                continue
            trading_date = datetime.fromtimestamp(int(ts), TAIPEI_TZ).strftime("%Y-%m-%d")
        except (TypeError, ValueError, OSError):
            continue
        if trading_date > scan_date:
            rows.append({"date": trading_date, "price": price})
    return rows


def _return_pct(entry: float, current: float) -> float:
    return round((current - entry) / entry * 100, 4) if entry else 0.0


def update_recommendation_performance(limit: int = 100) -> Dict:
    pending = get_pending_ai_performance(limit=limit)
    updated_rows = 0
    day1_updates = 0
    day5_updates = 0
    price_failures = 0

    for row in pending:
        symbol = str(row.get("symbol") or "")
        scan_date = str(row.get("scan_date") or "")
        entry_price = float(row.get("entry_price") or 0)
        if not symbol or not scan_date or entry_price <= 0:
            continue

        trading_rows = _trading_closes_after(_ticker(symbol, row.get("market")), scan_date)
        if not trading_rows:
            price_failures += 1
            continue

        values = {}
        if row.get("day1_price") is None and len(trading_rows) >= 1:
            values.update({
                "day1_date": trading_rows[0]["date"],
                "day1_price": trading_rows[0]["price"],
                "day1_return": _return_pct(entry_price, trading_rows[0]["price"]),
            })
            day1_updates += 1

        if row.get("day5_price") is None and len(trading_rows) >= 5:
            values.update({
                "day5_date": trading_rows[4]["date"],
                "day5_price": trading_rows[4]["price"],
                "day5_return": _return_pct(entry_price, trading_rows[4]["price"]),
            })
            day5_updates += 1

        if values and update_ai_performance(row.get("id"), values):
            updated_rows += 1

    return {
        "status": "ok",
        "pending_count": len(pending),
        "updated_rows": updated_rows,
        "day1_updates": day1_updates,
        "day5_updates": day5_updates,
        "price_failures": price_failures,
    }
