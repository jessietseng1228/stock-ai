from flask import Flask, request
import requests
import os

app = Flask(__name__)

# LINE Channel Access Token（你自己的）
LINE_TOKEN = "kGWl+cSBUwKrKWFmvyDCp0kPabfuiCK5Rtcc2SXPX93jJvTA6e0+X5TkySmutdCrJfCBMEP4UFnguW1SObeNdgVTCXEzGurdKUaCwjNxZHOydseQwQh9Md3EJ1OCM/QRWsN6Va56KMP32J8valpqZwdB04t89/1O/w1cDnyilFU="


LINE_API = "https://api.line.me/v2/bot/message/reply"

@app.route("/", methods=["GET"])
def home():
    return "OK", 200


@app.route("/webhook", methods=["POST"])
def webhook():
    body = request.get_json()
    print("🔥 收到LINE訊息:", body)

    try:
        event = body["events"][0]
        reply_token = event["replyToken"]
        user_msg = event["message"]["text"]

        # 👉 最簡單回覆
        reply_text = f"你剛剛說：{user_msg}"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {LINE_TOKEN}"
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