"""Detect whether omw is running inside a Hermes agent session, and resolve
the kanban card assignee — without forcing the user to create any profile.

The Hermes-only runners (hermes-kanban / hermes-delegate) gate on
in_hermes_session(); everything here is pure + hermetically testable
(env vars + a profiles dir root override).
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path


class AmbiguousProfile(Exception):
    """resolve_assignee could not pick a single profile; caller must ask."""

    def __init__(self, choices: list[str]):
        self.choices = list(choices)
        super().__init__(
            "multiple Hermes profiles found; pass --assignee "
            f"(choices: {', '.join(self.choices) or '(none)'})"
        )


def in_hermes_session() -> bool:
    """True iff omw is running under a Hermes agent session."""
    return bool(os.environ.get("HERMES_SESSION_ID") or os.environ.get("HERMES_PROFILE"))


def hermes_cli(override: str | None = None) -> str | None:
    """Path to the hermes CLI (test override wins, else PATH lookup)."""
    return override or shutil.which("hermes")


def hermes_home() -> Path:
    """Hermes home dir (HERMES_HOME env or ~/.hermes)."""
    return Path(os.environ.get("HERMES_HOME") or (Path.home() / ".hermes"))


def list_profiles(*, home: Path | None = None) -> list[str]:
    """Profile names under <home>/profiles that look like real profiles."""
    root = (home or hermes_home()) / "profiles"
    if not root.is_dir():
        return []
    names = []
    for child in sorted(root.iterdir()):
        if child.is_dir() and (
            (child / "config.yaml").exists() or (child / "SOUL.md").exists()
        ):
            names.append(child.name)
    return names


def resolve_assignee(explicit: str | None = None, *, home: Path | None = None) -> str:
    """Resolve the kanban card assignee: explicit > current session profile >
    the sole profile on disk. Raise AmbiguousProfile when 0 or 2+ remain."""
    if explicit:
        return explicit
    env = os.environ.get("HERMES_PROFILE")
    if env:
        return env
    profs = list_profiles(home=home)
    if len(profs) == 1:
        return profs[0]
    raise AmbiguousProfile(profs)
