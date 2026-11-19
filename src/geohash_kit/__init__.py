"""geohash-kit: geohash encoding, neighbours and polygon covers."""

from .core import (
    cell_area_km2,
    cell_size,
    cover,
    cover_geojson,
    decode,
    decode_bbox,
    encode,
    neighbours,
    read_geometry,
)

__all__ = [
    "cell_area_km2",
    "cell_size",
    "cover",
    "cover_geojson",
    "decode",
    "decode_bbox",
    "encode",
    "neighbours",
    "read_geometry",
]
__version__ = "0.1.0"
