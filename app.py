from flask import Flask, request

app = Flask(__name__)

@app.route("/", methods=["POST"])
def webhook():
    try:
        data = request.get_json()
        print("收到LINE資料：", data)

        return "OK", 200   # ⭐關鍵：一定要回 200

    except Exception as e:
        print("錯誤：", e)
        return "OK", 200   # ⭐避免LINE判定失敗

if __name__ == "__main__":
    app.run(port=5000)