"""Tile-origin convention for OPERA / Sentinel-2 MGRS tiles."""
import pytest

from app import geo


def test_tile_is_anchored_at_the_nw_corner_of_its_100km_square():
    zone, x0, y0 = geo.mgrs_tile_origin("15QUV")
    assert zone == 15
    # 15QUV: square SW corner is (300000, 1900000); tile top edge = the square's north edge.
    assert x0 == pytest.approx(300_000, abs=1)
    assert y0 + geo.TILE_SIZE_M == pytest.approx(2_000_000, abs=1)


@pytest.mark.parametrize("tile,ex,ey", [("15QTV", 200_000, 2_000_000), ("15QUA", 300_000, 2_100_000), ("15QTA", 200_000, 2_100_000)])
def test_neighbouring_tiles(tile, ex, ey):
    _, x0, y0 = geo.mgrs_tile_origin(tile)
    assert x0 == pytest.approx(ex, abs=1)
    assert y0 + geo.TILE_SIZE_M == pytest.approx(ey, abs=1)


def test_aoi_grid_covers_bbox():
    t, w, h = geo.aoi_grid()
    x0, y0 = geo.to_mercator(-94.9, 17.6)
    x1, y1 = geo.to_mercator(-94.0, 18.3)
    assert t.c < x0 and t.f > y1 and t.c + w * geo.RES > x1 and t.f - h * geo.RES < y0
