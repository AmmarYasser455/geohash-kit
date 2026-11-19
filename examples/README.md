# Example data

`central_park.geojson` is a four-corner simplified outline of Central Park,
New York City, in WGS84 lon/lat (GeoJSON order, x=lon, y=lat).

## Source and provenance

- **What defines the outline:** NYC Parks describes Central Park as bounded by
  59th Street (south), 110th Street (north), Fifth Avenue (east) and
  Central Park West / Eighth Avenue (west)
  (<https://www.nycgovparks.org/parks/central-park>). The four vertices are the
  corners of that street-bounded rectangle: 59th St & 5th Ave, 59th St & 8th Ave,
  110th St & 8th Ave, 110th St & 5th Ave.
- **Coordinates:** the longitude/latitude values were entered by hand, to four
  decimals (about 10 m), as approximate positions of those intersections. They
  were not copied from, or exported from, any dataset (OpenStreetMap, Natural
  Earth or otherwise), so no third-party data licence applies, and they were
  not surveyed. Treat them as an approximation of the real boundary, which is
  slightly irregular; verify against an authoritative source before relying on
  them.
- **Licence:** the file is released under the repository's MIT licence.

`demo.ipynb` walks through the Python API on this file.
