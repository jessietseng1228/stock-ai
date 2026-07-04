print("🔥 APP IS STARTING")

from flask import Flask, request
import os

app = Flask(__name__)

@app.route("/", methods=["GET"])
def home():
    return "OK", 200

@app.route("/", methods=["POST"])
def webhook():
    print("LINE webhook received")
    return "OK", 200


# ⭐ Render 入口（重點）
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)