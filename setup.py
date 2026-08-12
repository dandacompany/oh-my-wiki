"""Build shim: copy the repo-root skill bundle into the package so a built wheel
is self-contained (works for PyPI installs AND `pip install git+https://…`).

All project metadata lives in pyproject.toml; this file exists only to hook a
custom ``build_py`` that materializes ``scripts/_bundle/`` at build time. The
runtime resolver (``scripts.paths.bundled_root``) prefers this packaged
``_bundle`` in an installed wheel and falls back to the repo root in dev /
skill-copy checkouts.

The bundle must reproduce the SAME skill tree that ``scripts.agent_skills``
copies in a dev checkout, so that ``omw setup agents`` from an installed wheel
yields a discoverable, runnable skill: the data dirs PLUS the ``scripts`` package
and the root ``SKILL.md`` entry point (omitting these silently installs an
unusable skill).
"""
import shutil
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py

# Directories copied into scripts/_bundle/. `scripts` (the package itself) and the
# root SKILL.md are required for an installed-wheel `omw setup agents` to produce a
# working skill — not just the data dirs.
_BUNDLE_DIRS = [
    "schemas",
    "personas",
    "backends",
    "commands",
    "omw",
    "references",
    "scripts",
]
# Root files the skill tree needs (SKILL.md is the discoverable entry point;
# README/LICENSE make the copied skill dir self-describing).
_BUNDLE_FILES = ["SKILL.md", "README.md", "LICENSE"]

_IGNORE = shutil.ignore_patterns(
    "__pycache__", "*.pyc", "*.pyo", "*.egg-info", "_bundle"
)
_ROOT = Path(__file__).resolve().parent


class _BundleBuildPy(build_py):
    """Standard build_py, plus a copy of the repo-root skill bundle into the package."""

    def run(self):
        super().run()
        dest = Path(self.build_lib) / "scripts" / "_bundle"
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True)
        for name in _BUNDLE_DIRS:
            src = _ROOT / name
            if src.is_dir():
                shutil.copytree(src, dest / name, ignore=_IGNORE)
        for name in _BUNDLE_FILES:
            src = _ROOT / name
            if src.is_file():
                shutil.copy2(src, dest / name)


setup(cmdclass={"build_py": _BundleBuildPy})
