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
    assert any(n == "scripts/db/schema.sql" for n in names)
    # The bundle must reproduce a runnable skill: scripts package + SKILL.md entry.
    assert any(n.startswith("scripts/_bundle/scripts/") for n in names)
    assert any(n == "scripts/_bundle/SKILL.md" for n in names)


@pytest.mark.packaging
def test_installed_wheel_bundle_yields_runnable_skill_copy(tmp_path):
    """An installed-wheel `omw setup agents` copy must include SKILL.md + scripts.

    Reproduces the wheel layout (scripts/_bundle/) from a built wheel, then runs
    agent_skills._copy_bundle against it (the fallback Hermes/CLI-down path) and
    asserts the copied skill dir is discoverable + runnable — not a data-only
    husk missing the entry point and the python package.
    """
    from scripts import agent_skills

    repo = pathlib.Path(__file__).resolve().parents[1]
    out = tmp_path / "dist"
    subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(out)],
        cwd=repo,
        check=True,
    )
    whl = glob.glob(str(out / "*.whl"))[0]
    extract = tmp_path / "wheel"
    zipfile.ZipFile(whl).extractall(extract)
    bundle = extract / "scripts" / "_bundle"
    assert bundle.is_dir(), "wheel must ship scripts/_bundle/"

    dest_skills = tmp_path / "skills"
    dest_skills.mkdir()
    skill = agent_skills._copy_bundle(dest_skills, repo_root=bundle)
    assert (skill / "SKILL.md").is_file(), "copied skill missing SKILL.md entry point"
    assert (skill / "scripts" / "omw_cli.py").is_file(), "copied skill missing scripts package"
    assert (skill / "commands").is_dir()
    assert (skill / "schemas").is_dir()
