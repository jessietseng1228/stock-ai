股票 AI 助理 v18.1.0-stable（2026-07-11）

新增：
1. 每次 /scan_top5 完成後，只把實際 Top5 寫入 ai_recommend_history。
2. 同一天相同股票使用 upsert，不重複新增。
3. 保存 AI Score 2.0 與五因子分數、推薦價、排名。
4. /update_performance 依實際交易日更新 Day+1、Day+5 價格與報酬率。
5. 歷史表未建立時，不阻斷既有 /scan_top5；回傳 history_error 提醒。

部署前：
請先到 Supabase SQL Editor 執行：
sql/260711_ai_recommend_history.sql

建議 Cron（台北時間）：
- 週一至週五 09:00：GET /cron（自選股早報）
- 週一至週五 17:30：GET /scan_top5?limit=30（收盤後掃描 Top5 並寫入推薦歷史）
- 週一至週五 18:00：GET /update_performance?limit=100（更新 Day+1 / Day+5 績效）

若 Cron 平台使用 UTC：
- 09:00 台北 = 01:00 UTC
- 17:30 台北 = 09:30 UTC
- 18:00 台北 = 10:00 UTC

驗證：
1. /health 應顯示 v18.1.0-stable
2. /scan_top5?limit=30 應出現 history_saved_count: 5
3. /update_performance?limit=100 應回傳 pending_count / updated_rows / day1_updates / day5_updates
