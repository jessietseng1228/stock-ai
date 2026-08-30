股票 AI 助理 v21.0 STABLE
=========================
Base: v20.9 STABLE 260810

核心新增
1. Sample Dedup
   - DB: scan_date + symbol unique guard
   - Learning Engine: 再以 scan_date + symbol 做 logical dedup
   - /learning_status 新增 clean_before_dedup_count, dedup_sample_count,
     duplicate_excluded_count

2. Learning Guard
   - 30 Clean Samples 不再等於自動套用
   - 預設還需：至少 6 個 scan dates、單日樣本 <= 25%、至少一個具 meaningful edge 的因子
   - Day+5 絕對報酬 > 20% 預設排除，避免極端值污染學習
   - 所有門檻可用 Render Environment Variables 調整

3. Market Regime (Shadow only)
   - 使用 ^TWII 近 6 個月日線
   - BULL: Close > MA20 > MA60 且 5D > -1%
   - BEAR: Close < MA20 < MA60 且 5D < +1%
   - 其餘 NEUTRAL；資料不足/失敗為 UNKNOWN
   - Regime 會寫入 ai_recommend_history，Learning Status 產生 market_regime_buckets
   - v21.0 不使用 regime 直接改 Top5 分數

上線前必要步驟
- Supabase SQL Editor 執行：sql/260830_v21_0_sample_guard_regime.sql
- 部署整包程式
- 呼叫 /health 應顯示 v21.0-stable
- 呼叫 /learning_status 檢查 learning_guard 與 duplicate_excluded_count
- 呼叫 /scan_top5 預覽 market_regime（preview 不寫 DB）

可選 Environment Variables
LEARNING_SHADOW_MIN_SAMPLES=10
LEARNING_AUTO_APPLY_MIN_SAMPLES=30
LEARNING_MAX_ADJUSTMENT=3
LEARNING_MAX_ABS_DAY5_RETURN=20
LEARNING_GUARD_MIN_UNIQUE_DATES=6
LEARNING_GUARD_MAX_SINGLE_DATE_SHARE=0.25
LEARNING_GUARD_MIN_FACTOR_SIDE=5
LEARNING_GUARD_MIN_WIN_EDGE=5
LEARNING_GUARD_MIN_RETURN_EDGE=0.30
