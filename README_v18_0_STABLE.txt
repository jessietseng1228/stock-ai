股票 AI 助理 v18.0.0-stable（Day 1）
基底：v17.4.2-stable

本版完成：AI Score 2.0 + Explainable AI

一、AI Score 2.0（總分 100）
- 趨勢 Trend：30 分
- 動能 Momentum：25 分
- 量能 Volume：15 分
- 風險 Risk：15 分
- 20日位置 Position：15 分

二、不是寫死推薦
每檔股票的分數均由實際歷史收盤價、均線、五日漲跌、成交量比、
近20日波動率與區間位置計算。程式不指定任何股票固定分數或固定排名。

三、可解釋理由
新增均線排列、五日動能、量能倍數、波動與20日位置等理由。
個股分析會顯示完整五因子分數；Top5 會保留可讀推薦理由。

四、相容性
- 不需修改現有 Supabase table 即可部署。
- /cron、/push、自選股功能維持原流程。
- /scan_top5 回傳 score_version = AI Score 2.0。
- v18.1 才加入外資、投信、自營商資料；v18.0 不偽造籌碼分數。

建議測試：
1. /health：版本應為 v18.0.0-stable
2. /scan_top5?limit=30：應看到 score_version、scored_count、saved_count
3. LINE 點 TOP5可買：顯示 AI 2.0 與推薦理由
4. LINE 個股分析 2330：顯示五因子拆分
