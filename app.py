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
    print("🔥 收到LINE:", body)

    try:
        event = body["events"][0]
        reply_token = event["replyToken"]

        headers = {
            "Authorization": f"Bearer {LINE_TOKEN}",
            "Content-Type": "application/json"
        }

        data = {
            "replyToken": reply_token,
            "messages": [
                {
                    "type": "text",
                    "text": "我已收到你的訊息 👍"
                }
            ]
        }

        requests.post("https://api.line.me/v2/bot/message/reply",
                      headers=headers,
                      json=data)

    except Exception as e:
        print("ERROR:", e)

    return "OK", 200