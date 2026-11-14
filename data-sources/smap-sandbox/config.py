"""Area of interest and product settings for the SMAP sandbox."""
from pathlib import Path

AOI_NAME = "coatzacoalcos"

# Lower Coatzacoalcos basin, Veracruz, Mexico: the city, Minatitlán, the river
# floodplain and the Tonalá wetlands to the east. (W, S, E, N) in degrees.
# The northern edge reaches into the Gulf; SMAP has no data over the sea, so
# those cells stay empty.
BBOX = (-94.90, 17.60, -94.00, 18.30)

DEFAULT_START = "2025-11-01"
DEFAULT_END = "2026-11-14"

PRODUCTS = {
    # Daily satellite retrieval, AM (6 am) and PM (6 pm) overpasses, 9 km.
    "l3": {"short_name": "SPL3SMP_E", "version": "006"},
    # Model-assimilated, gap-free, 3-hourly surface + root-zone moisture, 9 km.
    "l4": {"short_name": "SPL4SMGP", "version": "008"},
}

ROOT = Path(__file__).resolve().parent
CACHE_DIR = ROOT / "data" / "cache"
OUT_DIR = ROOT / "data" / "processed"
