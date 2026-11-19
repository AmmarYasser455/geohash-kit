"""One-off download of the showcase data (not needed to rebuild the showcase).

Fetches the Cairo Governorate boundary from OpenStreetMap via the Overpass API
and writes showcase/data/cairo_governorate.geojson. Data (c) OpenStreetMap
contributors, ODbL 1.0.
"""

import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

QUERY = (
    '[out:json][timeout:90];'
    'rel(4103336);'
    'out geom;'
)


def main(out):
    req = urllib.request.Request(
        "https://overpass-api.de/api/interpreter",
        data=urllib.parse.urlencode({"data": QUERY}).encode(),
        headers={"User-Agent": "geohash-kit-showcase"},
    )
    from shapely.geometry import LineString, mapping
    from shapely.ops import polygonize, unary_union

    import time

    for attempt in range(6):
        try:
            data = json.loads(urllib.request.urlopen(req, timeout=120).read())
            break
        except Exception as exc:  # Overpass is often busy (502/504)
            print("retry:", exc)
            time.sleep(10 * (attempt + 1))
    else:
        raise SystemExit("Overpass unavailable")
    (rel,) = data["elements"]
    lines = [
        LineString([(p["lon"], p["lat"]) for p in m["geometry"]])
        for m in rel["members"]
        if m["type"] == "way" and m["role"] == "outer"
    ]
    polys = list(polygonize(unary_union(lines)))
    poly = unary_union(polys)
    feature = {
        "type": "Feature",
        "properties": {
            "name": rel["tags"]["name:en"] + " Governorate",
            "osm_relation": rel["id"],
            "fetched": data["osm3s"]["timestamp_osm_base"],
        },
        "geometry": mapping(poly),
    }
    fc = {"type": "FeatureCollection", "features": [feature]}
    Path(out).write_text(json.dumps(fc), encoding="utf-8")
    print(poly.geom_type, len(polys), "ring(s)")


if __name__ == "__main__":
    main(sys.argv[1])
