from flask import Flask, request, jsonify
import requests
import os
import yfinance as yf
import json

app = Flask(__name__)

# =========================
# LINE
# =========================
LINE_TOKEN = "kGWl+cSBUwKrKWFmvyDCp0kPabfuiCK5Rtcc2SXPX93jJvTA6e0+X5TkySmutdCrJfCBMEP4UFnguW1SObeNdgVTCXEzGurdKUaCwjNxZHOydseQwQh9Md3EJ1OCM/QRWsN6Va56KMP32J8valpqZwdB04t89/1O/w1cDnyilFU="
LINE_REPLY_API = "https://api.line.me/v2/bot/message/reply"
LINE_PUSH_API = "https://api.line.me/v2/bot/message/push"

# =========================
# DATA
# =========================
DATA_FILE = "user_data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

user_data = load_data()

# =========================
# cache
# =========================
_cache = {}

def get_history(stock):
    if stock in _cache:
        return _cache[stock]

    data = yf.Ticker(stock).history(period="5d")
    _cache[stock] = data
    return data

# =========================
# LINE push
# =========================
def push_message(user_id, text):
    headers = {
        "Authorization": f"Bearer {LINE_TOKEN}",
        "Content-Type": "application/json"
    }

    data = {
        "to": user_id,
        "messages": [{"type": "text", "text": text}]
    }

    r = requests.post(LINE_PUSH_API, headers=headers, json=data)

    print("LINE STATUS:", r.status_code)
    print("LINE RESPONSE:", r.text)

# =========================
# user stock
# =========================
def get_user_stocks(user_id):
    return user_data.get(user_id, [])

def add_stock(user_id, code):
    if user_id not in user_data:
        user_data[user_id] = []

    if code not in user_data[user_id]:
        user_data[user_id].append(code)
        save_data(user_data)

def del_stock(user_id, code):
    if user_id in user_data and code in user_data[user_id]:
        user_data[user_id].remove(code)
        save_data(user_data)

# =========================
# 評級系統
# =========================
def get_grade(pct_5d):
    if pct_5d >= 3:
        return "🟢強勢"
    elif pct_5d <= -3:
        return "🔴弱勢"
    else:
        return "🟡中性"

# =========================
# 股票分析
# =========================
def analyze(code):
    try:
        data = get_history(f"{code}.TW")

        if data is None or data.empty:
            return None

        close = data["Close"].dropna()
        if len(close) < 2:
            return None

        price = close.iloc[-1]
        prev = close.iloc[-2]

        change = price - prev
        pct = (change / prev) * 100

        pct_5d = (close.iloc[-1] - close.iloc[0]) / close.iloc[0] * 100

        grade = get_grade(pct_5d)

        return {
            "code": code,
            "price": price,
            "change": change,
            "pct": pct,
            "grade": grade,
            "pct_5d": pct_5d
        }

    except Exception as e:
        print("ANALYZE ERROR:", e)
        return None

# =========================
# report v6
# =========================
def build_report(user_id):
    stocks = get_user_stocks(user_id)

    if not stocks:
        return ["⚠️ 尚未設定股票，請先 add 2330"]

    results = []

    for code in stocks:
        r = analyze(code)
        if r:
            results.append(r)

    if not results:
        return ["⚠️ 無法取得股票資料"]

    # 排序：強勢優先
    results.sort(key=lambda x: x["pct_5d"], reverse=True)

    lines = ["📊 今日股票早報 v6\n"]

    for r in results:
        lines.append(
            f"{r['code']} {r['grade']}\n"
            f"價格：{round(r['price'],2)}\n"
            f"漲跌：{round(r['change'],2)} ({round(r['pct'],2)}%)\n"
            f"5日：{round(r['pct_5d'],2)}%\n"
        )

    return lines

# =========================
# chunk（防爆 LINE）
# =========================
def chunk_lines(lines, max_len=1800):
    chunks = []
    buf = ""

    for l in lines:
        if len(buf) + len(l) > max_len:
            chunks.append(buf)
            buf = l
        else:
            buf += l

    if buf:
        chunks.append(buf)

    return chunks

# =========================
# webhook
# =========================
@app.route("/webhook", methods=["POST"])
def webhook():
    global user_data

    body = request.get_json(silent=True)

    if not body or "events" not in body:
        return "OK", 200

    try:
        event = body["events"][0]

        user_id = event["source"]["userId"]
        msg = event["message"]["text"].strip().lower()
        reply_token = event["replyToken"]

        print("USER:", user_id, "MSG:", msg)

        if msg.startswith("add "):
            code = msg.replace("add ", "")
            add_stock(user_id, code)
            push_message(user_id, f"已加入：{code}")

        elif msg.startswith("del "):
            code = msg.replace("del ", "")
            del_stock(user_id, code)
            push_message(user_id, f"已刪除：{code}")

        elif msg == "list":
            stocks = get_user_stocks(user_id)
            push_message(user_id, "清單：\n" + "\n".join(stocks))

        elif msg.isdigit():
            r = analyze(msg)
            if r:
                push_message(user_id, f"{msg} {round(r['price'],2)} ({round(r['pct'],2)}%)")

        else:
            push_message(user_id, "指令：add / del / list / 股票代號")

    except Exception as e:
        print("WEBHOOK ERROR:", e)

    return "OK", 200

# =========================
# push v6
# =========================
@app.route("/push", methods=["GET", "POST"])
def push():
    try:
        print("USER DATA:", user_data)

        if not user_data:
            return jsonify({
                "status": "EMPTY",
                "message": "no users"
            })

        for user_id in user_data:
            report = build_report(user_id)
            chunks = chunk_lines(report)

            for c in chunks:
                push_message(user_id, c)

        return jsonify({
            "status": "OK",
            "users": len(user_data)
        })

    except Exception as e:
        print("PUSH ERROR:", e)
        return jsonify({
            "status": "ERROR",
            "message": str(e)
        }), 500

# =========================
# health
# =========================
@app.route("/", methods=["GET"])
def home():
    return "OK", 200

# =========================
# run
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)