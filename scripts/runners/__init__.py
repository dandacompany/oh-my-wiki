"""Runner seam: choose WHERE a persona dispatch executes.

`host` (default, universal): the host AI agent orchestrates via omw's own
one-shot dispatch (current behavior on any platform).
`hermes-kanban` (Hermes session only): translate the request into
`hermes kanban create` cards. Hard-gated by hermes_detect.in_hermes_session().
"""
from __future__ import annotations

from scripts import hermes_detect


class RunnerUnavailable(Exception):
    """Requested runner cannot run in this environment (e.g. not a Hermes session)."""


def available_runners() -> list[str]:
    names = ["host"]
    if hermes_detect.in_hermes_session():
        names.append("hermes-kanban")
    return names


def resolve_runner(name: str | None):
    if name in (None, "host"):
        from scripts.runners.host import HostRunner
        return HostRunner()
    if name == "hermes-kanban":
        if not hermes_detect.in_hermes_session():
            raise RunnerUnavailable(
                "hermes-kanban runner requires a Hermes agent session; "
                "use --runner host"
            )
        from scripts.runners.hermes_kanban import HermesKanbanRunner
        return HermesKanbanRunner()
    raise ValueError(f"unknown runner: {name!r}")
