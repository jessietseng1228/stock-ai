from flask import Flask, request
import requests
import os
import yfinance as yf

app = Flask(__name__)

# =========================
# 🟢 LINE 設定
# =========================
LINE_TOKEN = "kGWl+cSBUwKrKWFmvyDCp0kPabfuiCK5Rtcc2SXPX93jJvTA6e0+X5TkySmutdCrJfCBMEP4UFnguW1SObeNdgVTCXEzGurdKUaCwjNxZHOydseQwQh9Md3EJ1OCM/QRWsN6Va56KMP32J8valpqZwdB04t89/1O/w1cDnyilFU="

LINE_REPLY_API = "https://api.line.me/v2/bot/message/reply"
LINE_PUSH_API = "https://api.line.me/v2/bot/message/push"

USER_ID = "你的USER_ID"


# =========================
# 🟢 查股價（穩定版）
# =========================
def get_stock_price(code):
    try:
        stock = f"{code}.TW"
        data = yf.Ticker(stock).history(period="5d")

        # 防空
        if data is None or data.empty:
            return f"{code}：查無資料（Yahoo限制或代碼錯誤）"

        close = data["Close"].dropna()

        if len(close) < 2:
            return f"{code}：資料不足"

        price = close.iloc[-1]
        prev = close.iloc[-2]

        change = price - prev
        pct = (change / prev) * 100

        # 🧠 簡單判斷原因
        if pct > 2:
            reason = "🔥 強勢上漲"
        elif pct < -2:
            reason = "⚠️ 明顯回檔"
        else:
            reason = "📊 小幅震盪"

        return (
            f"{code}\n"
            f"價格：{round(price,2)}\n"
            f"漲跌：{round(change,2)} ({round(pct,2)}%)\n"
            f"原因：{reason}"
        )

    except Exception as e:
        print("stock error:", repr(e))
        return f"{code}：查詢失敗"


# =========================
# 🟢 LINE 回覆
# =========================
def reply_message(reply_token, text):
    headers = {
        "Authorization": f"Bearer {LINE_TOKEN}",
        "Content-Type": "application/json"
    }

    data = {
        "replyToken": reply_token,
        "messages": [
            {"type": "text", "text": str(text)}
        ]
    }

    requests.post(LINE_REPLY_API, headers=headers, json=data)


# =========================
# 🟢 LINE 推播（早報用）
# =========================
def push_message(text):
    headers = {
        "Authorization": f"Bearer {LINE_TOKEN}",
        "Content-Type": "application/json"
    }

    data = {
        "to": USER_ID,
        "messages": [
            {"type": "text", "text": str(text)}
        ]
    }

    requests.post(LINE_PUSH_API, headers=headers, json=data)


# =========================
# 🟢 早報股票
# =========================
TOP_STOCKS = ["2330", "2317", "2454", "2881", "0050"]


def build_report():
    lines = ["📊 今日股票早報\n"]

    for code in TOP_STOCKS:
        try:
            stock = f"{code}.TW"
            data = yf.Ticker(stock).history(period="5d")

            if data is None or data.empty:
                continue

            close = data["Close"].dropna()

            if len(close) < 2:
                continue

            price = close.iloc[-1]
            prev = close.iloc[-2]

            change = price - prev
            pct = (change / prev) * 100

            if pct > 2:
                reason = "🔥 強勢上漲"
            elif pct < -2:
                reason = "⚠️ 明顯回檔"
            else:
                reason = "📊 小幅震盪"

            lines.append(
                f"{code}\n"
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

    print("webhook:", body)

    if not body or "events" not in body:
        return "OK", 200

    try:
        event = body["events"][0]

        msg = event["message"]["text"].strip()
        reply_token = event["replyToken"]

        # 🟢 查股票
        if msg.isdigit():
            result = get_stock_price(msg)
        else:
            result = "請輸入股票代號，例如 2330、2317、0050"

        reply_message(reply_token, result)

    except Exception as e:
        print("webhook error:", repr(e))

    return "OK", 200


# =========================
# 🟢 cron-job 早報 API
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