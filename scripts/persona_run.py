"""Dispatch a persona as an isolated one-shot subagent via backends.py.

Host-universal (claude/codex/gemini/opencode): loads the portable persona spec,
gathers deterministic inputs, spawns a one-shot agent with the persona body as
system prompt, and files the result. Hermetically testable via
OMW_BACKEND_OVERRIDE_PATH + tests/fakes/.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from scripts import backends
from scripts import host_detect
from scripts import links as _links
from scripts import personas
from scripts import registry
from scripts import wiki_lint as _wiki_lint


class RunError(Exception):
    pass


# Deterministic manual fallback per role — surfaced when no usable backend can
# run the persona, so the user gets a concrete next step instead of a dead end.
_FALLBACK_HINT: dict[str, str] = {
    "wiki-librarian": "omw links suggest / omw connections / omw lint",
    "wiki-auditor": "omw lint / omw report / omw maint status",
    "curator": "omw lint / omw connections",
    "consistency-checker": "omw lint (contradiction_candidates)",
    "terminology-manager": "omw fields <page> / omw list --type entity",
    "fact-checker": "omw search <claim> / omw context <claim>",
}


def _fallback_hint(role: str) -> str:
    return _FALLBACK_HINT.get(role, "omw lint / omw status")


# Roles that compute their own deterministic input (lint/drift reports) and need
# no source document. Single source of truth for persona_bundle's --page check;
# matches _gather_inputs's self-gathering branches.
_SELF_GATHERING_ROLES = frozenset({"consistency-checker", "curator",
                                    "wiki-auditor", "wiki-librarian"})


def needs_source(role: str) -> bool:
    """True if the persona requires a source document (page/file/text) to run."""
    return role not in _SELF_GATHERING_ROLES


def _filing_instructions(persona: dict, role: str) -> str:
    """How the host agent should handle the subagent's output, per the persona's
    access/output contract."""
    access = persona.get("access", "write")
    output_kind = persona.get("output_kind", "stdout")
    if access == "propose":
        return (f"This persona has access=**propose** — do NOT write its output into "
                f"any vault page directly. Stage it as a `.proposed.md` next to the "
                f"target, show the user the diff, and only on their confirmation run "
                f"`omw persona-run {role} --apply <proposal>`.")
    if output_kind == "stdout":
        return ("This persona is **read-only / stdout** — present the subagent's "
                "output to the user as the answer; do not write any vault files.")
    return (f"output_kind=**{output_kind}** — file the subagent's output per the "
            f"persona's contract (sibling report / in-place as configured), never "
            f"overwriting a page silently.")


def build_host_card(role: str, *, host: str, db_path, vault_id, source=None) -> str:
    """Host-native dispatch procedure card.

    When omw runs *inside* a known host agent, instead of shelling out to an
    external CLI it returns this card telling the calling host to run the persona
    as its OWN subagent (its Task/Agent tool) with the persona body as the system
    prompt and the deterministic `_gather_inputs` payload as the task. The caller
    prints it; the host reads + executes it. Mirrors the hermes-kanban runner's
    card pattern, generalized to any host."""
    persona = personas.load_persona(role)
    task, _meta = _gather_inputs(role, db_path=db_path, vault_id=vault_id, source=source)
    access = persona.get("access", "write")
    output_kind = persona.get("output_kind", "stdout")
    return (
        f'<omw-persona-card host="{host}" role="{role}" '
        f'access="{access}" output="{output_kind}">\n\n'
        f"# Host-native persona dispatch — {role}\n\n"
        f"omw detected it is running **inside the `{host}` host**, so it is handing "
        f"this persona to *your own* subagent mechanism (e.g. your Task/Agent tool) "
        f"rather than shelling out to a sibling agent CLI.\n\n"
        f"**Do this now:** spawn one subagent with the *Persona spec* below as its "
        f"system prompt and the *Deterministic input* as its task, then handle its "
        f"result per *Filing*.\n\n"
        f"## Persona spec (system prompt)\n\n{persona['body']}\n\n"
        f"---\n\n## Deterministic input (task)\n\n{task}\n\n"
        f"---\n\n## Filing\n\n{_filing_instructions(persona, role)}\n\n"
        f"## If you cannot dispatch a subagent\n\n"
        f"Run the deterministic fallback instead: {_fallback_hint(role)}\n"
        f"</omw-persona-card>\n"
    )


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
    - wiki-auditor: embeds lint + broken_links health signal JSON (no --page needed).
    - wiki-librarian: embeds orphans + graph + broken_links link graph JSON (no --page needed).
    - fact-checker / terminology-manager: calls personas.resolve_input with the provided
      source dict and embeds content in task_prompt.
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

    if role == "wiki-auditor":
        data = {
            "lint": _wiki_lint.check(Path(db_path), vault_id=vault_id),
            "broken_links": _links.broken_links(Path(db_path), vault_id),
        }
        task = ("Diagnose what's sick in this vault and emit a prioritized triage. "
                "Deterministic health signal (JSON):\n"
                + json.dumps(data, ensure_ascii=False, indent=2))
        return task, {}

    if role == "wiki-librarian":
        data = {
            "orphans": _links.orphans(Path(db_path), vault_id),
            "graph": _links.graph(Path(db_path), vault_id),
            "broken_links": _links.broken_links(Path(db_path), vault_id),
        }
        task = ("Propose structure fixes (missing cross-links, orphan resolution, "
                "merge/split candidates). Deterministic link graph (JSON):\n"
                + json.dumps(data, ensure_ascii=False, indent=2))
        return task, {}

    # fact-checker / terminology-manager: source-driven
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


_MODEL_UNSUPPORTED_RE = re.compile(r"model[^\n]*is not supported", re.IGNORECASE)


def _model_unsupported(stdout: str, stderr: str) -> bool:
    """True if the backend rejected the requested model (retry without --model)."""
    blob = f"{stdout or ''}\n{stderr or ''}"
    return bool(_MODEL_UNSUPPORTED_RE.search(blob))


def _dispatch(persona_body: str, task_prompt: str, *, backend: str, model: str,
              override_cli_path: str | None, timeout: int = 600) -> str:
    def _run(m: str):
        argv = backends.build_invocation(
            backend, persona_body=persona_body, task_prompt=task_prompt,
            model=m, skip_permissions=True, override_cli_path=override_cli_path,
        )
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                              stdin=subprocess.DEVNULL)
    try:
        cp = _run(model)
        # codex (ChatGPT-account) rejects catalog model ids with "is not supported";
        # retry once without --model so codex uses the account default.
        if (cp.returncode != 0 and backend == "codex" and model
                and _model_unsupported(cp.stdout, cp.stderr)):
            cp = _run("")
    except subprocess.TimeoutExpired as exc:
        raise RunError(f"{backend} dispatch timed out after {timeout}s") from exc
    if cp.returncode != 0:
        raise RunError(f"{backend} dispatch failed (rc={cp.returncode}): "
                       f"{(cp.stderr or '').strip()[:200]}")
    # rc==0 but no usable output is a *failure*, not a silent success — some
    # backends (e.g. a fire-and-forget codex exec) can exit 0 having produced
    # nothing. Catch it here so the caller never files/echoes an empty result.
    if not (cp.stdout or "").strip():
        raise RunError(f"{backend} dispatch returned empty output "
                       f"(rc=0); the backend ran but produced nothing")
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


def _propose_target(role, persona, source_meta, db_path, vault_id) -> Path:
    """Resolve the content page a `propose` persona stages onto.

    curator rewrites the vault index (its output_kind is stdout, so the target
    is fixed, not derivable); any other propose persona resolves its target
    from output_kind via personas.resolve_output_path.
    """
    if role == "curator":
        return registry.get_vault_root(db_path, vault_id) / "wiki" / "index.md"
    suffix = persona.get("output_suffix") or role.replace("-", "")
    target = personas.resolve_output_path(
        persona=persona, source_meta=source_meta,
        db_path=Path(db_path), vault_id=vault_id, suffix=suffix,
    )
    if target is None:
        raise RunError(
            f"persona {role!r} has access=propose but output_kind "
            f"{persona.get('output_kind')!r} yields no content target"
        )
    return target


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
        # If omw is running *inside* a known host but that host's CLI isn't usable
        # as an external backend, dispatch silently slides to a sibling CLI — the
        # root cause of "personas look broken in <host>". Surface it loudly.
        host = host_detect.current_host()
        if backend is None and host and host != chosen and host in backends.BACKENDS:
            print(f"warning: running inside the '{host}' host, but its CLI isn't usable "
                  f"as an external backend (not installed/authed) — falling back to "
                  f"'{chosen}'. Host-native dispatch is not implemented yet; if the "
                  f"result looks empty, run deterministically: {_fallback_hint(role)}",
                  file=sys.stderr)
        model = _resolve_model(persona.get("model_hint", ""), chosen)
        out = _dispatch(
            persona["body"], task,
            backend=chosen, model=model,
            override_cli_path=override_cli_path,
        )
    except RunError as exc:
        print(f"error: {exc}\n  fallback (run deterministically): {_fallback_hint(role)}",
              file=sys.stderr)
        return 1

    if persona["access"] == "propose":
        target = _propose_target(role, persona, meta, db_path, vault_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        prop = _stage_proposal(target, out)
        print(
            f"proposal staged: {prop}\n"
            f"Review, then `omw persona-run {role} --apply {prop}` to apply."
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
    if output_kind == "stdout":
        # A read-only/stdout persona's *result is its stdout* (e.g. wiki-librarian
        # "proposes on stdout"). Emit the body so it isn't silently dropped, and
        # keep the machine-readable receipt on stderr — `filed:null` here means
        # "stdout persona, body printed", no longer ambiguous with "nothing ran"
        # (empty output already failed loud in _dispatch).
        sys.stdout.write(out if out.endswith("\n") else out + "\n")
        print(json.dumps(
            {"role": role, "backend": chosen, "filed": None, "kind": "stdout"},
            ensure_ascii=False,
        ), file=sys.stderr)
    else:
        print(json.dumps(
            {"role": role, "backend": chosen, "filed": str(written) if written else None},
            ensure_ascii=False,
        ))
    return 0
