# NASA SpaceApps Challenges
## NISAN: Wetlands and floodplains analysis

Use NISAR radar data to map how wetlands and floodplains expand and shrink over time, and use that history to predict where water will go next.

## Docker

One image serves the web app at `/` and the data API at `/api` (see `Dockerfile`).

```yaml
services:
  nisan:
    build:
      context: ./nisan-wetland-analysis
      args:
        CARTO_API_KEY: ${CARTO_API_KEY}   # baked into the web bundle; public by design, restrict it to your domain
    environment:
      EARTHDATA_TOKEN: ${EARTHDATA_TOKEN} # runtime only, never in the bundle; needed for SMAP and SWOT
    volumes:
      - nisan-data:/data                  # downloaded passes, forecasts, caches
      - nisan-webroot:/srv/www            # served at /: ACME challenges, robots.txt, ... (see webroot/README.md)
    ports:
      - "8000:8000"
    restart: unless-stopped

  # Optional: certificates via HTTP-01. Port 80 must reach the nisan service (directly or through your proxy).
  certbot:
    image: certbot/certbot
    volumes:
      - nisan-webroot:/srv/www
      - ./letsencrypt:/etc/letsencrypt
    command: certonly --webroot -w /srv/www -d flood.example.com --email you@example.com --agree-tos -n
    profiles: ["certs"]                   # run on demand: docker compose run --rm certbot

volumes:
  nisan-data:
  nisan-webroot:
```

Anything in `/srv/www` is served at the site root ahead of the web app, so `/.well-known/acme-challenge/<token>` works as soon as the ACME client writes it. A named volume starts with the repo's `webroot/` contents; a bind mount (`./webroot:/srv/www`) works too.

Keep it to one replica: the refresh jobs run inside the process.

The API fetches all of its data itself and caches it in `/data`; there is nothing to prepare by hand. On first start it downloads the terrain (Copernicus GLO-30 elevation and HAND, about a minute, public), the latest radar and optical water maps and NISAR images (public), and with `EARTHDATA_TOKEN` the SMAP soil moisture (one granule a day, last 45 days, about 11 s each) and SWOT water levels (last 120 days). Only the basin's part of each file is read. Later refreshes only fetch what is new; the cache stays around 150 MB.
