#!/usr/bin/env sh
set -eu

cd /app

: "${DISCOVERY_PROVIDERS:=seeds}"
: "${SYNC_VALUE_TIERS:=high,medium,low}"
: "${WARMR_TABLE_NAME:=community_scanner}"
: "${WARMR_UPSERT_KEY:=canonical_key}"

NICE_ARGS="${PIPE_NICHE:-accounting}"
GEO_ARGS="${PIPE_GEO:-Florida}"
# One query batch; pull a large seed page so we don't stop at 3 URLs
QUERIES_ARGS="${PIPE_QUERIES:-1}"
PER_QUERY_ARGS="${PIPE_PER_QUERY:-120}"
MAX_FETCH_ARGS="${PIPE_MAX_FETCH:-120}"

community-scanner init-db

community-scanner run \
  --niche "$NICE_ARGS" \
  --geo "$GEO_ARGS" \
  --queries "$QUERIES_ARGS" \
  --per-query "$PER_QUERY_ARGS" \
  --max-fetch "$MAX_FETCH_ARGS"

if [ -n "${WARMR_DATABASE_URL:-}" ]; then
  community-scanner sync-warmr \
    --value-tiers "$SYNC_VALUE_TIERS" \
    --table "$WARMR_TABLE_NAME" \
    --upsert-key "$WARMR_UPSERT_KEY"
fi
