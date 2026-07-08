from flask import Flask, request, jsonify
import threading
from datetime import datetime

from line import reply_text, push_text, reply_flex, push_flex, get_event_text, get_user_id
from supabase_db import (
    get_all_user_ids,
    get_user_stocks,
    add_user_stocks,
    delete_user_stocks,
    delete_all_user_stocks,
    get_user_state,
    set_user_state,
    clear_user_state,
    parse_symbols,
)
from report import (
    build_morning_report,
    build_watchlist_report,
    build_top5_report,
    build_single_analysis,
    build_morning_flex,
    build_top5_flex,
    build_single_flex,
)
from market_scan import scan_market_top5, market_top5_status

app = Flask(__name__)

VERSION = "v17.3"

STATE_ADD = "WAIT_ADD_STOCK"
STATE_DELETE = "WAIT_DELETE_STOCK"
STATE_ANALYZE = "WAIT_ANALYZE_STOCK"

CMD_MORNING = {"今日早報", "morning_report", "action=morning_report"}
CMD_LIST = {"自選清單", "watchlist", "action=watchlist"}
CMD_ADD = {"加股票", "新增股票", "➕ 加股票", "action=add_stock"}
CMD_DELETE = {"刪股票", "刪除股票", "➖ 刪股票", "action=delete_stock"}
CMD_TOP5 = {"TOP5可買", "🔥 TOP5可買", "top5", "action=top5"}
CMD_ANALYZE = {"個股分析", "📈 個股分析", "analyze", "action=analyze"}
CMD_CANCEL = {"取消", "cancel", "離開"}
CMD_DELETE_ALL = {"ALL", "DEL ALL", "DELETE ALL", "全部刪除", "清空", "清空自選"}
ALL_COMMANDS = CMD_MORNING | CMD_LIST | CMD_ADD | CMD_DELETE | CMD_TOP5 | CMD_ANALYZE | CMD_CANCEL

# v17.3: Render Cron 測試逾時修正。
# /scan_top5 仍保留手動同步測試；Cron 請改打 /scan_top5_cron，先快速回應，再背景掃描。
SCAN_JOB_LOCK = threading.Lock()
SCAN_JOB_STATUS = {
    "running": False,
    "last_start": None,
    "last_end": None,
    "last_status": None,
    "last_error": None,
}

def _run_scan_job(limit: int | None = None) -> None:
    with SCAN_JOB_LOCK:
        if SCAN_JOB_STATUS.get("running"):
            return
        SCAN_JOB_STATUS.update({
            "running": True,
            "last_start": datetime.now().isoformat(timespec="seconds"),
            "last_end": None,
            "last_status": "running",
            "last_error": None,
        })
    try:
        result = scan_market_top5(limit=limit, save=True)
        with SCAN_JOB_LOCK:
            SCAN_JOB_STATUS.update({
                "running": False,
                "last_end": datetime.now().isoformat(timespec="seconds"),
                "last_status": "ok",
                "last_error": None,
                "last_result": {
                    "scan_date": result.get("scan_date"),
                    "universe_count": result.get("universe_count"),
                    "candidate_count": result.get("candidate_count"),
                    "scored_count": result.get("scored_count"),
                    "saved_count": result.get("saved_count"),
                },
            })
    except Exception as exc:
        with SCAN_JOB_LOCK:
            SCAN_JOB_STATUS.update({
                "running": False,
                "last_end": datetime.now().isoformat(timespec="seconds"),
                "last_status": "error",
                "last_error": str(exc)[:300],
            })



def is_delete_all_text(text: str) -> bool:
    return (text or "").strip().upper() in CMD_DELETE_ALL


def parse_postback_symbol(text: str) -> str:
    if not text.startswith("action=analyze_symbol"):
        return ""
    parts = text.split("symbol=", 1)
    return parts[1].strip() if len(parts) == 2 else ""


@app.route("/", methods=["GET"])
def home():
    return f"Stock AI Assistant {VERSION} is running."


@app.route("/health", methods=["GET"])
@app.route("/status", methods=["GET"])
def health():
    return jsonify({"status": "ok", "version": VERSION})


@app.route("/callback", methods=["POST"])
@app.route("/webhook", methods=["POST"])
def callback():
    body = request.get_json(silent=True) or {}
    events = body.get("events", [])
    for event in events:
        handle_line_event(event)
    return jsonify({"status": "ok"})


def handle_line_event(event: dict) -> None:
    reply_token = event.get("replyToken")
    user_id = get_user_id(event)
    text = get_event_text(event)

    if not reply_token or not user_id:
        return

    if not text:
        reply_text(reply_token, "請使用下方選單，或輸入股票代號 / 股票名稱。")
        return

    symbol_from_button = parse_postback_symbol(text)
    if symbol_from_button:
        clear_user_state(user_id)
        alt, flex, fallback = build_single_flex(symbol_from_button)
        reply_flex(reply_token, alt, flex, fallback)
        return

    # 指令優先於等待狀態，避免卡在「加股票」時把「刪除股票」誤加入。
    if text in CMD_CANCEL:
        clear_user_state(user_id)
        reply_text(reply_token, "已取消目前操作。")
        return

    if text in CMD_MORNING:
        clear_user_state(user_id)
        stocks = get_user_stocks(user_id)
        alt, flex, fallback = build_morning_flex(stocks)
        reply_flex(reply_token, alt, flex, fallback)
        return

    if text in CMD_LIST:
        clear_user_state(user_id)
        stocks = get_user_stocks(user_id)
        reply_text(reply_token, build_watchlist_report(stocks))
        return

    if text in CMD_ADD:
        set_user_state(user_id, STATE_ADD)
        reply_text(reply_token, "請輸入股票代號，可一次多檔，例如：\n2330 2317 2454\n\n若要取消，請輸入：取消")
        return

    if text in CMD_DELETE:
        set_user_state(user_id, STATE_DELETE)
        reply_text(reply_token, "請輸入要刪除的股票代號，可一次多檔，例如：\n2330 2317\n\n若要清空，請輸入：全部刪除\n若要取消，請輸入：取消")
        return

    if text in CMD_TOP5:
        clear_user_state(user_id)
        alt, flex, fallback = build_top5_flex()
        reply_flex(reply_token, alt, flex, fallback)
        return

    if text in CMD_ANALYZE:
        set_user_state(user_id, STATE_ANALYZE)
        reply_text(reply_token, "請輸入要分析的股票代號或股票名稱，例如：2330、台積電、TSMC\n\n若要取消，請輸入：取消")
        return

    state = get_user_state(user_id)

    if state == STATE_ADD:
        symbols = parse_symbols(text)
        added = add_user_stocks(user_id, symbols)
        if added:
            clear_user_state(user_id)
            reply_text(reply_token, "✅ 已加入：\n" + "\n".join(added))
        else:
            reply_text(reply_token, "股票代號格式不正確，請重新輸入，例如：2330 2317 2454\n\n若要取消，請輸入：取消")
        return

    if state == STATE_DELETE:
        if is_delete_all_text(text):
            delete_all_user_stocks(user_id)
            clear_user_state(user_id)
            reply_text(reply_token, "✅ 已清空自選清單")
            return

        symbols = parse_symbols(text)
        deleted = delete_user_stocks(user_id, symbols)
        clear_user_state(user_id)
        if deleted:
            reply_text(reply_token, "✅ 已刪除：\n" + "\n".join(deleted))
        else:
            reply_text(reply_token, "沒有刪除任何股票，請確認代號。")
        return

    if state == STATE_ANALYZE:
        clear_user_state(user_id)
        alt, flex, fallback = build_single_flex(text)
        reply_flex(reply_token, alt, flex, fallback)
        return

    # 使用者直接輸入股票代號 / 股票名稱，也支援直接分析。
    alt, flex, fallback = build_single_flex(text)
    reply_flex(reply_token, alt, flex, fallback)


@app.route("/cron", methods=["GET", "POST"])
def cron_push_morning_report():
    """Render Cron 每天 09:00 呼叫這支。

    v17.2：這支只負責推播早報，不再重新掃描 TOP5。
    TOP5 請由 08:30 的 /scan_top5 預先產生，避免免費 Render 重複大量運算，
    也避免 Cron Response 過大被判定失敗。
    """
    user_ids = get_all_user_ids()
    sent = 0

    for user_id in user_ids:
        stocks = get_user_stocks(user_id)
        if not stocks:
            continue
        alt, flex, fallback = build_morning_flex(stocks)
        push_flex(user_id, alt, flex, fallback)
        sent += 1

    return jsonify({"status": "ok", "version": VERSION, "job": "morning_push", "sent": sent})


@app.route("/push", methods=["GET", "POST"])
def manual_push_morning_report():
    return cron_push_morning_report()


@app.route("/scan_top5", methods=["GET", "POST"])
def manual_scan_top5():
    """手動或 Render Cron 重算 v17 市場 TOP5。

    預設只回傳極短 JSON，避免 Render Cron 出現「輸出過大」。
    若要看明細，請使用 /top5 或 /top5_status。
    可用 /scan_top5?limit=30 控制候選檔數。
    """
    limit = request.args.get("limit", default=None, type=int)
    result = scan_market_top5(limit=limit or 300, save=True)
    return jsonify({
        "status": "ok",
        "version": VERSION,
        "job": "scan_top5",
        "scan_date": result.get("scan_date"),
        "universe_count": result.get("universe_count"),
        "candidate_count": result.get("candidate_count"),
        "scored_count": result.get("scored_count"),
        "saved_count": result.get("saved_count"),
    })


@app.route("/top5_status", methods=["GET"])
def top5_status():
    return jsonify({"status": "ok", "version": VERSION, "scan_job": SCAN_JOB_STATUS, **market_top5_status()})


@app.route("/scan_top5_cron", methods=["GET", "POST"])
def scan_top5_cron():
    """Render Cron 專用：立即回應，背景掃描，避免 Cron 測試逾時。"""
    try:
        limit = int(request.args.get("limit", "0") or 0)
    except Exception:
        limit = 0

    with SCAN_JOB_LOCK:
        if SCAN_JOB_STATUS.get("running"):
            return (
                f"ok version={VERSION} job=scan_top5_cron status=already_running\n",
                200,
                {"Content-Type": "text/plain; charset=utf-8"},
            )

    thread = threading.Thread(target=_run_scan_job, kwargs={"limit": limit or None}, daemon=True)
    thread.start()
    return (
        f"ok version={VERSION} job=scan_top5_cron status=accepted limit={limit or 'default'}\n",
        200,
        {"Content-Type": "text/plain; charset=utf-8"},
    )


@app.route("/top5", methods=["GET"])
def top5_page():
    return build_top5_report(), 200, {"Content-Type": "text/plain; charset=utf-8"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
