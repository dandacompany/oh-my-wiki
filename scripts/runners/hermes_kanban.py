"""Hermes-kanban runner: translate an omw persona dispatch into
`hermes kanban create` cards. Deterministic — enqueues cards and returns
their ids; the Hermes dispatcher runs the worker sessions asynchronously.
"""
from __future__ import annotations

import json
import subprocess

from scripts import hermes_detect, hermes_kanban, persona_bundle, persona_fanout


class KanbanError(Exception):
    """A `hermes kanban create` call failed or returned unparseable output."""


class HermesKanbanRunner:
    name = "hermes-kanban"

    def _cli(self, override_cli_path):
        cli = hermes_detect.hermes_cli(override_cli_path)
        if not cli:
            raise KanbanError("hermes CLI not found on PATH")
        return cli

    def _create_card(self, cli, *, title, body, assignee, parents=()) -> str:
        argv = hermes_kanban.build_create_argv(
            cli, title=title, body=body, assignee=assignee,
            skills=[hermes_kanban.WORKER_SKILL], parents=tuple(parents),
        )
        cp = subprocess.run(
            argv, capture_output=True, text=True,
            stdin=subprocess.DEVNULL, timeout=60,
        )
        if cp.returncode != 0:
            raise KanbanError(
                f"kanban create failed (rc={cp.returncode}): "
                f"{(cp.stderr or '').strip()[:200]}"
            )
        try:
            return json.loads(cp.stdout)["id"]
        except (ValueError, KeyError) as exc:
            raise KanbanError(
                f"could not parse kanban create output: {cp.stdout[:200]!r}"
            ) from exc

    def run_one(
        self, role, *, db_path, vault_id, source, backend=None,
        apply=False, override_cli_path=None, assignee=None,
    ) -> dict:
        cli = self._cli(override_cli_path)
        who = hermes_detect.resolve_assignee(assignee)
        body = hermes_kanban.build_card_body(
            role, db_path=db_path, vault_id=vault_id, source=source
        )
        rel = (source or {}).get("vault_relpath") or (source or {}).get("file")
        title = f"{role}: {rel}" if rel else role
        cid = self._create_card(cli, title=title, body=body, assignee=who)
        return {"cards": [cid], "board": None}

    def resolve_fanout(
        self, role, *, db_path, vault_id, pages=None, tag=None,
        type=None, status=None, layer=None, visibility=None,
        backend=None, assignee=None, override_cli_path=None,
    ) -> dict:
        # NOTE: override_cli_path added here (corrected from thinko in brief)
        cli = self._cli(override_cli_path)
        who = hermes_detect.resolve_assignee(assignee)
        resolved = persona_fanout.resolve(
            role, db_path=db_path, vault_id=vault_id, pages=pages, tag=tag,
            type=type, status=status, layer=layer, visibility=visibility,
            backend=backend,
        )
        cards = []
        for rel in resolved["pages"]:
            body = hermes_kanban.build_card_body(
                role, db_path=db_path, vault_id=vault_id,
                source={"vault_relpath": rel},
            )
            cards.append(
                self._create_card(cli, title=f"{role}: {rel}", body=body, assignee=who)
            )
        return {"role": role, "count": len(cards), "cards": cards}

    def run_bundle(
        self, name, *, db_path, vault_id, page=None, backend=None,
        override_cli_path=None, assignee=None,
    ) -> dict:
        cli = self._cli(override_cli_path)
        who = hermes_detect.resolve_assignee(assignee)
        bundle = persona_bundle.load_bundle(name)
        cards = []
        prev = None
        for role in bundle["roles"]:
            from scripts import persona_run

            src = (
                {"vault_relpath": page}
                if (page and persona_run.needs_source(role))
                else None
            )
            body = hermes_kanban.build_card_body(
                role, db_path=db_path, vault_id=vault_id, source=src
            )
            parents = (prev,) if prev else ()
            cid = self._create_card(
                cli, title=f"{name}/{role}", body=body, assignee=who,
                parents=parents,
            )
            cards.append(cid)
            prev = cid
        return {"bundle": name, "cards": cards}
