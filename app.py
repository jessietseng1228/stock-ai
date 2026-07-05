from flask import Flask, request, jsonify
import requests
import os
import yfinance as yf
import json

app = Flask(__name__)

# =========================
# 🟢 LINE 設定
# =========================
LINE_TOKEN = "kGWl+cSBUwKrKWFmvyDCp0kPabfuiCK5Rtcc2SXPX93jJvTA6e0+X5TkySmutdCrJfCBMEP4UFnguW1SObeNdgVTCXEzGurdKUaCwjNxZHOydseQwQh9Md3EJ1OCM/QRWsN6Va56KMP32J8valpqZwdB04t89/1O/w1cDnyilFU="
LINE_REPLY_API = "https://api.line.me/v2/bot/message/reply"
LINE_PUSH_API = "https://api.line.me/v2/bot/message/push"

# =========================
# 🟢 永久資料（多使用者）
# =========================
DATA_FILE = "user_data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

user_data = load_data()

# =========================
# 🟢 Yahoo cache
# =========================
_cache = {}

def get_history(stock):
    if stock in _cache:
        return _cache[stock]

    data = yf.Ticker(stock).history(period="5d")
    _cache[stock] = data
    return data

# =========================
# 🟢 LINE reply
# =========================
def reply_message(reply_token, text):
    headers = {
        "Authorization": f"Bearer {LINE_TOKEN}",
        "Content-Type": "application/json"
    }

    data = {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": str(text)}]
    }

    requests.post(LINE_REPLY_API, headers=headers, json=data)

# =========================
# 🟢 LINE push
# =========================
def push_message(user_id, text):
    headers = {
        "Authorization": f"Bearer {LINE_TOKEN}",
        "Content-Type": "application/json"
    }

    data = {
        "to": user_id,
        "messages": [{"type": "text", "text": str(text)}]
    }

    requests.post(LINE_PUSH_API, headers=headers, json=data)

# =========================
# 🟢 user 股票管理
# =========================
def get_user_stocks(user_id):
    return user_data.get(user_id, [])

def add_stock(user_id, code):
    stocks = user_data.get(user_id, [])
    if code not in stocks:
        stocks.append(code)

    user_data[user_id] = stocks
    save_data(user_data)

def del_stock(user_id, code):
    stocks = user_data.get(user_id, [])
    if code in stocks:
        stocks.remove(code)

    user_data[user_id] = stocks
    save_data(user_data)

# =========================
# 🟢 股票查詢
# =========================
def get_stock_price(code):
    try:
        stock = f"{code}.TW"
        data = get_history(stock)

        if data is None or data.empty:
            return f"{code}：查無資料"

        close = data["Close"].dropna()
        if len(close) < 2:
            return f"{code}：資料不足"

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

        return (
            f"{code}\n"
            f"價格：{round(price,2)}\n"
            f"漲跌：{round(change,2)} ({round(pct,2)}%)\n"
            f"原因：{reason}"
        )

    except Exception as e:
        print("error:", repr(e))
        return f"{code}：查詢失敗"

# =========================
# 🟢 report（v4重點：弱勢提醒，不刪股）
# =========================
def build_report(user_id):
    stocks = get_user_stocks(user_id)

    if not stocks:
        stocks = ["2330", "2317", "0050"]

    lines = ["📊 今日股票早報\n"]

    for code in stocks:
        try:
            stock = f"{code}.TW"
            data = get_history(stock)

            if data is None or data.empty:
                continue

            close = data["Close"].dropna()
            if len(close) < 5:
                continue

            price = close.iloc[-1]
            prev = close.iloc[-2]

            change = price - prev
            pct = (change / prev) * 100

            # =========================
            # 🟡 弱勢判斷（只標記不刪）
            # =========================
            pct_5d = (close.iloc[-1] - close.iloc[0]) / close.iloc[0] * 100

            last3 = close.iloc[-3:]
            is_down_3 = all(last3[i] < last3[i-1] for i in range(1, 3))

            is_weak = pct_5d < -5 or is_down_3

            warning = " ⚠️ 弱勢提醒" if is_weak else ""

            # =========================
            # 🟢 狀態
            # =========================
            if pct > 2:
                reason = "🔥 強勢上漲"
            elif pct < -2:
                reason = "⚠️ 明顯回檔"
            else:
                reason = "📊 小幅震盪"

            lines.append(
                f"{code}{warning}\n"
                f"價格：{round(price,2)}\n"
                f"漲跌：{round(change,2)} ({round(pct,2)}%)\n"
                f"原因：{reason}\n"
            )

        except Exception as e:
            print("report error:", repr(e))

    return lines

# =========================
# 🟢 chunk
# =========================
def chunk_lines(lines, max_len=1800):
    chunks = []
    current = ""

    for line in lines:
        if len(current) + len(line) > max_len:
            chunks.append(current)
            current = line
        else:
            current += line

    if current:
        chunks.append(current)

    return chunks

# =========================
# 🟢 webhook
# =========================
@app.route("/webhook", methods=["POST"])
def webhook():
    body = request.get_json(silent=True)

    if not body or "events" not in body:
        return "OK", 200

    try:
        event = body["events"][0]

        user_id = event["source"]["userId"]
        msg = event["message"]["text"].strip().lower()
        reply_token = event["replyToken"]

        # ➕ add
        if msg.startswith("add "):
            code = msg.replace("add ", "").strip()
            add_stock(user_id, code)
            reply_message(reply_token, f"已加入：{code}")

        # ➖ del
        elif msg.startswith("del "):
            code = msg.replace("del ", "").strip()
            del_stock(user_id, code)
            reply_message(reply_token, f"已刪除：{code}")

        # 📋 list
        elif msg == "list":
            stocks = get_user_stocks(user_id)
            reply_message(reply_token, "清單：\n" + "\n".join(stocks))

        # 📊 單股查詢
        elif msg.isdigit():
            reply_message(reply_token, get_stock_price(msg))

        else:
            reply_message(reply_token, "指令：add / del / list / 股票代號")

    except Exception as e:
        print("webhook error:", repr(e))

    return "OK", 200

# =========================
# 🟢 push（v4：多user）
# =========================
@app.route("/push", methods=["POST"])
def push():
    try:
        for user_id in user_data.keys():
            lines = build_report(user_id)
            chunks = chunk_lines(lines)

            for c in chunks:
                push_message(user_id, c)

        return jsonify({
            "status": "OK",
            "users": len(user_data)
        })

    except Exception as e:
        return jsonify({
            "status": "ERROR",
            "message": str(e)
        }), 500

# =========================
# 🟢 health check
# =========================
@app.route("/", methods=["GET"])
def home():
    return "OK", 200

# =========================
# 🟢 start
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)