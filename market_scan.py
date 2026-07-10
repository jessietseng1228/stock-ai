from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
import os
import re
import math
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import yfinance as yf

from stock import _build_data_from_values, display_symbol
from supabase_db import save_market_top5, get_market_top5, get_latest_market_top5, get_market_top5_meta
from ai import SCORE_VERSION

TAIPEI_TZ = timezone(timedelta(hours=8))

# v17.4 Stable：單一 Cron、同步完成、批次抓價。
# 可由 Render Environment 調整，不必改程式。
DEFAULT_CANDIDATE_LIMIT = max(20, int(os.getenv("TOP5_CANDIDATE_LIMIT", "60")))
DEFAULT_STORE_COUNT = max(5, int(os.getenv("TOP5_STORE_COUNT", "20")))
MIN_TURNOVER = max(0, int(os.getenv("TOP5_MIN_TURNOVER", "100000000")))
YF_PERIOD = os.getenv("TOP5_YF_PERIOD", "3mo")
YF_TIMEOUT = max(10, int(os.getenv("TOP5_YF_TIMEOUT", "25")))


def today_taipei() -> str:
    return datetime.now(TAIPEI_TZ).strftime("%Y-%m-%d")


def _to_number(value) -> float:
    text = str(value or "").replace(",", "").replace("--", "").strip()
    if not text:
        return 0.0
    try:
        return float(text)
    except Exception:
        return 0.0


def _is_common_stock(code: str, name: str = "") -> bool:
    code = str(code or "").strip()
    name = str(name or "").strip()
    if not re.fullmatch(r"\d{4}", code):
        return False
    bad_words = ["ETF", "ETN", "權證", "牛", "熊", "購", "售", "特", "受益", "指數"]
    return not any(word in name.upper() for word in bad_words)


def fetch_twse_quotes() -> List[Dict]:
    url = "https://www.twse.com.tw/exchangeReport/MI_INDEX"
    params = {"response": "json", "type": "ALLBUT0999"}
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, params=params, headers=headers, timeout=15)
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return []

    rows: List[Dict] = []
    for table in payload.get("tables") or []:
        fields = table.get("fields") or []
        data_rows = table.get("data") or []
        if "證券代號" not in fields or "證券名稱" not in fields:
            continue
        idx_code = fields.index("證券代號")
        idx_name = fields.index("證券名稱")
        idx_value = fields.index("成交金額") if "成交金額" in fields else None
        idx_volume = fields.index("成交股數") if "成交股數" in fields else None
        idx_close = fields.index("收盤價") if "收盤價" in fields else None
        for row in data_rows:
            if len(row) <= max(idx_code, idx_name):
                continue
            code = str(row[idx_code]).strip()
            name = str(row[idx_name]).strip()
            if not _is_common_stock(code, name):
                continue
            rows.append({
                "symbol": code,
                "name": name,
                "market": "TWSE",
                "turnover": _to_number(row[idx_value]) if idx_value is not None and len(row) > idx_value else 0,
                "volume": _to_number(row[idx_volume]) if idx_volume is not None and len(row) > idx_volume else 0,
                "close": _to_number(row[idx_close]) if idx_close is not None and len(row) > idx_close else 0,
            })
    return rows


def fetch_tpex_quotes() -> List[Dict]:
    url = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return []

    rows: List[Dict] = []
    for item in payload if isinstance(payload, list) else []:
        code = str(item.get("SecuritiesCompanyCode") or item.get("代號") or "").strip()
        name = str(item.get("CompanyName") or item.get("名稱") or "").strip()
        if not _is_common_stock(code, name):
            continue
        rows.append({
            "symbol": code,
            "name": name,
            "market": "TPEx",
            "turnover": _to_number(item.get("TransactionAmount") or item.get("成交金額")),
            "volume": _to_number(item.get("TradingShares") or item.get("成交股數")),
            "close": _to_number(item.get("Close") or item.get("收盤")),
        })
    return rows


def get_market_universe() -> List[Dict]:
    rows = fetch_twse_quotes() + fetch_tpex_quotes()
    seen = set()
    clean: List[Dict] = []
    for row in rows:
        code = display_symbol(row.get("symbol", ""))
        if not code or code in seen:
            continue
        if row.get("turnover", 0) < MIN_TURNOVER:
            continue
        seen.add(code)
        row["symbol"] = code
        clean.append(row)
    return sorted(clean, key=lambda item: item.get("turnover", 0), reverse=True)


def _yf_ticker(row: Dict) -> str:
    """上市使用 .TW，上櫃使用 .TWO。"""
    suffix = ".TWO" if str(row.get("market", "")).upper() == "TPEX" else ".TW"
    return f"{row['symbol']}{suffix}"


def _clean_numeric(values) -> List[float]:
    cleaned: List[float] = []
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            cleaned.append(number)
    return cleaned


def _extract_series(batch, ticker: str, field: str) -> List[float]:
    """相容 yfinance 不同版本的單層／多層欄位格式。"""
    if batch is None or getattr(batch, "empty", True):
        return []

    try:
        columns = batch.columns
        if getattr(columns, "nlevels", 1) <= 1:
            if field not in columns:
                return []
            return _clean_numeric(batch[field].tolist())

        # yfinance 可能回 (Ticker, Price) 或 (Price, Ticker)，不依賴固定層級順序。
        for column in columns:
            parts = [str(part) for part in column]
            if ticker in parts and field in parts:
                return _clean_numeric(batch[column].tolist())

        # group_by=ticker 時通常可直接 batch[ticker][field]。
        try:
            frame = batch[ticker]
            if field in frame.columns:
                return _clean_numeric(frame[field].tolist())
        except Exception:
            pass

        return []
    except Exception:
        return []




def _fetch_yahoo_chart(ticker: str) -> Optional[Dict]:
    """yfinance 批次無資料時的備援；直接讀 Yahoo Chart JSON。"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    params = {"range": YF_PERIOD, "interval": "1d"}
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json,text/plain,*/*"}
    try:
        response = requests.get(url, params=params, headers=headers, timeout=12)
        response.raise_for_status()
        payload = response.json()
        result = payload.get("chart", {}).get("result") or []
        if not result:
            return None
        quote = (result[0].get("indicators", {}).get("quote") or [{}])[0]
        closes = _clean_numeric(quote.get("close") or [])
        volumes = _clean_numeric(quote.get("volume") or [])
        if not closes:
            return None
        return {"closes": closes, "volumes": volumes}
    except Exception:
        return None


def _fallback_chart_batch(candidates: List[Dict]) -> Dict[str, Dict]:
    """平行抓取備援行情，避免逐檔等待造成 Render timeout。"""
    results: Dict[str, Dict] = {}
    if not candidates:
        return results
    workers = min(8, max(1, len(candidates)))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_fetch_yahoo_chart, _yf_ticker(row)): _yf_ticker(row) for row in candidates}
        for future in as_completed(futures):
            ticker = futures[future]
            try:
                data = future.result()
            except Exception:
                data = None
            if data:
                results[ticker] = data
    return results

def _batch_download(candidates: List[Dict]):
    tickers = [_yf_ticker(row) for row in candidates]
    if not tickers:
        return None
    return yf.download(
        tickers=tickers,
        period=YF_PERIOD,
        interval="1d",
        group_by="ticker",
        auto_adjust=False,
        progress=False,
        threads=True,
        timeout=YF_TIMEOUT,
    )

def scan_market_top5(limit: int = DEFAULT_CANDIDATE_LIMIT, save: bool = True) -> Dict:
    """從高成交值候選池批次抓歷史行情，產生 Top5。"""
    scan_date = today_taipei()
    requested_limit = max(5, min(int(limit or DEFAULT_CANDIDATE_LIMIT), 150))
    universe = get_market_universe()
    candidates = universe[:requested_limit]
    rows: List[Dict] = []

    batch = _batch_download(candidates)
    batch_is_empty = bool(batch is None or getattr(batch, "empty", True))
    fallback_data = _fallback_chart_batch(candidates) if batch_is_empty else {}

    for quote in candidates:
        code = quote["symbol"]
        ticker = _yf_ticker(quote)
        closes = _extract_series(batch, ticker, "Close")
        volumes = _extract_series(batch, ticker, "Volume")
        if not closes and ticker in fallback_data:
            closes = fallback_data[ticker].get("closes", [])
            volumes = fallback_data[ticker].get("volumes", [])
        data = _build_data_from_values(ticker, closes, volumes)
        if not data:
            continue

        price = float(data.get("price", 0) or 0)
        change_pct = float(data.get("change_pct", 0) or 0)
        five_pct = float(data.get("five_pct", 0) or 0)
        effective_volume = float(data.get("volume", 0) or quote.get("volume", 0) or 0)

        if price <= 0 or change_pct <= -6 or five_pct <= -12:
            continue
        if effective_volume and effective_volume < 300_000:
            continue

        data["name"] = quote.get("name") or data.get("name", "")
        data["title"] = f"{code} {data['name']}" if data.get("name") else code
        data["market"] = quote.get("market", "")
        data["turnover"] = quote.get("turnover", 0)
        data["scan_date"] = scan_date
        rows.append(data)

    rows.sort(key=lambda item: (item.get("score", 0), item.get("turnover", 0)), reverse=True)
    stored_rows = rows[:DEFAULT_STORE_COUNT]
    saved_count = save_market_top5(scan_date, stored_rows) if save else 0

    return {
        "status": "ok",
        "scan_date": scan_date,
        "universe_count": len(universe),
        "candidate_count": len(candidates),
        "scored_count": len(rows),
        "saved_count": saved_count,
        "batch_empty": batch_is_empty,
        "fallback_count": len(fallback_data),
        "score_version": SCORE_VERSION,
        "batch_rows": int(getattr(batch, "shape", (0, 0))[0]) if batch is not None else 0,
        "batch_columns": int(getattr(batch, "shape", (0, 0))[1]) if batch is not None else 0,
        "top5": stored_rows[:5],
    }


def get_saved_or_scan_top5(auto_scan: bool = False) -> List[Dict]:
    scan_date = today_taipei()
    rows = get_market_top5(scan_date, limit=5)
    if rows:
        return rows

    # 跨午夜、週末或休市日：顯示最近一次成功掃描，不再誤導使用者重跑。
    latest_rows = get_latest_market_top5(limit=5)
    if latest_rows:
        return latest_rows

    if auto_scan:
        result = scan_market_top5(save=True)
        return result.get("top5", [])
    return []


def market_top5_status() -> Dict:
    scan_date = today_taipei()
    meta = get_market_top5_meta(scan_date)
    return {"scan_date": scan_date, **meta}
