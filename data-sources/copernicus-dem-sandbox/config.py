"""Area of interest and output settings for the Copernicus DEM sandbox."""
from pathlib import Path

AOI_NAME = "coatzacoalcos"

# Lower Coatzacoalcos basin, Veracruz, Mexico. (W, S, E, N) in degrees.
# Same box as the other sandboxes so the layers line up.
BBOX = (-94.90, 17.60, -94.00, 18.30)

# Shared analysis grid for all sandboxes: UTM zone 15N.
TARGET_CRS = "EPSG:32615"
TARGET_RES_M = 30

# Copernicus GLO-30 DEM and the ASF/NASA GLO-30 HAND layer, both public COGs on
# AWS Open Data (no login). Tiles are 1x1 degree, named by their SW corner.
DEM_URL = ("https://copernicus-dem-30m.s3.amazonaws.com/"
           "Copernicus_DSM_COG_10_{tile}_DEM/Copernicus_DSM_COG_10_{tile}_DEM.tif")
HAND_URL = "https://glo-30-hand.s3.amazonaws.com/v1/2021/Copernicus_DSM_COG_10_{tile}_HAND.tif"

# Height Above Nearest Drainage class breaks (m). Cells close to the drainage
# network flood first; these are common starting points, not calibrated values.
HAND_CLASSES = (0, 1, 5, 15)

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "data" / "processed"
