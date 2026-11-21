import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BRAND = ROOT / "assets" / "brand"
ALLOWED = {
    "logo.svg": {"#121417", "#f2552c"},
    "logo-dark.svg": {"#f3eee4", "#f2552c"},
}


def test_logos_valid():
    for name, allowed in ALLOWED.items():
        path = BRAND / name
        assert path.exists()
        root = ET.parse(path).getroot()
        assert root.get("viewBox") == "0 0 100 100"
        assert root.get("width") == "100" and root.get("height") == "100"
        text = path.read_text(encoding="utf-8").lower()
        assert set(re.findall(r"#[0-9a-f]{6}", text)) == allowed
        for el in root.iter():
            fill = el.get("fill")
            if fill is not None:
                assert fill.lower() in allowed
        assert "opacity" not in text and "gradient" not in text


def test_readme_header():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "assets/brand/logo-dark.svg" in readme
    assert "[OpenTerra](https://github.com/AmmarYasser455)" in readme
