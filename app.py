from flask import Flask, request, jsonify
import requests
import os
import yfinance as yf
import sqlite3

app = Flask(__name__)

# =========================
# LINE
# =========================
LINE_TOKEN = "kGWl+cSBUwKrKWFmvyDCp0kPabfuiCK5Rtcc2SXPX93jJvTA6e0+X5TkySmutdCrJfCBMEP4UFnguW1SObeNdgVTCXEzGurdKUaCwjNxZHOydseQwQh9Md3EJ1OCM/QRWsN6Va56KMP32J8valpqZwdB04t89/1O/w1cDnyilFU="
LINE_REPLY_API = "https://api.line.me/v2/bot/message/reply"
LINE_PUSH_API = "https://api.line.me/v2/bot/message/push"

# =========================
# SQLite DB
# =========================
DB_FILE = "stocks.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS user_stocks (
            user_id TEXT,
            stock TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

def db_execute(query, params=()):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(query, params)
    conn.commit()
    conn.close()

def db_fetch(query, params=()):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(query, params)
    rows = c.fetchall()
    conn.close()
    return rows

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

    print("PUSH:", r.status_code, r.text)

# =========================
# stock data
# =========================
def get_history(stock):
    return yf.Ticker(stock).history(period="5d")

# =========================
# DB 操作
# =========================
def add_stock(user_id, stock):
    db_execute(
        "INSERT INTO user_stocks (user_id, stock) VALUES (?, ?)",
        (user_id, stock)
    )

def del_stock(user_id, stock):
    db_execute(
        "DELETE FROM user_stocks WHERE user_id=? AND stock=?",
        (user_id, stock)
    )

def get_user_stocks(user_id):
    rows = db_fetch(
        "SELECT stock FROM user_stocks WHERE user_id=?",
        (user_id,)
    )
    return [r[0] for r in rows]

# =========================
# 分析
# =========================
def analyze(stock):
    try:
        data = get_history(f"{stock}.TW")
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

        if pct_5d >= 3:
            grade = "🟢強勢"
        elif pct_5d <= -3:
            grade = "🔴弱勢"
        else:
            grade = "🟡中性"

        return {
            "stock": stock,
            "price": price,
            "change": change,
            "pct": pct,
            "pct_5d": pct_5d,
            "grade": grade
        }

    except:
        return None

# =========================
# report
# =========================
def build_report(user_id):
    stocks = get_user_stocks(user_id)

    if not stocks:
        return ["⚠️ 尚未設定股票，請先 add 2330"]

    results = []
    for s in stocks:
        r = analyze(s)
        if r:
            results.append(r)

    if not results:
        return ["⚠️ 無法取得資料"]

    results.sort(key=lambda x: x["pct_5d"], reverse=True)

    lines = ["📊 今日股票早報 v7\n"]

    for r in results:
        lines.append(
            f"{r['stock']} {r['grade']}\n"
            f"價格：{round(r['price'],2)}\n"
            f"漲跌：{round(r['change'],2)} ({round(r['pct'],2)}%)\n"
            f"5日：{round(r['pct_5d'],2)}%\n"
        )

    return lines

# =========================
# chunk
# =========================
def chunk(lines, max_len=1800):
    out = []
    buf = ""

    for l in lines:
        if len(buf) + len(l) > max_len:
            out.append(buf)
            buf = l
        else:
            buf += l

    if buf:
        out.append(buf)

    return out

# =========================
# webhook
# =========================
@app.route("/webhook", methods=["POST"])
def webhook():
    body = request.get_json(silent=True)

    if not body or "events" not in body:
        return "OK", 200

    event = body["events"][0]

    user_id = event["source"]["userId"]
    msg = event["message"]["text"].strip().lower()
    reply_token = event["replyToken"]

    print("USER:", user_id, "MSG:", msg)

    if msg.startswith("add "):
        stock = msg.replace("add ", "")
        add_stock(user_id, stock)
        push_message(user_id, f"已加入：{stock}")

    elif msg.startswith("del "):
        stock = msg.replace("del ", "")
        del_stock(user_id, stock)
        push_message(user_id, f"已刪除：{stock}")

    elif msg == "list":
        stocks = get_user_stocks(user_id)
        push_message(user_id, "清單：\n" + "\n".join(stocks))

    elif msg.isdigit():
        r = analyze(msg)
        if r:
            push_message(user_id, f"{msg} {round(r['price'],2)} ({round(r['pct'],2)}%)")

    else:
        push_message(user_id, "指令：add / del / list / 股票代號")

    return "OK", 200

# =========================
# push
# =========================
@app.route("/push", methods=["GET", "POST"])
def push():
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT DISTINCT user_id FROM user_stocks")
        users = [r[0] for r in c.fetchall()]
        conn.close()

        print("USERS:", users)

        if not users:
            return jsonify({"status": "EMPTY", "users": 0})

        for u in users:
            report = build_report(u)
            chunks = chunk(report)

            for c in chunks:
                push_message(u, c)

        return jsonify({"status": "OK", "users": len(users)})

    except Exception as e:
        return jsonify({"status": "ERROR", "message": str(e)}), 500

# =========================
# health
# =========================
@app.route("/", methods=["GET"])
def home():
    return "OK", 200

# =========================
# start
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)