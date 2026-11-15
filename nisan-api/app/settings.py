"""Paths, the area of interest and credentials. Secrets come from nisan-app/.env and never leave the server."""
import os
from pathlib import Path

from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[2]
load_dotenv(REPO / "nisan-app" / ".env")

DATA = Path(os.environ.get("NISAN_DATA", REPO / "nisan-api" / "data"))
PLACES_JSON = REPO / "nisan-app" / "src" / "data" / "places.json"

# The lower Coatzacoalcos basin (W, S, E, N).
BBOX = (-94.90, 17.60, -94.00, 18.30)

# Strip quotes and whitespace: `docker run --env-file` and some compose setups pass them through literally,
# and a quoted token fails Earthdata login with a 401.
EARTHDATA_TOKEN = os.environ.get("EARTHDATA_TOKEN", "").strip().strip("\"'").strip()
os.environ["EARTHDATA_TOKEN"] = EARTHDATA_TOKEN  # earthaccess reads it from the environment

CMR = "https://cmr.earthdata.nasa.gov/search/granules.umm_json"
FLOOD_API = "https://flood-api.open-meteo.com/v1/flood"
WEATHER_API = "https://api.open-meteo.com/v1/forecast"

for sub in ("cmr", "browse", "passes", "nisar", "forecast", "series", "dem", "cache"):
    (DATA / sub).mkdir(parents=True, exist_ok=True)
