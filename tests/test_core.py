import pytest
from shapely.geometry import Polygon, box

from geohash_kit import cell_area_km2, cover, decode, decode_bbox, encode, neighbours
from geohash_kit.cli import main


def test_encode_known_values():
    # Reference values from the geohash Wikipedia article / original spec.
    assert encode(57.64911, 10.40744, 11) == "u4pruydqqvj"
    assert encode(42.6, -5.6, 5) == "ezs42"


def test_axis_order_not_swapped():
    lat, lon = decode("u4pruydqqvj")
    assert lat == pytest.approx(57.64911, abs=1e-5)
    assert lon == pytest.approx(10.40744, abs=1e-5)


def test_roundtrip_and_bbox_contains_point():
    for lat, lon in [(0, 0), (-33.8688, 151.2093), (90, 180), (-90, -180)]:
        w, s, e, n = decode_bbox(encode(lat, lon, 8))
        assert w <= lon <= e and s <= lat <= n


def test_neighbours_and_antimeridian_and_pole():
    nb = neighbours("ezs42")
    assert len(nb) == 8 and len(set(nb.values())) == 8
    assert decode_bbox(nb["e"])[0] == pytest.approx(decode_bbox("ezs42")[2])
    # cell touching 180 E wraps to the -180 side
    east_edge = encode(10, 179.9999, 4)
    assert decode_bbox(neighbours(east_edge)["e"])[0] == pytest.approx(-180)
    # cell touching the north pole has no northern neighbours
    assert set(neighbours(encode(89.99, 10, 3))) == {"e", "se", "s", "sw", "w"}


def test_invalid_input():
    with pytest.raises(ValueError):
        encode(91, 0)
    with pytest.raises(ValueError):
        decode("abc!")  # '!' invalid
    with pytest.raises(ValueError):
        decode("a")  # 'a' is not in the geohash alphabet
    with pytest.raises(ValueError):
        encode(0, 0, 0)


def test_cover_modes_and_edge_cases():
    poly = box(10.0, 50.0, 10.5, 50.3)
    inter = cover(poly, 4)
    inside = cover(poly, 4, "within")
    assert set(inside) <= set(inter) and inter
    assert encode(50.15, 10.25, 4) in inter
    assert cover(Polygon(), 4) == [] and cover(None, 4) == []
    with pytest.raises(ValueError):
        cover(Polygon([(0, 0), (1, 1), (1, 0), (0, 1)]), 4)  # bow-tie
    with pytest.raises(ValueError):
        cover(box(170, 0, 190, 10), 3)  # crosses the antimeridian
    with pytest.raises(ValueError):
        cover(box(-10, -10, 10, 10), 8)  # too many cells


def test_cover_rejects_normalised_antimeridian_ring():
    ring = Polygon([(179, 10), (-179, 10), (-179, 11), (179, 11)])
    with pytest.raises(ValueError, match="antimeridian"):
        cover(ring, 2)


def test_cover_includes_cells_touching_aligned_west_south_edges():
    # precision 1 cells are 45 x 45 degrees; box(0,0,45,45) touches 9 cells
    got = cover(box(0, 0, 45, 45), 1)
    assert len(got) == 9
    assert encode(-22.5, -22.5, 1) in got and encode(22.5, 22.5, 1) in got
    assert cover(box(0, 0, 45, 45), 1, "within") == [encode(22.5, 22.5, 1)]
    # world corner stays clamped
    assert len(cover(box(-180, -90, -135, -45), 1)) == 4


def test_cell_area_uses_ellipsoid():
    # precision-5 cells are about 4.9 km x 4.9 km at the equator, smaller at 60N
    eq, hi = cell_area_km2(encode(0.01, 0.01, 5)), cell_area_km2(encode(60, 0.01, 5))
    assert 20 < eq < 25 and hi < eq * 0.6


def test_cli(capsys):
    assert main(["encode", "57.64911", "10.40744", "-p", "11"]) == 0
    assert capsys.readouterr().out.strip() == "u4pruydqqvj"
    assert main(["decode", "zzz!"]) == 1


@pytest.mark.parametrize("geohash", ["ezs42", "zzzzzzzzzzzz", "000000000000", "u4pruydqqvjx"])
def test_cli_decode_keeps_full_precision(capsys, geohash):
    assert main(["decode", geohash]) == 0
    first, second = capsys.readouterr().out.strip().splitlines()
    lat_part, lon_part = first.split()
    lat, lon = float(lat_part.split("=")[1]), float(lon_part.split("=")[1])
    bbox = tuple(float(v) for v in second.split("=")[1].split(","))
    assert (lat, lon) == decode(geohash)
    assert bbox == decode_bbox(geohash)
    w, s, e, n = bbox
    assert w < e and s < n
    assert s < lat < n and w < lon < e


def test_parent_children_hierarchy(capsys):
    import geohash_kit as gk

    kids = gk.children("ezs4")
    assert len(kids) == 32 and kids[2] == "ezs42"
    assert all(gk.parent(k) == "ezs4" for k in kids)
    # children lie inside the parent's bounds (lon/lat order)
    w, s, e, n = decode_bbox("ezs4")
    for k in kids:
        kw, ks, ke, kn = decode_bbox(k)
        assert w <= kw and s <= ks and ke <= e and kn <= n
    assert gk.parent("EZS42") == "ezs4"
    for bad in ("e", "", "a1"):
        with pytest.raises(ValueError):
            gk.parent(bad)
    with pytest.raises(ValueError):
        gk.children("u4pruydqqvjk")
    assert main(["parent", "ezs42"]) == 0
    assert capsys.readouterr().out == "ezs4\n"
    assert main(["children", "ezs4"]) == 0
    assert capsys.readouterr().out.split()[:3] == ["ezs40", "ezs41", "ezs42"]
    assert main(["children", "!"]) == 1


@pytest.mark.parametrize(
    "lat, lon, prefix",
    [
        (-33.8688, 151.2093, "r3gx2"),   # Sydney (southern, eastern hemisphere)
        (35.6762, 139.6503, "xn76"),     # Tokyo
        (-34.6037, -58.3816, "69y7"),    # Buenos Aires (southern, western)
        (51.5074, -0.1278, "gcpvj"),     # London, just west of the prime meridian
    ],
)
def test_encode_real_cities_in_all_hemispheres(lat, lon, prefix):
    code = encode(lat, lon, 7)
    assert code.startswith(prefix)
    w, s, e, n = decode_bbox(code)
    assert w <= lon <= e and s <= lat <= n
