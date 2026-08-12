# scripts/schema.py
"""Declarative per-type page schemas: load YAML, validate parsed pages.

Schemas live in the skill's bundled schemas/ dir; a vault may override or add
types via <vault>/schemas/. lint and the ingest path both call validate().
"""
from __future__ import annotations

import datetime
from pathlib import Path

import yaml

from scripts import paths

_BUNDLED_DIR = paths.bundled_dir("schemas")


def _coarse_ok(value, want: str) -> bool:
    if want == "list":
        return isinstance(value, list)
    if want == "str":
        # YAML parses ISO date literals (e.g. 2026-01-01) as datetime.date,
        # not str; treat those as valid for a "str" field constraint.
        return isinstance(value, (str, datetime.date, datetime.datetime))
    if want == "int":
        return isinstance(value, int) and not isinstance(value, bool)
    if want == "dict":
        return isinstance(value, dict)
    return True  # unknown constraint token → don't fail


def _has_section(body: str, section: str) -> bool:
    return any(line.strip() == section for line in body.splitlines())


def validate(meta: dict, body: str, *, schemas: dict) -> list[dict]:
    """Return a list of issue dicts for a parsed page. Pure."""
    issues: list[dict] = []
    t = meta.get("type")
    spec = schemas.get(t) if t is not None else None
    if t is not None and spec is None:
        issues.append({"issue": "invalid_type", "detail": str(t)})
    if spec is None:
        spec = schemas.get("base")
    if spec is None:
        return issues
    for field in spec.get("required_fields", []):
        if field not in meta:
            issues.append({"issue": f"missing_field:{field}", "detail": None})
    for field, want in spec.get("field_types", {}).items():
        if field in meta and not _coarse_ok(meta[field], want):
            issues.append({
                "issue": f"wrong_type:{field}",
                "detail": f"got {type(meta[field]).__name__}",
            })
    for section in spec.get("required_sections", []):
        if not _has_section(body, section):
            issues.append({"issue": f"missing_section:{section}", "detail": None})
    for field, allowed in spec.get("allowed_values", {}).items():
        if field in meta and meta[field] not in allowed:
            issues.append({"issue": f"invalid_value:{field}", "detail": str(meta[field])})
    vr = spec.get("valid_relations") or []
    if vr:
        rels = meta.get("relations")
        if isinstance(rels, dict):
            for rel in rels:
                if rel not in vr:
                    issues.append({"issue": f"unexpected_relation:{rel}", "detail": None})
    return issues


def scaffold_required_sections(body: str, spec: dict | None) -> str:
    """Add missing schema sections once, using optional start/end placement.

    ``section_positions`` is a mapping from the exact heading to ``start`` or
    ``end``. Unspecified custom sections default to ``end`` for compatibility.
    """
    spec = spec or {}
    positions = spec.get("section_positions") or {}
    starts: list[str] = []
    ends: list[str] = []
    for section in spec.get("required_sections", []):
        if _has_section(body, section):
            continue
        target = starts if positions.get(section) == "start" else ends
        target.append(section)
    parts = []
    if starts:
        parts.append("\n\n".join(starts))
    if body.strip():
        parts.append(body.strip())
    if ends:
        parts.append("\n\n".join(ends))
    return "\n\n".join(parts) + ("\n" if parts else "")


def _load_dir(dir_path: Path) -> tuple[dict[str, dict], list[dict]]:
    """Read every *.yml in dir_path; key = filename stem, value = raw dict.

    Returns (schemas, errors) where errors is a list of
    ``{"path": str, "error": str}`` dicts for files that could not be parsed.
    Bad files are skipped so lint/reindex still run against the valid subset.
    """
    out: dict[str, dict] = {}
    errors: list[dict] = []
    if not dir_path.is_dir():
        return out, errors
    for f in sorted(dir_path.glob("*.yml")):
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8"))
        except (yaml.YAMLError, OSError) as exc:
            errors.append({"path": str(f), "error": str(exc)})
            continue
        if data is None or data == {}:
            continue  # empty file — silently skip
        if not isinstance(data, dict):
            errors.append({"path": str(f), "error": "schema root must be a mapping"})
            continue
        out[f.stem] = data
    return out, errors


def _resolve(raw: dict[str, dict]) -> dict[str, dict]:
    """Apply `extends: base` merges; fill defaults. Keeps `base` in the result."""
    base = raw.get("base", {})
    resolved: dict[str, dict] = {}
    for name, spec in raw.items():
        merged = {
            "required_fields": [],
            "field_types": {},
            "required_sections": [],
            "section_positions": {},
            "allowed_values": {},
            "valid_relations": [],
        }
        if name != "base" and spec.get("extends") == "base":
            merged["required_fields"] = list(base.get("required_fields", []))
            merged["required_sections"] = list(base.get("required_sections", []))
            merged["section_positions"] = dict(base.get("section_positions", {}))
            merged["field_types"] = dict(base.get("field_types", {}))
            merged["allowed_values"] = dict(base.get("allowed_values", {}))
            merged["valid_relations"] = list(base.get("valid_relations", []))
        # type-specific values extend/override the base
        for f in spec.get("required_fields", []):
            if f not in merged["required_fields"]:
                merged["required_fields"].append(f)
        for s in spec.get("required_sections", []):
            if s not in merged["required_sections"]:
                merged["required_sections"].append(s)
        merged["section_positions"].update(spec.get("section_positions", {}))
        merged["field_types"].update(spec.get("field_types", {}))
        merged["allowed_values"].update(spec.get("allowed_values", {}))
        for r in spec.get("valid_relations", []):
            if r not in merged["valid_relations"]:
                merged["valid_relations"].append(r)
        resolved[name] = merged
    return resolved


def load_schemas_with_errors(
    *, vault_path=None
) -> tuple[dict[str, dict], list[dict]]:
    """Load bundled schemas, overlay <vault>/schemas/, resolve extends.

    Returns ``(schemas, errors)`` where *errors* is a list of
    ``{"path": str, "error": str}`` dicts for every YAML file that could not
    be parsed (from either the bundled dir or the vault override dir).
    Callers that only need the schemas can use :func:`load_schemas` instead.
    """
    raw, errors = _load_dir(_BUNDLED_DIR)
    if vault_path is not None:
        vault_raw, vault_errors = _load_dir(Path(vault_path) / "schemas")
        raw.update(vault_raw)
        errors.extend(vault_errors)
    return _resolve(raw), errors


def load_schemas(*, vault_path=None) -> dict[str, dict]:
    """Load bundled schemas, overlay <vault>/schemas/, resolve extends. Includes `base`.

    Back-compat wrapper around :func:`load_schemas_with_errors`; parse errors
    are silently discarded. Use the ``_with_errors`` variant when you need to
    surface malformed schema files to the user (e.g. in lint reports).
    """
    schemas, _errors = load_schemas_with_errors(vault_path=vault_path)
    return schemas


def valid_types(schemas: dict) -> set[str]:
    return set(schemas) - {"base"}
