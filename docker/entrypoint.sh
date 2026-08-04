#!/usr/bin/env sh
set -eu

cd /app

# Minimal smoke for production-like envs.
# You can override DISCOVERY_PROVIDERS/BRAVE/WARM[AR] env vars in Railway/Render.

: "${DISCOVERY_PROVIDERS:=seeds}"

NICE_ARGS="${PIPE_NICHE:-accounting}"
GEO_ARGS="${PIPE_GEO:-Florida}"
QUERIES_ARGS="${PIPE_QUERIES:-1}"

# 1) Run scanner
community-scanner run --niche "$NICE_ARGS" --geo "$GEO_ARGS" --queries "$QUERIES_ARGS" --per-query "${PIPE_PER_QUERY:-10}" --max-fetch "${PIPE_MAX_FETCH:-20}"

# 2) Optional sync into Warmr (only if WARMR_DATABASE_URL is set)
if [ -n "${WARMR_DATABASE_URL:-}" ]; then
  community-scanner sync-warmr --value-tiers "${SYNC_VALUE_TIERS:-high,medium}" --table "${WARMR_TABLE_NAME:-communities}" --upsert-key "${WARMR_UPSERT_KEY:-canonical_key}"
fi

