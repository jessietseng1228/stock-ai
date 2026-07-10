import os
import re
from typing import List, Optional
from supabase import create_client, Client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Missing SUPABASE_URL or SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def normalize_stock_id(stock_id: str) -> str:
    """資料庫內統一存台股代號，例如 2330、0050、006208。"""
    s = (stock_id or "").strip().upper().replace(" ", "")
    if not s:
        return ""

    # 允許使用者輸入 2330.TW / 2330.TWO，但 DB 仍只存 2330
    s = s.replace(".TW", "").replace(".TWO", "")

    # 目前先只接受台股常見 4~6 碼數字，避免把「刪除股票」誤加入
    if re.fullmatch(r"\d{4,6}", s):
        return s
    return ""


def parse_stock_ids(text: str) -> List[str]:
    """支援：2330 2317、2330,2317、2330/2317、換行輸入。"""
    raw = (text or "").upper()
    parts = re.split(r"[\s,，、/／;；]+", raw)
    stock_ids: List[str] = []
    for p in parts:
        s = normalize_stock_id(p)
        if s and s not in stock_ids:
            stock_ids.append(s)
    return stock_ids


# v15 相容名稱：app.py 可用 parse_symbols / normalize_symbol

def normalize_symbol(symbol: str) -> str:
    return normalize_stock_id(symbol)


def parse_symbols(text: str) -> List[str]:
    return parse_stock_ids(text)


def get_all_user_ids() -> List[str]:
    """取得所有有自選股的 LINE user_id，供 Cron 推播。"""
    res = supabase.table("user_stocks").select("user_id").execute()
    rows = res.data or []
    return sorted({r["user_id"] for r in rows if r.get("user_id")})


def get_user_stocks(user_id: str) -> List[str]:
    res = (
        supabase.table("user_stocks")
        .select("stock_id")
        .eq("user_id", user_id)
        .order("stock_id")
        .execute()
    )
    rows = res.data or []
    return [r["stock_id"] for r in rows if r.get("stock_id")]


def add_user_stock(user_id: str, stock_id: str) -> bool:
    stock_id = normalize_stock_id(stock_id)
    if not stock_id:
        return False

    exists = (
        supabase.table("user_stocks")
        .select("id")
        .eq("user_id", user_id)
        .eq("stock_id", stock_id)
        .limit(1)
        .execute()
    )
    if exists.data:
        return True

    supabase.table("user_stocks").insert({"user_id": user_id, "stock_id": stock_id}).execute()
    return True


def add_user_stocks(user_id: str, stock_ids: List[str]) -> List[str]:
    added: List[str] = []
    for stock_id in stock_ids:
        s = normalize_stock_id(stock_id)
        if s and add_user_stock(user_id, s):
            added.append(s)
    return added


def delete_user_stock(user_id: str, stock_id: str) -> bool:
    stock_id = normalize_stock_id(stock_id)
    if not stock_id:
        return False

    supabase.table("user_stocks").delete().eq("user_id", user_id).eq("stock_id", stock_id).execute()
    return True


def delete_user_stocks(user_id: str, stock_ids: List[str]) -> List[str]:
    deleted: List[str] = []
    for stock_id in stock_ids:
        s = normalize_stock_id(stock_id)
        if s and delete_user_stock(user_id, s):
            deleted.append(s)
    return deleted


def delete_all_user_stocks(user_id: str) -> bool:
    if not user_id:
        return False
    supabase.table("user_stocks").delete().eq("user_id", user_id).execute()
    return True


def get_user_state(user_id: str) -> Optional[str]:
    res = (
        supabase.table("user_state")
        .select("state")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        return None
    return res.data[0].get("state")


def set_user_state(user_id: str, state: str) -> None:
    existing = (
        supabase.table("user_state")
        .select("id")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if existing.data:
        supabase.table("user_state").update({"state": state}).eq("user_id", user_id).execute()
    else:
        supabase.table("user_state").insert({"user_id": user_id, "state": state}).execute()


def clear_user_state(user_id: str) -> None:
    supabase.table("user_state").delete().eq("user_id", user_id).execute()


# =========================
# v17 market TOP5 results
# =========================

def save_market_top5(scan_date: str, rows: list) -> int:
    """儲存每日市場掃描結果。需要先建立 market_top5_results table。"""
    if not scan_date:
        return 0

    # 同一天重算時先清掉，避免舊排名殘留。
    try:
        supabase.table("market_top5_results").delete().eq("scan_date", scan_date).execute()
    except Exception:
        return 0

    payload = []
    for rank, data in enumerate(rows or [], 1):
        symbol = normalize_stock_id(str(data.get("symbol", "")))
        if not symbol:
            continue
        payload.append({
            "scan_date": scan_date,
            "rank": rank,
            "symbol": symbol,
            "name": data.get("name") or "",
            "score": int(data.get("score", 0) or 0),
            "stars": data.get("stars") or "",
            "trend": data.get("trend") or "",
            "price": float(data.get("price", 0) or 0),
            "change_pct": float(data.get("change_pct", 0) or 0),
            "five_pct": float(data.get("five_pct", 0) or 0),
            "support": float(data.get("support", 0) or 0),
            "resistance": float(data.get("resistance", 0) or 0),
            "stop_loss": float(data.get("stop_loss", 0) or 0),
            "turnover": float(data.get("turnover", 0) or 0),
            "reasons": data.get("reasons") or [],
        })

    if payload:
        supabase.table("market_top5_results").insert(payload).execute()
    return len(payload)


def get_market_top5(scan_date: str, limit: int = 5) -> list:
    try:
        res = (
            supabase.table("market_top5_results")
            .select("*")
            .eq("scan_date", scan_date)
            .order("rank")
            .limit(limit)
            .execute()
        )
    except Exception:
        return []

    rows = []
    for r in res.data or []:
        symbol = normalize_stock_id(str(r.get("symbol", "")))
        title = f"{symbol} {r.get('name')}" if r.get("name") else symbol
        rows.append({
            "symbol": symbol,
            "name": r.get("name") or "",
            "title": title,
            "score": int(r.get("score", 0) or 0),
            "stars": r.get("stars") or "",
            "trend": r.get("trend") or "",
            "price": float(r.get("price", 0) or 0),
            "change": 0,
            "change_pct": float(r.get("change_pct", 0) or 0),
            "five_pct": float(r.get("five_pct", 0) or 0),
            "support": float(r.get("support", 0) or 0),
            "resistance": float(r.get("resistance", 0) or 0),
            "stop_loss": float(r.get("stop_loss", 0) or 0),
            "turnover": float(r.get("turnover", 0) or 0),
            "reasons": r.get("reasons") or [],
            "scan_date": scan_date,
        })
    return rows



def get_latest_market_top5(limit: int = 5) -> list:
    """取得最近一次成功掃描結果，供跨日、週末與休市日使用。"""
    try:
        date_res = (
            supabase.table("market_top5_results")
            .select("scan_date")
            .order("scan_date", desc=True)
            .limit(1)
            .execute()
        )
    except Exception:
        return []

    if not date_res.data:
        return []

    latest_date = str(date_res.data[0].get("scan_date") or "")
    if not latest_date:
        return []
    return get_market_top5(latest_date, limit=limit)

def get_market_top5_meta(scan_date: str) -> dict:
    try:
        res = (
            supabase.table("market_top5_results")
            .select("id,scan_date")
            .eq("scan_date", scan_date)
            .execute()
        )
        return {"has_result": bool(res.data), "count": len(res.data or [])}
    except Exception as e:
        return {"has_result": False, "count": 0, "error": str(e)}
