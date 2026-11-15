"""XYZ PNG tiles from GeoTIFFs via rio-tiler. Nearest-neighbour: classes must never be blended."""
import struct
import zlib
from pathlib import Path

from fastapi import Response
from rio_tiler.errors import TileOutsideBounds
from rio_tiler.io import Reader

def _empty_png() -> bytes:
    """1x1 fully transparent RGBA PNG, built rather than hard-coded so the checksums are always right."""
    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00\x00")) + chunk(b"IEND", b"")


# for tiles outside a raster
EMPTY = _empty_png()
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
