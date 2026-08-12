"""Optional external evidence adapters for session knowledge candidates."""
from __future__ import annotations

import json
from pathlib import Path

from scripts import session_capture

_MAX_OBSERVATIONS = 20
_MAX_EXPORT_BYTES = 5_000_000


def _text(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("content", "text", "summary", "observation"):
            if isinstance(value.get(key), str):
                return value[key]
    return ""


def load_agentmemory_export(path: str | Path) -> list[str]:
    """Read summary + important observations from an explicit AgentMemory export.

    This adapter intentionally does not inspect AgentMemory's database or guess an
    undocumented REST query shape. The caller supplies JSON exported through the
    documented ``GET /agentmemory/export`` surface.
    """
    try:
        source = Path(path)
        if source.stat().st_size > _MAX_EXPORT_BYTES:
            return []
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, TypeError):
        return []
    out: list[str] = []
    roots = payload if isinstance(payload, list) else [payload]
    for root in roots:
        if not isinstance(root, dict):
            continue
        for summary in (
            root.get("summary"),
            (root.get("session") or {}).get("summary")
            if isinstance(root.get("session"), dict) else None,
        ):
            clean = session_capture.sanitize_text(_text(summary), limit=4_000)
            if clean and "[REDACTED]" not in clean and clean not in out:
                out.append(clean)
        observations = root.get("observations") or root.get("important_observations") or []
        if not isinstance(observations, list):
            continue
        for observation in observations:
            if isinstance(observation, dict):
                important = observation.get("important") is True
                try:
                    importance = float(observation.get("importance") or 0)
                except (TypeError, ValueError):
                    importance = 0
                if not important and importance < 0.7:
                    continue
            clean = session_capture.sanitize_text(_text(observation), limit=2_000)
            if clean and "[REDACTED]" not in clean and clean not in out:
                out.append(clean)
            if len(out) >= _MAX_OBSERVATIONS:
                return out
    return out[:_MAX_OBSERVATIONS]
