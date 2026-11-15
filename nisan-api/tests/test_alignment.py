"""Do the water maps sit where the terrain says water should be?

Independent check: rivers and lagoons in a DSWx pass must lie in DEM valleys, i.e. the
mean height-above-nearest-drainage under 'open water' pixels is near zero. If the tile
georeferencing were off by a few hundred metres this number jumps (4.9 km: 3.9 m -> 0.5 m
when the origin was fixed). Needs a built pass and the terrain in data/dem (dem.refresh()).
"""
import numpy as np
import pytest
import rasterio

from app import geo
from app.settings import DATA  # noqa: F401
from app.sources import dem, opera

PROD = "opera-dswx-s1"


def _setup():
    if not dem.available():
        pytest.skip("terrain not fetched yet (data/dem)")
    rows = opera.index(PROD)
    if not rows:
        pytest.skip("no processed pass yet")
    return rows[-1]


def _mean_hand_under_water(water: np.ndarray) -> float:
    hand = dem.grids()["hand"]
    sel = water[300:-20] & np.isfinite(hand[300:-20])  # inland rows only: the Gulf is not a valley
    return float(hand[300:-20][sel].mean())


def test_water_sits_in_valleys():
    row = _setup()
    with rasterio.open(opera.pass_path(PROD, row["id"])) as src:
        water = src.read(1) == 1
    assert _mean_hand_under_water(water) < 1.0


@pytest.mark.parametrize("dx,dy", [(300, 0), (-300, 0), (0, 300), (0, -300)])
def test_a_300m_shift_is_visibly_worse(dx, dy):
    row = _setup()
    with rasterio.open(opera.pass_path(PROD, row["id"])) as src:
        water = src.read(1) == 1
    base = _mean_hand_under_water(water)
    shifted = np.roll(np.roll(water, dy // 100, axis=0), dx // 100, axis=1)
    assert _mean_hand_under_water(shifted) > base


def test_point_lookup_matches_the_raster():
    row = _setup()
    with rasterio.open(opera.pass_path(PROD, row["id"])) as src:
        arr = src.read(1)
        rr, cc = np.where(arr == 1)
        i = len(rr) // 2
        t = src.transform
        lon, lat = geo.to_lonlat(t.c + (cc[i] + 0.5) * geo.RES, t.f - (rr[i] + 0.5) * geo.RES)
    hist = opera.history(PROD, lon, lat)
    assert hist and hist[-1]["code"] == 1


def test_nisar_backscatter_is_darkest_over_dswx_water_at_zero_shift():
    """NISAR browse images (lat/lon) and DSWx (UTM tiles) come from different pipelines.
    Water is dark in L-band, so the contrast between land and water should peak at no shift."""
    import glob

    from rasterio.warp import Resampling, reproject

    row = _setup()
    files = sorted(glob.glob(str(DATA / "nisar" / "*.tif")))
    if not files:
        pytest.skip("no NISAR image built yet")
    t, w, h = geo.aoi_grid()
    with rasterio.open(opera.pass_path(PROD, row["id"])) as src:
        water = src.read(1) == 1
    best = None
    for f in files:
        with rasterio.open(f) as s:
            lum, alpha = np.zeros((h, w), "float32"), np.zeros((h, w), "uint8")
            reproject(s.read([1, 2, 3]).astype("float32").mean(axis=0), lum, src_transform=s.transform, src_crs=s.crs, dst_transform=t, dst_crs="EPSG:3857", resampling=Resampling.average)
            reproject(s.read(4), alpha, src_transform=s.transform, src_crs=s.crs, dst_transform=t, dst_crs="EPSG:3857", resampling=Resampling.nearest)
        valid = alpha > 0
        if (water & valid).sum() > 500:
            best = (lum, valid)
            break
    if best is None:
        pytest.skip("no NISAR pass overlaps enough water")
    lum, valid = best
    scores = {}
    for dy in range(-9, 10, 3):
        for dx in range(-9, 10, 3):
            wsh = np.roll(np.roll(water, dy, 0), dx, 1) & valid
            dry = valid & ~wsh
            if wsh.sum() > 200:
                scores[(dy, dx)] = float(lum[dry].mean() - lum[wsh].mean())
    assert max(scores, key=scores.get) == (0, 0)
