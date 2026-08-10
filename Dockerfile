# All-in-one: bundled SearXNG + community scanner (single Railway service).
# Base image searxng/searxng is Alpine — use apk, not apt-get.
FROM searxng/searxng:latest

USER root

WORKDIR /app

RUN apk add --no-cache \
    build-base \
    curl \
    python3-dev \
    py3-pip \
    libxml2-dev \
    libxslt-dev \
    libffi-dev \
    openssl-dev

COPY pyproject.toml README.md ./
COPY src ./src
COPY docker ./docker

RUN pip3 install --no-cache-dir . \
    && mkdir -p /app/data

COPY docker/searxng/settings.yml /etc/searxng/settings.yml

ENV SCANNER_DATA_DIR=/app/data \
    BUNDLE_SEARXNG=true \
    SEARXNG_BASE_URL=http://127.0.0.1:8080 \
    SEARXNG_BIND_ADDRESS=127.0.0.1 \
    USE_FETCH_QUEUE=false \
    SCANNER_MODE=run \
    DISCOVERY_PROVIDERS=searxng

RUN chmod +x /app/docker/entrypoint.sh /app/docker/entrypoint-all-in-one.sh

ENTRYPOINT ["/app/docker/entrypoint-all-in-one.sh"]
