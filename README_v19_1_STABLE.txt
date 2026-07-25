股票 AI 助理 v19.1 Stable

基底：v18.1.2 Stable

本版完成：
1. RSI(14)
2. MACD(12,26,9) 與柱狀體
3. ATR(14)，使用每日 High/Low/Close 真實波幅
4. MA5、MA10、MA20 每日平均斜率
5. 個股文字分析與 LINE Flex 顯示上述指標
6. yfinance 批次與 Yahoo Chart 備援皆補入 High/Low
7. App 版本更新為 v19.1-stable

相容性：
- 保留 AI Score 2.0 原始配分，不在 v19.1 改變 Top5 排名邏輯。
- 不修改 Render Cron、LINE webhook、Supabase 既有資料表與 endpoints。
- v19.2 再進行 AI Score 3.0 權重與評分升級。
