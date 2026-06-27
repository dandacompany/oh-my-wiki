"""Host runner — thin passthrough to omw's existing in-session dispatch.

This is the universal default: every non-Hermes platform uses its own
subagent system through the host AI agent, which calls these directly.
"""
from __future__ import annotations

from scripts import persona_bundle, persona_fanout, persona_run


class HostRunner:
    name = "host"

    def run_one(self, role, *, db_path, vault_id, source, backend=None,
                apply=False, override_cli_path=None) -> int:
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
