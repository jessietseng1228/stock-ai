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
    return (stock_id or "").strip().upper().replace(" ", "")


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




# v15.1 相容名稱：app.py 使用 parse_symbols / normalize_symbol，
# 資料庫欄位仍維持 stock_id，不需要改 Supabase 表結構。
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
