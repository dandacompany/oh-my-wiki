"""Pure builders for translating an omw persona dispatch into a Hermes
`kanban create` invocation. No subprocess here (see scripts/runners/hermes_kanban.py).

The card body carries THIS run's specifics (which persona + its system-prompt
body + the deterministic input); the generic worker-behaviour skill is force-
loaded per card via --skill, so no per-persona profile or skill is needed.
"""
from __future__ import annotations

from scripts import persona_run, personas

WORKER_SKILL = "omw-kanban-worker"


def build_card_body(role, *, db_path, vault_id, source=None) -> str:
    """Persona system-prompt body + deterministic input, as one card body."""
    persona = personas.load_persona(role)
    task, _meta = persona_run._gather_inputs(
        role, db_path=db_path, vault_id=vault_id, source=source
    )
    return (
        f"# omw persona: {role}\n\n"
        "You are running as an omw kanban worker. Read the persona spec below as "
        "your system prompt, then apply it to the deterministic input.\n\n"
        "## Persona spec\n\n"
        f"{persona['body']}\n\n"
        "---\n\n"
        "## Deterministic input\n\n"
        f"{task}\n"
    )


def build_create_argv(cli, *, title, body, assignee, skills, parents=(), model="") -> list[str]:
    """argv for `hermes kanban create` (no shell). --json for parseable output;
    no --initial-status (default 'running' yields ready, or todo when gated by
    incomplete parents)."""
    argv = [cli, "kanban", "create", title,
            "--assignee", assignee, "--body", body, "--json"]
    for s in skills:
        argv += ["--skill", s]
    for p in parents:
        argv += ["--parent", p]
    if model:
        argv += ["--model", model]
    return argv
