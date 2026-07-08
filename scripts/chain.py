"""Deterministic lifecycle chain — the static op→next-op map plus a state-aware
resolver. Hybrid: the static successor is offered only when `omw next`'s vault-state
signals still endorse it, so pointless steps (lint with 0 issues, synthesis with no
clusters) are skipped. Pure rules — no LLM, no randomness; same (op, signals) → same
result. The oh-my-wiki skill runs `omw next --after <op>` after a unit of work and
offers the survivor via the host's native ask tool (safe default: stop).
"""
from __future__ import annotations

# Static successor edges — only ops that participate in the knowledge-building
# pipeline. An op absent here (status, version, …) has no successor → nothing offered.
CHAIN: dict[str, tuple[str, ...]] = {
    "search": ("ingest",),
    "fetch": ("ingest",),
    "autoresearch": ("synthesis",),
    "ingest": ("summary",),
    "summary": ("synthesis",),
    "synthesis": ("lint",),
    "lint": ("review",),
}


def _endorsed(op: str, sig: dict) -> bool:
    """Does the vault state still justify offering this successor? (reuses
    nextstep.signals shape). Ops with no gate here are always offered."""
    sig = sig or {}
    if op == "synthesis":
        return sig.get("clusters", 0) > 0
    if op == "lint":
        return sig.get("lint_issues", 0) > 0
    if op == "review":
        return (sig.get("stale", 0) + sig.get("expired", 0)) > 0
    return True


def next_after(op: str, sig: dict | None = None) -> list[dict]:
    """Successor ops of `op` that the current state still endorses, as
    [{op, command, reason, phase}]. Empty when `op` has no successor or none survive."""
    from scripts import ops_registry
    out: list[dict] = []
    for succ in CHAIN.get(op, ()):  # noqa: SIM118 — dict.get on a plain map
        if not _endorsed(succ, sig or {}):
            continue
        spec = ops_registry.get(succ)
        out.append({
            "op": succ,
            "command": f"omw {succ}" if spec else succ,
            "reason": f"next step after {op}",
            "phase": spec.phase if spec else None,
        })
    return out
