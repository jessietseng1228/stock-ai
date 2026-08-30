股票 AI 助理 v21.0.2 Diagnostics (2026-08-30)

基底：v21.0.1 HOTFIX
目的：解釋 legacy_excluded_count，而不改變 Top5、Decision Engine、Learning Guard 或 Market Regime 判定邏輯。

新增 /learning_status 欄位：
- legacy_excluded_primary_reasons：每筆排除樣本只歸一個主因，加總 = legacy_excluded_count
- legacy_excluded_reason_counts：完整原因計數，一筆可能同時命中多項，因此加總可大於排除筆數
- legacy_excluded_preview：最多 12 筆範例，顯示 scan_date / symbol / decision / base_score / day5_return / reasons
- legacy_diagnostics_notes：統計口徑說明

主要 reason code：
- decision_not_allowed
- missing_or_invalid_base_score
- missing_day5_return
- day5_return_outlier
- missing_factor_scores
- missing_trend_score / missing_momentum_score / missing_volume_score / missing_risk_score / missing_position_score / missing_technical_score
- missing_scan_date / missing_symbol

部署後驗證：
1. /health -> version = v21.0.2-diagnostics
2. /learning_status -> Learning Engine v21.0.2
3. legacy_excluded_primary_reasons 加總應等於 legacy_excluded_count

本版不需新增 SQL migration。
