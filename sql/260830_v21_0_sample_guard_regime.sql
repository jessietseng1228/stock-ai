-- 股票 AI 助理 v21.0 | Sample Dedup + Learning Guard + Market Regime
-- Supabase SQL Editor 執行一次。可重複執行。

ALTER TABLE public.ai_recommend_history
    ADD COLUMN IF NOT EXISTS market_regime varchar(20) DEFAULT 'UNKNOWN',
    ADD COLUMN IF NOT EXISTS market_regime_reason text DEFAULT '';

-- DB 層 Sample Dedup Guard：同一掃描日、同一股票只能有一筆推薦。
-- 舊版理論上已有此 constraint；此段用 index 再保護一次。
CREATE UNIQUE INDEX IF NOT EXISTS idx_ai_recommend_history_sample_dedup
    ON public.ai_recommend_history (scan_date, symbol);

CREATE INDEX IF NOT EXISTS idx_ai_recommend_history_regime_day5
    ON public.ai_recommend_history (market_regime, day5_date, day5_return);
