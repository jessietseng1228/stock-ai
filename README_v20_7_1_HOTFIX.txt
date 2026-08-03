股票 AI 助理 v20.7.1 Hotfix
============================

修正內容
1. 今日掃描完成但零入選時，會保存內部空結果標記。
2. /top5 不再回退顯示昨天的推薦，改顯示「今日無符合進場條件標的」。
3. 今日尚未掃描時，才顯示最近一次成功 Top5，標題會明確標示「最近一次 Top5」。
4. 內部空結果標記不會出現在 Top5、AI 歷史或 LINE 推薦內容。
5. 不調整 v20.6 Entry Filter、v20.7 Final Score、Risk Engine 或 Learning Engine。

部署後首次驗證
1. 執行 /health，應顯示 v20.7.1-stable。
2. 重新執行 /scan_top5，讓當日零入選狀態寫入 Supabase。
3. 執行 /top5：若 eligible_count=0，應顯示今日無符合進場條件標的。
