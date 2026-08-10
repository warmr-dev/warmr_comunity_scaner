#!/usr/bin/env sh
set -eu

# Bundled SearXNG + scanner in one Railway service.
# Set BUNDLE_SEARXNG=false if you run an external SearXNG sidecar instead.

start_searxng() {
  if [ "${BUNDLE_SEARXNG:-true}" != "true" ]; then
    echo "BUNDLE_SEARXNG=false — using external SEARXNG_BASE_URL=${SEARXNG_BASE_URL:-}"
    return 0
  fi

  echo "Starting bundled SearXNG on 127.0.0.1:8080..."
  export SEARXNG_BIND_ADDRESS="${SEARXNG_BIND_ADDRESS:-127.0.0.1}"
  export SEARXNG_PORT="${SEARXNG_PORT:-8080}"
  if [ -z "${SEARXNG_SECRET:-}" ]; then
    export SEARXNG_SECRET="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
  fi

  if [ -f /usr/local/searxng/dockerfiles/docker-entrypoint.sh ]; then
    sh /usr/local/searxng/dockerfiles/docker-entrypoint.sh &
  else
    echo "ERROR: SearXNG entrypoint not found in image" >&2
    exit 1
  fi
}

wait_searxng() {
  if [ "${BUNDLE_SEARXNG:-true}" != "true" ]; then
    return 0
  fi

  base="${SEARXNG_BASE_URL:-http://127.0.0.1:8080}"
  base="${base%/}"
  for _ in $(seq 1 90); do
    if curl -sf "${base}/search?q=warmr&format=json" >/dev/null 2>&1; then
      echo "SearXNG ready at ${base}"
      return 0
    fi
    sleep 1
  done
  echo "WARN: SearXNG did not respond in 90s — discovery may fail" >&2
}

start_searxng
wait_searxng

export SEARXNG_BASE_URL="${SEARXNG_BASE_URL:-http://127.0.0.1:8080}"

exec /app/docker/entrypoint.sh
