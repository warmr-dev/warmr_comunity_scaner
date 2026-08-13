#!/usr/bin/env sh
set -eu

cd /app

: "${SCANNER_MODE:=run}"
: "${DISCOVERY_PROVIDERS:=directory,searxng}"
: "${SYNC_VALUE_TIERS:=high,medium,low}"
: "${WARMR_TABLE_NAME:=community_scanner}"
: "${WARMR_UPSERT_KEY:=canonical_key}"
: "${USE_FETCH_QUEUE:=false}"
: "${NICHE_PAUSE_SECONDS:=3}"
: "${PIPE_NICHES:=auto}"
: "${PIPE_QUERIES:=24}"
: "${PIPE_PER_QUERY:=25}"
: "${PIPE_MAX_FETCH:=80}"
: "${NICHE_LOOPS:=1}"

resolve_niches() {
  if [ "$PIPE_NICHES" != "auto" ] && [ -n "$PIPE_NICHES" ]; then
    echo "$PIPE_NICHES"
    return 0
  fi

  for candidate in \
    "/app/src/community_scanner/seed_data/niches_usa.txt" \
    "/usr/local/lib/python3.12/site-packages/community_scanner/seed_data/niches_usa.txt" \
    "/usr/local/lib/python3.11/site-packages/community_scanner/seed_data/niches_usa.txt" \
    "/usr/local/lib/python3.10/site-packages/community_scanner/seed_data/niches_usa.txt" \
    "/app/data/niches_usa.txt"
  do
    if [ -f "$candidate" ]; then
      echo "Loading niches from $candidate" >&2
      # Convert newlines to commas; strip UTF-8 BOM / CR
      tr -d '\r' < "$candidate" | sed '1s/^\xEF\xBB\xBF//' | tr '\n' ',' | sed 's/,$//'
      return 0
    fi
  done

  # Fallback single niche
  echo "${PIPE_NICHE:-business}"
}

NICHES="$(resolve_niches)"
GEO_ARGS="${PIPE_GEO:-USA}"
AUDIENCE_ARGS="${PIPE_AUDIENCE:-professionals}"
QUERIES_ARGS="${PIPE_QUERIES}"
PER_QUERY_ARGS="${PIPE_PER_QUERY}"
MAX_FETCH_ARGS="${PIPE_MAX_FETCH}"
WORKER_MAX_ITEMS_ARGS="${WORKER_MAX_ITEMS:-100000}"

NICHE_COUNT=$(echo "$NICHES" | tr ',' '\n' | sed '/^\s*$/d' | wc -l | tr -d ' ')
echo "USA niches queued: ${NICHE_COUNT} loops=${NICHE_LOOPS}"

community-scanner init-db

run_one_niche() {
  niche="$1"
  echo "=== niche=${niche} geo=${GEO_ARGS} ==="
  community-scanner run \
    --niche "$niche" \
    --geo "$GEO_ARGS" \
    --audience "$AUDIENCE_ARGS" \
    --queries "$QUERIES_ARGS" \
    --per-query "$PER_QUERY_ARGS" \
    --max-fetch "$MAX_FETCH_ARGS"
}

run_all_niches() {
  OLD_IFS=$IFS
  IFS=,
  # shellcheck disable=SC2086
  set -- $NICHES
  IFS=$OLD_IFS
  first=1
  for niche in "$@"; do
    niche=$(echo "$niche" | tr -d ' \r')
    [ -z "$niche" ] && continue
    if [ "$first" -eq 0 ] && [ "$NICHE_PAUSE_SECONDS" -gt 0 ]; then
      echo "pause ${NICHE_PAUSE_SECONDS}s between niches"
      sleep "$NICHE_PAUSE_SECONDS"
    fi
    first=0
    if ! run_one_niche "$niche"; then
      echo "WARN: niche=${niche} failed; continuing"
    fi
  done
}

case "$SCANNER_MODE" in
  discovery|run|full)
    loop=1
    while [ "$loop" -le "$NICHE_LOOPS" ]; do
      echo "=== niche loop ${loop}/${NICHE_LOOPS} ==="
      run_all_niches
      loop=$((loop + 1))
    done
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
