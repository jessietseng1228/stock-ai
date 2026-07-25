-- 股票 AI 助理 v20.5 Learning Engine
-- 在 Supabase SQL Editor 執行一次。
-- 使用 IF NOT EXISTS，可重複執行。

ALTER TABLE public.ai_recommend_history
    ADD COLUMN IF NOT EXISTS base_score integer,
    ADD COLUMN IF NOT EXISTS confidence integer,
    ADD COLUMN IF NOT EXISTS rr numeric(10,4),
    ADD COLUMN IF NOT EXISTS pattern text,
    ADD COLUMN IF NOT EXISTS decision text,
    ADD COLUMN IF NOT EXISTS technical_score integer,
    ADD COLUMN IF NOT EXISTS learning_adjustment numeric(10,2),
    ADD COLUMN IF NOT EXISTS learning_version text;

CREATE INDEX IF NOT EXISTS idx_ai_recommend_history_day5
    ON public.ai_recommend_history (day5_date, day5_return);

CREATE INDEX IF NOT EXISTS idx_ai_recommend_history_learning
    ON public.ai_recommend_history (base_score, confidence, rr);
