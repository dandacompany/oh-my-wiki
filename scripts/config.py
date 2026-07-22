"""Read/write the ~/.omw config model: config.yaml (settings) + .env (secrets).

Mirrors the Hermes three-file split: non-secret settings go in config.yaml,
secrets in .env (chmod 0600). Secret resolution order: live env -> .env.
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml

from scripts.paths import ensure_home, omw_home


def _config_path() -> Path:
    return omw_home() / "config.yaml"


def _env_path() -> Path:
    return omw_home() / ".env"


def load_config() -> dict:
    p = _config_path()
    if not p.exists():
        return {}
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def save_config(data: dict) -> None:
    ensure_home()
    _config_path().write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                              encoding="utf-8")


def set_config(dotted_key: str, value) -> None:
    """Set a nested key like 'search.provider' = value, preserving siblings."""
    data = load_config()
    node = data
    parts = dotted_key.split(".")
    for k in parts[:-1]:
        node = node.setdefault(k, {})
    node[parts[-1]] = value
    save_config(data)


def _read_env_file() -> dict:
    p = _env_path()
    if not p.exists():
        return {}
    out = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def read_secret(var: str) -> str | None:
    """live env -> ~/.omw/.env -> None."""
    if os.environ.get(var):
        return os.environ[var]
    return _read_env_file().get(var) or None


def set_secret(var: str, value: str) -> None:
    ensure_home()
    env = _read_env_file()
    env[var] = value
    p = _env_path()
    p.write_text("".join(f"{k}={v}\n" for k, v in env.items()), encoding="utf-8")
    p.chmod(0o600)
