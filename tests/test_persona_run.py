import os
import pathlib
import pytest
from scripts import persona_run

FAKES = str(pathlib.Path(__file__).resolve().parent / "fakes")


def test_pick_backend_prefers_requested_then_first_authed():
    detected = {
        "claude": {"installed": True, "authed": True},
        "codex": {"installed": True, "authed": False},
    }
    assert persona_run._pick_backend(detected, "claude") == "claude"
    assert persona_run._pick_backend(detected, None) == "claude"
    with pytest.raises(persona_run.RunError):
        persona_run._pick_backend({"codex": {"installed": True, "authed": False}}, None)


def test_dispatch_runs_fake_backend_and_returns_stdout(monkeypatch):
    out = persona_run._dispatch(
        "You are a tester.", "Say hello.",
        backend="codex", model="fake-model", override_cli_path=FAKES,
    )
    assert isinstance(out, str) and out  # fake echoes something non-empty


def test_dispatch_raises_on_backend_failure():
    with pytest.raises(persona_run.RunError):
        os.environ["OMW_FAKE_FAIL"] = "1"
        try:
            persona_run._dispatch("b", "t", backend="codex", model="m",
                                  override_cli_path=FAKES)
        finally:
            os.environ.pop("OMW_FAKE_FAIL", None)
