"""Table-driven boundary validation for every public function and the CLI."""

import json
import math

import pytest
from pyproj import Geod, Transformer
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box

from geohash_kit import (
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
from geohash_kit.cli import main

NAN, INF = float("nan"), float("inf")
BOWTIE = Polygon([(0, 0), (1, 1), (1, 0), (0, 1)])
OVERLAP = MultiPolygon([box(0, 0, 2, 2), box(1, 1, 3, 3)])

BAD_CALLS = [
    ("encode lat NaN", lambda: encode(NAN, 0)),
    ("encode lon NaN", lambda: encode(0, NAN)),
    ("encode lat inf", lambda: encode(INF, 0)),
    ("encode lat > 90", lambda: encode(90.0001, 0)),
    ("encode lon < -180", lambda: encode(0, -180.0001)),
    ("encode lat None", lambda: encode(None, 0)),
    ("encode lat str", lambda: encode("40.7", 0)),
    ("encode lat bool", lambda: encode(True, 0)),
    ("encode lat dict", lambda: encode({"lat": 1}, 0)),
    ("encode precision 0", lambda: encode(0, 0, 0)),
    ("encode precision 13", lambda: encode(0, 0, 13)),
    ("encode precision float", lambda: encode(0, 0, 5.0)),
    ("encode precision bool", lambda: encode(0, 0, True)),
    ("encode precision None", lambda: encode(0, 0, None)),
    ("cell_size precision str", lambda: cell_size("5")),
    ("decode empty", lambda: decode("")),
    ("decode None", lambda: decode(None)),
    ("decode int", lambda: decode(12345)),
    ("decode bad char", lambda: decode("ezs4a")),
    ("decode whitespace", lambda: decode(" ezs42")),
    ("decode too long", lambda: decode("u4pruydqqvjxx")),
    ("decode_bbox list", lambda: decode_bbox(["e", "z"])),
    ("neighbours None", lambda: neighbours(None)),
    ("neighbours bad", lambda: neighbours("i")),
    ("cell_area None", lambda: cell_area_km2(None)),
    ("cover dict", lambda: cover({"type": "Polygon", "coordinates": []}, 4)),
    ("cover str", lambda: cover("POLYGON((0 0,1 0,1 1,0 0))", 4)),
    ("cover point", lambda: cover(Point(0, 0), 4)),
    ("cover line", lambda: cover(LineString([(0, 0), (1, 1)]), 4)),
    ("cover bow-tie", lambda: cover(BOWTIE, 4)),
    ("cover overlapping multipolygon", lambda: cover(OVERLAP, 4)),
    ("cover NaN coords", lambda: cover(Polygon([(0, 0), (1, 0), (NAN, 1)]), 4)),
    ("cover lat > 90", lambda: cover(box(0, 80, 1, 91), 2)),
    ("cover bad mode", lambda: cover(box(0, 0, 1, 1), 4, "touches")),
    ("cover mode None", lambda: cover(box(0, 0, 1, 1), 4, None)),
    ("cover precision 0", lambda: cover(box(0, 0, 1, 1), 0)),
]


@pytest.mark.parametrize("call", [c for _, c in BAD_CALLS], ids=[n for n, _ in BAD_CALLS])
def test_bad_api_input_raises_valueerror(call):
    with pytest.raises(ValueError):
        call()


def _poly(coords):
    return {"type": "Polygon", "coordinates": [coords]}


SQUARE = [[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]
BOWTIE_GJ = [[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]
FC = "FeatureCollection"
# a 1 m square at the EPSG:3857 origin: also numerically valid as lon/lat
SQUARE_M = [[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]
CROSSING = [[179, 10], [-179, 10], [-179, 11], [179, 11], [179, 10]]


def NAMED(name):
    return {"type": "name", "properties": {"name": name}}

BAD_FILES = [
    ("not json", "{nope"),
    ("json array", [1, 2]),
    ("json string", "\"Polygon\""),
    ("json null", None),
    ("no type", {"coordinates": [SQUARE]}),
    ("point geometry", {"type": "Point", "coordinates": [0, 0]}),
    ("features not list", {"type": FC, "features": {"a": 1}}),
    ("features missing", {"type": FC}),
    ("feature is string", {"type": FC, "features": ["x"]}),
    ("feature no geometry key", {"type": FC, "features": [{"type": "Feature"}]}),
    ("geometry is string", {"type": "Feature", "geometry": "POLYGON"}),
    ("geometry is list", {"type": "Feature", "geometry": [SQUARE]}),
    ("coords missing", {"type": "Polygon"}),
    ("coords string", {"type": "Polygon", "coordinates": "abc"}),
    ("coords too few", _poly([[0, 0], [1, 1]])),
    ("coords NaN", _poly([[0, 0], [1, 0], [float("nan"), 1], [0, 0]])),
    ("bow-tie feature", {"type": "Feature", "geometry": _poly(BOWTIE_GJ)}),
    ("invalid member among valid", {"type": FC, "features": [
        {"type": "Feature", "geometry": _poly(SQUARE)},
        {"type": "Feature", "geometry": _poly(BOWTIE_GJ)}]}),
    ("overlapping multipolygon", {"type": "MultiPolygon", "coordinates": [
        [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]],
        [[[1, 1], [3, 1], [3, 3], [1, 3], [1, 1]]]]}),
    ("mixed collection with line", {"type": "GeometryCollection", "geometries": [
        _poly(SQUARE), {"type": "LineString", "coordinates": [[0, 0], [1, 1]]}]}),
    ("collection without list", {"type": "GeometryCollection", "geometries": 3}),
    # legacy "crs" members: anything but WGS84 lon/lat must be rejected, on any
    # object. The projected coordinates below (metres, EPSG:3857) also fall
    # inside the lon/lat limits, so only the declaration reveals the problem.
    ("crs 3857 top level", {"type": FC, "crs": NAMED("EPSG:3857"), "features": [
        {"type": "Feature", "geometry": _poly(SQUARE_M)}]}),
    ("crs 3857 urn on feature", {"type": FC, "features": [
        {"type": "Feature", "crs": NAMED("urn:ogc:def:crs:EPSG::3857"),
         "geometry": _poly(SQUARE_M)}]}),
    ("crs 3857 on geometry", {"type": "Feature", "geometry": {
        **_poly(SQUARE_M), "crs": NAMED("EPSG:3857")}}),
    ("crs 3857 on nested member", {"type": "GeometryCollection", "geometries": [
        {**_poly(SQUARE_M), "crs": NAMED("EPSG:3857")}]}),
    ("crs 3857 on standalone feature", {"type": "Feature", "crs": NAMED("EPSG:3857"),
                                        "geometry": _poly(SQUARE_M)}),
    ("crs linked", {"type": "Polygon", "coordinates": [SQUARE],
                    "crs": {"type": "link", "properties": {"href": "x.prj"}}}),
    ("crs null", {"type": "Polygon", "coordinates": [SQUARE], "crs": None}),
    ("crs string", {"type": "Polygon", "coordinates": [SQUARE], "crs": "EPSG:4326"}),
    ("crs name not string", {"type": "Polygon", "coordinates": [SQUARE], "crs": NAMED(4326)}),
    ("crs unknown name", {"type": "Polygon", "coordinates": [SQUARE], "crs": NAMED("EPSG:0")}),
    # antimeridian crossings must be caught on each original polygon, even when
    # merging with another feature would split the crossing edges
    ("antimeridian ring", _poly(CROSSING)),
    ("antimeridian ring merged with box", {"type": FC, "features": [
        {"type": "Feature", "geometry": _poly(CROSSING)},
        {"type": "Feature", "geometry": _poly([[-1, 9], [1, 9], [1, 12], [-1, 12], [-1, 9]])}]}),
    ("antimeridian in collection member", {"type": "GeometryCollection", "geometries": [
        _poly(CROSSING), _poly([[-1, 9], [1, 9], [1, 12], [-1, 12], [-1, 9]])]}),
    ("lon beyond 180", _poly([[179, 0], [181, 0], [181, 1], [179, 1], [179, 0]])),
    # raw coordinates are checked before shapely could close, coerce or repair them
    ("unclosed ring", _poly([[0, 0], [1, 0], [1, 1], [0, 1]])),
    ("unclosed hole", {"type": "Polygon", "coordinates": [
        [[0, 0], [4, 0], [4, 4], [0, 4], [0, 0]], [[1, 1], [1, 2], [2, 2], [2, 1]]]}),
    ("numeric string coords", _poly([["0", "0"], [1, 0], [1, 1], [0, 1], ["0", "0"]])),
    ("boolean coords", _poly([[0, 0], [True, 0], [1, 1], [0, 1], [0, 0]])),
    ("null coord", _poly([[0, 0], [1, None], [1, 1], [0, 1], [0, 0]])),
    ("infinite coord", _poly([[0, 0], [INF, 0], [1, 1], [0, 1], [0, 0]])),
    ("position of 1 value", _poly([[0, 0], [1], [1, 1], [0, 1], [0, 0]])),
    ("position of 4 values", _poly([[0, 0], [1, 0, 0, 0], [1, 1], [0, 1], [0, 0]])),
    ("position is mapping", _poly([[0, 0], {"x": 1, "y": 0}, [1, 1], [0, 1], [0, 0]])),
    ("ring is mapping", {"type": "Polygon", "coordinates": [{"a": 1}]}),
    ("coords null", {"type": "Polygon", "coordinates": None}),
    ("coords mapping", {"type": "Polygon", "coordinates": {"a": 1}}),
    ("multipolygon member empty", {"type": "MultiPolygon", "coordinates": [[]]}),
    ("multipolygon member not list", {"type": "MultiPolygon", "coordinates": [5]}),
    ("multipolygon flat rings", {"type": "MultiPolygon", "coordinates": [SQUARE]}),
]


def _write(tmp_path, data):
    p = tmp_path / "in.geojson"
    p.write_text(data if isinstance(data, str) and data.startswith("{") else json.dumps(data),
                 encoding="utf-8")
    return p


@pytest.mark.parametrize("data", [d for _, d in BAD_FILES], ids=[n for n, _ in BAD_FILES])
def test_bad_geojson_raises_valueerror_and_cli_exits_1(tmp_path, capsys, data):
    p = _write(tmp_path, data)
    with pytest.raises(ValueError):
        cover_geojson(p, 4)
    assert main(["cover", str(p), "-p", "4"]) == 1
    assert capsys.readouterr().err.startswith("error:")


EMPTY_FILES = [
    ("standalone feature null geometry", {"type": "Feature", "geometry": None}),
    ("empty feature collection", {"type": FC, "features": []}),
    ("all-null collection", {"type": FC, "features": [{"type": "Feature", "geometry": None}]}),
    ("empty polygon", {"type": "Polygon", "coordinates": []}),
    ("empty geometry collection", {"type": "GeometryCollection", "geometries": []}),
]


@pytest.mark.parametrize("data", [d for _, d in EMPTY_FILES], ids=[n for n, _ in EMPTY_FILES])
def test_null_and_empty_geojson_gives_empty_cover(tmp_path, data):
    p = _write(tmp_path, data)
    assert read_geometry(p) is None
    assert cover_geojson(p, 4) == {"type": "FeatureCollection", "features": []}
    assert main(["cover", str(p), "-p", "4"]) == 0


def test_null_geometry_skipped_next_to_valid_one(tmp_path):
    p = _write(tmp_path, {"type": FC, "features": [
        {"type": "Feature", "geometry": None, "properties": {}},
        {"type": "Feature", "geometry": _poly(SQUARE), "properties": {}}]})
    assert cover_geojson(p, 2)["features"]


def test_cli_rejects_missing_file_and_nan(capsys, tmp_path):
    assert main(["cover", str(tmp_path / "missing.geojson"), "-p", "4"]) == 1
    assert main(["encode", "nan", "0"]) == 1
    assert main(["neighbours", "ezs4a"]) == 1
    assert main(["decode", ""]) == 1


@pytest.mark.parametrize("name", ["urn:ogc:def:crs:OGC:1.3:CRS84", "EPSG:4326",
                                  "urn:ogc:def:crs:EPSG::4326"])
def test_wgs84_crs_declaration_accepted(tmp_path, name):
    p = _write(tmp_path, {"type": FC, "crs": NAMED(name), "features": [
        {"type": "Feature", "geometry": {**_poly(SQUARE), "crs": NAMED(name)}}]})
    assert cover_geojson(p, 2)["features"]


def _equal_area_km2(geohash):
    """Independent reference: in the WGS84 cylindrical equal-area projection
    (EPSG:6933) meridians and parallels are straight, so a lon/lat rectangle
    maps to an exact rectangle whose planar area equals its ellipsoidal area.
    The projection's formula stays defined up to the poles."""
    w, s, e, n = decode_bbox(geohash)
    t = Transformer.from_crs("EPSG:4326", "EPSG:6933", always_xy=True)
    (x0, x1), (y0, y1) = t.transform([w, e], [s, n])
    return abs((x1 - x0) * (y1 - y0)) / 1e6


# equatorial, mid-latitude, polar (both hemispheres) and fine cells; corner-to-
# corner geodesic edges would be off by +2.6 % ('s') and -6.3 % ('u', 'b', '0')
@pytest.mark.parametrize("geohash", ["s", "k", "u", "b", "0", "s0", "dr5ru", "zzzzzz"])
def test_cell_area_matches_equal_area_reference(geohash):
    assert cell_area_km2(geohash) == pytest.approx(_equal_area_km2(geohash), rel=1e-4, abs=0)


def test_cell_area_matches_ellipsoid_surface():
    # The 32 precision-1 cells tile the globe; their areas must sum to the WGS84
    # ellipsoid surface area (510,065,621.7 km2).
    total = sum(cell_area_km2(c) for c in "0123456789bcdefghjkmnpqrstuvwxyz")
    assert total == pytest.approx(510_065_621.7, rel=1e-4)
    assert not math.isnan(cell_area_km2("zzzzzzzzzzzz"))


def test_tiny_polar_cell_area_is_stable():
    # Near the pole the surface is locally flat, so a top-row cell is a wedge of
    # a disc whose radius r is the cell height: area = dlon_rad * r^2 / 2, and
    # the next row down (radii r..2r) has three times that area.
    _, s, _, n = decode_bbox("zzzzzzzzzzzz")
    _, _, r = Geod(ellps="WGS84").inv(0, s, 0, n)
    dlon = math.radians(cell_size(12)[0])
    top = cell_area_km2("zzzzzzzzzzzz")
    # abs=0: the areas are ~1e-18 km2, far below pytest's default abs=1e-12
    assert top == pytest.approx(dlon * r * r / 2 / 1e6, rel=1e-6, abs=0)
    assert top > 0
    assert cell_area_km2("zzzzzzzzzzzw") == pytest.approx(3 * top, rel=1e-6, abs=0)
    # area does not depend on longitude: the westernmost top-row cell matches
    west = encode(89.9999999999, -179.9999999999, 12)
    assert decode_bbox(west)[3] == 90
    assert cell_area_km2(west) == pytest.approx(top, rel=1e-9, abs=0)
    # the small-cell method (children) agrees with the polygon method (parent)
    children = sum(cell_area_km2("zzzzz" + c) for c in "0123456789bcdefghjkmnpqrstuvwxyz")
    assert children == pytest.approx(cell_area_km2("zzzzz"), rel=1e-6, abs=0)
