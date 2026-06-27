"""Persona bundles — run a named team of personas in sequence.

A bundle lives at personas/bundles/<name>.yaml with keys name, description, and
roles (an ordered list of known persona names). This module loads + validates
bundles and orchestrates a run by looping persona_run.run() per role. Like
personas.py it never calls an LLM; the cognitive work happens inside each
isolated one-shot subagent that persona_run dispatches.
"""
from __future__ import annotations

import sys

import yaml

from scripts import paths, personas

BUNDLES_ROOT = paths.bundled_dir("personas") / "bundles"
REQUIRED_KEYS = ("name", "description", "roles")


class BundleError(Exception):
    """Raised for unknown bundle, malformed yaml, unknown role, etc."""


def _known_roles() -> set[str]:
    return {p["name"] for p in personas.list_personas()}


def _parse_bundle_text(text: str, *, known_roles: set[str]) -> dict:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise BundleError(f"malformed bundle yaml: {exc}") from exc
    if not isinstance(data, dict):
        raise BundleError("bundle must be a YAML mapping")
    for key in REQUIRED_KEYS:
        if key not in data:
            raise BundleError(f"missing required key in bundle: {key!r}")
    for key in ("name", "description"):
        if not isinstance(data[key], str) or not data[key].strip():
            raise BundleError(f"{key} must be a non-empty string")
    roles = data["roles"]
    if not isinstance(roles, list) or not roles:
        raise BundleError("roles must be a non-empty list")
    unknown = [r for r in roles if r not in known_roles]
    if unknown:
        raise BundleError(f"unknown role(s) in bundle: {unknown}")
    return {"name": data["name"], "description": data["description"], "roles": list(roles)}


def load_bundle(name: str) -> dict:
    """Return the validated bundle spec {name, description, roles}."""
    target = BUNDLES_ROOT / f"{name}.yaml"
    if not target.exists():
        raise BundleError(f"unknown bundle: {name!r}")
    return _parse_bundle_text(target.read_text(encoding="utf-8"), known_roles=_known_roles())


def list_bundles() -> list[dict]:
    """Return [{name, description, roles}, ...] for every valid bundle yaml."""
    out: list[dict] = []
    if not BUNDLES_ROOT.is_dir():
        return out
    known = _known_roles()
    for yml in sorted(BUNDLES_ROOT.glob("*.yaml")):
        try:
            out.append(_parse_bundle_text(yml.read_text(encoding="utf-8"), known_roles=known))
        except BundleError:
            continue
    return out


def run_bundle(name, *, db_path, vault_id, page=None, backend=None,
               override_cli_path=None) -> int:
    """Run a bundle's roles in order. Returns 0 iff every role succeeded."""
    from scripts import persona_run
    try:
        bundle = load_bundle(name)
    except BundleError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    roles = bundle["roles"]
    if page is None:
        missing = [r for r in roles if persona_run.needs_source(r)]
        if missing:
            print(f"error: bundle {name!r} has source-driven role(s) {missing} "
                  f"but no --page was given", file=sys.stderr)
            return 1
    results = []
    for role in roles:
        src = {"vault_relpath": page} if (page and persona_run.needs_source(role)) else None
        try:
            rc = persona_run.run(role, db_path=db_path, vault_id=vault_id, source=src,
                                 backend=backend, override_cli_path=override_cli_path)
        except Exception as exc:  # noqa: BLE001 — one bad role must not abort the team
            print(f"error: role {role!r} failed: {exc}", file=sys.stderr)
            rc = 1
        results.append((role, rc))
    print(f"\n--- bundle {name!r} summary ---")
    for role, rc in results:
        print(f"  {'ok  ' if rc == 0 else 'FAIL'}  {role}")
    return 0 if all(rc == 0 for _, rc in results) else 1
