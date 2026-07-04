from flask import Flask, request
import requests
import os
import yfinance as yf

app = Flask(__name__)

LINE_TOKEN = "kGWl+cSBUwKrKWFmvyDCp0kPabfuiCK5Rtcc2SXPX93jJvTA6e0+X5TkySmutdCrJfCBMEP4UFnguW1SObeNdgVTCXEzGurdKUaCwjNxZHOydseQwQh9Md3EJ1OCM/QRWsN6Va56KMP32J8valpqZwdB04t89/1O/w1cDnyilFU="
LINE_API = "https://api.line.me/v2/bot/message/reply"


@app.route("/", methods=["GET"])
def home():
    return "OK", 200


def get_price(stock):
    try:
        data = yf.Ticker(stock).history(period="1d")
        price = data["Close"].iloc[-1]
        return round(price, 2)
    except:
        return None


@app.route("/webhook", methods=["POST"])
def webhook():

    body = request.get_json(silent=True)
    print("🔥 webhook:", body)

    if not body or "events" not in body:
        return "OK", 200

    try:
        event = body["events"][0]
        reply_token = event["replyToken"]
        msg = event["message"]["text"]

        reply_text = ""

        # 🟢 股票判斷邏輯
        if msg == "2330":
            price = get_price("2330.TW")
            reply_text = f"台積電：{price}"

        elif msg == "006208":
            price = get_price("006208.TW")
            reply_text = f"富邦台50：{price}"

        else:
            reply_text = f"你輸入：{msg}"

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

        requests.post(LINE_API, headers=headers, json=data)

    except Exception as e:
        print("ERROR:", e)

    return "OK", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)