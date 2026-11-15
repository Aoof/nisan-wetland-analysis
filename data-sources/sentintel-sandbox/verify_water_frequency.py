import matplotlib.pyplot as plt
import numpy as np
import rasterio

# Update with the path to your generated water frequency GeoTIFF
tif_path = "NAME_FILE_water_frequency.tif"

with rasterio.open(tif_path) as src:
  # Read bands (Rasterio is 1-indexed)
  water_freq = src.read(1).astype("float32")
  obs_count = src.read(2).astype("float32")

  # Read descriptions saved in the GeoTIFF metadata
  band1_desc = src.descriptions[0] or "Water Frequency"
  band2_desc = src.descriptions[1] or "Observation Count"

# 1. Handle Nodata / Masking
# Band 1 uses -1 for nodata
water_freq_masked = np.ma.masked_where(water_freq < 0, water_freq)

# Band 2: pixels with 0 observations can be masked for clean rendering
obs_count_masked = np.ma.masked_where(obs_count == 0, obs_count)

# 2. Set up the plotting canvas (side-by-side subplots)
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

# --- Plot Band 1: Water Frequency ---
im1 = axes[0].imshow(water_freq_masked, cmap="Blues", vmin=0.0, vmax=1.0)
axes[0].set_title(f"Band 1: {band1_desc}\n(0 = Never, 1 = Always)")
axes[0].axis("off")
fig.colorbar(im1, ax=axes[0], fraction=0.046, pad=0.04, label="Proportion")

# --- Plot Band 2: Observation Count ---
im2 = axes[1].imshow(obs_count_masked, cmap="viridis")
axes[1].set_title(f"Band 2: {band2_desc}\n(Total Valid Dates)")
axes[1].axis("off")
fig.colorbar(im2, ax=axes[1], fraction=0.046, pad=0.04, label="Count")

plt.tight_layout()
plt.show()