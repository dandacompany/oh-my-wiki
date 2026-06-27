"""Persona batch fan-out — resolve a page list + emit per-page persona-run commands.

Pure resolver: validates the role, resolves target pages (explicit list or
faceted query), and emits ready-to-run `omw persona-run` command strings. It
never calls an LLM, never dispatches, and never mutates the vault. The host runs
the emitted commands in parallel (see commands/persona-fanout.md).
"""
from __future__ import annotations

import shlex

from scripts import personas, persona_run, registry


class FanoutError(Exception):
    """Raised for unknown/vault-wide role, bad selector combination, etc."""


def _dedup(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        if it not in seen:
            seen.add(it)
            out.append(it)
    return out


def resolve(role, *, db_path, vault_id, pages=None, tag=None, type=None,
            status=None, layer=None, visibility=None, backend=None) -> dict:
    """Resolve target pages for a per-page fan-out of `role`.

    Returns {role, backend, count, pages, commands}. Raises FanoutError on an
    unknown/vault-wide role, both selectors, or no selector.
    """
    known = {p["name"] for p in personas.list_personas()}
    if role not in known:
        raise FanoutError(f"unknown persona: {role!r}")
    if not persona_run.needs_source(role):
        raise FanoutError(
            f"role {role!r} is vault-wide (self-gathering), not page-fannable")

    facets = {"tag": tag, "type": type, "status": status,
              "layer": layer, "visibility": visibility}
    has_facet = any(v is not None for v in facets.values())
    has_pages = bool(pages)
    if has_pages and has_facet:
        raise FanoutError("explicit --pages and facet selectors are mutually exclusive")
    if not has_pages and not has_facet:
        raise FanoutError("no page selector given (use --pages or a facet)")

    if has_pages:
        relpaths = _dedup(list(pages))
    else:
        rows = registry.list_notes_faceted(
            db_path, vault_id=vault_id, tag=tag, type_=type, status=status,
            layer=layer, visibility=visibility)
        relpaths = [r["relpath"] for r in rows]

    suffix = f" --backend {backend}" if backend else ""
    commands = [f"omw persona-run {role} --page {shlex.quote(rp)}{suffix}" for rp in relpaths]
    return {"role": role, "backend": backend, "count": len(relpaths),
            "pages": relpaths, "commands": commands}
