from flask import Flask, request, jsonify
import requests
import os
import yfinance as yf
import sqlite3
import time

app = Flask(__name__)

# =========================
# LINE
# =========================
LINE_TOKEN = "kGWl+cSBUwKrKWFmvyDCp0kPabfuiCK5Rtcc2SXPX93jJvTA6e0+X5TkySmutdCrJfCBMEP4UFnguW1SObeNdgVTCXEzGurdKUaCwjNxZHOydseQwQh9Md3EJ1OCM/QRWsN6Va56KMP32J8valpqZwdB04t89/1O/w1cDnyilFU="
LINE_PUSH_API = "https://api.line.me/v2/bot/message/push"

# =========================
# DB
# =========================
DB_FILE = "stocks.db"

# =========================
# 🔥 v9：防 crash DB保險
# =========================
def ensure_db():
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

# =========================
# 防重複 push（cron safe）
# =========================
_last_push = 0

def can_push():
    global _last_push
    now = time.time()

    if now - _last_push < 300:  # 5分鐘內不重複
        return False

    _last_push = now
    return True

# =========================
# DB helpers
# =========================
def db_fetch(query, params=()):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(query, params)
    rows = c.fetchall()
    conn.close()
    return rows

def get_all_users():
    rows = db_fetch("SELECT DISTINCT user_id FROM user_stocks")
    return [r[0] for r in rows]

def get_user_stocks(user_id):
    rows = db_fetch(
        "SELECT stock FROM user_stocks WHERE user_id=?",
        (user_id,)
    )
    return [r[0] for r in rows]

def add_stock(user_id, stock):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "INSERT INTO user_stocks VALUES (?, ?)",
        (user_id, stock)
    )
    conn.commit()
    conn.close()

def del_stock(user_id, stock):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "DELETE FROM user_stocks WHERE user_id=? AND stock=?",
        (user_id, stock)
    )
    conn.commit()
    conn.close()

# =========================
# LINE push
# =========================
def push_message(user_id, text):
    requests.post(
        LINE_PUSH_API,
        headers={
            "Authorization": f"Bearer {LINE_TOKEN}",
            "Content-Type": "application/json"
        },
        json={
            "to": user_id,
            "messages": [{"type": "text", "text": text}]
        }
    )

# =========================
# Yahoo safe fetch
# =========================
def get_stock(stock):
    try:
        data = yf.Ticker(f"{stock}.TW").history(period="5d")

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

        grade = (
            "🟢強勢" if pct_5d >= 3 else
            "🔴弱勢" if pct_5d <= -3 else
            "🟡中性"
        )

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
# report v9（保證有內容）
# =========================
def build_report(user_id):
    stocks = get_user_stocks(user_id)

    if not stocks:
        return ["⚠️ 尚未設定股票，請 add 2330"]

    lines = ["📊 今日股票早報 v9\n"]

    has_data = False

    for s in stocks:
        r = get_stock(s)

        if not r:
            lines.append(f"{s} ⚠️無資料")
            continue

        has_data = True

        lines.append(
            f"{r['stock']} {r['grade']}\n"
            f"價格：{round(r['price'],2)}\n"
            f"漲跌：{round(r['change'],2)} ({round(r['pct'],2)}%)\n"
            f"5日：{round(r['pct_5d'],2)}%\n"
        )

    if not has_data:
        return ["⚠️ 今日所有股票暫無資料"]

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
    ensure_db()

    body = request.get_json(silent=True)
    if not body:
        return "OK"

    event = body["events"][0]

    user_id = event["source"]["userId"]
    msg = event["message"]["text"].strip().lower()

    print("USER:", user_id, msg)

    if msg.startswith("add "):
        add_stock(user_id, msg.replace("add ", ""))
        push_message(user_id, "已加入")

    elif msg.startswith("del "):
        del_stock(user_id, msg.replace("del ", ""))
        push_message(user_id, "已刪除")

    elif msg == "list":
        stocks = get_user_stocks(user_id)
        push_message(user_id, "清單:\n" + "\n".join(stocks))

    return "OK"

# =========================
# push v9（穩定版）
# =========================
@app.route("/push", methods=["GET", "POST"])
def push():
    ensure_db()

    if not can_push():
        return jsonify({"status": "SKIP duplicate"})

    users = get_all_users()

    if not users:
        return jsonify({"status": "EMPTY", "users": 0})

    for u in users:
        report = build_report(u)
        chunks = chunk(report)

        for c in chunks:
            push_message(u, c)

    return jsonify({
        "status": "OK",
        "users": len(users)
    })

# =========================
# health
# =========================
@app.route("/")
def home():
    return "OK"

# =========================
# start
# =========================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))