"""Tests for scripts.backends — backend detection, model catalog, invocation builder."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts import backends


# ---------------------------------------------------------------------------
# BACKENDS table structure
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", ["claude", "codex", "gemini", "opencode"])
def test_backends_table_has_required_keys(name):
    b = backends.BACKENDS[name]
    required = {
        "cli_name", "detect_cmd", "skip_perm_flag",
        "non_interactive_flag", "system_prompt_flag",
        "model_flag", "model_catalog_path",
    }
    assert required <= set(b.keys()), f"{name} missing keys: {required - set(b.keys())}"


@pytest.mark.parametrize("name", ["claude", "codex", "gemini", "opencode"])
def test_backends_detect_cmd_is_list(name):
    assert isinstance(backends.BACKENDS[name]["detect_cmd"], list)
    assert len(backends.BACKENDS[name]["detect_cmd"]) >= 1


# ---------------------------------------------------------------------------
# detect_available — mocking subprocess
# ---------------------------------------------------------------------------

def _make_completed(returncode=0, stdout="1.0.0", stderr=""):
    cp = MagicMock()
    cp.returncode = returncode
    cp.stdout = stdout
    cp.stderr = stderr
    return cp


def test_detect_available_all_installed(monkeypatch):
    monkeypatch.setattr(
        backends.subprocess, "run",
        lambda cmd, **kw: _make_completed(returncode=0, stdout="2.0.0"),
    )
    result = backends.detect_available()
    assert set(result.keys()) == {"claude", "codex", "gemini", "opencode"}
    for name, info in result.items():
        assert info["installed"] is True, f"{name} should be installed"


def test_detect_available_none_installed(monkeypatch):
    monkeypatch.setattr(
        backends.subprocess, "run",
        lambda cmd, **kw: _make_completed(returncode=1, stdout="", stderr="not found"),
    )
    result = backends.detect_available()
    for name, info in result.items():
        assert info["installed"] is False, f"{name} should not be installed"


def test_detect_available_mixed(monkeypatch):
    installed = {"claude", "gemini"}

    def fake_run(cmd, **kw):
        cli = cmd[0]
        rc = 0 if any(cli == backends.BACKENDS[n]["cli_name"] for n in installed) else 1
        return _make_completed(returncode=rc, stdout="1.0.0" if rc == 0 else "")

    monkeypatch.setattr(backends.subprocess, "run", fake_run)
    result = backends.detect_available()
    assert result["claude"]["installed"] is True
    assert result["gemini"]["installed"] is True
    assert result["codex"]["installed"] is False
    assert result["opencode"]["installed"] is False


def test_detect_available_returns_version_string(monkeypatch):
    monkeypatch.setattr(
        backends.subprocess, "run",
        lambda cmd, **kw: _make_completed(returncode=0, stdout="claude 1.2.3\n"),
    )
    result = backends.detect_available()
    assert "1.2.3" in result["claude"]["version"] or result["claude"]["version"] != ""


def test_detect_available_handles_oserror(monkeypatch):
    def raise_oserror(cmd, **kw):
        raise OSError("No such file or directory")

    monkeypatch.setattr(backends.subprocess, "run", raise_oserror)
    result = backends.detect_available()
    for info in result.values():
        assert info["installed"] is False


# ---------------------------------------------------------------------------
# list_models
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("name", ["claude", "codex", "gemini", "opencode"])
def test_list_models_returns_nonempty_list(name):
    models = backends.list_models(name, repo_root=PROJECT_ROOT)
    assert isinstance(models, list)
    assert len(models) >= 1, f"{name} catalog must have at least 1 model"


@pytest.mark.parametrize("name", ["claude", "codex", "gemini", "opencode"])
def test_list_models_each_has_required_keys(name):
    models = backends.list_models(name, repo_root=PROJECT_ROOT)
    for m in models:
        assert "id" in m, f"{name} model missing 'id'"
        assert "hint" in m, f"{name} model missing 'hint'"
        assert "description" in m, f"{name} model missing 'description'"


@pytest.mark.parametrize("name", ["claude", "codex", "gemini", "opencode"])
def test_list_models_hints_are_valid(name):
    valid_hints = {"fast", "standard", "most_capable"}
    models = backends.list_models(name, repo_root=PROJECT_ROOT)
    for m in models:
        assert m["hint"] in valid_hints, (
            f"{name} model {m['id']!r} has invalid hint {m['hint']!r}"
        )


def test_list_models_filter_by_hint(monkeypatch, tmp_path):
    catalog = [
        {"id": "fast-model", "hint": "fast", "description": "Quick"},
        {"id": "std-model", "hint": "standard", "description": "Standard"},
        {"id": "cap-model", "hint": "most_capable", "description": "Capable"},
    ]
    (tmp_path / "backends").mkdir()
    (tmp_path / "backends" / "claude.json").write_text(
        __import__("json").dumps(catalog), encoding="utf-8"
    )
    fast_only = backends.list_models("claude", repo_root=tmp_path, hint_filter="fast")
    assert len(fast_only) == 1
    assert fast_only[0]["id"] == "fast-model"


def test_list_models_bad_backend_raises():
    with pytest.raises(backends.BackendError, match="unknown backend"):
        backends.list_models("noexist", repo_root=PROJECT_ROOT)


# ---------------------------------------------------------------------------
# build_invocation — argv matrix
# ---------------------------------------------------------------------------

BUILD_CASES = [
    # (backend, model, skip_permissions, expected_head, expected_contains)
    pytest.param(
        "claude", "claude-sonnet-4-6", False,
        ["claude"],
        ["--model", "claude-sonnet-4-6", "--append-system-prompt", "-p"],
        id="claude-no-skip",
    ),
    pytest.param(
        "claude", "claude-opus-4-7", True,
        ["claude", "--dangerously-skip-permissions"],
        ["--model", "claude-opus-4-7"],
        id="claude-skip-perms",
    ),
    pytest.param(
        "codex", "gpt-5", False,
        ["codex", "exec"],
        ["--model", "gpt-5"],
        id="codex-no-skip",
    ),
    pytest.param(
        "codex", "gpt-5-high", True,
        ["codex", "exec", "--dangerously-bypass-approvals-and-sandbox"],
        ["--model", "gpt-5-high"],
        id="codex-skip-perms",
    ),
    pytest.param(
        "gemini", "gemini-2.5-pro", False,
        ["gemini"],
        ["--model", "gemini-2.5-pro", "--system", "-p"],
        id="gemini-no-skip",
    ),
    pytest.param(
        "gemini", "gemini-2.5-pro", True,
        ["gemini"],
        ["--model", "gemini-2.5-pro"],
        id="gemini-skip-ignored",  # gemini has no skip_perm_flag
    ),
    pytest.param(
        "opencode", "opencode-standard", False,
        ["opencode", "run"],
        ["--model", "opencode-standard", "--system"],
        id="opencode-no-skip",
    ),
    pytest.param(
        "opencode", "opencode-plus", True,
        ["opencode", "run"],
        ["--model", "opencode-plus"],
        id="opencode-skip-ignored",  # opencode skip_perm_flag is None
    ),
]


@pytest.mark.parametrize("backend,model,skip_perms,expected_head,expected_contains", BUILD_CASES)
def test_build_invocation_head(backend, model, skip_perms, expected_head, expected_contains):
    argv = backends.build_invocation(
        backend,
        persona_body="You are a test persona.",
        task_prompt="Check this text.",
        model=model,
        skip_permissions=skip_perms,
    )
    # argv starts with expected_head
    assert argv[:len(expected_head)] == expected_head, (
        f"{backend} argv head mismatch: {argv[:len(expected_head)]!r} != {expected_head!r}"
    )


@pytest.mark.parametrize("backend,model,skip_perms,expected_head,expected_contains", BUILD_CASES)
def test_build_invocation_contains_model(backend, model, skip_perms, expected_head, expected_contains):
    argv = backends.build_invocation(
        backend,
        persona_body="You are a test persona.",
        task_prompt="Check this text.",
        model=model,
        skip_permissions=skip_perms,
    )
    assert "--model" in argv
    model_pos = argv.index("--model")
    assert argv[model_pos + 1] == model


@pytest.mark.parametrize("backend,model,skip_perms,expected_head,expected_contains", BUILD_CASES)
def test_build_invocation_contains_persona_body(backend, model, skip_perms, expected_head, expected_contains):
    persona_body = "UNIQUE_PERSONA_BODY_SENTINEL"
    argv = backends.build_invocation(
        backend,
        persona_body=persona_body,
        task_prompt="task",
        model=model,
        skip_permissions=skip_perms,
    )
    # Persona body must appear somewhere in argv
    assert any(persona_body in str(arg) for arg in argv), (
        f"persona_body not found in argv for {backend}: {argv!r}"
    )


def test_build_invocation_unknown_backend_raises():
    with pytest.raises(backends.BackendError, match="unknown backend"):
        backends.build_invocation(
            "noexist",
            persona_body="x",
            task_prompt="y",
            model="z",
            skip_permissions=False,
        )


def test_build_invocation_extra_args_appended():
    argv = backends.build_invocation(
        "claude",
        persona_body="persona",
        task_prompt="task",
        model="claude-sonnet-4-6",
        skip_permissions=False,
        extra_args=["--output-format", "stream-json"],
    )
    assert "--output-format" in argv
    assert "stream-json" in argv


# ---------------------------------------------------------------------------
# Fake-backend integration: OMW_BACKEND_OVERRIDE_PATH
# ---------------------------------------------------------------------------
import os
import stat


FAKES_DIR = PROJECT_ROOT / "tests" / "fakes"


@pytest.mark.parametrize("backend,cli_name", [
    ("claude", "claude"),
    ("codex", "codex"),
    ("gemini", "gemini"),
    ("opencode", "opencode"),
])
def test_detect_available_finds_fake_backends(backend, cli_name, tmp_path):
    """With OMW_BACKEND_OVERRIDE_PATH pointing at tests/fakes/, detect_available
    should report all 4 backends as installed."""
    assert FAKES_DIR.exists(), f"tests/fakes/ not found at {FAKES_DIR}"
    result = backends.detect_available(override_path=str(FAKES_DIR))
    assert result[backend]["installed"] is True, (
        f"fake {backend} not detected; fakes dir: {list(FAKES_DIR.iterdir())}"
    )


@pytest.mark.parametrize("backend,cli_name,fake_script", [
    ("claude", "claude", "claude-fake.sh"),
    ("codex", "codex", "codex-fake.sh"),
    ("gemini", "gemini", "gemini-fake.sh"),
    ("opencode", "opencode", "opencode-fake.sh"),
])
def test_fake_script_is_executable(backend, cli_name, fake_script):
    """Each *-fake.sh must be executable (chmod +x)."""
    script_path = FAKES_DIR / fake_script
    assert script_path.exists(), f"{fake_script} not found at {script_path}"
    assert os.access(script_path, os.X_OK), f"{fake_script} is not executable"


@pytest.mark.parametrize("backend,symlink_name,fake_script", [
    ("claude", "claude", "claude-fake.sh"),
    ("codex", "codex", "codex-fake.sh"),
    ("gemini", "gemini", "gemini-fake.sh"),
    ("opencode", "opencode", "opencode-fake.sh"),
])
def test_bare_name_symlink_exists_and_points_to_fake(backend, symlink_name, fake_script):
    """Bare-name symlink (no .sh) must exist and resolve to *-fake.sh."""
    symlink_path = FAKES_DIR / symlink_name
    assert symlink_path.exists(), f"symlink {symlink_name!r} not found at {symlink_path}"
    assert symlink_path.is_symlink(), f"{symlink_name!r} is not a symlink"
    target = symlink_path.resolve().name
    assert target == fake_script, (
        f"symlink {symlink_name!r} points to {target!r}, expected {fake_script!r}"
    )


@pytest.mark.parametrize("backend,cli_name", [
    ("claude", "claude"),
    ("codex", "codex"),
    ("gemini", "gemini"),
    ("opencode", "opencode"),
])
def test_fake_dry_run_produces_output(backend, cli_name, tmp_path):
    """Running the fake via PATH override should write output to OMW_FAKE_OUTPUT_PATH."""
    output_file = tmp_path / f"{backend}-output.txt"
    env = os.environ.copy()
    env["PATH"] = f"{FAKES_DIR}:{env.get('PATH', '')}"
    env["OMW_FAKE_OUTPUT_PATH"] = str(output_file)

    # Use build_invocation to get real argv, then run it
    argv = backends.build_invocation(
        backend,
        persona_body="Test persona body.",
        task_prompt="Test task prompt.",
        model="test-model",
        skip_permissions=False,
    )
    result = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, (
        f"fake {backend} exited {result.returncode}; "
        f"stdout={result.stdout!r}; stderr={result.stderr!r}"
    )
    assert output_file.exists(), (
        f"OMW_FAKE_OUTPUT_PATH file not written by fake {backend}"
    )
    content = output_file.read_text(encoding="utf-8")
    assert f"FAKE-{backend.upper()}" in content, (
        f"Expected 'FAKE-{backend.upper()}' in output; got: {content!r}"
    )


def test_codex_folds_persona_into_prompt_no_invalid_flags():
    argv = backends.build_invocation(
        "codex",
        persona_body="UNIQUE_PERSONA_SENTINEL",
        task_prompt="TASK_SENTINEL",
        model="gpt-5",
        skip_permissions=True,
    )
    # invalid flags must be gone
    assert "--instructions" not in argv
    assert "--yolo" not in argv
    # real skip flag present
    assert "--dangerously-bypass-approvals-and-sandbox" in argv
    # persona has no flag on codex — it is folded into the final positional prompt
    assert "--system" not in argv and "--append-system-prompt" not in argv
    prompt = argv[-1]
    assert "UNIQUE_PERSONA_SENTINEL" in prompt
    assert "TASK_SENTINEL" in prompt
    # codex exec subcommand + model still present
    assert argv[:2] == ["codex", "exec"]
    assert "--model" in argv and argv[argv.index("--model") + 1] == "gpt-5"
