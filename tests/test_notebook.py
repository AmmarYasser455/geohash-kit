import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_notebook_runs(monkeypatch):
    monkeypatch.chdir(ROOT)
    nb = json.loads((ROOT / "examples" / "demo.ipynb").read_text(encoding="utf-8"))
    assert nb["nbformat"] == 4
    ns = {}
    for cell in nb["cells"]:
        if cell["cell_type"] == "code":
            assert cell["outputs"] == []
            exec("".join(cell["source"]), ns)
    assert ns["gh"] == "u4pruydqqvj"
