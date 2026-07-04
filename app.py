from flask import Flask, request
import requests
import os

app = Flask(__name__)

LINE_TOKEN = "填你的token"

LINE_API = "https://api.line.me/v2/bot/message/reply"


@app.route("/", methods=["GET"])
def home():
    return "OK", 200


@app.route("/webhook", methods=["POST"])
def webhook():

    body = request.get_json(silent=True)

    print("🔥 webhook received:", body)

    # 🟢 防呆：避免空值 crash
    if not body or "events" not in body:
        return "OK", 200

    try:
        event = body["events"][0]

        if "message" not in event:
            return "OK", 200

        reply_token = event["replyToken"]
        user_msg = event["message"]["text"]

        headers = {
            "Authorization": f"Bearer {LINE_TOKEN}",
            "Content-Type": "application/json"
        }

        data = {
            "replyToken": reply_token,
            "messages": [
                {"type": "text", "text": f"收到：{user_msg}"}
            ]
        }

        requests.post(LINE_API, headers=headers, json=data)

    except Exception as e:
        print("ERROR:", e)

    return "OK", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)