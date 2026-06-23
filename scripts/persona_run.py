"""Dispatch a persona as an isolated one-shot subagent via backends.py.

Host-universal (claude/codex/gemini/opencode): loads the portable persona spec,
gathers deterministic inputs, spawns a one-shot agent with the persona body as
system prompt, and files the result. Hermetically testable via
OMW_BACKEND_OVERRIDE_PATH + tests/fakes/.
"""
from __future__ import annotations

import os
import subprocess

from scripts import backends


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
