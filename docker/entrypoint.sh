#!/usr/bin/env sh
set -eu

cd /app

: "${SCANNER_MODE:=run}"
: "${DISCOVERY_PROVIDERS:=searxng}"
: "${SYNC_VALUE_TIERS:=high,medium,low}"
: "${WARMR_TABLE_NAME:=community_scanner}"
: "${WARMR_UPSERT_KEY:=canonical_key}"
: "${USE_FETCH_QUEUE:=false}"

NICE_ARGS="${PIPE_NICHE:-business}"
GEO_ARGS="${PIPE_GEO:-USA}"
QUERIES_ARGS="${PIPE_QUERIES:-20}"
PER_QUERY_ARGS="${PIPE_PER_QUERY:-30}"
MAX_FETCH_ARGS="${PIPE_MAX_FETCH:-500}"
WORKER_MAX_ITEMS_ARGS="${WORKER_MAX_ITEMS:-100000}"

community-scanner init-db

run_discovery() {
  if [ "$USE_FETCH_QUEUE" = "true" ]; then
    community-scanner discover \
      --niche "$NICE_ARGS" \
      --geo "$GEO_ARGS" \
      --queries "$QUERIES_ARGS" \
      --per-query "$PER_QUERY_ARGS"
  else
    community-scanner run \
      --niche "$NICE_ARGS" \
      --geo "$GEO_ARGS" \
      --queries "$QUERIES_ARGS" \
      --per-query "$PER_QUERY_ARGS" \
      --max-fetch "$MAX_FETCH_ARGS"
  fi
}

run_worker() {
  community-scanner worker --max-items "$WORKER_MAX_ITEMS_ARGS"
}

case "$SCANNER_MODE" in
  discovery)
    run_discovery
    ;;
  worker)
    run_worker
    ;;
  run)
    community-scanner run \
      --niche "$NICE_ARGS" \
      --geo "$GEO_ARGS" \
      --queries "$QUERIES_ARGS" \
      --per-query "$PER_QUERY_ARGS" \
      --max-fetch "$MAX_FETCH_ARGS"
    ;;
  full)
    run_discovery
    if [ "$USE_FETCH_QUEUE" = "true" ]; then
      run_worker
    fi
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
