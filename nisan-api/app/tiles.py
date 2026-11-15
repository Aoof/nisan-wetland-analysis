"""XYZ PNG tiles from GeoTIFFs via rio-tiler. Nearest-neighbour: classes must never be blended."""
from pathlib import Path

from fastapi import Response
from rio_tiler.errors import TileOutsideBounds
from rio_tiler.io import Reader

# 1x1 transparent PNG for tiles outside a raster
EMPTY = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d4944415478da63fcffff3f0300050001a5f645400000000049454e44ae426082"
)
HEADERS = {"Cache-Control": "public, max-age=31536000, immutable"}


def png_tile(path: Path, z: int, x: int, y: int, colormap: dict | None = None, indexes: tuple[int, ...] | None = None, cache: str | None = None) -> Response:
    headers = {"Cache-Control": cache} if cache else HEADERS
    try:
        with Reader(str(path)) as src:
            img = src.tile(x, y, z, indexes=indexes, resampling_method="nearest", tilesize=256)
        body = img.render(img_format="PNG", colormap=colormap)
    except TileOutsideBounds:
        return Response(EMPTY, media_type="image/png", headers=headers)
    return Response(body, media_type="image/png", headers=headers)
