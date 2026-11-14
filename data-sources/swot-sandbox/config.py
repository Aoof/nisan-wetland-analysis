"""Area of interest and product settings for the SWOT sandbox."""
from pathlib import Path

AOI_NAME = "coatzacoalcos"

# Lower Coatzacoalcos basin, Veracruz, Mexico. (W, S, E, N) in degrees.
BBOX = (-94.90, 17.60, -94.00, 18.30)

DEFAULT_START = "2025-11-01"
DEFAULT_END = "2026-11-14"

# Same UTM 15N grid as the other sandboxes, but at the raster product's 100 m.
TARGET_CRS = "EPSG:32615"
TARGET_RES_M = 100

# SWOT Level 2 high-rate water surface raster, 100 m, latest processing (D).
SHORT_NAME = "SWOT_L2_HR_Raster_100m_D"
UTM_ZONE_TAG = "_UTM15"   # the AOI is in UTM zone 15; skip tiles in other zones

VARIABLES = ["wse", "wse_uncert", "wse_qual", "water_frac", "water_area"]
# wse_qual: 0 good, 1 suspect, 2 degraded, 3 bad. Keep up to this value.
MAX_WSE_QUAL = 1
# A pixel counts as water for the summary if at least this fraction is water.
MIN_WATER_FRAC = 0.5

ROOT = Path(__file__).resolve().parent
CACHE_DIR = ROOT / "data" / "cache"
OUT_DIR = ROOT / "data" / "processed"
