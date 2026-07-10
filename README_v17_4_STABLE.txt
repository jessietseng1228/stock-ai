Stock AI Assistant v17.4 Stable

目標：
- 單一 Cron 同步完成 Top5
- 不使用 Flask background thread
- 不使用 10 批 staging / finalize
- 使用 TWSE/TPEx 成交值建立候選池
- 使用 yfinance 一次批次下載候選池歷史行情

Render Cron 建議：
08:30 https://你的網址/scan_top5_cron?limit=60
09:00 https://你的網址/cron

Render Environment 可選設定：
TOP5_CANDIDATE_LIMIT=60
TOP5_STORE_COUNT=20
TOP5_MIN_TURNOVER=100000000
TOP5_YF_TIMEOUT=25

測試：
/status
/scan_top5?limit=30
/top5_status
/top5
/scan_top5_cron?limit=60

注意：
- v17.4 不需要新增 SQL。
- 沿用 market_top5_results。
- 舊的分批 staging SQL 不需要執行。
