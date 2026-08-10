#!/usr/bin/env sh
set -eu

start_searxng() {
  if [ "${BUNDLE_SEARXNG:-true}" != "true" ]; then
    echo "BUNDLE_SEARXNG=false — using external SEARXNG_BASE_URL=${SEARXNG_BASE_URL:-}"
    return 0
  fi

  echo "Starting bundled SearXNG (granian) on ${SEARXNG_BIND_ADDRESS:-127.0.0.1}:${SEARXNG_PORT:-8080}..."
  export SEARXNG_SETTINGS_PATH="${SEARXNG_SETTINGS_PATH:-/etc/searxng/settings.yml}"
  export GRANIAN_INTERFACE=wsgi
  export GRANIAN_HOST="${SEARXNG_BIND_ADDRESS:-127.0.0.1}"
  export GRANIAN_PORT="${SEARXNG_PORT:-8080}"
  export GRANIAN_WEBSOCKETS=false

  granian searx.webapp:app &
}

wait_searxng() {
  if [ "${BUNDLE_SEARXNG:-true}" != "true" ]; then
    return 0
  fi

  base="${SEARXNG_BASE_URL:-http://127.0.0.1:8080}"
  base="${base%/}"
  for _ in $(seq 1 120); do
    if curl -sf "${base}/search?q=warmr&format=json" >/dev/null 2>&1; then
      echo "SearXNG ready at ${base}"
      return 0
    fi
    sleep 1
  done
  echo "WARN: SearXNG did not respond in 120s — discovery may fail" >&2
}

start_searxng
wait_searxng

export SEARXNG_BASE_URL="${SEARXNG_BASE_URL:-http://127.0.0.1:8080}"

exec /app/docker/entrypoint.sh
