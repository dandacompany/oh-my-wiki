"""Acceptance: a built wheel is self-contained (bundle + schema.sql shipped).

Heavy (invokes `python -m build`). Deselected by default via the `packaging`
marker; run explicitly with `pytest tests/test_packaging.py -m packaging`.
"""
import glob
import pathlib
import subprocess
import sys
import zipfile

import pytest


@pytest.mark.packaging
def test_built_wheel_is_self_contained(tmp_path):
    repo = pathlib.Path(__file__).resolve().parents[1]
    out = tmp_path / "dist"
    subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(out)],
        cwd=repo,
        check=True,
    )
    whl = glob.glob(str(out / "*.whl"))[0]
    names = zipfile.ZipFile(whl).namelist()
    assert any(n.startswith("scripts/_bundle/schemas/") for n in names)
    assert any(n.startswith("scripts/_bundle/personas/") for n in names)
    assert any(n.startswith("scripts/_bundle/backends/") for n in names)
    assert any(n == "scripts/_bundle/.claude-plugin/plugin.json" for n in names)
    assert any(n == "scripts/db/schema.sql" for n in names)
