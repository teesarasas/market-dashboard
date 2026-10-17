-- Trade log table for the dashboard. Run once in Supabase: SQL Editor > New query > paste > Run.
create table if not exists public.trades (
  id            uuid primary key default gen_random_uuid(),
  created_at    timestamptz not null default now(),
  status        text not null check (status in ('open', 'closed', 'skipped')),
  entry_time    timestamptz not null,
  pair          text not null,
  side          text not null check (side in ('Long', 'Short')),
  entry         numeric not null,
  sl            numeric not null,
  tp            numeric,
  tp_choice     text,
  lots          numeric,
  balance       numeric,
  risk_pct      numeric,
  risk_money    numeric,
  stop_method   text,
  stop_band     text,
  tags          text[] not null default '{}',
  note          text,
  snapshot      jsonb not null default '{}'::jsonb,   -- every dashboard value at the moment of logging
  exit_time     timestamptz,
  exit_price    numeric,
  exit_reason   text,
  r_result      numeric,
  pnl           numeric,
  hold_minutes  numeric
);

create index if not exists trades_status_idx on public.trades (status, entry_time desc);

-- Row Level Security on, with no policies: the public (publishable/anon) key can do nothing.
-- The dashboard uses a server-side secret key, which bypasses RLS.
alter table public.trades enable row level security;
