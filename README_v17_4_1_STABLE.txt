v17.4.1 Stable 修正

1. 修正 yfinance 批次下載 MultiIndex 欄位解析。
2. 上市股票使用 .TW，上櫃股票使用 .TWO。
3. 過濾 NaN/無效行情值。
4. /scan_top5 回傳 batch_empty、batch_rows、batch_columns，方便診斷。
5. 不需新增或重跑 SQL。

部署後測試：
/status
/scan_top5?limit=30
/top5_status
/top5
