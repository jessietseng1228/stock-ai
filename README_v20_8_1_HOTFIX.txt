Stock AI Assistant v20.8.1 HOTFIX - 2026-08-10

目的：清理 Performance Analytics 樣本分層，避免舊版本資料污染 v20.9 Learning Engine。

1. ALL HISTORY：保留全部歷史績效，只作 Legacy Benchmark。
2. CURRENT STRATEGY：只接受現行 Entry Filter 決策（🟢 可分批布局 / 🔵 突破確認後布局）且 base_score > 0。
3. CLEAN LEARNING SAMPLE：CURRENT STRATEGY + Day+5 完成 + 六項 factor 欄位完整。
4. worst_cases 改為只顯示 CURRENT STRATEGY，不再把 decision 空白 / Base 0 舊資料列為現行失敗案例。
5. factor_effectiveness 改為只使用 CLEAN LEARNING SAMPLE。
6. clean sample 未滿 30 筆時 ready_for_auto_weight=false；v20.8.1 不自動調整權重。
7. 不新增 Supabase 欄位，不需執行 SQL；不修改 v20.7.2 每日正式 Top5 鎖定機制。

測試：
/health -> v20.8.1-hotfix
/performance_status -> 檢查 current_strategy_count / clean_learning_count / legacy_count
/performance -> LINE 摘要應分現行策略、全部歷史、Clean Learning Sample
/top5 -> 確認今日 Top5 不變
