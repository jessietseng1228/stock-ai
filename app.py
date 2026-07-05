from flask import Flask, request, jsonify
import requests
import os
import yfinance as yf
import time
from supabase import create_client

app = Flask(__name__)

# =========================
# LINE
# =========================
LINE_TOKEN = os.environ.get("LINE_TOKEN")
LINE_PUSH_API = "https://api.line.me/v2/bot/message/push"

# =========================
# SUPABASE
# =========================
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

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
# Supabase DB 操作
# =========================
def get_users():
    res = supabase.table("user_stocks").select("user_id").execute()
    if not res.data:
        return []
    return list(set([r["user_id"] for r in res.data]))

def get_stocks(user):
    res = supabase.table("user_stocks") \
        .select("stock") \
        .eq("user_id", user) \
        .execute()

    if not res.data:
        return []

    return [r["stock"] for r in res.data]

def add_stock(user, stock):
    supabase.table("user_stocks").insert({
        "user_id": user,
        "stock": stock
    }).execute()

def del_stock(user, stock):
    supabase.table("user_stocks") \
        .delete() \
        .eq("user_id", user) \
        .eq("stock", stock) \
        .execute()

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
# 股票抓取
# =========================
def fetch_stock(stock):

    def try_fetch(period):
        return yf.Ticker(f"{stock}.TW").history(period=period)

    data = try_fetch("5d")
    if data is not None and not data.empty:
        return data, "OK"

    data = try_fetch("10d")
    if data is not None and not data.empty:
        return data, "DELAY"

    for _ in range(2):
        time.sleep(1)
        data = try_fetch("10d")
        if data is not None and not data.empty:
            return data, "DELAY"

    return None, "FAIL"

# =========================
# 分析
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
# report
# =========================
def build_report(user):
    stocks = get_stocks(user)

    if not stocks:
        return ["⚠️ 尚未設定股票"]

    results = [analyze(s) for s in stocks]

    ok_any = any(r.get("status") != "FAIL" for r in results)

    lines = ["📊 今日股票早報 v11\n"]

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
# webhook (LINE)
# =========================
@app.route("/webhook", methods=["POST"])
def webhook():

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
# push job (Render cron)
# =========================
@app.route("/push", methods=["GET", "POST"])
def push_job():

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
# health check
# =========================
@app.route("/")
def home():
    return "OK"

# =========================
# start
# =========================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))