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
    get_completed_ai_learning_history,
    get_ai_performance_history,
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
    build_performance_report,
)
from market_scan import scan_market_top5, market_top5_status, get_saved_or_scan_top5
from performance_tracker import update_recommendation_performance
from learning_engine import build_learning_profile, LEARNING_VERSION
from performance_analytics import build_performance_analytics, ANALYTICS_VERSION
from morning_job import run_morning_report

app = Flask(__name__)

VERSION = "v20.9-stable"

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
CMD_PERFORMANCE = {"AI績效", "績效驗證", "performance", "action=performance"}
CMD_CANCEL = {"取消", "cancel", "離開"}
CMD_DELETE_ALL = {"ALL", "DEL ALL", "DELETE ALL", "全部刪除", "清空", "清空自選"}
ALL_COMMANDS = CMD_MORNING | CMD_LIST | CMD_ADD | CMD_DELETE | CMD_TOP5 | CMD_ANALYZE | CMD_AI_HISTORY | CMD_PERFORMANCE | CMD_CANCEL

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

    if text in CMD_PERFORMANCE:
        clear_user_state(user_id)
        reply_text(reply_token, build_performance_report())
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


def _scan_response(result: dict, job: str, mode: str, locked: bool = False):
    return jsonify({
        "status": "ok",
        "version": VERSION,
        "job": job,
        "mode": mode,
        "locked": locked,
        "scan_date": result.get("scan_date"),
        "candidate_count": result.get("candidate_count"),
        "scored_count": result.get("scored_count"),
        "eligible_count": result.get("eligible_count"),
        "excluded_count": result.get("excluded_count"),
        "saved_count": result.get("saved_count"),
        "top5": result.get("top5"),
        "excluded_preview": result.get("excluded_preview"),
        "batch_empty": result.get("batch_empty"),
        "batch_rows": result.get("batch_rows"),
        "batch_columns": result.get("batch_columns"),
        "fallback_count": result.get("fallback_count"),
        "score_version": result.get("score_version"),
        "history_saved_count": result.get("history_saved_count"),
        "history_error": result.get("history_error"),
        "history_warning": result.get("history_warning"),
        "learning_version": result.get("learning_version"),
        "learning_ready": result.get("learning_ready"),
        "learning_sample_count": result.get("learning_sample_count"),
        "learning_min_samples": result.get("learning_min_samples"),
        "decision_engine_version": result.get("decision_engine_version"),
        "message": result.get("message"),
    })


@app.route("/scan_top5", methods=["GET", "POST"])
def scan_top5_preview():
    """v20.7.2：手動掃描預設僅預覽，不寫入正式 Top5。"""
    limit = request.args.get("limit", default=None, type=int)
    result = scan_market_top5(limit=limit or 60, save=False)
    result["saved_count"] = 0
    result["history_saved_count"] = 0
    result["message"] = "預覽模式：未寫入 Supabase，不影響正式 Top5。"
    return _scan_response(result, "scan_top5_preview", "preview", locked=False)


@app.route("/scan_top5_cron", methods=["GET", "POST"])
def scan_top5_cron():
    """v20.7.2：正式每日快照；同一天第一次成功後鎖定。"""
    limit = request.args.get("limit", default=None, type=int)
    force = str(request.args.get("force", "0")).strip().lower() in {"1", "true", "yes"}
    status = market_top5_status()

    if status.get("has_result") and not force:
        rows = get_saved_or_scan_top5(auto_scan=False)
        result = {
            "scan_date": status.get("scan_date"),
            "candidate_count": None,
            "scored_count": None,
            "eligible_count": len(rows),
            "excluded_count": None,
            "saved_count": 0,
            "top5": rows,
            "history_saved_count": 0,
            "message": "今日正式 Top5 已鎖定，本次未重新掃描或覆蓋。",
        }
        return _scan_response(result, "scan_top5_cron", "official", locked=True)

    result = scan_market_top5(limit=limit or 60, save=True)
    result["message"] = "正式 Top5 已建立並鎖定。" if not force else "已使用 force=1 強制重算正式 Top5。"
    return _scan_response(result, "scan_top5_cron", "official_force" if force else "official", locked=True)


@app.route("/update_performance", methods=["GET", "POST"])
@app.route("/update_performance_cron", methods=["GET", "POST"])
def update_performance():
    """v18.1：更新 Top5 推薦的第 1 與第 5 個交易日績效。"""
    limit = request.args.get("limit", default=100, type=int)
    result = update_recommendation_performance(limit=limit or 100)
    return jsonify({"version": VERSION, "job": "update_performance", **result})



@app.route("/learning_status", methods=["GET"])
def learning_status():
    """查看歷史樣本、勝率及各分組表現。"""
    limit = request.args.get("limit", default=2000, type=int)
    rows = get_completed_ai_learning_history(limit=limit or 2000)
    profile = build_learning_profile(rows)
    return jsonify({"status": "ok", "version": VERSION, **profile})


@app.route("/performance_status", methods=["GET"])
def performance_status():
    """v20.8：Top5 Day+1 / Day+5 勝率、分數分層、失敗案例與因子觀察。"""
    limit = request.args.get("limit", default=2000, type=int)
    rows = get_ai_performance_history(limit=limit or 2000)
    analytics = build_performance_analytics(rows)
    return jsonify({"status": "ok", "version": VERSION, **analytics})


@app.route("/performance", methods=["GET"])
def performance_page():
    return build_performance_report(), 200, {"Content-Type": "text/plain; charset=utf-8"}

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
