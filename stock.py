import yfinance as yf

stocks = {
    "2330.TW": "台積電",
    "006208.TW": "富邦台50",
    "0050.TW": "元大台灣50"
}

for code, name in stocks.items():
    data = yf.Ticker(code).history(period="2d")

    close = data["Close"].iloc[-1]
    prev = data["Close"].iloc[-2]

    change = close - prev
    pct = (change / prev) * 100

    print(name, round(close, 2), f"{change:+.2f}", f"({pct:+.2f}%)")