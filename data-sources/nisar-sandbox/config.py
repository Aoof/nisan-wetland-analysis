"""Area of interest, products and water thresholds for the NISAR sandbox."""
from pathlib import Path

AOI_NAME = "coatzacoalcos"

# Lower Coatzacoalcos basin, Veracruz, Mexico. (W, S, E, N) in degrees.
BBOX = (-94.90, 17.60, -94.00, 18.30)

DEFAULT_START = "2025-10-01"
DEFAULT_END = "2026-11-14"

# Shared analysis grid for all sandboxes: UTM zone 15N, 30 m. GCOV is averaged
# down to it, which also smooths speckle.
TARGET_CRS = "EPSG:32615"
TARGET_RES_M = 30

# L2 GCOV (geocoded backscatter covariance) at ASF. Validated V1 is preferred;
# provisional products fill the earlier record. Same acquisition in both -> V1 wins.
GCOV_COLLECTIONS = ["NISAR_L2_GCOV_V1", "NISAR_L2_GCOV_PROVISIONAL_V1"]
GCOV_GRID = "science/LSAR/GCOV/grids/frequencyA"

# Starting thresholds for L-band water classes, in dB. Tune them against OPERA
# DSWx and field knowledge before trusting the maps.
OPEN_WATER_HH_MAX_DB = -18.0     # smooth water reflects the radar away: very dark
FLOODED_VEG_HH_MIN_DB = -3.0     # water + trunks give a double bounce: very bright HH
FLOODED_VEG_HH_HV_MIN_DB = 8.0   # ...with HH well above HV

# Classes in the output rasters.
CLASSES = {0: "no data", 1: "not water", 2: "open water", 3: "flooded vegetation"}

# Optional sea mask from the DEM sandbox (class 0 = sea), same grid. Used only
# in the summaries, so the Gulf is not counted as open water.
SEA_MASK = (Path(__file__).resolve().parent.parent / "copernicus-dem-sandbox" / "data"
            / "processed" / f"{AOI_NAME}_hand_class_utm15n.tif")

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "data" / "processed"
