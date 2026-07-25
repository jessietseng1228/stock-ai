股票 AI 助理 v20.1 Stable｜AI Decision Engine

本版重點：
1. 新增五種操作決策：可分批布局、突破確認後布局、等待回檔、持續觀察、不建議進場／避免追高。
2. 新增 Confidence 訊號一致度（不是勝率）。
3. 新增型態辨識：突破／主升段、多頭趨勢、多頭回檔、高檔震盪、箱型整理、空頭弱勢等。
4. 新增建議買點區間、第一／第二目標與風險報酬比 RR。
5. 個股 LINE 分析卡與 TOP5 卡片同步顯示決策資訊。
6. 沿用 AI Score 3.0，不改 Supabase 資料表；v20.1 計畫資料封裝於既有 trend 欄位，舊資料仍可讀取。
7. Render Cron、LINE Webhook、Day+1／Day+5 績效追蹤及既有 endpoint 保持不變。

部署後測試：
/health
/scan_top5
/top5
個股分析（例如 2376）

重要：Confidence 是技術訊號一致度，買點、停損、目標與 RR 都是模型參考值，不是保證獲利或投資建議。
