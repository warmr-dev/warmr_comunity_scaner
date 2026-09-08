#!/usr/bin/env sh
set -eu

cd /app

: "${SCANNER_MODE:=mass}"
: "${DISCOVERY_PROVIDERS:=commoncrawl,hive,searxng}"
: "${SYNC_VALUE_TIERS:=high,medium,low}"
: "${WARMR_TABLE_NAME:=community_scanner}"
: "${WARMR_UPSERT_KEY:=canonical_key}"
: "${USE_FETCH_QUEUE:=false}"
: "${NICHE_PAUSE_SECONDS:=2}"
: "${PIPE_NICHES:=auto}"
: "${PIPE_QUERIES:=60}"
: "${PIPE_PER_QUERY:=80}"
: "${PIPE_MAX_FETCH:=3000}"
: "${NICHE_LOOPS:=0}"
: "${LOOP_PAUSE_SECONDS:=45}"
: "${SCANNER_DATA_DIR:=/app/data}"

mkdir -p "$SCANNER_DATA_DIR"
OFFSET_FILE="${SCANNER_DATA_DIR}/cc_index_offset"

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

bump_cc_offset() {
  offset=0
  if [ -f "$OFFSET_FILE" ]; then
    offset=$(tr -d ' \r\n' < "$OFFSET_FILE" || echo 0)
  fi
  case "$offset" in
    ''|*[!0-9]*) offset=0 ;;
  esac
  export COMMONCRAWL_INDEX_OFFSET="$offset"
  echo "COMMONCRAWL_INDEX_OFFSET=${COMMONCRAWL_INDEX_OFFSET}"
  echo $((offset + 1)) > "$OFFSET_FILE"
}

NICHES="$(resolve_niches)"
GEO_ARGS="${PIPE_GEO:-USA}"
AUDIENCE_ARGS="${PIPE_AUDIENCE:-professionals}"
QUERIES_ARGS="${PIPE_QUERIES}"
PER_QUERY_ARGS="${PIPE_PER_QUERY}"
MAX_FETCH_ARGS="${PIPE_MAX_FETCH}"
WORKER_MAX_ITEMS_ARGS="${WORKER_MAX_ITEMS:-100000}"

NICHE_COUNT=$(echo "$NICHES" | tr ',' '\n' | sed '/^\s*$/d' | wc -l | tr -d ' ')
if [ "$NICHE_LOOPS" = "0" ]; then
  echo "USA niches queued: ${NICHE_COUNT} loops=infinite (pause ${LOOP_PAUSE_SECONDS}s between cycles)"
else
  echo "USA niches queued: ${NICHE_COUNT} loops=${NICHE_LOOPS}"
fi

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

run_mass_cycle() {
  bump_cc_offset
  echo "=== mass-fill harvest geo=${GEO_ARGS} queries=${QUERIES_ARGS} per_query=${PER_QUERY_ARGS} max_fetch=${MAX_FETCH_ARGS} ==="
  community-scanner mass-fill \
    --niche harvest \
    --geo "$GEO_ARGS" \
    --audience "$AUDIENCE_ARGS" \
    --queries "$QUERIES_ARGS" \
    --per-query "$PER_QUERY_ARGS" \
    --max-fetch "$MAX_FETCH_ARGS"
}

case "$SCANNER_MODE" in
  mass|mass-fill|harvest)
    # Fast free-tier volume: Common Crawl + Hive, rotate CC index each cycle.
    loop=1
    while :; do
      if [ "$NICHE_LOOPS" = "0" ]; then
        echo "=== mass loop ${loop}/∞ ==="
      else
        if [ "$loop" -gt "$NICHE_LOOPS" ]; then
          break
        fi
        echo "=== mass loop ${loop}/${NICHE_LOOPS} ==="
      fi
      if ! run_mass_cycle; then
        echo "WARN: mass-fill cycle failed; continuing after pause"
      fi
      if [ "$NICHE_LOOPS" != "0" ]; then
        loop=$((loop + 1))
        continue
      fi
      if [ "$LOOP_PAUSE_SECONDS" -gt 0 ]; then
        echo "mass cycle ${loop} done; pause ${LOOP_PAUSE_SECONDS}s before next cycle"
        sleep "$LOOP_PAUSE_SECONDS"
      fi
      loop=$((loop + 1))
    done
    ;;
  discovery|run|full)
    loop=1
    while :; do
      if [ "$NICHE_LOOPS" = "0" ]; then
        echo "=== niche loop ${loop}/∞ ==="
      else
        if [ "$loop" -gt "$NICHE_LOOPS" ]; then
          break
        fi
        echo "=== niche loop ${loop}/${NICHE_LOOPS} ==="
      fi
      run_all_niches
      if [ "$NICHE_LOOPS" != "0" ]; then
        loop=$((loop + 1))
        continue
      fi
      if [ "$LOOP_PAUSE_SECONDS" -gt 0 ]; then
        echo "cycle ${loop} done; pause ${LOOP_PAUSE_SECONDS}s before next cycle"
        sleep "$LOOP_PAUSE_SECONDS"
      fi
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
    echo "Unknown SCANNER_MODE=$SCANNER_MODE (use mass|full|discovery|worker|run)" >&2
    exit 1
    ;;
esac

if [ -n "${WARMR_DATABASE_URL:-}" ]; then
  community-scanner sync-warmr \
    --value-tiers "$SYNC_VALUE_TIERS" \
    --table "$WARMR_TABLE_NAME" \
    --upsert-key "$WARMR_UPSERT_KEY"
fi
