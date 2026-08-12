# Production setup: Brave Search + Supabase (`community_scanner`)

Project ref: `bpxiawuzidhjalaemejy` (name: scanner)

## 1. Why Railway crashed

Log: `psycopg.errors.ConnectionTimeout` on `init-db`.

Usually means `DATABASE_URL` points at Supabase **Direct** host (`db.xxx.supabase.co:5432`), which often needs IPv6. Railway needs **Session pooler** (IPv4).

## 2. Get Supabase connection string (required)

1. Open https://supabase.com/dashboard/project/bpxiawuzidhjalaemejy  
2. **Project Settings → Database → Connection string**  
3. Choose **Session pooler** (or Transaction pooler)  
4. Copy URI, replace `[YOUR-PASSWORD]` with DB password  

Convert for SQLAlchemy/psycopg:

```text
postgresql://postgres.bpxiawuzidhjalaemejy:PASSWORD@aws-0-REGION.pooler.supabase.com:5432/postgres
```

→ for our app:

```text
postgresql+psycopg://postgres.bpxiawuzidhjalaemejy:PASSWORD@aws-0-REGION.pooler.supabase.com:5432/postgres
```

Notes:
- Prefer **port 5432 Session mode** for SQLAlchemy `create_all` / upserts.  
- If password has special chars (`@`, `#`, `%`), URL-encode them.  
- Do **not** use `localhost` / Railway Postgres unless you intend a separate DB.

## 3. Create table `community_scanner`

Option A — Supabase SQL Editor: paste `supabase/community_scanner.sql` and Run.

Option B — Railway will run `community-scanner init-db` on start (creates table if connection works).

## 4. Discovery: Brave only

```env
DISCOVERY_PROVIDERS=brave
BRAVE_SEARCH_API_KEY=your_key_here
BRAVE_COUNTRY=us
BRAVE_SEARCH_LANG=en
BRAVE_MAX_REQUESTS=200
DISCOVERY_CONCURRENCY=1
```

Key: https://brave.com/search/api/

## 5. Other keys (optional)

| Key | Needed? | Where |
|-----|---------|--------|
| `BRAVE_SEARCH_API_KEY` | Required for web search | brave.com/search/api |
| `OPENAI_API_KEY` | Only if `LLM_ENABLED=true` | platform.openai.com |

## 6. Railway Variables (copy)

```env
APP_ENV=production
DATABASE_URL=postgresql+psycopg://postgres.bpxiawuzidhjalaemejy:YOUR_DB_PASSWORD@YOUR_POOLER_HOST:5432/postgres
SCANNER_DATA_DIR=/app/data

DISCOVERY_PROVIDERS=brave
BRAVE_SEARCH_API_KEY=
BRAVE_COUNTRY=us
BRAVE_SEARCH_LANG=en
BRAVE_MAX_REQUESTS=200
DISCOVERY_CONCURRENCY=1

LLM_ENABLED=false
OPENAI_API_KEY=
LLM_MODEL=gpt-4o-mini

WARMR_DATABASE_URL=
WARMR_SYNC_ENABLED=false
SYNC_VALUE_TIERS=high,medium,low
WARMR_TABLE_NAME=community_scanner
WARMR_UPSERT_KEY=canonical_key

HTTP_TIMEOUT_SECONDS=20
CRAWL_DOWNLOAD_DELAY_SECONDS=1.0

PIPE_NICHES=software-engineering,education
PIPE_GEO=USA
PIPE_QUERIES=20
PIPE_PER_QUERY=25
PIPE_MAX_FETCH=100
SCANNER_MODE=run
```

## 7. Redeploy and verify

Redeploy after setting vars. Check logs for Brave search hits and successful DB upserts.
