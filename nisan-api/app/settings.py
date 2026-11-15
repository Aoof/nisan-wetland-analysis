"""Paths, the area of interest and credentials. Secrets come from nisan-app/.env and never leave the server."""
import os
from pathlib import Path

from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[2]
load_dotenv(REPO / "nisan-app" / ".env")

DATA = Path(os.environ.get("NISAN_DATA", REPO / "nisan-api" / "data"))
SANDBOXES = REPO / "data-sources"
PLACES_JSON = REPO / "nisan-app" / "src" / "data" / "places.json"

# Same box as every sandbox (W, S, E, N).
BBOX = (-94.90, 17.60, -94.00, 18.30)

EARTHDATA_TOKEN = os.environ.get("EARTHDATA_TOKEN", "")

CMR = "https://cmr.earthdata.nasa.gov/search/granules.umm_json"
FLOOD_API = "https://flood-api.open-meteo.com/v1/flood"
WEATHER_API = "https://api.open-meteo.com/v1/forecast"

for sub in ("cmr", "browse", "passes", "nisar", "forecast", "series"):
    (DATA / sub).mkdir(parents=True, exist_ok=True)
