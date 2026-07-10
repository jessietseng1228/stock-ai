股票 AI 助理 v18.1.1-stable

新增：
1. LINE 指令「AI歷史」或「AI推薦歷史」
2. 顯示最近一次 Top5 推薦：排名、AI Score、推薦價、Day+1、Day+5
3. 尚未到績效更新交易日時顯示「等待中」
4. 新增 GET /ai_history 文字測試端點

不需新增或修改 SQL。
Cron 維持：
- 09:00 /cron
- 17:30 /scan_top5?limit=30
- 18:00 /update_performance?limit=100
