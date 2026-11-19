import json
from pathlib import Path

from shapely.geometry import shape

from geohash_kit import cover_geojson, encode

ROOT = Path(__file__).resolve().parents[1]
PARK = ROOT / "examples" / "central_park.geojson"


def test_central_park_cover():
    fc = cover_geojson(PARK, 6)
    cells = {f["properties"]["geohash"] for f in fc["features"]}
    # Known places inside / near Central Park (lat, lon)
    assert encode(40.7794, -73.9632, 6) in cells  # Metropolitan Museum of Art
    assert encode(40.7794, -73.9691, 6) in cells  # Belvedere Castle
    assert encode(40.6892, -74.0445, 6) not in cells  # Statue of Liberty
    # Manhattan cells share the "dr5" / "dr7" prefixes
    assert all(c.startswith(("dr5", "dr7")) for c in cells)
    # precision-6 cells are ~1.2 km x 0.6 km, ~0.7 km2 each
    assert all(0.5 < f["properties"]["area_km2"] < 0.9 for f in fc["features"])


def test_demo_geojson_is_current():
    demo = json.loads((ROOT / "docs" / "demo.geojson").read_text(encoding="utf-8"))
    assert demo == cover_geojson(PARK, 6)


def test_geojson_area_keeps_fine_cells_positive(tmp_path):
    import pytest

    from geohash_kit import cell_area_km2

    p = tmp_path / "tiny.geojson"
    p.write_text(json.dumps({"type": "Polygon", "coordinates": [[
        [-73.9680, 40.7794], [-73.9679, 40.7794], [-73.9679, 40.7795],
        [-73.9680, 40.7795], [-73.9680, 40.7794]]]}), encoding="utf-8")
    fc = cover_geojson(p, 11)
    assert fc["features"]
    for f in fc["features"]:
        a = f["properties"]["area_km2"]
        assert a > 0
        assert a == pytest.approx(cell_area_km2(f["properties"]["geohash"]), rel=1e-6, abs=0)


def test_rfc7946_ring_orientation():
    # Exterior rings must be counter-clockwise in both the input and the output.
    for path in (PARK, ROOT / "docs" / "demo.geojson"):
        fc = json.loads(path.read_text(encoding="utf-8"))
        for f in fc["features"]:
            poly = shape(f["geometry"])
            assert poly.exterior.is_ccw, path.name
            assert all(not r.is_ccw for r in poly.interiors)
