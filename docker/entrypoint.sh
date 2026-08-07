#!/usr/bin/env sh
set -eu

cd /app

: "${DISCOVERY_PROVIDERS:=seeds}"
: "${SYNC_VALUE_TIERS:=high,medium,low}"
: "${WARMR_TABLE_NAME:=community_scanner}"
: "${WARMR_UPSERT_KEY:=canonical_key}"

NICE_ARGS="${PIPE_NICHE:-accounting}"
GEO_ARGS="${PIPE_GEO:-Florida}"
QUERIES_ARGS="${PIPE_QUERIES:-5}"

# 0) Create/update schema on DATABASE_URL (Supabase table community_scanner)
community-scanner init-db

# 1) Discovery + parse + classify + upsert into community_scanner
community-scanner run \
  --niche "$NICE_ARGS" \
  --geo "$GEO_ARGS" \
  --queries "$QUERIES_ARGS" \
  --per-query "${PIPE_PER_QUERY:-10}" \
  --max-fetch "${PIPE_MAX_FETCH:-40}"

# 2) Optional: sync to a second DB if WARMR_DATABASE_URL is set
if [ -n "${WARMR_DATABASE_URL:-}" ]; then
  community-scanner sync-warmr \
    --value-tiers "$SYNC_VALUE_TIERS" \
    --table "$WARMR_TABLE_NAME" \
    --upsert-key "$WARMR_UPSERT_KEY"
fi
