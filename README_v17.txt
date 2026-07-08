Stock AI Assistant v17.0

重點：
1. TOP5可買改成每日市場預掃描結果，不再使用自選股。
2. 新增 /scan_top5：手動或 Cron 產生今日 TOP5。
3. 新增 /top5_status：檢查今天是否已有 TOP5 掃描結果。
4. /cron 會先掃描 TOP5，再推播今日早報。

部署前請先到 Supabase SQL Editor 執行：
- supabase_market_top5.sql

建議 Render Cron：
- 08:30 呼叫 https://你的網址/scan_top5
- 09:00 呼叫 https://你的網址/cron

如果 09:00 的 /cron 太久，可以保留 08:30 /scan_top5，並把 09:00 改回只推播。
