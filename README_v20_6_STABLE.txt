股票 AI 助理 v20.6 Stable｜修正 Top5 入選條件
日期：2026-08-03

核心修正：
1. Top5 不再只依 AI 分數排序。
2. 僅允許「🟢 可分批布局」與「🔵 突破確認後布局」進入 Top5。
3. 排除「🟡 等待回檔」「🟠 避免追高」「⚪ 持續觀察」「🔴 不建議進場」。
4. 風險報酬比低於 1.0、買點區間無效或停損位置無效者一併排除。
5. 合格股票不足 5 檔時不強制補滿。
6. /scan_top5 新增 eligible_count、excluded_count、excluded_preview，方便核對排除原因。
7. Supabase market_top5_results 與 ai_recommend_history 只保存合格入選股票。
8. Day1／Day5 與 Learning Engine 流程不變。

測試順序：
/health
/scan_top5?limit=30
/top5
/top5_status

預期：
- top5 可能少於 5 檔。
- excluded_preview 可看到高分但遭排除的股票與原因。
- 不需要新增 Supabase 欄位或執行 SQL。
