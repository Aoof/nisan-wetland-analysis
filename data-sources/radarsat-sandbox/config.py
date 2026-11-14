"""Area of interest and collection settings for the RADARSAT sandbox."""
from pathlib import Path

AOI_NAME = "coatzacoalcos"

# Lower Coatzacoalcos basin, Veracruz, Mexico. (W, S, E, N) in degrees.
BBOX = (-94.90, 17.60, -94.00, 18.30)

DEFAULT_START = "2019-06-01"   # RADARSAT Constellation Mission launch
DEFAULT_END = "2026-11-14"

# Canada's EODMS catalogue (not NASA Earthdata). Collection IDs as EODMS names them.
COLLECTIONS = {
    "rcm": "RCMImageProducts",   # RADARSAT Constellation Mission, C-band, 2019 onward
    "r1": "Radarsat1",           # RADARSAT-1 archive, C-band HH, 1995-2013
}

ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / "data" / "raw"
OUT_DIR = ROOT / "data" / "processed"


def bbox_wkt(bbox=BBOX):
    w, s, e, n = bbox
    return f"POLYGON(({w} {s}, {e} {s}, {e} {n}, {w} {n}, {w} {s}))"
