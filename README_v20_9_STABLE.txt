Stock AI Assistant v20.9 STABLE - 2026-08-10

核心：Shadow Learning / Clean Learning Sample

1. Learning Engine 僅使用現行 Entry Filter 決策：
   - 🟢 可分批布局
   - 🔵 突破確認後布局
   且 base_score > 0、Day+5 已完成、六項 factor 欄位完整。

2. Legacy Day+5 資料完全排除於 Learning Engine，不再污染正式掃描。

3. 三階段模式：
   - collecting：Clean Sample < 10，僅收集資料，不產生學習校正。
   - shadow：Clean Sample >= 10 且 < 30，計算 Shadow Score，但不套用正式 Top5。
   - auto：Clean Sample >= 30，才允許最多 +/-3 分受控校正。

4. /learning_status 可查看：
   mode / clean_sample_count / legacy_excluded_count / shadow_ready / auto_apply_ready / factor_shadow。

5. 正式 Top5 在 auto_apply_ready=false 時仍使用 Base Score，不受 Shadow 建議影響。

6. 不需要新增 Supabase SQL。
