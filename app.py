from flask import Flask, request

app = Flask(__name__)

@app.route("/", methods=["GET"])
def home():
    return "OK", 200


@app.route("/webhook", methods=["POST"])
def webhook():
    print("收到 LINE 訊息")

    body = request.get_json()
    print(body)

    return "OK", 200


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)