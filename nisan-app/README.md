# nisan-app

The NISAN web app: MapLibre map, Overview and Authorities views, the Settings sheet and the risk rules.

```bash
npm install && npm run dev        # http://localhost:5173, proxies /api to 127.0.0.1:8000
```

Start the API first (`cd ../nisan-api && uv run python -m app`). Full instructions are in [docs/development.md](../docs/development.md); how the app loads data is in [docs/architecture.md](../docs/architecture.md), the risk rules in [docs/risk-model.md](../docs/risk-model.md) and the design rules in [docs/design.md](../docs/design.md).
