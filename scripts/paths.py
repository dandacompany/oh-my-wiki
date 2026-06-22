"""Single source of truth for all OMW filesystem paths.

The registry is ALWAYS the one global DB at ~/.omw/registry.db (override the
root with OMW_HOME for tests/CI/profiles). Vault *content* can live under the
global home, project-local, or at a custom path — but every vault is registered
in the one global registry, so the skill can always reach all vaults.
"""
from __future__ import annotations

import os
from pathlib import Path

from scripts.slugify import slugify


def omw_home() -> Path:
    """OMW data root. Default ~/.omw; OMW_HOME env overrides (tests, CI, profiles).
    An unset OR empty OMW_HOME falls back to ~/.omw (empty string must not become cwd)."""
    raw = os.environ.get("OMW_HOME")
    return Path(raw).expanduser() if raw else Path.home() / ".omw"


def registry_path() -> Path:
    """The single global registry DB. ~/.omw/registry.db."""
    return omw_home() / "registry.db"


def default_vault_root(name: str) -> Path:
    """vault-setup 'global default' content location. ~/.omw/vaults/<slug>."""
    return omw_home() / "vaults" / slugify(name)


def project_vault_root(name: str) -> Path:
    """vault-setup 'project-local' content location. <cwd>/.omw/<slug>."""
    return Path.cwd() / ".omw" / slugify(name)


def resolve_vault_root(name: str, location: str) -> Path:
    """global | project | <absolute/relative path>."""
    if location == "global":
        return default_vault_root(name)
    if location == "project":
        return project_vault_root(name)
    return Path(location).expanduser()


def ensure_home() -> Path:
    """Create ~/.omw and ~/.omw/vaults/ (idempotent). Call before registry access."""
    home = omw_home()
    (home / "vaults").mkdir(parents=True, exist_ok=True)
    return home


def legacy_registry_candidates() -> list[Path]:
    """Old registry locations for migration detection, in priority order:
    [<skill_dir>/data/registry.db, <cwd>/data/registry.db]."""
    skill_dir = Path(__file__).resolve().parent.parent
    return [skill_dir / "data" / "registry.db", Path.cwd() / "data" / "registry.db"]


# ---------------------------------------------------------------------------
# Bundled data resolver (dev checkout vs installed wheel)
# ---------------------------------------------------------------------------

_PKG_DIR = Path(__file__).resolve().parent            # .../scripts
_REPO_ROOT = _PKG_DIR.parent                          # repo root (dev/skill checkout)
_bundled_root_cache: "Path | None" = None


def bundled_root() -> Path:
    """Base dir for bundled data (schemas/personas/backends/commands/omw/.claude-plugin).

    Sentinel is self-scoped: an installed wheel ships the data under THIS package's
    own <scripts>/_bundle (created by setup.py's build_py), so its presence is an
    unambiguous "I am an installed wheel" marker — immune to an unrelated top-level
    schemas/ appearing in site-packages. When _bundle is absent (dev + skill-copy
    checkout) the data lives at the repo root, which is authoritative there.
    """
    global _bundled_root_cache
    if _bundled_root_cache is None:
        packaged = _PKG_DIR / "_bundle"
        _bundled_root_cache = packaged if packaged.is_dir() else _REPO_ROOT
    return _bundled_root_cache


def bundled_dir(name: str) -> Path:
    """Return bundled_root() / name."""
    return bundled_root() / name
