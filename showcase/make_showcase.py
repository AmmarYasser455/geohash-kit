"""Build the Cairo geohash-cover showcase from the data in showcase/data/.

Run from the repository root, offline:  python showcase/make_showcase.py

Question: how many precision-5 geohash cells (about 5 km wide) are needed to
cover Cairo Governorate, and how much of each border cell is really inside?

Outputs (next to this script by default): map.geojson, map.png, index.html.
Coordinates are WGS84 lon/lat (x=lon, y=lat); areas are geodesic (WGS84).
"""

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))

import geohash_kit as gk  # noqa: E402
from pyproj import Geod  # noqa: E402
from shapely.geometry import box, mapping  # noqa: E402
from shapely.geometry.polygon import orient  # noqa: E402

PRECISION = 5
DATA = HERE / "data" / "cairo_governorate.geojson"
CREDIT = "Data: (c) OpenStreetMap contributors, ODbL 1.0"
REPO = "https://github.com/AmmarYasser455/geohash-kit"
# Tahrir Square, Cairo (lat, lon): a real reference point for the cell lookup.
TAHRIR = (30.0444, 31.2357)
GEOD = Geod(ellps="WGS84")


def geodesic_area_km2(geom):
    """Absolute WGS84 ellipsoidal area of a lon/lat (multi)polygon in km2."""
    return abs(GEOD.geometry_area_perimeter(geom)[0]) / 1e6


def compute(data=DATA):
    """Run geohash-kit on the boundary; return (boundary, rows, summary)."""
    boundary = gk.read_geometry(data)
    boundary_km2 = geodesic_area_km2(boundary)
    touching = gk.cover(boundary, PRECISION)
    inside = set(gk.cover(boundary, PRECISION, "within"))
    rows = []
    for code in touching:
        cell = box(*gk.decode_bbox(code))
        area = gk.cell_area_km2(code)
        covered = area if code in inside else geodesic_area_km2(cell.intersection(boundary))
        rows.append(
            {
                "geohash": code,
                "kind": "inside" if code in inside else "edge",
                "cell_km2": area,
                "inside_km2": min(covered, area),
                "share_inside": min(covered / area, 1.0),
                "geometry": cell,
            }
        )
    tahrir = gk.encode(*TAHRIR, PRECISION)
    cover_km2 = sum(r["cell_km2"] for r in rows)
    summary = {
        "precision": PRECISION,
        "boundary_km2": boundary_km2,
        "cells_intersecting": len(rows),
        "cells_within": len(inside),
        "cells_edge": len(rows) - len(inside),
        "cover_km2": cover_km2,
        "overshoot_pct": 100 * (cover_km2 / boundary_km2 - 1),
        "within_km2": sum(r["cell_km2"] for r in rows if r["kind"] == "inside"),
        "tahrir_cell": tahrir,
        "tahrir_neighbours": sorted(gk.neighbours(tahrir).values()),
    }
    return boundary, rows, summary


def feature_collection(boundary, rows, summary):
    """RFC 7946 FeatureCollection (EPSG:4326 lon/lat, CCW exteriors)."""
    feats = [
        {
            "type": "Feature",
            "properties": {
                "kind": "boundary",
                "name": "Cairo Governorate (OpenStreetMap relation 4103336)",
                "area_km2": round(summary["boundary_km2"], 3),
            },
            "geometry": mapping(orient(boundary, 1.0)),
        }
    ]
    for r in rows:
        feats.append(
            {
                "type": "Feature",
                "properties": {
                    "kind": r["kind"],
                    "geohash": r["geohash"],
                    "cell_km2": round(r["cell_km2"], 3),
                    "inside_km2": round(r["inside_km2"], 3),
                    "share_inside": round(r["share_inside"], 3),
                    "has_tahrir_square": r["geohash"] == summary["tahrir_cell"],
                },
                "geometry": mapping(orient(r["geometry"], 1.0)),
            }
        )
    return {"type": "FeatureCollection", "features": feats}


def draw_map(ax, boundary, rows, summary, title=True):
    """Draw cells shaded by share inside, plus the boundary, on lon/lat axes."""
    import matplotlib.pyplot as plt
    from matplotlib.collections import PatchCollection
    from matplotlib.patches import Polygon as MplPolygon

    cmap = plt.get_cmap("YlGnBu")
    patches = [MplPolygon(list(r["geometry"].exterior.coords)) for r in rows]
    pc = PatchCollection(patches, cmap=cmap, edgecolor="#555555", linewidth=0.4, alpha=0.85)
    pc.set_array([r["share_inside"] for r in rows])
    pc.set_clim(0, 1)
    ax.add_collection(pc)
    polys = boundary.geoms if hasattr(boundary, "geoms") else [boundary]
    for p in polys:
        x, y = p.exterior.xy
        ax.plot(x, y, color="#c0392b", linewidth=1.6)
    ax.plot([], [], color="#c0392b", linewidth=1.6, label="Cairo Governorate boundary")
    lat, lon = TAHRIR
    ax.plot(lon, lat, marker="*", color="black", markersize=12, linestyle="", label="Tahrir Square")
    ax.annotate(summary["tahrir_cell"], (lon, lat), xytext=(6, 8), textcoords="offset points",
                fontsize=9, weight="bold")
    minx, miny, maxx, maxy = boundary.bounds
    ax.set_xlim(minx - 0.03, maxx + 0.03)
    ax.set_ylim(miny - 0.03, maxy + 0.03)
    ax.set_aspect(1 / math.cos(math.radians((miny + maxy) / 2)))
    ax.set_xlabel("Longitude (deg E, WGS84 / EPSG:4326)")
    ax.set_ylabel("Latitude (deg N); north is up")
    ax.grid(color="#dddddd", linewidth=0.4)
    ax.legend(loc="upper left", fontsize=8, framealpha=0.9)
    if title:
        ax.set_title(
            f"Cairo Governorate covered by {summary['cells_intersecting']} precision-5 geohash cells",
            fontsize=12,
        )
    return pc


def render_png(path, boundary, rows, summary):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 6.4), dpi=150)
    pc = draw_map(ax, boundary, rows, summary)
    cb = fig.colorbar(pc, ax=ax, shrink=0.8, pad=0.02)
    cb.set_label("Share of cell inside the boundary (geodesic)")
    fig.text(0.99, 0.01, CREDIT + "; cells by geohash-kit", ha="right", va="bottom", fontsize=7,
             color="#444444")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(path, dpi=150)
    plt.close(fig)


HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cairo Governorate as geohash cells</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
body { margin: 0; font-family: sans-serif; }
header { padding: 8px 14px; }
h1 { font-size: 1.2em; margin: 0 0 4px; }
p { margin: 2px 0; font-size: 0.9em; }
#map { height: calc(100vh - 110px); }
</style>
</head>
<body>
<header>
<h1>Cairo Governorate covered by __N__ precision-5 geohash cells</h1>
<p>Each box is a geohash cell that touches the governorate boundary (red); darker cells lie mostly inside it. Click a cell for its code and area.</p>
<p>Built with <a href="__REPO__">geohash-kit</a>. Serve over http (e.g. <code>python -m http.server</code>) so the page can fetch map.geojson.</p>
</header>
<div id="map"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
var map = L.map('map');
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 19,
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
}).addTo(map);
function shade(s) { return s > 0.9 ? '#08589e' : s > 0.6 ? '#2b8cbe' : s > 0.3 ? '#7bccc4' : '#ccebc5'; }
function style(f) {
  if (f.properties.kind === 'boundary') {
    return {color: '#c0392b', weight: 2.5, fill: false};
  }
  return {color: '#555', weight: 0.6, fillColor: shade(f.properties.share_inside), fillOpacity: 0.55};
}
function popup(f, layer) {
  var rows = Object.keys(f.properties).map(function (k) {
    return '<tr><td>' + k + '</td><td>' + f.properties[k] + '</td></tr>';
  }).join('');
  layer.bindPopup('<table>' + rows + '</table>');
}
fetch('map.geojson').then(function (r) { return r.json(); }).then(function (data) {
  var layer = L.geoJSON(data, {style: style, onEachFeature: popup}).addTo(map);
  map.fitBounds(layer.getBounds());
});
</script>
</body>
</html>
"""


def build(out_dir=HERE, png=True, data=DATA):
    """Write map.geojson, index.html and (optionally) map.png into out_dir."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    boundary, rows, summary = compute(data)
    fc = feature_collection(boundary, rows, summary)
    (out / "map.geojson").write_text(json.dumps(fc, indent=1) + "\n", encoding="utf-8")
    html = HTML.replace("__N__", str(summary["cells_intersecting"])).replace("__REPO__", REPO)
    (out / "index.html").write_text(html, encoding="utf-8")
    if png:
        render_png(out / "map.png", boundary, rows, summary)
    return summary


def main(argv=None):
    summary = build(HERE)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
