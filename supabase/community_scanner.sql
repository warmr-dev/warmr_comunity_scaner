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

-- Bulk discovery buffer (high-volume URLs before community upsert)
create table if not exists public.raw_candidates (
  id text primary key,
  url text not null,
  canonical_key text,
  platform text,
  platform_id text,
  source_provider text not null,
  source_record_id text not null,
  title text,
  snippet text,
  raw_payload_hash text,
  community_likelihood double precision not null default 0,
  status text not null default 'new',
  discovered_at timestamptz not null default now(),
  processed_at timestamptz
);

create unique index if not exists uq_raw_candidates_source_record
  on public.raw_candidates (source_provider, source_record_id);

create index if not exists ix_raw_candidates_canonical_key
  on public.raw_candidates (canonical_key);

create index if not exists ix_raw_candidates_provider
  on public.raw_candidates (source_provider);

create index if not exists ix_raw_candidates_status
  on public.raw_candidates (status);

create index if not exists ix_raw_candidates_likelihood
  on public.raw_candidates (community_likelihood);
