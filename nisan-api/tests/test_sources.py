"""Offline checks of the fetchers that replaced the data-sources sandboxes (no network)."""
import os
import time

import numpy as np

from app import geo
from app.sources import dem, earthdata, smap, swot


def test_dem_tiles_cover_the_basin():
    assert sorted(dem.tile_names()) == ["N17_00_W095_00", "N18_00_W095_00"]  # the east edge is exactly -94.0


def test_hand_classes_and_sea_mask():
    hand = np.array([0.5, 3, 10, 40, 0.0, -9999, np.nan], dtype="float32")
    elev = np.array([5, 5, 20, 60, 0.0, 5, 5], dtype="float32")
    assert dem.classify(hand, elev, -9999).tolist() == [1, 2, 3, 4, 0, 0, 0]


def test_utm_grid_covers_bbox_on_whole_cells():
    t, w, h = geo.utm_grid(30)
    assert t.c % 30 == 0 and t.f % 30 == 0 and (w, h) == (3198, 2608)
    t100, w100, h100 = geo.utm_grid(100)
    assert t100.a == 100 and w100 < w


def test_smap_window_matches_ease_grid_latitudes():
    rows, cols = smap.window()
    lats = smap.row_lats(rows)
    assert 0 < rows.stop - rows.start < 20 and 0 < cols.stop - cols.start < 20
    assert lats[0] >= 18.3 - 0.1 and lats[-1] <= 17.6 + 0.1 and np.all(np.diff(lats) < 0)


def _smap_item(t):
    base = "https://data.nsidc.earthdatacloud.nasa.gov/nsidc-cumulus-prod-protected/SMAP/SPL4SMGP/008/"
    return {"umm": {"RelatedUrls": [
        {"Type": "GET DATA", "URL": f"{base}SMAP_L4_SM_gph_{t}_Vv8013_001.h5"},
        {"Type": "GET DATA", "URL": f"{base}SMAP_L4_SM_gph_{t}_Vv8013_001.qa"},
        {"Type": "GET DATA VIA DIRECT ACCESS", "URL": f"s3://x/SMAP_L4_SM_gph_{t}_Vv8013_001.h5"},
    ]}}


def test_smap_keeps_one_https_h5_per_day():
    got = smap.urls([_smap_item("20261112T133000"), _smap_item("20261112T163000"), _smap_item("20261111T133000")])
    assert [u.rsplit("/", 1)[1] for u in got] == ["SMAP_L4_SM_gph_20261111T133000_Vv8013_001.h5", "SMAP_L4_SM_gph_20261112T133000_Vv8013_001.h5"]


def test_smap_series_is_land_mean(tmp_path):
    a = np.array([[0.8, np.nan], [0.6, np.nan]], dtype="float32")
    np.savez(tmp_path / "SMAP_L4_SM_gph_20261112T133000_Vv8013_001.npz", **{v: a for v in smap.VARS})
    s = smap.series(list(tmp_path.glob("*.npz")))
    assert s["t"] == ["2026-11-12T13:30:00+00:00"] and s["rootzone_wetness"] == [0.7]


def test_swot_merges_scenes_of_one_pass(tmp_path):
    shape = (2, 2)
    full = lambda v: np.full(shape, v, dtype="float32")  # noqa: E731
    a = {"wse": np.array([[1, np.nan], [np.nan, np.nan]], "float32"), "wse_uncert": full(0), "wse_qual": full(0), "water_frac": full(1), "water_area": full(1e4)}
    b = {"wse": np.array([[9, 2], [3, np.nan]], "float32"), "wse_uncert": full(0), "wse_qual": full(0), "water_frac": full(1), "water_area": full(1e4)}
    np.savez(tmp_path / "SWOT_L2_HR_Raster_100m_UTM15Q_N_x_x_x_058_537_094F_20261110T162958_20261110T163006_PID0_01.npz", **a)
    np.savez(tmp_path / "SWOT_L2_HR_Raster_100m_UTM15Q_N_x_x_x_058_537_095F_20261110T163018_20261110T163026_PID0_01.npz", **b)
    s = swot.series(list(tmp_path.glob("*.npz")))
    assert s["cycle"] == [58] and s["pass"] == [537]  # two scenes, one time step
    assert s["good_water_pixels"] == [3] and s["wse_median_m"] == [2.0]  # first scene wins where both have data


def test_cached_granules_are_not_fetched_again(tmp_path, monkeypatch):
    monkeypatch.setattr(earthdata, "cache_dir", lambda source: tmp_path)
    url = "https://x/SMAP_L4_SM_gph_20261112T133000_Vv8013_001.h5"
    (tmp_path / "SMAP_L4_SM_gph_20261112T133000_Vv8013_001.npz").write_bytes(b"")
    monkeypatch.setattr(earthdata, "_login", lambda: (_ for _ in ()).throw(AssertionError("should not log in")))
    assert earthdata._fetch_one("smap-l4", url) == "cached"


def test_rebuild_prunes_only_stale_files_outside_the_window(tmp_path, monkeypatch):
    monkeypatch.setattr(earthdata, "cache_dir", lambda source: tmp_path)
    monkeypatch.setattr(earthdata, "series_path", lambda source: tmp_path / "out.json")
    a = np.full((1, 1), 0.5, "float32")
    keep = "SMAP_L4_SM_gph_20261112T133000_Vv8013_001"
    np.savez(tmp_path / f"{keep}.npz", **{v: a for v in smap.VARS})
    old = tmp_path / "SMAP_L4_SM_gph_20250101T133000_Vv8013_001.npz"
    np.savez(old, **{v: a for v in smap.VARS})
    os.utime(old, (time.time() - 400 * 86400,) * 2)
    recent_gone = tmp_path / "SMAP_L4_SM_gph_20261001T133000_Vv8013_001.npz"  # left the CMR list but still recent
    np.savez(recent_gone, **{v: a for v in smap.VARS})
    s = earthdata._rebuild("smap-l4", [f"https://x/{keep}.h5"])
    assert s["t"] == ["2026-11-12T13:30:00+00:00"] and not old.exists() and recent_gone.exists()


def test_quoted_token_is_unwrapped(monkeypatch):
    import importlib

    from app import settings

    monkeypatch.setenv("EARTHDATA_TOKEN", "  'abc.def.ghi'\r\n")
    try:
        assert importlib.reload(settings).EARTHDATA_TOKEN == "abc.def.ghi"
        assert os.environ["EARTHDATA_TOKEN"] == "abc.def.ghi"
    finally:
        monkeypatch.undo()
        importlib.reload(settings)
