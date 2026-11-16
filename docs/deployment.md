# Deployment

One image serves the web app at `/` and the data API at `/api` (see the [`Dockerfile`](../Dockerfile)). It listens on plain HTTP on port 8000. Put it behind whatever reverse proxy or load balancer already handles TLS and your domain; the container itself knows nothing about either.

## Build and run

```bash
docker build -t nisan --build-arg CARTO_API_KEY=your-carto-key .
```

```bash
docker run -d -p 8000:8000 -e EARTHDATA_TOKEN=your-token -v nisan-data:/data --name nisan nisan
```

Or with Compose:

```yaml
services:
  nisan:
    build:
      context: .
      args:
        CARTO_API_KEY: ${CARTO_API_KEY}   # baked into the web bundle; public by design
    environment:
      EARTHDATA_TOKEN: ${EARTHDATA_TOKEN} # runtime only, never in the bundle
    volumes:
      - nisan-data:/data
    ports:
      - "8000:8000"
    restart: unless-stopped

volumes:
  nisan-data:
```

## Configuration

| Variable | When | Required | Purpose |
|---|---|---|---|
| `CARTO_API_KEY` | build arg | no | CARTO vector basemap key. Inlined in the JavaScript bundle, so restrict it to your domain in the CARTO dashboard. Without it, basemap requests are sent without a key. |
| `VITE_API_BASE` | build arg | no | API origin, if the API is served from a different origin than the app. Leave empty for the single container. |
| `EARTHDATA_TOKEN` | runtime | for SMAP and SWOT | NASA Earthdata bearer token. Stays on the server. Quotes and whitespace are stripped. Everything else works without it. |
| `NISAN_DATA` | runtime | no | Cache folder. `/data` in the image. |
| `NISAN_STATIC` | runtime | no | Built app folder served at `/`. `/app/web` in the image. |

## Volumes and first start

Mount `/data`. It holds the terrain, every processed pass, the forecast and the SMAP/SWOT granule cuts, about 150 MB in total.

There is nothing to prepare by hand. On first start the API downloads:

1. the forecast and the terrain (Copernicus GLO-30 elevation and HAND, about a minute),
2. the latest radar water map, then optical water and NISAR images,
3. with `EARTHDATA_TOKEN`: SMAP soil moisture (last 45 days, about 11 s per granule) and SWOT water levels (last 120 days).

The app shows whatever is ready and fills in the rest as it arrives; Settings → Data shows each source's status. Later refreshes only fetch what is new.

## Operating notes

- Run one replica with one worker. The refresh scheduler runs inside the API process. Two replicas would download everything twice and race on the cache.
- The image runs as an unprivileged user (UID 10001), so a bind-mounted `/data` must be writable by it.
- `HEALTHCHECK` polls `/api/health`.
- uvicorn trusts `X-Forwarded-*` headers from any address (`--forwarded-allow-ips "*"`). Don't expose port 8000 to the internet directly when a proxy sits in front.
- To rebuild the terrain, delete `/data/dem` and restart.
