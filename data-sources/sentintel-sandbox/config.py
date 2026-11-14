"""Area of interest and product settings for the Sentinel (OPERA) sandbox."""
from pathlib import Path

AOI_NAME = "coatzacoalcos"

# Lower Coatzacoalcos basin, Veracruz, Mexico. (W, S, E, N) in degrees.
BBOX = (-94.90, 17.60, -94.00, 18.30)

DEFAULT_START = "2025-11-01"
DEFAULT_END = "2026-11-14"

# Shared analysis grid for all sandboxes: UTM zone 15N, 30 m (OPERA's native posting).
TARGET_CRS = "EPSG:32615"
TARGET_RES_M = 30

# NASA OPERA products built from Sentinel-1 radar and Harmonized Landsat/Sentinel-2.
PRODUCTS = {
    # Water classification from Sentinel-1 radar: sees through cloud.
    "dswx-s1": {"short_name": "OPERA_L3_DSWX-S1_V1", "layers": ["_B01_WTR.tif"], "kind": "water"},
    # Water classification from Landsat 8/9 + Sentinel-2 optical: blocked by cloud.
    "dswx-hls": {"short_name": "OPERA_L3_DSWX-HLS_V1", "layers": ["_B01_WTR.tif"], "kind": "water"},
    # Terrain-corrected Sentinel-1 backscatter (gamma0, linear power), per burst.
    "rtc-s1": {"short_name": "OPERA_L2_RTC-S1_V1", "layers": ["_VV.tif", "_VH.tif"], "kind": "backscatter"},
}

# DSWx WTR layer classes. Everything else (250 HAND-masked, 251 layover/shadow,
# 252 snow/ice, 253 cloud, 254 ocean, 255 fill) counts as "no observation".
DSWX_DRY = {0}
DSWX_WATER = {1: "open water", 2: "partial surface water (HLS)", 3: "inundated vegetation (S1)"}

ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / "data" / "raw"
OUT_DIR = ROOT / "data" / "processed"
