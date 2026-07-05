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
# 防重複 push
# =========================
_last_push = 0

def can_push():
    global _last_push
    now = time.time()
    if now - _last_push < 300:
        return False
    _last_push = now
    return True

# =========================
# DB
# =========================
def db_fetch(q, p=()):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(q, p)
    r = c.fetchall()
    conn.close()
    return r

def get_users():
    return [r[0] for r in db_fetch("SELECT DISTINCT user_id FROM user_stocks")]

def get_stocks(user):
    return [r[0] for r in db_fetch("SELECT stock FROM user_stocks WHERE user_id=?", (user,))]

def add_stock(user, stock):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO user_stocks VALUES (?,?)", (user, stock))
    conn.commit()
    conn.close()

def del_stock(user, stock):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM user_stocks WHERE user_id=? AND stock=?", (user, stock))
    conn.commit()
    conn.close()

# =========================
# LINE push
# =========================
def push(user, text):
    requests.post(
        LINE_PUSH_API,
        headers={
            "Authorization": f"Bearer {LINE_TOKEN}",
            "Content-Type": "application/json"
        },
        json={
            "to": user,
            "messages": [{"type": "text", "text": text}]
        }
    )

# =========================
# 🧠 v9.2 智慧資料層（核心）
# =========================
def fetch_stock(stock):
    """
    回傳：
    - data
    - status: OK / DELAY / FAIL
    """

    def try_fetch(period):
        return yf.Ticker(f"{stock}.TW").history(period=period)

    # 1️⃣ 5d
    data = try_fetch("5d")
    if data is not None and not data.empty:
        return data, "OK"

    # 2️⃣ 10d fallback
    data = try_fetch("10d")
    if data is not None and not data.empty:
        return data, "DELAY"

    # 3️⃣ retry
    for _ in range(2):
        time.sleep(1)
        data = try_fetch("10d")
        if data is not None and not data.empty:
            return data, "DELAY"

    return None, "FAIL"

# =========================
# analyze
# =========================
def analyze(stock):
    data, status = fetch_stock(stock)

    if status == "FAIL":
        return {"stock": stock, "status": "FAIL"}

    close = data["Close"].dropna()

    if len(close) < 2:
        return {"stock": stock, "status": "FAIL"}

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
        "grade": grade,
        "status": status
    }

# =========================
# report v10
# =========================
def build_report(user):
    stocks = get_stocks(user)

    if not stocks:
        return ["⚠️ 尚未設定股票"]

    results = [analyze(s) for s in stocks]

    ok_any = any(r.get("status") != "FAIL" for r in results)

    lines = ["📊 今日股票早報 v10\n"]

    for r in results:
        if r["status"] == "FAIL":
            lines.append(f"{r['stock']} ⚠️資料更新中")
            continue

        tag = "⏳" if r["status"] == "DELAY" else ""

        lines.append(
            f"{r['stock']} {r['grade']} {tag}\n"
            f"價格：{round(r['price'],2)}\n"
            f"漲跌：{round(r['change'],2)} ({round(r['pct'],2)}%)\n"
            f"5日：{round(r['pct_5d'],2)}%\n"
        )

    if not ok_any:
        return ["⚠️ 今日資料尚未更新（稍後自動刷新）"]

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

    e = body["events"][0]
    user = e["source"]["userId"]
    msg = e["message"]["text"].strip().lower()

    if msg.startswith("add "):
        add_stock(user, msg.replace("add ", ""))
        push(user, "已加入")

    elif msg.startswith("del "):
        del_stock(user, msg.replace("del ", ""))
        push(user, "已刪除")

    elif msg == "list":
        push(user, "\n".join(get_stocks(user)))

    return "OK"

# =========================
# push v10
# =========================
@app.route("/push", methods=["GET", "POST"])
def push_job():
    ensure_db()

    if not can_push():
        return jsonify({"status": "SKIP duplicate"})

    users = get_users()

    if not users:
        return jsonify({"status": "EMPTY"})

    for u in users:
        report = build_report(u)
        push(u, "\n".join(report))

    return jsonify({"status": "OK", "users": len(users)})

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