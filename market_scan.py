from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
import re
import time
import requests

from stock import get_stock_data, display_symbol
from supabase_db import save_market_top5, get_market_top5, get_market_top5_meta

TAIPEI_TZ = timezone(timedelta(hours=8))

# v17：每天 Cron 預先掃描市場，不再由使用者點擊時即時掃描。
# 預設先取成交值前 300 檔，再做 AI Score，避免 1800 檔逐檔打 Yahoo 造成 Render / LINE timeout。
TOP_TURNOVER_LIMIT = 300
SCAN_SLEEP_SECONDS = 0.03


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
    return not any(w in name.upper() for w in bad_words)


def fetch_twse_quotes() -> List[Dict]:
    """抓上市每日行情。失敗時回傳空清單，不中斷流程。"""
    url = "https://www.twse.com.tw/exchangeReport/MI_INDEX"
    params = {"response": "json", "type": "ALLBUT0999"}
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=20)
        payload = resp.json()
    except Exception:
        return []

    tables = payload.get("tables") or []
    rows: List[Dict] = []
    for table in tables:
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
    """抓上櫃每日行情。失敗時回傳空清單，不中斷流程。"""
    url = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        resp = requests.get(url, headers=headers, timeout=20)
        data_rows = resp.json()
    except Exception:
        return []

    rows: List[Dict] = []
    for item in data_rows if isinstance(data_rows, list) else []:
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
        seen.add(code)
        row["symbol"] = code
        clean.append(row)
    return sorted(clean, key=lambda x: x.get("turnover", 0), reverse=True)


def scan_market_top5(limit: int = TOP_TURNOVER_LIMIT, save: bool = True) -> Dict:
    """
    v17 主流程：
    1. 抓上市櫃行情
    2. 依成交值取前 N 檔
    3. 逐檔抓 K 線並算 AI Score
    4. 存 Supabase market_top5_results
    """
    scan_date = today_taipei()
    universe = get_market_universe()
    candidates = universe[: max(1, int(limit or TOP_TURNOVER_LIMIT))]
    rows: List[Dict] = []

    for q in candidates:
        code = q["symbol"]
        data = get_stock_data(code, force_refresh=True)
        if not data:
            continue
        price = data.get("price", 0) or 0
        volume = data.get("volume", 0) or 0
        change_pct = data.get("change_pct", 0) or 0
        five_pct = data.get("five_pct", 0) or 0
        if price <= 0 or change_pct <= -6 or five_pct <= -12:
            continue
        # 若 Yahoo 回傳 volume 缺漏，使用交易所當日量補判斷。
        effective_volume = volume or q.get("volume", 0)
        if effective_volume and effective_volume < 300_000:
            continue
        data["market"] = q.get("market", "")
        data["turnover"] = q.get("turnover", 0)
        data["scan_date"] = scan_date
        rows.append(data)
        time.sleep(SCAN_SLEEP_SECONDS)

    rows = sorted(rows, key=lambda x: (x.get("score", 0), x.get("turnover", 0)), reverse=True)
    top_rows = rows[:20]
    if save:
        save_market_top5(scan_date, top_rows)

    return {
        "status": "ok",
        "scan_date": scan_date,
        "universe_count": len(universe),
        "candidate_count": len(candidates),
        "scored_count": len(rows),
        "saved_count": len(top_rows),
        "top5": top_rows[:5],
    }


def get_saved_or_scan_top5(auto_scan: bool = False) -> List[Dict]:
    scan_date = today_taipei()
    rows = get_market_top5(scan_date, limit=5)
    if rows:
        return rows
    if auto_scan:
        result = scan_market_top5(save=True)
        return result.get("top5", [])
    return []


def market_top5_status() -> Dict:
    scan_date = today_taipei()
    meta = get_market_top5_meta(scan_date)
    return {"scan_date": scan_date, **meta}
