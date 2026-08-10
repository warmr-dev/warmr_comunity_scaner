#!/usr/bin/env sh
set -eu

cd /app

: "${SCANNER_MODE:=run}"
: "${DISCOVERY_PROVIDERS:=searxng}"
: "${SYNC_VALUE_TIERS:=high,medium,low}"
: "${WARMR_TABLE_NAME:=community_scanner}"
: "${WARMR_UPSERT_KEY:=canonical_key}"
: "${USE_FETCH_QUEUE:=false}"
: "${NICHE_PAUSE_SECONDS:=20}"

# PIPE_NICHES takes priority (comma-separated). Fallback: single PIPE_NICHE.
if [ -n "${PIPE_NICHES:-}" ]; then
  NICHES="$PIPE_NICHES"
else
  NICHES="${PIPE_NICHE:-business}"
fi

GEO_ARGS="${PIPE_GEO:-USA}"
AUDIENCE_ARGS="${PIPE_AUDIENCE:-professionals}"
QUERIES_ARGS="${PIPE_QUERIES:-12}"
PER_QUERY_ARGS="${PIPE_PER_QUERY:-20}"
MAX_FETCH_ARGS="${PIPE_MAX_FETCH:-500}"
WORKER_MAX_ITEMS_ARGS="${WORKER_MAX_ITEMS:-100000}"

community-scanner init-db

run_one_niche() {
  niche="$1"
  echo "=== niche=${niche} geo=${GEO_ARGS} ==="
  if [ "$USE_FETCH_QUEUE" = "true" ] && [ "$SCANNER_MODE" = "discovery" ]; then
    community-scanner discover \
      --niche "$niche" \
      --geo "$GEO_ARGS" \
      --audience "$AUDIENCE_ARGS" \
      --queries "$QUERIES_ARGS" \
      --per-query "$PER_QUERY_ARGS"
  else
    community-scanner run \
      --niche "$niche" \
      --geo "$GEO_ARGS" \
      --audience "$AUDIENCE_ARGS" \
      --queries "$QUERIES_ARGS" \
      --per-query "$PER_QUERY_ARGS" \
      --max-fetch "$MAX_FETCH_ARGS"
  fi
}

run_all_niches() {
  OLD_IFS=$IFS
  IFS=,
  # shellcheck disable=SC2086
  set -- $NICHES
  IFS=$OLD_IFS
  first=1
  for niche in "$@"; do
    niche=$(echo "$niche" | tr -d ' ')
    [ -z "$niche" ] && continue
    if [ "$first" -eq 0 ] && [ "$NICHE_PAUSE_SECONDS" -gt 0 ]; then
      echo "pause ${NICHE_PAUSE_SECONDS}s between niches (rate-limit protection)"
      sleep "$NICHE_PAUSE_SECONDS"
    fi
    first=0
    run_one_niche "$niche"
  done
}

case "$SCANNER_MODE" in
  discovery|run|full)
    run_all_niches
    if [ "$SCANNER_MODE" = "full" ] && [ "$USE_FETCH_QUEUE" = "true" ]; then
      community-scanner worker --max-items "$WORKER_MAX_ITEMS_ARGS"
    fi
    ;;
  worker)
    community-scanner worker --max-items "$WORKER_MAX_ITEMS_ARGS"
    ;;
  *)
    echo "Unknown SCANNER_MODE=$SCANNER_MODE (use full|discovery|worker|run)" >&2
    exit 1
    ;;
esac

if [ -n "${WARMR_DATABASE_URL:-}" ]; then
  community-scanner sync-warmr \
    --value-tiers "$SYNC_VALUE_TIERS" \
    --table "$WARMR_TABLE_NAME" \
    --upsert-key "$WARMR_UPSERT_KEY"
fi
