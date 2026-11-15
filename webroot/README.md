# webroot

Served at the site root by the API container, before the built web app (`nisan-api/app/web.py`).
Anything here wins over a built file with the same path; `/api/*` always goes to the API.

- `.well-known/acme-challenge/` is where an ACME client (certbot `--webroot -w <this folder>`, acme.sh `-w`, lego `--http.webroot`) writes HTTP-01 tokens.
  They are served as `text/plain` with `Cache-Control: no-store`.
- Put other root files here too: `robots.txt`, `security.txt` under `.well-known/`, site-verification files.

In Docker this folder is `/srv/www` (`NISAN_WEBROOT`). Mount a volume there and share it with your ACME client.
