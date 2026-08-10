股票 AI 助理 v20.8 STABLE
日期：2026-08-10

本版主題
- Top5 成效驗證（Performance Analytics）
- 保留 v20.7.2 每日正式 Top5 鎖定機制，不改掃描與入選規則。
- 不新增 Supabase 欄位，直接使用既有 ai_recommend_history。

新增功能
1. /performance_status
   - 回傳 Day+1 / Day+5 筆數、勝率、平均報酬、最佳/最差報酬。
   - AI Base Score 分層（90+ / 85-89 / 80-84 / 75-79 / <75）比較 Day+5。
   - Top1~Top5 排名分層績效。
   - decision 分層績效。
   - trend / momentum / volume / risk / position / technical 因子高低分組效果觀察。
   - 回傳 Day+5 最差 5 筆案例供失敗分析。

2. /performance
   - 人類可讀的績效摘要頁面。

3. LINE 指令
   - 輸入「AI績效」或「績效驗證」可查看目前 Top5 歷史績效摘要。

4. 樣本保護
   - Day+5 少於 10 筆時，報表會明確標示樣本不足，避免太早依小樣本調權重。

部署後測試
- /health 應為 v20.8-stable
- /top5 多次查詢仍必須維持同日相同結果
- /performance_status 應回 analytics_version=Performance Analytics v20.8
- /performance 應顯示 Day+1 / Day+5 勝率與平均報酬
- LINE 輸入「AI績效」應回傳績效摘要

注意
- factor_effectiveness 為分組觀察指標，不代表因果關係。
- 本版先做「驗證」，不自動改 AI 權重；待樣本累積後再進 v20.9 Learning Engine 強化。
