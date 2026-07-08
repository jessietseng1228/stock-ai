-- v17：TOP5 可買每日市場掃描結果
-- 請到 Supabase SQL Editor 執行一次。

create table if not exists public.market_top5_results (
  id bigserial primary key,
  scan_date date not null,
  rank int not null,
  symbol text not null,
  name text,
  score int,
  stars text,
  trend text,
  price numeric,
  change_pct numeric,
  five_pct numeric,
  support numeric,
  resistance numeric,
  stop_loss numeric,
  turnover numeric,
  reasons jsonb default '[]'::jsonb,
  created_at timestamptz default now(),
  unique (scan_date, symbol)
);

create index if not exists idx_market_top5_results_date_rank
on public.market_top5_results (scan_date, rank);
