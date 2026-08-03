import os
import re
import json
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



def _encode_v20_plan(data: dict) -> str:
    plan = data.get("trade_plan") or {}
    if not plan:
        return str(data.get("trend") or "")
    payload = {
        "v": "20.6",
        "decision": plan.get("decision") or data.get("decision") or "",
        "confidence": int(plan.get("confidence", data.get("confidence", 0)) or 0),
        "pattern": plan.get("pattern") or data.get("pattern") or "",
        "entry_low": float(plan.get("entry_low", data.get("entry_low", 0)) or 0),
        "entry_high": float(plan.get("entry_high", data.get("entry_high", 0)) or 0),
        "target1": float(plan.get("target1", data.get("target1", 0)) or 0),
        "target2": float(plan.get("target2", data.get("target2", 0)) or 0),
        "rr": float(plan.get("rr", data.get("rr", 0)) or 0),
        "base_score": int(data.get("base_score", data.get("score", 0)) or 0),
        "learning_adjustment": float(data.get("learning_adjustment", 0) or 0),
        "learning_ready": bool(data.get("learning_ready", False)),
        "learning_sample_count": int(data.get("learning_sample_count", 0) or 0),
        "learning_version": data.get("learning_version") or "Learning Engine v20.5",
    }
    return "V20PLAN:" + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _decode_v20_plan(value) -> dict:
    text = str(value or "")
    if not text.startswith("V20PLAN:"):
        return {}
    try:
        payload = json.loads(text[len("V20PLAN:"):])
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}

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
            "trend": _encode_v20_plan(data),
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
        plan = _decode_v20_plan(r.get("trend"))
        rows.append({
            "symbol": symbol,
            "name": r.get("name") or "",
            "title": title,
            "score": int(r.get("score", 0) or 0),
            "stars": r.get("stars") or "",
            "trend": plan.get("decision") or r.get("trend") or "",
            "decision": plan.get("decision") or "",
            "confidence": int(plan.get("confidence", 0) or 0),
            "pattern": plan.get("pattern") or "",
            "entry_low": float(plan.get("entry_low", 0) or 0),
            "entry_high": float(plan.get("entry_high", 0) or 0),
            "target1": float(plan.get("target1", 0) or 0),
            "target2": float(plan.get("target2", 0) or 0),
            "rr": float(plan.get("rr", 0) or 0),
            "trade_plan": plan,
            "base_score": int(plan.get("base_score", r.get("score", 0)) or 0),
            "learning_adjustment": float(plan.get("learning_adjustment", 0) or 0),
            "learning_ready": bool(plan.get("learning_ready", False)),
            "learning_sample_count": int(plan.get("learning_sample_count", 0) or 0),
            "learning_version": plan.get("learning_version") or "",
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

# =========================
# v18.1 AI recommendation performance history
# =========================

def save_ai_recommend_history(scan_date: str, rows: list, limit: int = 5) -> dict:
    """保存實際展示的 Top5。相同 scan_date + symbol 使用 upsert，不重複新增。"""
    payload = []
    for rank, data in enumerate((rows or [])[:max(1, limit)], 1):
        symbol = normalize_stock_id(str(data.get("symbol", "")))
        if not symbol:
            continue
        factors = data.get("factor_scores") or {}
        payload.append({
            "scan_date": scan_date,
            "symbol": symbol,
            "name": data.get("name") or "",
            "market": data.get("market") or "TWSE",
            "rank": rank,
            "score_version": data.get("score_version") or "AI Score 3.0",
            "ai_score": int(data.get("score", 0) or 0),
            "trend_score": int(factors.get("trend", 0) or 0),
            "momentum_score": int(factors.get("momentum", 0) or 0),
            "volume_score": int(factors.get("volume", 0) or 0),
            "risk_score": int(factors.get("risk", 0) or 0),
            "position_score": int(factors.get("position", 0) or 0),
            "entry_price": float(data.get("price", 0) or 0),
            "base_score": int(data.get("base_score", data.get("score", 0)) or 0),
            "confidence": int(data.get("confidence", (data.get("trade_plan") or {}).get("confidence", 0)) or 0),
            "rr": float(data.get("rr", (data.get("trade_plan") or {}).get("rr", 0)) or 0),
            "pattern": data.get("pattern") or (data.get("trade_plan") or {}).get("pattern") or "",
            "decision": data.get("decision") or (data.get("trade_plan") or {}).get("decision") or "",
            "technical_score": int(factors.get("technical", 0) or 0),
            "learning_adjustment": float(data.get("learning_adjustment", 0) or 0),
            "learning_version": data.get("learning_version") or "Learning Engine v20.5",
        })

    if not payload:
        return {"saved_count": 0}

    try:
        res = (
            supabase.table("ai_recommend_history")
            .upsert(payload, on_conflict="scan_date,symbol")
            .execute()
        )
        return {"saved_count": len(res.data or payload)}
    except Exception as exc:
        # 若尚未執行 v20.5 SQL，先用舊欄位保存，不影響 Top5。
        legacy_keys = {
            "scan_date", "symbol", "name", "market", "rank", "score_version",
            "ai_score", "trend_score", "momentum_score", "volume_score",
            "risk_score", "position_score", "entry_price"
        }
        legacy_payload = [{k: v for k, v in row.items() if k in legacy_keys} for row in payload]
        try:
            res = (
                supabase.table("ai_recommend_history")
                .upsert(legacy_payload, on_conflict="scan_date,symbol")
                .execute()
            )
            return {
                "saved_count": len(res.data or legacy_payload),
                "warning": "v20.5 learning columns missing; run sql/260726_v20_5_learning_engine.sql",
            }
        except Exception:
            return {"saved_count": 0, "error": str(exc)}



def get_completed_ai_learning_history(limit: int = 1000) -> list:
    """取得已完成 Day+5 的歷史資料，供 Learning Engine 統計。"""
    try:
        res = (
            supabase.table("ai_recommend_history")
            .select("*")
            .not_.is_("day5_return", "null")
            .order("scan_date", desc=True)
            .limit(max(1, min(limit, 5000)))
            .execute()
        )
        return res.data or []
    except Exception:
        return []

def get_pending_ai_performance(limit: int = 100) -> list:
    """讀取尚未完成 Day+1 或 Day+5 的紀錄。"""
    try:
        res = (
            supabase.table("ai_recommend_history")
            .select("*")
            .or_("day1_price.is.null,day5_price.is.null")
            .order("scan_date")
            .limit(max(1, min(limit, 500)))
            .execute()
        )
        return res.data or []
    except Exception:
        return []


def update_ai_performance(row_id: int, values: dict) -> bool:
    if not row_id or not values:
        return False
    try:
        supabase.table("ai_recommend_history").update(values).eq("id", row_id).execute()
        return True
    except Exception:
        return False


def get_latest_ai_recommend_history(limit: int = 5) -> list:
    """取得最近一次 Top5 推薦歷史，供 LINE「AI歷史」查詢。"""
    try:
        date_res = (
            supabase.table("ai_recommend_history")
            .select("scan_date")
            .order("scan_date", desc=True)
            .limit(1)
            .execute()
        )
        if not date_res.data:
            return []

        latest_date = str(date_res.data[0].get("scan_date") or "")
        if not latest_date:
            return []

        res = (
            supabase.table("ai_recommend_history")
            .select("*")
            .eq("scan_date", latest_date)
            .order("rank")
            .limit(max(1, min(limit, 20)))
            .execute()
        )
        return res.data or []
    except Exception:
        return []
