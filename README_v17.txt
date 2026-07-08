Stock AI Assistant v17.1 REAL

重點：
1. TOP5可買改成每日市場預掃描結果，不再使用自選股。
2. 新增 /scan_top5：手動或 Cron 產生今日 TOP5。
3. 新增 /top5_status：檢查今天是否已有 TOP5 掃描結果。
4. 新增 /top5：瀏覽器直接查看目前 TOP5 文字版。
5. 新增 /status：與 /health 相同，方便部署後檢查版本。

部署前請先到 Supabase SQL Editor 執行：
- supabase_market_top5.sql

建議 Render Cron：
- 08:30 呼叫 https://你的網址/scan_top5
- 09:00 呼叫 https://你的網址/cron

測試順序：
1. /status
2. /scan_top5?limit=30  （先小量測試）
3. /top5_status
4. /top5
5. LINE 點「TOP5可買」

環境變數：
- TOP_TURNOVER_LIMIT：預設 120。穩定後可改 200 或 300。
- SCAN_SLEEP_SECONDS：預設 0.02。

注意：
- TOP5 掃描來源是 TWSE / TPEx 每日行情，先依成交值排序，再抓 K 線計算 AI Score。
- 若交易所資料或 Yahoo K 線暫時取不到，/scan_top5 可能產生較少筆結果，可稍後重跑。
- 這是量價模型，不是投資建議。
