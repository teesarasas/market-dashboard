-- Signals recorded by the Telegram bot (bot/run.py). Run once in Supabase: SQL Editor > New query > Run.
-- kind 'setup' = passed ADX, DI spread and Trend (recorded silently, to test the extra conditions later)
-- kind 'alert' = passed every alert condition (sent to Telegram when sent = true)
create table if not exists public.signals (
  id          uuid primary key default gen_random_uuid(),
  created_at  timestamptz not null default now(),
  kind        text not null check (kind in ('setup', 'alert')),
  symbol      text not null,
  side        text not null check (side in ('Long', 'Short')),
  bar_time    timestamptz not null,        -- start of the closed 10m bar that triggered it (UTC)
  price       numeric,
  checks      jsonb not null default '{}'::jsonb,
  snapshot    jsonb not null default '{}'::jsonb,
  sent        boolean not null default false,
  unique (symbol, bar_time, kind)
);

create index if not exists signals_bar_time_idx on public.signals (bar_time desc);

-- Same security as the trades table: RLS on, no policies; the server-side secret key bypasses RLS.
alter table public.signals enable row level security;
