from flask import Flask, request, jsonify

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
    build_ai_history_report,
    build_ai_history_flex,
)
from market_scan import scan_market_top5, market_top5_status
from performance_tracker import update_recommendation_performance
from morning_job import run_morning_report

app = Flask(__name__)

VERSION = "v18.1.2-stable"

STATE_ADD = "WAIT_ADD_STOCK"
STATE_DELETE = "WAIT_DELETE_STOCK"
STATE_ANALYZE = "WAIT_ANALYZE_STOCK"

CMD_MORNING = {"今日早報", "morning_report", "action=morning_report"}
CMD_LIST = {"自選清單", "watchlist", "action=watchlist"}
CMD_ADD = {"加股票", "新增股票", "➕ 加股票", "action=add_stock"}
CMD_DELETE = {"刪股票", "刪除股票", "➖ 刪股票", "action=delete_stock"}
CMD_TOP5 = {"TOP5可買", "🔥 TOP5可買", "top5", "action=top5"}
CMD_ANALYZE = {"個股分析", "📈 個股分析", "analyze", "action=analyze"}
CMD_AI_HISTORY = {"AI歷史", "AI推薦歷史", "ai_history", "action=ai_history"}
CMD_CANCEL = {"取消", "cancel", "離開"}
CMD_DELETE_ALL = {"ALL", "DEL ALL", "DELETE ALL", "全部刪除", "清空", "清空自選"}
ALL_COMMANDS = CMD_MORNING | CMD_LIST | CMD_ADD | CMD_DELETE | CMD_TOP5 | CMD_ANALYZE | CMD_AI_HISTORY | CMD_CANCEL

# v17.4 Stable：不使用背景 thread；Top5 掃描由單一同步 Cron 完成。



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

    if text in CMD_AI_HISTORY:
        clear_user_state(user_id)
        alt, flex, fallback = build_ai_history_flex()
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
    """手動測試入口；正式排程請使用 Render Cron Job 執行 cron_runner.py。"""
    result = run_morning_report()
    http_status = 200 if result.get("failed", 0) == 0 else 500
    return jsonify({"version": VERSION, **result}), http_status


@app.route("/push", methods=["GET", "POST"])
def manual_push_morning_report():
    return cron_push_morning_report()


@app.route("/scan_top5", methods=["GET", "POST"])
@app.route("/scan_top5_cron", methods=["GET", "POST"])
def scan_top5():
    """v17.4 Stable：手動與 Cron 共用的同步批次抓價掃描。"""
    limit = request.args.get("limit", default=None, type=int)
    result = scan_market_top5(limit=limit or 60, save=True)
    return jsonify({
        "status": "ok",
        "version": VERSION,
        "job": "scan_top5",
        "scan_date": result.get("scan_date"),
        "candidate_count": result.get("candidate_count"),
        "scored_count": result.get("scored_count"),
        "saved_count": result.get("saved_count"),
        "batch_empty": result.get("batch_empty"),
        "batch_rows": result.get("batch_rows"),
        "batch_columns": result.get("batch_columns"),
        "fallback_count": result.get("fallback_count"),
        "score_version": result.get("score_version"),
        "history_saved_count": result.get("history_saved_count"),
        "history_error": result.get("history_error"),
    })


@app.route("/update_performance", methods=["GET", "POST"])
@app.route("/update_performance_cron", methods=["GET", "POST"])
def update_performance():
    """v18.1：更新 Top5 推薦的第 1 與第 5 個交易日績效。"""
    limit = request.args.get("limit", default=100, type=int)
    result = update_recommendation_performance(limit=limit or 100)
    return jsonify({"version": VERSION, "job": "update_performance", **result})


@app.route("/top5_status", methods=["GET"])
def top5_status():
    return jsonify({"status": "ok", "version": VERSION, **market_top5_status()})


@app.route("/ai_history", methods=["GET"])
def ai_history_page():
    return build_ai_history_report(), 200, {"Content-Type": "text/plain; charset=utf-8"}


@app.route("/top5", methods=["GET"])
def top5_page():
    return build_top5_report(), 200, {"Content-Type": "text/plain; charset=utf-8"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
