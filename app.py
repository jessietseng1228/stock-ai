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
LINE_PUSH_API = "https://api.line.me/v2/bot/message/push"

# =========================
# DB
# =========================
DB_FILE = "stocks.db"

def db_fetch(query, params=()):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(query, params)
    rows = c.fetchall()
    conn.close()
    return rows

# =========================
# PUSH
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
# 📦 重要：批次抓資料（v8核心）
# =========================
stock_cache = {}

def fetch_stock_batch(stocks):
    """
    一次抓全部股票，避免 N 次 request
    """
    for s in stocks:
        try:
            data = yf.Ticker(f"{s}.TW").history(period="5d")

            if data is None or data.empty:
                stock_cache[s] = None
                continue

            close = data["Close"].dropna()

            if len(close) < 2:
                stock_cache[s] = None
                continue

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

            stock_cache[s] = {
                "price": price,
                "change": change,
                "pct": pct,
                "pct_5d": pct_5d,
                "grade": grade
            }

        except Exception as e:
            print("FETCH ERROR:", s, e)
            stock_cache[s] = None

# =========================
# DB stocks
# =========================
def get_all_users():
    rows = db_fetch("SELECT DISTINCT user_id FROM user_stocks")
    return [r[0] for r in rows]

def get_user_stocks(user_id):
    rows = db_fetch(
        "SELECT stock FROM user_stocks WHERE user_id=?",
        (user_id,)
    )
    return [r[0] for r in rows]

# =========================
# report
# =========================
def build_report(user_id, stocks):
    lines = ["📊 今日股票早報 v8\n"]

    ok = False

    for s in stocks:
        r = stock_cache.get(s)

        if not r:
            lines.append(f"{s} ⚠️無資料")
            continue

        ok = True

        lines.append(
            f"{s} {r['grade']}\n"
            f"價格：{round(r['price'],2)}\n"
            f"漲跌：{round(r['change'],2)} ({round(r['pct'],2)}%)\n"
            f"5日：{round(r['pct_5d'],2)}%\n"
        )

    if not ok:
        return ["⚠️ 今日無有效股票資料"]

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
# webhook（保留）
# =========================
@app.route("/webhook", methods=["POST"])
def webhook():
    body = request.get_json(silent=True)

    if not body:
        return "OK"

    event = body["events"][0]
    user_id = event["source"]["userId"]
    msg = event["message"]["text"].strip().lower()

    # 只保留 debug
    print("USER:", user_id, msg)

    return "OK"

# =========================
# push v8（核心優化）
# =========================
@app.route("/push", methods=["GET", "POST"])
def push():
    try:
        users = get_all_users()

        if not users:
            return jsonify({"status": "EMPTY", "users": 0})

        # 👉 所有股票一次抓
        all_stocks = list(set(
            s[0]
            for u in users
            for s in db_fetch("SELECT stock FROM user_stocks WHERE user_id=?", (u,))
        ))

        print("FETCH STOCKS:", all_stocks)

        fetch_stock_batch(all_stocks)

        # 推播
        for u in users:
            stocks = get_user_stocks(u)
            report = build_report(u, stocks)
            chunks = chunk(report)

            for c in chunks:
                push_message(u, c)

        return jsonify({
            "status": "OK",
            "users": len(users),
            "stocks": len(all_stocks)
        })

    except Exception as e:
        print("PUSH ERROR:", e)
        return jsonify({"status": "ERROR", "msg": str(e)}), 500

# =========================
# health
# =========================
@app.route("/")
def home():
    return "OK"

# =========================
# run
# =========================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))