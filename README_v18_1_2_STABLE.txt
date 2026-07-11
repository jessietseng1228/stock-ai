股票 AI 助理 v18.1.2 Stable
============================

本版重點：正式早報排程改用 Render Cron Job 直接執行 Python，
不再依賴 cron-job.org 呼叫休眠中的免費 Web Service。

新增檔案
--------
1. morning_job.py
   - 共用每日早報推播邏輯。
   - /cron 與 cron_runner.py 都呼叫同一個函式。

2. cron_runner.py
   - Render Cron Job 的執行入口。
   - LINE 推播失敗時以 exit code 1 結束，Render 會顯示失敗。

修改檔案
--------
1. app.py
   - 版本升為 v18.1.2-stable。
   - /cron 保留供瀏覽器手動測試，但正式排程不再呼叫網址。

2. line.py
   - push_text()、push_flex() 回傳成功或失敗，讓排程能正確判斷。

Render Cron Job 設定
--------------------
Name：stock-ai-morning-report
Runtime：Python 3
Build Command：pip install -r requirements.txt
Command：python cron_runner.py
Schedule：0 1 * * *

注意：Render Cron 使用 UTC。
0 1 * * * = 台灣每天 09:00。

Environment Variables
---------------------
Cron Job 必須設定與 Web Service 相同的環境變數，至少包括：
- LINE_CHANNEL_ACCESS_TOKEN
- SUPABASE_URL
- SUPABASE_KEY
- 其他目前專案使用中的 API Key（如有）

切換完成後
----------
- cron-job.org 的 /health 與 /cron 早報工作可以停用。
- /health 可保留給人工檢查。
- /cron 可保留給人工測試，但不要再當正式排程。
