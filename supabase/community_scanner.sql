-- Supabase: public.community_scanner
-- Run in SQL Editor if init-db from Railway fails, or apply via MCP/migration.

create table if not exists public.community_scanner (
  id text primary key,
  canonical_key text not null,
  canonical_domain text not null,
  platform text not null default 'custom',
  platform_id text,
  website text not null,
  name text,
  niche text,
  audience text,
  geo text,
  join_url text,
  price_text text,
  price_amount double precision,
  currency text,
  size_text text,
  size_members integer,
  contacts jsonb not null default '{}'::jsonb,
  access_status text not null default 'watch',
  value_score integer not null default 0,
  value_tier text not null default 'low',
  relevance_score double precision not null default 0,
  source_queries jsonb not null default '[]'::jsonb,
  raw_signals jsonb not null default '{}'::jsonb,
  content_hash text,
  sync_status text not null default 'pending',
  synced_at timestamptz,
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  last_changed_at timestamptz
);

create unique index if not exists uq_community_scanner_canonical_key
  on public.community_scanner (canonical_key);

create index if not exists ix_community_scanner_canonical_domain
  on public.community_scanner (canonical_domain);

create index if not exists ix_community_scanner_platform_id
  on public.community_scanner (platform_id);

create index if not exists ix_community_scanner_value_tier
  on public.community_scanner (value_tier);

alter table public.community_scanner enable row level security;

-- Service role / direct Postgres (Railway) bypasses RLS.
-- Optional: allow read for authenticated users later.
