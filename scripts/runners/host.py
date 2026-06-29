"""Host runner — the universal default.

Two modes, chosen automatically:
  - **host-native** (preferred): when omw is running *inside* a known host agent
    (Claude Code / Codex / Gemini / OpenCode / Hermes) and no explicit `--backend`
    was given, emit a procedure card telling the calling host to run the persona
    as its OWN subagent — no external CLI spawn. This is the fix for "personas
    look broken in <host>": the host's own Task/Agent tool does the work.
  - **external dispatch**: when no host is detected, or the user pinned a
    `--backend`, fall back to omw's one-shot external-CLI dispatch (prior
    behavior).
"""
from __future__ import annotations

import sys

from scripts import host_detect, persona_bundle, persona_fanout, persona_run


class HostRunner:
    name = "host"

    def run_one(self, role, *, db_path, vault_id, source, backend=None,
                apply=False, override_cli_path=None) -> int:
        # Host-native: inside a known host, with no pinned backend and not an
        # --apply call, hand the task to the host's own subagent via a card.
        if backend is None and not apply:
            host = host_detect.current_host()
            if host:
                try:
                    card = persona_run.build_host_card(
                        role, host=host, db_path=db_path, vault_id=vault_id,
                        source=source,
                    )
                except persona_run.RunError as exc:
                    print(f"error: {exc}\n  fallback (run deterministically): "
                          f"{persona_run._fallback_hint(role)}", file=sys.stderr)
                    return 1
                print(card)
                return 0
        return persona_run.run(
            role, db_path=db_path, vault_id=vault_id, source=source,
            backend=backend, apply=apply, override_cli_path=override_cli_path,
        )

    def resolve_fanout(self, role, *, db_path, vault_id, pages=None, tag=None,
                       type=None, status=None, layer=None, visibility=None,
                       backend=None) -> dict:
        return persona_fanout.resolve(
            role, db_path=db_path, vault_id=vault_id, pages=pages, tag=tag,
            type=type, status=status, layer=layer, visibility=visibility,
            backend=backend,
        )

    def run_bundle(self, name, *, db_path, vault_id, page=None, backend=None,
                   override_cli_path=None) -> int:
        return persona_bundle.run_bundle(
            name, db_path=db_path, vault_id=vault_id, page=page,
            backend=backend, override_cli_path=override_cli_path,
        )
