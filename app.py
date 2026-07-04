from flask import Flask, request

app = Flask(__name__)

@app.route("/", methods=["POST"])
def webhook():
    print("收到LINE事件")

    # ⭐一定要立刻回應
    return "OK", 200


@app.route("/", methods=["GET"])
def home():
    return "OK"


if __name__ == "__main__":
    app.run()