"""Anti-drift checks for the public tutorial and full reference."""
from __future__ import annotations

import importlib.util
from pathlib import Path

from scripts.ops_registry import OPS


ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, relpath: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relpath)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_showcase_tracks_current_version_and_all_public_cli_ops():
    mod = _load("tutorial_showcase", "docs/tutorial-omw/build_tutorial_omw.py")
    html = mod.HEAD + mod.body()
    assert f"v{mod.VERSION}" in html
    assert "2.20.0" not in html and "CLI 명령어</dt><dd>17개" not in html
    assert 'id="step-STEP 14"' in html
    assert 'id="step-STEP 15"' in html
    assert "source_url" in html and "omw reindex --full" in html
    assert set(mod.OP_SUMMARY_KO) == {op.name for op in mod.CLI_OPS}
    for op in (item for item in OPS if item.kind == "deterministic"):
        assert f"<code>omw {op.name}</code>" in mod.QUICK_REFERENCE_TABLE


def test_reference_generator_owns_new_sections_and_current_contract():
    mod = _load("tutorial_reference", "docs/tutorial-reference/build_tutorial_reference.py")
    html = mod.HEAD + mod.body()
    nums = [section["num"] for section in mod.SECTIONS]
    assert nums[-5:] == ["K", "L", "M", "N", "부록"]
    assert "완전 삭제" in html and "OMW_HOME/.trash" in html
    assert "페르소나 6종" in html
    assert "fetch</code> · <code>serve" in html
    assert "<code>gate</code> · <code>playwright</code>" in html
    assert "python3 -m scripts.omw_cli" not in html
    assert "2.20.0" not in html and "2.23.0" not in html
    for op in (item for item in OPS if item.kind == "deterministic"):
        assert f"<code>omw {op.name}</code>" in mod.CLI_TABLE


def test_reference_tables_are_mobile_scrollable():
    mod = _load("tutorial_mobile", "docs/tutorial-reference/build_tutorial_reference.py")
    assert 'class="table-scroll"' in mod.CLI_TABLE
    assert ".table-scroll{max-width:100%;overflow-x:auto" in mod.HEAD
    assert "html,body{max-width:100%;overflow-x:hidden}" in mod.HEAD
