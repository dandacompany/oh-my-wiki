"""Dispatch a persona as an isolated one-shot subagent via backends.py.

Host-universal (claude/codex/gemini/opencode): loads the portable persona spec,
gathers deterministic inputs, spawns a one-shot agent with the persona body as
system prompt, and files the result. Hermetically testable via
OMW_BACKEND_OVERRIDE_PATH + tests/fakes/.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from scripts import backends
from scripts import links as _links
from scripts import personas
from scripts import registry
from scripts import wiki_lint as _wiki_lint


class RunError(Exception):
    pass


def _override_path() -> str | None:
    return os.environ.get("OMW_BACKEND_OVERRIDE_PATH") or None


def _pick_backend(detected: dict, requested: str | None) -> str:
    def ok(name):
        d = detected.get(name) or {}
        return d.get("installed") and d.get("authed")
    if requested:
        if ok(requested):
            return requested
        raise RunError(f"backend {requested!r} is not installed/authed")
    for name in ("claude", "codex", "gemini", "opencode"):
        if ok(name):
            return name
    raise RunError("no installed+authenticated backend found "
                   "(claude/codex/gemini/opencode)")


def _resolve_model(model_hint: str, backend: str) -> str:
    try:
        hinted = backends.list_models(backend, hint_filter=model_hint)
        if hinted:
            return hinted[0]["id"]
        allm = backends.list_models(backend)
        if allm:
            return allm[0]["id"]
    except Exception:
        pass
    return ""  # backend default


def _gather_inputs(role: str, *, db_path, vault_id, source: dict | None = None) -> tuple[str, dict]:
    """Return (task_prompt, source_meta) seeding the persona with deterministic data.

    Roles:
    - consistency-checker: embeds contradiction_candidates JSON from wiki_lint.check.
    - curator: embeds links.index_drift JSON.
    - fact-checker / terminology-manager / wiki-librarian: calls personas.resolve_input
      with the provided source dict and embeds content in task_prompt.
    """
    if role == "consistency-checker":
        rep = _wiki_lint.check(Path(db_path), vault_id=vault_id)
        cands = rep["contradiction_candidates"]
        task = ("Judge each contradiction candidate below. Deterministic candidates "
                "(JSON):\n" + json.dumps(cands, ensure_ascii=False, indent=2))
        return task, {}

    if role == "curator":
        drift = _links.index_drift(Path(db_path), vault_id)
        task = ("Propose a re-ordered index.md. Deterministic index_drift report "
                "(JSON):\n" + json.dumps(drift, ensure_ascii=False, indent=2))
        return task, {}

    # fact-checker / terminology-manager / wiki-librarian: source-driven
    src = source or {}
    content, meta = personas.resolve_input(
        text=src.get("text"),
        file_path=Path(src["file"]) if src.get("file") else None,
        vault_relpath=src.get("vault_relpath"),
        db_path=Path(db_path),
        vault_id=vault_id,
    )
    task = f"Apply your protocol to the following source:\n\n{content}"
    return task, meta


def _dispatch(persona_body: str, task_prompt: str, *, backend: str, model: str,
              override_cli_path: str | None, timeout: int = 600) -> str:
    argv = backends.build_invocation(
        backend, persona_body=persona_body, task_prompt=task_prompt,
        model=model, skip_permissions=True, override_cli_path=override_cli_path,
    )
    try:
        cp = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise RunError(f"{backend} dispatch timed out after {timeout}s") from exc
    if cp.returncode != 0:
        raise RunError(f"{backend} dispatch failed (rc={cp.returncode}): "
                       f"{(cp.stderr or '').strip()[:200]}")
    return cp.stdout


# ---------------------------------------------------------------------------
# Filing helpers
# ---------------------------------------------------------------------------

def _stage_proposal(target: Path, content: str) -> Path:
    """Write content to a .proposed.md sidecar; never touch target. Return proposal path."""
    proposal = target.with_name(target.name + ".proposed.md")
    proposal.write_text(content, encoding="utf-8")
    return proposal


def apply_proposal(proposal: Path) -> Path:
    """Move a .proposed.md onto its target. Raises RunError if not a proposal file."""
    if not proposal.name.endswith(".proposed.md"):
        raise RunError(f"not a proposal file: {proposal}")
    target = proposal.with_name(proposal.name[: -len(".proposed.md")])
    target.write_text(proposal.read_text(encoding="utf-8"), encoding="utf-8")
    proposal.unlink()
    return target


# Roles whose output rewrites an existing page — never auto-applied.
_MUTATION_ROLES: frozenset[str] = frozenset({"curator"})


def run(
    role: str,
    *,
    db_path,
    vault_id,
    source=None,
    backend=None,
    apply=False,
    override_cli_path=None,
) -> int:
    """Full pipeline: gather → pick backend → dispatch → file. Returns exit code."""
    override_cli_path = override_cli_path or _override_path()
    try:
        persona = personas.load_persona(role)
        task, meta = _gather_inputs(role, db_path=db_path, vault_id=vault_id, source=source)
        chosen = _pick_backend(
            backends.detect_available(override_path=override_cli_path), backend
        )
        model = _resolve_model(persona.get("model_hint", ""), chosen)
        out = _dispatch(
            persona["body"], task,
            backend=chosen, model=model,
            override_cli_path=override_cli_path,
        )
    except RunError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if role in _MUTATION_ROLES:
        target = registry.get_vault_root(db_path, vault_id) / "wiki" / "index.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        prop = _stage_proposal(target, out)
        print(
            f"proposal staged: {prop}\n"
            f"Review, then `omw persona-run {role} --apply` to apply."
        )
        return 0

    # Non-mutation: resolve output path and file directly.
    output_kind = persona.get("output_kind", "stdout")
    target_path: Path | None = None
    if output_kind != "stdout":
        # Prefer explicit output_suffix from persona frontmatter; fall back to
        # role name with hyphens stripped (e.g. "fact-checker" → "factchecker").
        suffix = persona.get("output_suffix") or role.replace("-", "")
        try:
            target_path = personas.resolve_output_path(
                persona=persona,
                source_meta=meta,
                db_path=Path(db_path),
                vault_id=vault_id,
                suffix=suffix,
            )
        except personas.PersonaError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

    written = personas.write_output(
        persona=persona,
        target_path=target_path,
        content=out,
        source_meta=meta,
    )
    print(json.dumps(
        {"role": role, "backend": chosen, "filed": str(written) if written else None},
        ensure_ascii=False,
    ))
    return 0
