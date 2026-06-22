"""Build shim: copy the repo-root bundle into the package so a built wheel is
self-contained (works for PyPI installs AND `pip install git+https://…`).

All project metadata lives in pyproject.toml; this file exists only to hook a
custom ``build_py`` that materializes ``scripts/_bundle/`` at build time. The
runtime resolver (``scripts.paths.bundled_root``) prefers the repo root in dev
/ skill-copy checkouts and falls back to this ``_bundle`` in an installed wheel.
"""
import shutil
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py

_BUNDLE_DIRS = [
    "schemas",
    "personas",
    "backends",
    "commands",
    "omw",
    "references",
    "hooks",
    ".claude-plugin",
]
_ROOT = Path(__file__).resolve().parent


class _BundleBuildPy(build_py):
    """Standard build_py, plus a copy of the repo-root bundle into the package."""

    def run(self):
        super().run()
        dest = Path(self.build_lib) / "scripts" / "_bundle"
        if dest.exists():
            shutil.rmtree(dest)
        for name in _BUNDLE_DIRS:
            src = _ROOT / name
            if src.is_dir():
                shutil.copytree(
                    src,
                    dest / name,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.egg-info"),
                )


setup(cmdclass={"build_py": _BundleBuildPy})
