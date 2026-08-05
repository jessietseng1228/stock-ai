股票 AI 助理 v20.7.2 HOTFIX
日期：2026-08-05

修正目的
- 同一掃描日期的正式 Top5 必須整天一致。
- 手動測試不得覆蓋正式 Top5。

正式規則
1. /scan_top5：預覽模式，重新計算但不寫入 Supabase。
2. /scan_top5_cron：正式模式；當日第一次成功後寫入並鎖定。
3. 同日再次呼叫 /scan_top5_cron：不重算、不覆蓋，回傳 locked=true。
4. 只有 /scan_top5_cron?force=1 才能強制重算，請僅在明確修復需求時使用。
5. /top5 與 LINE 永遠讀取正式快照。
6. 今日正式掃描零入選時，維持「今日無符合進場條件標的」。

部署後測試
- /health 應為 v20.7.2-stable
- /scan_top5 應回 mode=preview、saved_count=0
- /scan_top5_cron 第一次建立正式結果
- /scan_top5_cron 第二次應回 locked=true 且不重算
- /top5 多次查詢結果必須一致
