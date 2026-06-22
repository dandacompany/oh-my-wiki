"""Backend detection, model catalog, and CLI invocation builder for OMW dispatch.

Supports 4 backends: claude / codex / gemini / opencode.
Model IDs live in backends/<name>.json — never hardcoded here.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from scripts import paths

# ---------------------------------------------------------------------------
# Base dir for bundled backends/ data (repo root in dev, scripts/_bundle in a wheel)
# ---------------------------------------------------------------------------
_REPO_ROOT = paths.bundled_root()

# ---------------------------------------------------------------------------
# BACKENDS table
# ---------------------------------------------------------------------------
BACKENDS: dict[str, dict[str, Any]] = {
    "claude": {
        "cli_name": "claude",
        "detect_cmd": ["claude", "--version"],
        "auth_check_cmd": ["claude", "config", "get", "oauthAccount"],
        "skip_perm_flag": "--dangerously-skip-permissions",
        "non_interactive_flag": "-p",
        "system_prompt_flag": "--append-system-prompt",
        "model_flag": "--model",
        "model_catalog_path": "backends/claude.json",
    },
    "codex": {
        "cli_name": "codex",
        "detect_cmd": ["codex", "--version"],
        "auth_check_cmd": ["codex", "auth", "status"],
        "skip_perm_flag": "--yolo",
        "non_interactive_flag": "exec",
        "system_prompt_flag": "--instructions",
        "model_flag": "--model",
        "model_catalog_path": "backends/codex.json",
    },
    "gemini": {
        "cli_name": "gemini",
        "detect_cmd": ["gemini", "--version"],
        "auth_check_cmd": None,  # auth is implicit via gcloud
        "skip_perm_flag": None,  # no equivalent currently
        "non_interactive_flag": "-p",
        "system_prompt_flag": "--system",
        "model_flag": "--model",
        "model_catalog_path": "backends/gemini.json",
    },
    "opencode": {
        "cli_name": "opencode",
        "detect_cmd": ["opencode", "--version"],
        "auth_check_cmd": None,
        "skip_perm_flag": None,  # TBD per CLI's current state
        "non_interactive_flag": "run",
        "system_prompt_flag": "--system",
        "model_flag": "--model",
        "model_catalog_path": "backends/opencode.json",
    },
}


class BackendError(Exception):
    """Raised for missing/unauthed backend or bad invocation arguments."""


# ---------------------------------------------------------------------------
# detect_available
# ---------------------------------------------------------------------------

def detect_available(
    *,
    override_path: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Run each backend's detect_cmd. Return {name: {installed, version, authed}}.

    Args:
        override_path: If set (e.g. from OMW_BACKEND_OVERRIDE_PATH env var),
            prepend this directory to PATH so fake backends are found first.
            Used in tests with tests/fakes/.
    """
    import os

    env = None
    if override_path is not None:
        env = os.environ.copy()
        env["PATH"] = f"{override_path}:{env.get('PATH', '')}"

    result: dict[str, dict[str, Any]] = {}
    for name, spec in BACKENDS.items():
        info: dict[str, Any] = {"installed": False, "version": "", "authed": None}
        try:
            cp = subprocess.run(
                spec["detect_cmd"],
                capture_output=True,
                text=True,
                timeout=5,
                env=env,
            )
            if cp.returncode == 0:
                info["installed"] = True
                info["version"] = (cp.stdout or cp.stderr or "").strip()
            # authed check is advisory; skip if no auth_check_cmd
            if info["installed"] and spec.get("auth_check_cmd"):
                try:
                    acp = subprocess.run(
                        spec["auth_check_cmd"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                        env=env,
                    )
                    info["authed"] = acp.returncode == 0
                except (OSError, subprocess.TimeoutExpired):
                    info["authed"] = None
        except (OSError, subprocess.TimeoutExpired):
            pass
        result[name] = info
    return result


# ---------------------------------------------------------------------------
# list_models
# ---------------------------------------------------------------------------

def list_models(
    backend: str,
    *,
    repo_root: Path | None = None,
    hint_filter: str | None = None,
) -> list[dict[str, Any]]:
    """Read backends/<name>.json model catalog.

    Returns list of {id, hint, description} dicts, optionally filtered by hint.
    Model IDs are sourced from the JSON file; never hardcoded in Python.

    Args:
        backend: one of the keys in BACKENDS.
        repo_root: override repo root (useful in tests with tmp catalogs).
        hint_filter: if given, return only models with this hint value.
                     Must be one of: fast, standard, most_capable.
    """
    import json as _json

    if backend not in BACKENDS:
        raise BackendError(f"unknown backend: {backend!r}")

    root = repo_root if repo_root is not None else _REPO_ROOT
    catalog_rel = BACKENDS[backend]["model_catalog_path"]
    catalog_path = root / catalog_rel

    if not catalog_path.exists():
        raise BackendError(
            f"model catalog not found for backend {backend!r}: {catalog_path}"
        )

    with catalog_path.open(encoding="utf-8") as fh:
        models: list[dict[str, Any]] = _json.load(fh)

    if hint_filter is not None:
        models = [m for m in models if m.get("hint") == hint_filter]

    return models


# ---------------------------------------------------------------------------
# build_invocation
# ---------------------------------------------------------------------------

def build_invocation(
    backend: str,
    *,
    persona_body: str,
    task_prompt: str,
    model: str,
    skip_permissions: bool,
    extra_args: list[str] | None = None,
    override_cli_path: str | None = None,
) -> list[str]:
    """Build the argv list for spawning a backend with a persona/task.

    The resulting argv is suitable for passing directly to subprocess or tmux.
    No shell quoting is done here — callers must handle that for tmux pane
    commands (see tmux_runtime.spawn_worker).

    Backend-specific argv shapes:
      claude: claude [--dangerously-skip-permissions] --model M
              --append-system-prompt BODY -p TASK [extra]
      codex:  codex exec [--yolo] --model M --instructions BODY TASK [extra]
      gemini: gemini [--model M] --system BODY -p TASK [extra]
      opencode: opencode run --model M --system BODY TASK [extra]

    Args:
        override_cli_path: If set (e.g. from OMW_BACKEND_OVERRIDE_PATH env var),
            the CLI binary becomes <override_cli_path>/<backend>-fake.sh
            (without .sh if a symlink without extension exists).
            Used in tests to substitute fake backends.
    """
    if backend not in BACKENDS:
        raise BackendError(f"unknown backend: {backend!r}")

    spec = BACKENDS[backend]
    cli = spec["cli_name"]
    if override_cli_path is not None:
        # Prefer the bare symlink name (e.g. tests/fakes/claude) if it exists,
        # otherwise fall back to the .sh variant
        bare = str(Path(override_cli_path) / backend)
        sh_variant = str(Path(override_cli_path) / f"{backend}-fake.sh")
        cli = bare if Path(bare).exists() else sh_variant
    argv: list[str] = [cli]

    # codex uses a subcommand ("exec") as its non-interactive mode
    ni_flag = spec["non_interactive_flag"]
    if ni_flag and ni_flag not in ("-p",):
        # it's a subcommand word, not a flag
        argv.append(ni_flag)

    # skip-permissions flag (only if backend supports it and user opted in)
    if skip_permissions and spec.get("skip_perm_flag"):
        argv.append(spec["skip_perm_flag"])

    # model
    argv += [spec["model_flag"], model]

    # system / persona body
    argv += [spec["system_prompt_flag"], persona_body]

    # task prompt
    # For backends where non_interactive_flag == "-p" (claude, gemini):
    #   the task prompt is passed as -p TASK
    # For codex/opencode: task prompt is a positional after flags
    if ni_flag == "-p":
        argv += ["-p", task_prompt]
    else:
        argv.append(task_prompt)

    # extra args (e.g. --output-format stream-json)
    if extra_args:
        argv.extend(extra_args)

    return argv
