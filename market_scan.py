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
from supabase_db import (
    save_market_top5, get_market_top5, get_latest_market_top5, get_market_top5_meta,
    save_ai_recommend_history, get_completed_ai_learning_history
)
from ai import SCORE_VERSION, score_to_stars, trend_label, trade_plan, decision_narrative
from learning_engine import build_learning_profile, learning_adjustment, LEARNING_VERSION
from decision_engine import apply_decision_engine, DECISION_ENGINE_VERSION

TAIPEI_TZ = timezone(timedelta(hours=8))

# v17.4 Stable：單一 Cron、同步完成、批次抓價。
# 可由 Render Environment 調整，不必改程式。
DEFAULT_CANDIDATE_LIMIT = max(20, int(os.getenv("TOP5_CANDIDATE_LIMIT", "60")))
DEFAULT_STORE_COUNT = max(5, int(os.getenv("TOP5_STORE_COUNT", "20")))
MIN_TURNOVER = max(0, int(os.getenv("TOP5_MIN_TURNOVER", "100000000")))
YF_PERIOD = os.getenv("TOP5_YF_PERIOD", "3mo")
YF_TIMEOUT = max(10, int(os.getenv("TOP5_YF_TIMEOUT", "25")))


TOP5_ALLOWED_DECISIONS = {"🟢 可分批布局", "🔵 突破確認後布局"}


def _top5_entry_filter(data: Dict) -> tuple[bool, str]:
    """v20.6 Top5 硬門檻：只有目前具備進場條件的股票才可入選。"""
    plan = data.get("trade_plan") or {}
    decision = str(plan.get("decision") or data.get("decision") or "").strip()
    rr = float(plan.get("rr", data.get("rr", 0)) or 0)
    entry_low = float(plan.get("entry_low", data.get("entry_low", 0)) or 0)
    entry_high = float(plan.get("entry_high", data.get("entry_high", 0)) or 0)
    stop_loss = float(data.get("stop_loss", 0) or 0)

    if decision not in TOP5_ALLOWED_DECISIONS:
        return False, f"決策排除：{decision or '無明確進場決策'}"
    if rr < 1.0:
        return False, f"風險報酬比不足：{rr:.2f}"
    if entry_low <= 0 or entry_high < entry_low:
        return False, "買點區間無效"
    if stop_loss <= 0 or stop_loss >= entry_low:
        return False, "停損位置無效"
    return True, "符合進場條件"


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
        highs = _clean_numeric(quote.get("high") or [])
        lows = _clean_numeric(quote.get("low") or [])
        if not closes:
            return None
        return {"closes": closes, "volumes": volumes, "highs": highs, "lows": lows}
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



def _extract_yf_taiex_history(frame) -> tuple[List[float], List[str]]:
    """Return aligned TAIEX close/date lists from yfinance output."""
    if frame is None or getattr(frame, "empty", True):
        return [], []
    try:
        closes_series = None
        columns = getattr(frame, "columns", None)
        if getattr(columns, "nlevels", 1) > 1:
            for key in [("Close", "^TWII"), ("^TWII", "Close")]:
                try:
                    closes_series = frame[key]
                    break
                except Exception:
                    pass
        else:
            try:
                closes_series = frame["Close"]
            except Exception:
                closes_series = None
        if closes_series is None:
            return [], []
        values, dates = [], []
        for idx, value in closes_series.items():
            try:
                value = float(value)
                if math.isnan(value) or value <= 0:
                    continue
                dt = idx.to_pydatetime() if hasattr(idx, "to_pydatetime") else idx
                date_text = dt.strftime("%Y-%m-%d") if hasattr(dt, "strftime") else str(idx)[:10]
                values.append(value)
                dates.append(date_text)
            except Exception:
                continue
        return values, dates
    except Exception:
        return [], []


def _month_starts_back(months: int = 6) -> List[datetime]:
    now = datetime.now(TAIPEI_TZ)
    year, month = now.year, now.month
    out = []
    for offset in range(max(1, months)):
        m = month - offset
        y = year
        while m <= 0:
            m += 12
            y -= 1
        out.append(datetime(y, m, 1, tzinfo=TAIPEI_TZ))
    return out


def _roc_date_to_iso(value: str) -> str:
    """TWSE history uses ROC dates such as 115/08/28."""
    text = str(value or "").strip()
    parts = re.split(r"[/.-]", text)
    if len(parts) != 3:
        return text
    try:
        year, month, day = (int(x) for x in parts)
        if year < 1911:
            year += 1911
        return f"{year:04d}-{month:02d}-{day:02d}"
    except Exception:
        return text


def _fetch_taiex_from_twse(months: int = 6) -> tuple[List[float], List[str], str]:
    """Official TWSE monthly TAIEX history fallback when Yahoo returns no data."""
    rows_by_date: Dict[str, float] = {}
    errors: List[str] = []
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; StockAI/21.0.1)",
        "Accept": "application/json,text/plain,*/*",
    }
    for month_start in _month_starts_back(months):
        date_param = month_start.strftime("%Y%m01")
        url = "https://www.twse.com.tw/rwd/zh/TAIEX/MI_5MINS_HIST"
        try:
            resp = requests.get(
                url,
                params={"date": date_param, "response": "json"},
                headers=headers,
                timeout=YF_TIMEOUT,
            )
            resp.raise_for_status()
            payload = resp.json()
            fields = [str(x) for x in (payload.get("fields") or [])]
            data = payload.get("data") or []
            # Standard fields: 日期 / 開盤指數 / 最高指數 / 最低指數 / 收盤指數
            close_idx = next((i for i, name in enumerate(fields) if "收盤" in name), 4 if len(fields) > 4 else -1)
            date_idx = next((i for i, name in enumerate(fields) if "日期" in name), 0)
            if close_idx < 0:
                errors.append(f"{date_param}:close-field-missing")
                continue
            for row in data:
                try:
                    iso_date = _roc_date_to_iso(row[date_idx])
                    close = _to_number(row[close_idx])
                    if iso_date and close > 0:
                        rows_by_date[iso_date] = close
                except Exception:
                    continue
        except Exception as exc:
            errors.append(f"{date_param}:{type(exc).__name__}")
    dates = sorted(rows_by_date)
    closes = [rows_by_date[d] for d in dates]
    return closes, dates, ";".join(errors[-3:])


def detect_market_regime() -> Dict:
    """v21.0.1: TAIEX regime with Yahoo -> Ticker.history -> official TWSE fallback."""
    closes: List[float] = []
    dates: List[str] = []
    source = ""
    source_notes: List[str] = []

    # 1) Existing Yahoo batch path.
    try:
        frame = yf.download(
            tickers="^TWII", period="1y", interval="1d", auto_adjust=False,
            progress=False, threads=False, timeout=YF_TIMEOUT,
        )
        closes, dates = _extract_yf_taiex_history(frame)
        if closes:
            source = "yfinance.download"
        else:
            source_notes.append("yfinance.download=0")
    except Exception as exc:
        source_notes.append(f"yfinance.download={type(exc).__name__}")

    # 2) Yahoo's alternate history path. Some Render/Yahoo combinations fail only on download().
    if len(closes) < 60:
        try:
            frame = yf.Ticker("^TWII").history(period="1y", interval="1d", auto_adjust=False)
            alt_closes, alt_dates = _extract_yf_taiex_history(frame)
            if len(alt_closes) > len(closes):
                closes, dates = alt_closes, alt_dates
                source = "yfinance.Ticker.history"
            if not alt_closes:
                source_notes.append("Ticker.history=0")
        except Exception as exc:
            source_notes.append(f"Ticker.history={type(exc).__name__}")

    # 3) Official TWSE monthly history. This also naturally handles weekends/holidays by
    #    ending on the latest available trading date rather than requiring today's date.
    if len(closes) < 60:
        twse_closes, twse_dates, twse_error = _fetch_taiex_from_twse(months=6)
        if len(twse_closes) > len(closes):
            closes, dates = twse_closes, twse_dates
            source = "TWSE.MI_5MINS_HIST"
        if twse_error:
            source_notes.append(f"TWSE:{twse_error}")

    if len(closes) < 60:
        return {
            "regime": "UNKNOWN",
            "reason": f"TAIEX資料不足({len(closes)}日)",
            "close": round(float(closes[-1]), 2) if closes else 0,
            "market_data_date": dates[-1] if dates else None,
            "source": source or "NONE",
            "source_notes": source_notes,
        }

    close = float(closes[-1])
    ma20 = sum(closes[-20:]) / 20
    ma60 = sum(closes[-60:]) / 60
    ret5 = (close / closes[-6] - 1) * 100 if len(closes) >= 6 and closes[-6] else 0.0
    if close > ma20 > ma60 and ret5 > -1.0:
        regime = "BULL"
    elif close < ma20 < ma60 and ret5 < 1.0:
        regime = "BEAR"
    else:
        regime = "NEUTRAL"

    market_data_date = dates[-1] if dates else None
    reason = (
        f"TAIEX {close:.2f} / MA20 {ma20:.2f} / MA60 {ma60:.2f} / "
        f"5D {ret5:+.2f}% / 資料日 {market_data_date or 'N/A'}"
    )
    return {
        "regime": regime,
        "reason": reason,
        "close": round(close, 2),
        "ma20": round(ma20, 2),
        "ma60": round(ma60, 2),
        "return_5d": round(ret5, 3),
        "market_data_date": market_data_date,
        "source": source or "UNKNOWN",
        "history_days": len(closes),
        "source_notes": source_notes,
    }

def scan_market_top5(limit: int = DEFAULT_CANDIDATE_LIMIT, save: bool = True) -> Dict:
    """從高成交值候選池批次抓歷史行情，產生 Top5。"""
    scan_date = today_taipei()
    requested_limit = max(5, min(int(limit or DEFAULT_CANDIDATE_LIMIT), 150))
    universe = get_market_universe()
    candidates = universe[:requested_limit]
    rows: List[Dict] = []
    learning_rows = get_completed_ai_learning_history(limit=2000)
    learning_profile = build_learning_profile(learning_rows)
    regime_info = detect_market_regime()

    batch = _batch_download(candidates)
    batch_is_empty = bool(batch is None or getattr(batch, "empty", True))
    fallback_data = _fallback_chart_batch(candidates) if batch_is_empty else {}

    for quote in candidates:
        code = quote["symbol"]
        ticker = _yf_ticker(quote)
        closes = _extract_series(batch, ticker, "Close")
        volumes = _extract_series(batch, ticker, "Volume")
        highs = _extract_series(batch, ticker, "High")
        lows = _extract_series(batch, ticker, "Low")
        if not closes and ticker in fallback_data:
            closes = fallback_data[ticker].get("closes", [])
            volumes = fallback_data[ticker].get("volumes", [])
            highs = fallback_data[ticker].get("highs", [])
            lows = fallback_data[ticker].get("lows", [])
        data = _build_data_from_values(ticker, closes, volumes, highs, lows)
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
        data["market_regime"] = regime_info.get("regime", "UNKNOWN")
        data["market_regime_reason"] = regime_info.get("reason", "")

        # v20.5：以歷史 Day+5 表現做受控校正，最多加減 5 分。
        learning = learning_adjustment(data, learning_profile)
        data.update(learning)
        data["score"] = learning["learned_score"]
        data["stars"] = score_to_stars(data["score"])
        data["trend"] = trend_label(data["score"])
        data["trade_plan"] = trade_plan(data)
        data.update(data["trade_plan"])
        data["decision_narrative"] = decision_narrative(data)
        decision_result = apply_decision_engine(data)
        data.update(decision_result)
        data["score"] = decision_result["final_score"]
        data["stars"] = score_to_stars(data["score"])
        data["trend"] = trend_label(data["score"])
        eligible, filter_reason = _top5_entry_filter(data)
        data["top5_eligible"] = eligible
        data["top5_filter_reason"] = filter_reason
        rows.append(data)

    rows.sort(key=lambda item: (item.get("final_score", item.get("score", 0)), item.get("turnover", 0)), reverse=True)
    eligible_rows = [item for item in rows if item.get("top5_eligible")]
    excluded_rows = [item for item in rows if not item.get("top5_eligible")]
    stored_rows = eligible_rows[:DEFAULT_STORE_COUNT]
    saved_count = save_market_top5(scan_date, stored_rows) if save else 0
    history_result = save_ai_recommend_history(scan_date, stored_rows, limit=5) if save else {"saved_count": 0}

    return {
        "status": "ok",
        "scan_date": scan_date,
        "universe_count": len(universe),
        "candidate_count": len(candidates),
        "scored_count": len(rows),
        "eligible_count": len(eligible_rows),
        "excluded_count": len(excluded_rows),
        "saved_count": saved_count,
        "history_saved_count": history_result.get("saved_count", 0),
        "history_error": history_result.get("error"),
        "history_warning": history_result.get("warning"),
        "learning_version": LEARNING_VERSION,
        "learning_ready": learning_profile.get("ready", False),
        "learning_sample_count": (learning_profile.get("overall") or {}).get("count", 0),
        "learning_min_samples": learning_profile.get("auto_apply_min_samples"),
        "learning_shadow_min_samples": learning_profile.get("shadow_min_samples"),
        "learning_mode": learning_profile.get("mode"),
        "learning_guard": learning_profile.get("learning_guard"),
        "duplicate_excluded_count": learning_profile.get("duplicate_excluded_count", 0),
        "market_regime": regime_info.get("regime", "UNKNOWN"),
        "market_regime_reason": regime_info.get("reason", ""),
        "market_regime_meta": regime_info,
        "decision_engine_version": DECISION_ENGINE_VERSION,
        "batch_empty": batch_is_empty,
        "fallback_count": len(fallback_data),
        "score_version": SCORE_VERSION,
        "batch_rows": int(getattr(batch, "shape", (0, 0))[0]) if batch is not None else 0,
        "batch_columns": int(getattr(batch, "shape", (0, 0))[1]) if batch is not None else 0,
        "top5": stored_rows[:5],
        "excluded_preview": [
            {
                "symbol": item.get("symbol"),
                "score": item.get("score"),
                "final_score": item.get("final_score"),
                "risk_level": item.get("risk_level"),
                "decision": (item.get("trade_plan") or {}).get("decision"),
                "reason": item.get("top5_filter_reason"),
            }
            for item in excluded_rows[:10]
        ],
    }


def get_saved_or_scan_top5(auto_scan: bool = False) -> List[Dict]:
    scan_date = today_taipei()
    rows = get_market_top5(scan_date, limit=5)
    if rows:
        return rows

    # v20.7.1：今日已掃描但零入選時，不回退顯示昨日資料。
    today_meta = get_market_top5_meta(scan_date)
    if today_meta.get("has_result"):
        return []

    # 今日尚未掃描（例如午夜後、週末或休市日），才顯示最近一次成功結果。
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
