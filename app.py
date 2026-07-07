from flask import Flask, request, jsonify
import requests
import os
import yfinance as yf
import time

from supabase_db import (
    get_all_user_ids,
    get_user_stocks,
    add_user_stock,
    delete_user_stock
)

app = Flask(__name__)

# =========================
# 📌 LINE 設定（發訊息用）
# =========================
LINE_TOKEN = os.environ.get("LINE_TOKEN")
LINE_PUSH_API = "https://api.line.me/v2/bot/message/push"

# =========================
# 📌 限制設定
# =========================
MAX_STOCKS_PER_USER = 10
MAX_LINE_TEXT_LENGTH = 4000

# =========================
# 📌 防止短時間重複推播
# =========================
_last_push_time = 0


def can_push():
    global _last_push_time
    now = time.time()

    if now - _last_push_time < 300:
        return False

    _last_push_time = now
    return True


# =========================
# 📌 安全錯誤輸出，避免log爆量
# =========================
def log_error(prefix, e):
    print(f"{prefix}: {str(e)[:300]}")


# =========================
# 📌 發 LINE 訊息
# =========================
def push(user, text):
    try:
        if len(text) > MAX_LINE_TEXT_LENGTH:
            text = text[:MAX_LINE_TEXT_LENGTH] + "\n\n⚠️ 內容過長，已截斷"

        res = requests.post(
            LINE_PUSH_API,
            headers={
                "Authorization": f"Bearer {LINE_TOKEN}",
                "Content-Type": "application/json"
            },
            json={
                "to": user,
                "messages": [{"type": "text", "text": text}]
            },
            timeout=10
        )

        if res.status_code >= 400:
            print(f"❌ LINE推播失敗 status={res.status_code}, body={res.text[:300]}")

    except Exception as e:
        log_error("❌ 推播失敗", e)


# =========================
# 📌 抓股票資料（yfinance）
# =========================
def fetch_stock(stock):
    try:
        ticker = yf.Ticker(f"{stock}.TW")
        data = ticker.history(period="5d")

        if data is not None and not data.empty:
            return data, "OK"

        data = ticker.history(period="10d")

        if data is not None and not data.empty:
            return data, "DELAY"

        return None, "FAIL"

    except Exception as e:
        log_error(f"❌ yfinance抓取失敗 {stock}", e)
        return None, "FAIL"


# =========================
# 📌 分析股票
# =========================
def analyze(stock):
    data, status = fetch_stock(stock)

    if status == "FAIL" or data is None:
        return {"stock": stock, "status": "FAIL"}

    close = data["Close"].dropna()

    if len(close) < 2:
        return {"stock": stock, "status": "FAIL"}

    price = float(close.iloc[-1])
    prev = float(close.iloc[-2])

    change = price - prev
    pct = (change / prev) * 100
    pct_5d = (close.iloc[-1] - close.iloc[0]) / close.iloc[0] * 100

    if pct_5d >= 3:
        grade = "🟢強勢"
    elif pct_5d <= -3:
        grade = "🔴弱勢"
    else:
        grade = "🟡普通"

    return {
        "stock": stock,
        "price": price,
        "change": change,
        "pct": pct,
        "pct_5d": pct_5d,
        "grade": grade,
        "status": status
    }


# =========================
# 📌 產生報告（給 LINE 用）
# =========================
def build_report(user):
    stocks = get_user_stocks(user)

    if not stocks:
        return ["⚠️ 你還沒有加入任何股票"]

    total_count = len(stocks)
    stocks = stocks[:MAX_STOCKS_PER_USER]

    results = [analyze(s) for s in stocks]
    ok = any(r["status"] != "FAIL" for r in results)

    lines = ["📊 今日股票早報 v14\n"]

    if total_count > MAX_STOCKS_PER_USER:
        lines.append(f"⚠️ 追蹤股票共 {total_count} 檔，本次先顯示前 {MAX_STOCKS_PER_USER} 檔\n")

    for r in results:
        if r["status"] == "FAIL":
            lines.append(f"{r['stock']} ⚠️資料還沒更新\n")
            continue

        tag = "⏳" if r["status"] == "DELAY" else ""

        lines.append(
            f"{r['stock']} {r['grade']} {tag}\n"
            f"價格：{round(r['price'], 2)}\n"
            f"漲跌：{round(r['change'], 2)} ({round(r['pct'], 2)}%)\n"
            f"5日：{round(r['pct_5d'], 2)}%\n"
        )

    if not ok:
        return ["⚠️ 股票資料還在更新中"]

    return lines


# =========================
# 📌 LINE webhook
# =========================
@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        body = request.get_json(silent=True)

        if not body or "events" not in body or len(body["events"]) == 0:
            return "OK"

        event = body["events"][0]
        user = event["source"]["userId"]

        if event.get("type") != "message" or event.get("message", {}).get("type") != "text":
            return "OK"

        msg = event["message"]["text"].strip().lower()

        if msg.startswith("add "):
            stock = msg.replace("add ", "").strip()
            ok = add_user_stock(user, stock)

            if ok:
                push(user, f"✅ 已加入 {stock.upper()}")
            else:
                push(user, "⚠️ 股票代號不可空白")

        elif msg.startswith("del "):
            stock = msg.replace("del ", "").strip()
            ok = delete_user_stock(user, stock)

            if ok:
                push(user, f"🗑️ 已刪除 {stock.upper()}")
            else:
                push(user, "⚠️ 股票代號不可空白")

        elif msg == "list":
            stocks = get_user_stocks(user)

            if stocks:
                text = "📋 我的自選清單\n" + "\n".join(stocks)
            else:
                text = "⚠️ 沒有股票"

            push(user, text)

        return "OK"

    except Exception as e:
        log_error("❌ webhook錯誤", e)
        return "OK"


# =========================
# 📌 定時推播（Render cron用）
# =========================
@app.route("/push", methods=["GET", "POST"])
@app.route("/cron", methods=["GET", "POST"])
def push_job():
    try:
        #cron test mark
        #if not can_push():
        #    return "SKIP", 200

        users = get_all_user_ids()

        if not users:
            return "EMPTY", 200

        for u in users:
            report = build_report(u)
            text = "\n".join(report)
            push(u, text)

        return "OK", 200

    except Exception as e:
        log_error("❌ push_job錯誤", e)
        return "ERROR", 200


# =========================
# 📌 健康檢查（Render用）
# =========================
@app.route("/")
def home():
    return "OK"


# =========================
# 📌 啟動
# =========================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))