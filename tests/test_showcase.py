import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SHOWCASE = ROOT / "showcase"


def _load():
    spec = importlib.util.spec_from_file_location("make_showcase", SHOWCASE / "make_showcase.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_map_geojson_is_not_stale(tmp_path):
    mod = _load()
    summary = mod.build(tmp_path, png=False)
    fresh = json.loads((tmp_path / "map.geojson").read_text(encoding="utf-8"))
    committed = json.loads((SHOWCASE / "map.geojson").read_text(encoding="utf-8"))
    assert fresh == committed
    assert (tmp_path / "index.html").read_text(encoding="utf-8") == (
        SHOWCASE / "index.html"
    ).read_text(encoding="utf-8")
    # Tahrir Square (30.0444 N, 31.2357 E) lies in cell stq4y; a swapped axis would not.
    assert summary["tahrir_cell"] == "stq4y"
    tahrir = [
        f for f in fresh["features"] if f["properties"].get("has_tahrir_square")
    ]
    assert [f["properties"]["geohash"] for f in tahrir] == ["stq4y"]
    xs = [p[0] for f in fresh["features"] for p in f["geometry"]["coordinates"][0]]
    assert all(31.0 < x < 32.0 for x in xs)  # lon is x, Cairo is near 31 E


def test_map_png_is_produced(tmp_path):
    pytest.importorskip("matplotlib")
    _load().build(tmp_path, png=True)
    png = tmp_path / "map.png"
    assert png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_notebook_executes_and_plots_inline():
    nbformat = pytest.importorskip("nbformat")
    nbclient = pytest.importorskip("nbclient")
    pytest.importorskip("matplotlib")
    pytest.importorskip("ipykernel")
    nb = nbformat.read(str(SHOWCASE / "showcase.ipynb"), as_version=4)
    # Executed in memory only; the committed notebook file is not modified.
    nbclient.NotebookClient(
        nb,
        timeout=300,
        kernel_name="python3",
        resources={"metadata": {"path": str(SHOWCASE)}},
    ).execute()
    outputs = [o for c in nb.cells if c.cell_type == "code" for o in c.get("outputs", [])]
    assert not [o for o in outputs if o.output_type == "error"]
    assert any("image/png" in o.get("data", {}) for o in outputs)
