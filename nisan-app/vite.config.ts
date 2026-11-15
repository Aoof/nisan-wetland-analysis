import { defineConfig } from "vite";

export default defineConfig({
  // CARTO_API_KEY lives in .env; map tile keys are public by design, so it is exposed to the client.
  // Restrict it to your domains in the CARTO dashboard. EARTHDATA_TOKEN is never exposed (not in this list).
  envPrefix: ["VITE_", "CARTO_"],
  server: { port: 5173, strictPort: true, proxy: { "/api": "http://127.0.0.1:8000" } },
  preview: { proxy: { "/api": "http://127.0.0.1:8000" } },
});
