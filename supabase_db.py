import os
from typing import List, Optional
from supabase import create_client, Client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def normalize_symbol(symbol: str) -> str:
    return (symbol or "").strip().upper().replace(" ", "")


def get_all_user_ids() -> List[str]:
    res = supabase.table("user_stocks").select("user_id").execute()
    rows = res.data or []
    return sorted({r["user_id"] for r in rows if r.get("user_id")})


def get_user_stocks(user_id: str) -> List[str]:
    res = (
        supabase.table("user_stocks")
        .select("symbol")
        .eq("user_id", user_id)
        .order("symbol")
        .execute()
    )
    rows = res.data or []
    return [r["symbol"] for r in rows if r.get("symbol")]


def add_user_stock(user_id: str, symbol: str) -> bool:
    symbol = normalize_symbol(symbol)
    if not symbol:
        return False

    exists = (
        supabase.table("user_stocks")
        .select("id")
        .eq("user_id", user_id)
        .eq("symbol", symbol)
        .limit(1)
        .execute()
    )

    if exists.data:
        return True

    supabase.table("user_stocks").insert({
        "user_id": user_id,
        "symbol": symbol
    }).execute()

    return True


def delete_user_stock(user_id: str, symbol: str) -> bool:
    symbol = normalize_symbol(symbol)
    if not symbol:
        return False

    supabase.table("user_stocks") \
        .delete() \
        .eq("user_id", user_id) \
        .eq("symbol", symbol) \
        .execute()

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
        supabase.table("user_state") \
            .update({"state": state}) \
            .eq("user_id", user_id) \
            .execute()
    else:
        supabase.table("user_state").insert({
            "user_id": user_id,
            "state": state
        }).execute()


def clear_user_state(user_id: str) -> None:
    supabase.table("user_state") \
        .delete() \
        .eq("user_id", user_id) \
        .execute()