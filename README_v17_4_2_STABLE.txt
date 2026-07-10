v17.4.2 Stable 修正

1. 保留 v17.4.1 原有功能。
2. yfinance 批次下載若出現 0 rows，改用 Yahoo Chart JSON 平行備援抓價。
3. /scan_top5 新增 fallback_count 診斷欄位。
4. 只有取得有效行情並完成評分後才寫入 market_top5_results。
5. 不需重跑 SQL。

部署後測試：
/status
/scan_top5?limit=30
/top5_status
/top5
