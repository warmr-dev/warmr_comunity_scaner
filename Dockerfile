# All-in-one: scanner + SearXNG on Debian (python:3.10-slim).
# Official searxng/searxng image is Wolfi (no apt/apk) — install SearXNG from source instead.
FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    ca-certificates \
    git \
    libxml2-dev \
    libxslt-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src
COPY docker ./docker

# Clone SearXNG, install its deps first (setup.py imports msgspec), then scanner.
RUN git clone --depth 1 https://github.com/searxng/searxng.git /opt/searxng \
    && pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir granian \
    && pip install --no-cache-dir -r /opt/searxng/requirements.txt \
    && pip install --no-cache-dir --no-deps /opt/searxng \
    && pip install --no-cache-dir . \
    && mkdir -p /app/data /etc/searxng

COPY docker/searxng/settings.yml /etc/searxng/settings.yml

ENV SCANNER_DATA_DIR=/app/data \
    BUNDLE_SEARXNG=true \
    SEARXNG_BASE_URL=http://127.0.0.1:8080 \
    SEARXNG_SETTINGS_PATH=/etc/searxng/settings.yml \
    SEARXNG_BIND_ADDRESS=127.0.0.1 \
    SEARXNG_PORT=8080 \
    USE_FETCH_QUEUE=false \
    SCANNER_MODE=run \
    DISCOVERY_PROVIDERS=searxng \
    PYTHONPATH=/opt/searxng

RUN chmod +x /app/docker/entrypoint.sh /app/docker/entrypoint-all-in-one.sh

ENTRYPOINT ["/app/docker/entrypoint-all-in-one.sh"]
