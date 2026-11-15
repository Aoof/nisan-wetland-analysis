# NISAN flood watch: web app + data API in one container.
# The API (FastAPI) serves /api/* and the built Vite app at /, so the browser talks to a single origin.
#
#   docker build -t nisan --build-arg CARTO_API_KEY=... .
#   docker run -p 8000:8000 -e EARTHDATA_TOKEN=... -v nisan-data:/data nisan

# ---------- 1. web app ----------
FROM node:22-alpine AS web
WORKDIR /src/nisan-app
COPY nisan-app/package.json nisan-app/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY nisan-app/ ./
# Vite inlines these at build time. CARTO map keys are public by design: restrict the key to your domain.
# VITE_API_BASE stays empty so the app calls /api on the same origin.
ARG CARTO_API_KEY=""
ARG VITE_API_BASE=""
ENV CARTO_API_KEY=$CARTO_API_KEY VITE_API_BASE=$VITE_API_BASE
RUN npm run build

# ---------- 2. Python dependencies ----------
FROM python:3.12-slim-bookworm AS deps
COPY --from=ghcr.io/astral-sh/uv:0.9.7 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app/nisan-api
COPY nisan-api/pyproject.toml nisan-api/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project

# ---------- 3. runtime ----------
FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 \
    PATH=/app/nisan-api/.venv/bin:$PATH \
    NISAN_DATA=/data \
    NISAN_SANDBOXES=/sandboxes \
    NISAN_STATIC=/app/web \
    NISAN_WEBROOT=/srv/www
# libexpat1: the rasterio wheel's bundled GDAL links against it, and slim images leave it out.
RUN apt-get update && apt-get install -y --no-install-recommends libexpat1 && rm -rf /var/lib/apt/lists/* \
 && useradd --system --uid 10001 --home /app nisan \
 && mkdir -p /data /sandboxes /srv/www && chown nisan /data /sandboxes /srv/www
# Paths mirror the repo, so settings.py finds nisan-app/src/data/places.json without changes.
COPY --from=deps /app/nisan-api/.venv /app/nisan-api/.venv
COPY nisan-api/app /app/nisan-api/app
COPY nisan-app/src/data/places.json /app/nisan-app/src/data/places.json
COPY --from=web /src/nisan-app/dist /app/web
# Served at / ahead of the web app: ACME HTTP-01 tokens under .well-known/acme-challenge/, robots.txt, etc.
COPY --chown=nisan webroot/ /srv/www/
WORKDIR /app/nisan-api
USER nisan
EXPOSE 8000
# /data: everything the background jobs download and cut (keep it on a volume).
# /srv/www: webroot; share it with your ACME client (certbot --webroot -w /srv/www).
# /sandboxes: optional data-sources folder; the DEM/HAND rasters go in copernicus-dem-sandbox/data/processed/.
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"
# One worker on purpose: the refresh scheduler runs inside the process, more workers would duplicate the jobs.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
