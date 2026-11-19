"""Geohash maths on WGS84 (EPSG:4326) longitude/latitude in degrees.

Axis order: public functions taking a point use ``(lat, lon)`` as in the
usual geohash convention; every geometry and bounding box is GeoJSON/shapely
order ``(x=lon, y=lat)``.
"""

from __future__ import annotations

import json
import math
import numbers
from pathlib import Path

from pyproj import CRS, Geod
from pyproj.exceptions import CRSError
from shapely.geometry import Polygon, box, mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union
from shapely.prepared import prep

BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"
_INDEX = {c: i for i, c in enumerate(BASE32)}
MAX_PRECISION = 12
MAX_CELLS = 200_000
_GEOD = Geod(ellps="WGS84")
# Longitude step (degrees) used to densify the constant-latitude cell edges
# before the ellipsoidal area is computed; see ``cell_area_km2``.
AREA_DENSIFY_DEG = 0.05
# Cells at most this tall (degrees, precision >= 6) use the width x height
# area, which stays accurate where the polygon area cancels; see above.
SMALL_CELL_DEG = 0.01
# CRSs a legacy GeoJSON "crs" member may declare; coordinates are lon/lat.
_LONLAT_CRS = (CRS("OGC:CRS84"), CRS("EPSG:4326"))


def _check_precision(precision) -> None:
    if (isinstance(precision, bool) or not isinstance(precision, int)
            or not 1 <= precision <= MAX_PRECISION):
        raise ValueError(f"precision must be an integer in 1..{MAX_PRECISION}, got {precision!r}")


def _check_coord(value, name: str, limit: float) -> float:
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise ValueError(f"{name} must be a number, got {type(value).__name__}")
    if not math.isfinite(value) or not -limit <= value <= limit:
        raise ValueError(f"{name} {value!r} outside [-{limit:g}, {limit:g}]")
    return float(value)


def cell_size(precision: int) -> tuple[float, float]:
    """Return the cell ``(width, height)`` in degrees (lon, lat) at a precision."""
    _check_precision(precision)
    bits = 5 * precision
    return 360.0 / 2 ** ((bits + 1) // 2), 180.0 / 2 ** (bits // 2)


def encode(lat: float, lon: float, precision: int = 9) -> str:
    """Encode a WGS84 point (lat, lon in degrees) as a geohash."""
    _check_precision(precision)
    lat = _check_coord(lat, "latitude", 90)
    lon = _check_coord(lon, "longitude", 180)
    lat_rng, lon_rng = [-90.0, 90.0], [-180.0, 180.0]
    out, bit, ch, even = [], 0, 0, True
    while len(out) < precision:
        rng, val = (lon_rng, lon) if even else (lat_rng, lat)
        mid = (rng[0] + rng[1]) / 2
        if val >= mid:
            ch = (ch << 1) | 1
            rng[0] = mid
        else:
            ch <<= 1
            rng[1] = mid
        even = not even
        bit += 1
        if bit == 5:
            out.append(BASE32[ch])
            bit, ch = 0, 0
    return "".join(out)


def decode_bbox(geohash: str) -> tuple[float, float, float, float]:
    """Return the cell bounds ``(min_lon, min_lat, max_lon, max_lat)``."""
    if not isinstance(geohash, str):
        raise ValueError(f"geohash must be a string, got {type(geohash).__name__}")
    if not geohash:
        raise ValueError("empty geohash")
    if len(geohash) > MAX_PRECISION:
        raise ValueError(f"geohash longer than {MAX_PRECISION} characters")
    lat_rng, lon_rng = [-90.0, 90.0], [-180.0, 180.0]
    even = True
    for c in geohash.lower():
        if c not in _INDEX:
            raise ValueError(f"invalid geohash character {c!r}")
        for shift in range(4, -1, -1):
            rng = lon_rng if even else lat_rng
            mid = (rng[0] + rng[1]) / 2
            rng[0 if (_INDEX[c] >> shift) & 1 else 1] = mid
            even = not even
    return lon_rng[0], lat_rng[0], lon_rng[1], lat_rng[1]


def decode(geohash: str) -> tuple[float, float]:
    """Return the cell centre as ``(lat, lon)``."""
    w, s, e, n = decode_bbox(geohash)
    return (s + n) / 2, (w + e) / 2


def parent(geohash: str) -> str:
    """Return the enclosing cell one precision level coarser."""
    decode_bbox(geohash)  # validates
    if len(geohash) == 1:
        raise ValueError("a precision-1 geohash has no parent")
    return geohash[:-1].lower()


def children(geohash: str) -> list[str]:
    """Return the 32 cells one precision level finer, in base-32 order."""
    decode_bbox(geohash)  # validates
    if len(geohash) >= MAX_PRECISION:
        raise ValueError(f"a precision-{MAX_PRECISION} geohash has no children")
    return [geohash.lower() + c for c in BASE32]


def neighbours(geohash: str) -> dict[str, str]:
    """Return the adjacent cells keyed n, ne, e, se, s, sw, w, nw.

    Longitude wraps across the antimeridian; directions that would leave
    the globe at the poles are omitted.
    """
    w, s, e, n = decode_bbox(geohash)
    dx, dy = e - w, n - s
    cx, cy = (w + e) / 2, (s + n) / 2
    dirs = {"n": (0, 1), "ne": (1, 1), "e": (1, 0), "se": (1, -1),
            "s": (0, -1), "sw": (-1, -1), "w": (-1, 0), "nw": (-1, 1)}
    out = {}
    for name, (ix, iy) in dirs.items():
        lat = cy + iy * dy
        if not -90 < lat < 90:
            continue
        lon = (cx + ix * dx + 180) % 360 - 180
        out[name] = encode(lat, lon, len(geohash))
    return out


def cell_area_km2(geohash: str) -> float:
    """Area of a cell on the WGS84 ellipsoid, in km².

    A geohash cell is bounded by two meridians and two parallels. For cells
    taller than ``SMALL_CELL_DEG`` the north and south edges are densified
    every ``AREA_DENSIFY_DEG`` degrees of longitude (geodesics between the
    corners would bulge poleward of the parallels) and ``pyproj.Geod``
    computes the polygon area; the error is below 0.01 % (the 32 precision-1
    cells sum to the WGS84 surface area within that tolerance).

    A polygon area is a sum of large per-edge terms, so for tiny cells near
    a pole their difference is lost to rounding. Smaller cells are therefore
    measured as width x height: the ``Geod`` distance along the cell's
    middle parallel times the ``Geod`` meridian distance between its south
    and north edges. Both are short, well-conditioned distances, and the
    approximation error (midpoint rule, chord vs parallel) is below 1e-8.
    """
    w, s, e, n = decode_bbox(geohash)
    if n - s <= SMALL_CELL_DEG:
        mid = (s + n) / 2
        _, _, width = _GEOD.inv(w, mid, e, mid)
        _, _, height = _GEOD.inv(w, s, w, n)
        return width * height / 1e6
    steps = max(1, math.ceil((e - w) / AREA_DENSIFY_DEG))
    lons = [w + (e - w) * k / steps for k in range(steps + 1)]
    ring = [(x, s) for x in lons] + [(x, n) for x in reversed(lons)]
    area, _ = _GEOD.geometry_area_perimeter(Polygon(ring))
    return abs(area) / 1e6


def _crosses_antimeridian(geometry) -> bool:
    """True if any ring segment jumps more than 180 degrees of longitude."""
    polys = geometry.geoms if geometry.geom_type == "MultiPolygon" else [geometry]
    for poly in polys:
        for ring in [poly.exterior, *poly.interiors]:
            xs = [c[0] for c in ring.coords]
            if any(abs(b - a) > 180 for a, b in zip(xs, xs[1:])):
                return True
    return False


def _check_lonlat_extent(geometry, where: str) -> None:
    """Reject geometries outside lon/lat limits or crossing the antimeridian."""
    minx, miny, maxx, maxy = geometry.bounds
    if minx < -180 or maxx > 180 or miny < -90 or maxy > 90:
        raise ValueError(f"{where} must lie within lon [-180, 180], lat [-90, 90]; "
                         "reproject to WGS84 or split antimeridian-crossing shapes first")
    if _crosses_antimeridian(geometry):
        raise ValueError(f"{where} crosses the antimeridian (a ring segment spans more than "
                         "180 degrees of longitude); split it at 180 first")


def _check_crs(obj: dict, where: str) -> None:
    """Reject a legacy GeoJSON ``crs`` member unless it names WGS84 lon/lat.

    RFC 7946 removed ``crs``; older files may still declare one. A declared
    CRS is parsed with pyproj and must equal OGC:CRS84 or EPSG:4326, so data
    in, say, EPSG:3857 is never silently read as degrees.
    """
    if "crs" not in obj:
        return
    crs = obj["crs"]
    name = None
    if isinstance(crs, dict) and crs.get("type") == "name" and isinstance(crs.get("properties"), dict):
        name = crs["properties"].get("name")
    if not isinstance(name, str):
        raise ValueError(f"{where}: unsupported 'crs' member {crs!r}; only a named "
                         "WGS84 lon/lat CRS (OGC:CRS84 or EPSG:4326) is accepted")
    try:
        parsed = CRS.from_user_input(name)
    except CRSError:
        raise ValueError(f"{where}: unknown CRS {name!r}") from None
    if not any(parsed == ok for ok in _LONLAT_CRS):
        raise ValueError(f"{where}: CRS {name!r} is not WGS84 lon/lat; reproject the data "
                         "to EPSG:4326 first (e.g. with pyproj.Transformer)")


def cover(geometry, precision: int, mode: str = "intersects") -> list[str]:
    """Geohashes covering a shapely (Multi)Polygon given in lon/lat degrees.

    ``mode`` is ``"intersects"`` (every cell touching the polygon) or
    ``"within"`` (only cells fully inside). Empty geometries give ``[]``;
    invalid ones, geometries outside the lon/lat range (for instance
    crossing the antimeridian) and covers above ``MAX_CELLS`` raise
    ``ValueError``.
    """
    _check_precision(precision)
    if mode not in ("intersects", "within"):
        raise ValueError(f"mode must be 'intersects' or 'within', got {mode!r}")
    if geometry is None:
        return []
    if not isinstance(geometry, BaseGeometry):
        raise ValueError(f"expected a shapely geometry, got {type(geometry).__name__}")
    if geometry.is_empty:
        return []
    if geometry.geom_type not in ("Polygon", "MultiPolygon"):
        raise ValueError(f"expected a Polygon or MultiPolygon, got {geometry.geom_type}")
    if not all(math.isfinite(v) for v in geometry.bounds):
        raise ValueError("geometry has non-finite (NaN or infinite) coordinates")
    if not geometry.is_valid:
        raise ValueError("invalid geometry; repair it first (e.g. shapely.make_valid)")
    _check_lonlat_extent(geometry, "geometry")
    minx, miny, maxx, maxy = geometry.bounds
    dx, dy = cell_size(precision)
    # A minimum lying exactly on a grid line also touches the cell before it.
    i0 = max(0, math.ceil((minx + 180) / dx) - 1)
    j0 = max(0, math.ceil((miny + 90) / dy) - 1)
    i1 = int(min((maxx + 180) // dx, 360 / dx - 1))
    j1 = int(min((maxy + 90) // dy, 180 / dy - 1))
    if (i1 - i0 + 1) * (j1 - j0 + 1) > MAX_CELLS:
        raise ValueError(f"cover would test more than {MAX_CELLS} cells; lower the precision")
    test = prep(geometry)
    check = test.intersects if mode == "intersects" else test.contains
    hashes = []
    for j in range(j0, j1 + 1):
        for i in range(i0, i1 + 1):
            west, south = -180 + i * dx, -90 + j * dy
            if check(box(west, south, west + dx, south + dy)):
                hashes.append(encode(south + dy / 2, west + dx / 2, precision))
    return sorted(hashes)


def _check_rings(rings, where: str) -> None:
    """Validate raw GeoJSON polygon rings before shapely sees them.

    shapely would close open rings and coerce numeric strings or booleans,
    silently repairing malformed input; RFC 7946 rings instead need at least
    four positions of 2 or 3 finite JSON numbers, the last equal to the first.
    """
    if not isinstance(rings, list) or not rings:
        raise ValueError(f"{where}: rings must be a non-empty list")
    for r, ring in enumerate(rings):
        if not isinstance(ring, list) or len(ring) < 4:
            raise ValueError(f"{where}, ring {r}: needs a list of at least 4 positions")
        for pos in ring:
            if (not isinstance(pos, list) or len(pos) not in (2, 3)
                    or any(isinstance(v, bool) or not isinstance(v, (int, float))
                           or not math.isfinite(v) for v in pos)):
                raise ValueError(f"{where}, ring {r}: position {pos!r} is not "
                                 "[lon, lat] (or [lon, lat, z]) with finite numbers")
        if ring[0] != ring[-1]:
            raise ValueError(f"{where}, ring {r}: not closed (first and last positions differ)")


def _to_shape(obj, where: str):
    """Turn one GeoJSON geometry object into a validated polygonal geometry.

    ``None`` (a null geometry) gives ``None``; anything else that is not a
    valid, finite Polygon/MultiPolygon (or a GeometryCollection of them)
    raises ``ValueError`` naming ``where``.
    """
    if obj is None:
        return None
    if not isinstance(obj, dict):
        raise ValueError(f"{where}: geometry must be a JSON object or null")
    _check_crs(obj, where)
    if obj.get("type") == "GeometryCollection":
        members = obj.get("geometries")
        if not isinstance(members, list):
            raise ValueError(f"{where}: GeometryCollection needs a 'geometries' list")
        parts = [_to_shape(g, f"{where}.geometries[{k}]") for k, g in enumerate(members)]
        parts = [g for g in parts if g is not None and not g.is_empty]
        return unary_union(parts) if parts else None
    if obj.get("type") not in ("Polygon", "MultiPolygon"):
        raise ValueError(f"{where}: expected Polygon or MultiPolygon, got {obj.get('type')!r}")
    coords = obj.get("coordinates")
    if not isinstance(coords, list):
        raise ValueError(f"{where}: 'coordinates' must be a list")
    if not coords:
        return None  # an empty Polygon or MultiPolygon
    for k, rings in enumerate([coords] if obj["type"] == "Polygon" else coords):
        _check_rings(rings, f"{where}: polygon {k}")
    geom = shape(obj)
    if not geom.is_valid:
        raise ValueError(f"{where}: invalid geometry; repair it first (e.g. shapely.make_valid)")
    # Checked per original geometry: merging can split a crossing edge into
    # short segments that would no longer reveal the crossing.
    _check_lonlat_extent(geom, where)
    return geom


def read_geometry(path):
    """Read the polygons of a GeoJSON file (UTF-8, WGS84 lon/lat).

    Accepts a FeatureCollection, a Feature or a bare geometry. A legacy
    ``crs`` member (on any object) must name OGC:CRS84 or EPSG:4326; any
    other or malformed declaration raises ``ValueError``. Null and empty
    geometries are skipped; every remaining geometry is validated on its own
    before the parts are merged, so invalid input is never silently repaired.
    Returns a (Multi)Polygon, or ``None`` if nothing polygonal remains.
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: not valid JSON ({exc})") from None
    if not isinstance(data, dict):
        raise ValueError(f"{path}: top level must be a GeoJSON object")
    _check_crs(data, str(path))
    kind = data.get("type")
    if kind == "FeatureCollection":
        feats = data.get("features")
        if not isinstance(feats, list):
            raise ValueError(f"{path}: FeatureCollection needs a 'features' list")
    elif kind == "Feature":
        feats = [data]
    else:
        feats = None
    if feats is None:
        geoms = [_to_shape(data, str(path))]
    else:
        geoms = []
        for k, f in enumerate(feats):
            if not isinstance(f, dict) or f.get("type") != "Feature":
                raise ValueError(f"{path}: features[{k}] is not a GeoJSON Feature")
            if "geometry" not in f:
                raise ValueError(f"{path}: features[{k}] has no 'geometry' member")
            _check_crs(f, f"{path}: features[{k}]")
            geoms.append(_to_shape(f["geometry"], f"{path}: features[{k}]"))
    geoms = [g for g in geoms if g is not None]
    return unary_union(geoms) if geoms else None


def cover_geojson(path, precision: int, mode: str = "intersects") -> dict:
    """Cover the polygons in a GeoJSON file (WGS84 lon/lat) and return a
    FeatureCollection of cell polygons with ``geohash`` and ``area_km2``."""
    features = []
    for gh in cover(read_geometry(path), precision, mode):
        features.append({
            "type": "Feature",
            "properties": {"geohash": gh, "area_km2": float(f"{cell_area_km2(gh):.9g}")},
            "geometry": json.loads(json.dumps(mapping(box(*decode_bbox(gh))))),
        })
    return {"type": "FeatureCollection", "features": features}
