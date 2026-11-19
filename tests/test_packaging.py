"""Packaging metadata checks (offline, no build needed)."""

import re
from pathlib import Path

PYPROJECT = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")


def _version_tuple(text):
    return tuple(int(part) for part in text.split("."))


def test_spdx_license_string_needs_setuptools_77():
    # `license = "MIT"` (PEP 639 SPDX string) is only accepted by setuptools >= 77.0.3.
    assert re.search(r'^license\s*=\s*"MIT"\s*$', PYPROJECT, re.MULTILINE)
    match = re.search(r'"setuptools>=([0-9.]+)"', PYPROJECT)
    assert match, "build-system must pin a setuptools minimum"
    assert _version_tuple(match.group(1)) >= (77, 0, 3)


def test_project_metadata():
    assert re.search(r'^name\s*=\s*"geohash-kit"', PYPROJECT, re.MULTILINE)
    assert re.search(r'^version\s*=\s*"0\.1\.0"', PYPROJECT, re.MULTILINE)
    assert re.search(r'^requires-python\s*=\s*">=3\.10"', PYPROJECT, re.MULTILINE)
    assert re.search(r'^license-files\s*=\s*\["LICENSE"\]', PYPROJECT, re.MULTILINE)
    assert (Path(__file__).resolve().parents[1] / "LICENSE").is_file()
