"""Command-line interface for geohash-kit."""

from __future__ import annotations

import argparse
import json
import sys

from . import core


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="geohash-kit", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    e = sub.add_parser("encode", help="encode lat lon (degrees, WGS84)")
    e.add_argument("lat", type=float)
    e.add_argument("lon", type=float)
    e.add_argument("-p", "--precision", type=int, default=9)
    d = sub.add_parser("decode", help="decode a geohash to its centre and bounds")
    d.add_argument("geohash")
    n = sub.add_parser("neighbours", help="list the 8 adjacent cells")
    n.add_argument("geohash")
    pa = sub.add_parser("parent", help="print the enclosing cell one level coarser")
    pa.add_argument("geohash")
    ch = sub.add_parser("children", help="list the 32 cells one level finer")
    ch.add_argument("geohash")
    c = sub.add_parser("cover", help="cover GeoJSON polygons (lon/lat) with geohashes")
    c.add_argument("path")
    c.add_argument("-p", "--precision", type=int, required=True)
    c.add_argument("--mode", choices=["intersects", "within"], default="intersects")
    c.add_argument("--geojson", action="store_true", help="print cell polygons as GeoJSON")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "encode":
            print(core.encode(args.lat, args.lon, args.precision))
        elif args.command == "decode":
            # repr() prints the shortest exact round-trip form, so even
            # precision-12 cells keep distinct bounds and an exact centre
            lat, lon = core.decode(args.geohash)
            print(f"lat={lat!r} lon={lon!r}")
            print("bbox(min_lon,min_lat,max_lon,max_lat)="
                  + ",".join(repr(v) for v in core.decode_bbox(args.geohash)))
        elif args.command == "neighbours":
            for k, v in core.neighbours(args.geohash).items():
                print(f"{k}: {v}")
        elif args.command == "parent":
            print(core.parent(args.geohash))
        elif args.command == "children":
            print("\n".join(core.children(args.geohash)))
        else:
            fc = core.cover_geojson(args.path, args.precision, args.mode)
            if args.geojson:
                print(json.dumps(fc, indent=1))
            else:
                for f in fc["features"]:
                    print(f["properties"]["geohash"])
    except (ValueError, OSError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
