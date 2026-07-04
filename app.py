from flask import Flask, request
import requests
import os
import yfinance as yf

app = Flask(__name__)

# =========================
# 🟢 LINE 設定
# =========================
LINE_TOKEN = "kGWl+cSBUwKrKWFmvyDCp0kPabfuiCK5Rtcc2SXPX93jJvTA6e0+X5TkySmutdCrJfCBMEP4UFnguW1SObeNdgVTCXEzGurdKUaCwjNxZHOydseQwQh9Md3EJ1OCM/QRWsN6Va56KMP32J8valpqZwdB04t89/1O/w1cDnyilFU="
LINE_API_REPLY = "https://api.line.me/v2/bot/message/reply"
LINE_API_PUSH = "https://api.line.me/v2/bot/message/push"

# 👉 之後從 webhook 取得（先用 debug 拿）
USER_ID = "先填你的USER_ID"

# =========================
# 🟢 前5檔股票
# =========================
TOP_STOCKS = ["2330", "2317", "2454", "2881", "0050"]


# =========================
# 🟢 查股價 function
# =========================
def get_stock_price(code):
    try:
        stock = code + ".TW"
        data = yf.Ticker(stock).history(period="2d")

        if data.empty:
            return "查無資料"

        price = data["Close"].iloc[-1]
        change = price - data["Close"].iloc[-2]
        pct = (change / data["Close"].iloc[-2]) * 100

        # 🧠 簡單原因判斷
        if pct > 2:
            reason = "🔥 強勢上漲"
        elif pct < -2:
            reason = "⚠️ 明顯回檔"
        else:
            reason = "📊 小幅震盪"

        return f"{code}\n價格：{round(price,2)}\n漲跌：{round(change,2)} ({round(pct,2)}%)\n原因：{reason}"

    except Exception as e:
        print("stock error:", e)
        return "查詢失敗"


# =========================
# 🟢 推播 function（早報用）
# =========================
def push_message(text):
    headers = {
        "Authorization": f"Bearer {LINE_TOKEN}",
        "Content-Type": "application/json"
    }

    data = {
        "to": USER_ID,
        "messages": [
            {"type": "text", "text": text}
        ]
    }

    requests.post(LINE_API_PUSH, headers=headers, json=data)


# =========================
# 🟢 產生早報
# =========================
def build_report():
    lines = ["📊 今日股票早報\n"]

    for s in TOP_STOCKS:
        try:
            data = yf.Ticker(s + ".TW").history(period="2d")

            if data.empty:
                continue

            price = data["Close"].iloc[-1]
            change = price - data["Close"].iloc[-2]
            pct = (change / data["Close"].iloc[-2]) * 100

            if pct > 2:
                reason = "🔥 強勢上漲"
            elif pct < -2:
                reason = "⚠️ 明顯回檔"
            else:
                reason = "📊 小幅震盪"

            lines.append(
                f"{s}\n"
                f"價格：{round(price,2)}\n"
                f"漲跌：{round(change,2)} ({round(pct,2)}%)\n"
                f"原因：{reason}\n"
            )

        except:
            continue

    return "\n".join(lines)


# =========================
# 🟢 Render 健康檢查
# =========================
@app.route("/", methods=["GET"])
def home():
    return "OK", 200


# =========================
# 🟢 LINE webhook
# =========================
@app.route("/webhook", methods=["POST"])
def webhook():

    body = request.get_json(silent=True)
    print("🔥 webhook:", body)

    if not body or "events" not in body:
        return "OK", 200

    try:
        event = body["events"][0]

        # 👉 debug USER_ID（只要一次）
        print("USER_ID:", event["source"]["userId"])

        msg = event["message"]["text"].strip()
        reply_token = event["replyToken"]

        # 🟢 判斷邏輯
        if msg.isdigit():
            reply_text = get_stock_price(msg)
        else:
            reply_text = "請輸入股票代號，例如 2330 / 0050"

        headers = {
            "Authorization": f"Bearer {LINE_TOKEN}",
            "Content-Type": "application/json"
        }

        data = {
            "replyToken": reply_token,
            "messages": [
                {"type": "text", "text": reply_text}
            ]
        }

        requests.post(LINE_API_REPLY, headers=headers, json=data)

    except Exception as e:
        print("ERROR:", e)

    return "OK", 200


# =========================
# 🟢 早報 API（給 cron-job 用）
# =========================
@app.route("/push", methods=["GET"])
def push():
    text = build_report()
    push_message(text)
    return "OK"


# =========================
# 🟢 啟動
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)