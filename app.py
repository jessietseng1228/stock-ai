from flask import Flask, request, jsonify

from line import reply_text, push_text, get_event_text, get_user_id
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
from report import build_morning_report, build_watchlist_report, build_top5_report, build_single_analysis

app = Flask(__name__)

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


def is_delete_all_text(text: str) -> bool:
    return (text or "").strip().upper() in CMD_DELETE_ALL


@app.route("/", methods=["GET"])
def home():
    return "Stock AI Assistant v15 is running."


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "version": "v15"})


@app.route("/callback", methods=["POST"])
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
        reply_text(reply_token, "請使用下方選單，或輸入股票代號。")
        return

    if text in CMD_CANCEL:
        clear_user_state(user_id)
        reply_text(reply_token, "已取消目前操作。")
        return

    # 1) 先處理等待狀態：加股票 / 刪股票 / 個股分析
    state = get_user_state(user_id)

    if state == STATE_ADD:
        symbols = parse_symbols(text)
        added = add_user_stocks(user_id, symbols)
        if added:
            clear_user_state(user_id)
            reply_text(reply_token, "✅ 已加入：\n" + "\n".join(added))
        else:
            reply_text(reply_token, "股票代號格式不正確，請重新輸入，例如：2330 2317 2454")
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
        reply_text(reply_token, build_single_analysis(text))
        return

    # 2) Rich Menu 指令
    if text in CMD_MORNING:
        stocks = get_user_stocks(user_id)
        reply_text(reply_token, build_morning_report(stocks))
        return

    if text in CMD_LIST:
        stocks = get_user_stocks(user_id)
        reply_text(reply_token, build_watchlist_report(stocks))
        return

    if text in CMD_ADD:
        set_user_state(user_id, STATE_ADD)
        reply_text(reply_token, "請輸入股票代號，可一次多檔，例如：\n2330 2317 2454")
        return

    if text in CMD_DELETE:
        set_user_state(user_id, STATE_DELETE)
        reply_text(reply_token, "請輸入要刪除的股票代號，可一次多檔，例如：\n2330 2317\n\n若要清空，請輸入：全部刪除")
        return

    if text in CMD_TOP5:
        stocks = get_user_stocks(user_id)
        reply_text(reply_token, build_top5_report(stocks))
        return

    if text in CMD_ANALYZE:
        set_user_state(user_id, STATE_ANALYZE)
        reply_text(reply_token, "請輸入要分析的股票代號，例如：2330")
        return

    # 3) 使用者直接輸入股票代號，也支援直接分析
    reply_text(reply_token, build_single_analysis(text))


@app.route("/cron", methods=["GET", "POST"])
def cron_push_morning_report():
    """Render Cron 每天 09:00 呼叫這支。"""
    user_ids = get_all_user_ids()
    sent = 0

    for user_id in user_ids:
        stocks = get_user_stocks(user_id)
        if not stocks:
            continue
        report = build_morning_report(stocks)
        push_text(user_id, report)
        sent += 1

    return jsonify({"status": "ok", "sent": sent})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
