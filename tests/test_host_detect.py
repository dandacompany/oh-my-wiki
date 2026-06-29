"""host_detect — current agent-host session detection (pure env sniffing)."""
from scripts import host_detect


def test_claude_code_session_detected():
    env = {"CLAUDECODE": "1", "CLAUDE_CODE_SESSION_ID": "abc"}
    assert host_detect.in_host_session("claude", env=env) is True
    assert host_detect.current_host(env=env) == "claude"


def test_codex_companion_is_not_a_codex_session():
    """CODEX_COMPANION_SESSION_ID rides along inside Claude Code — must NOT read
    as a codex host session (false-positive guard)."""
    env = {"CLAUDECODE": "1", "CODEX_COMPANION_SESSION_ID": "x"}
    assert host_detect.in_host_session("codex", env=env) is False
    assert host_detect.current_host(env=env) == "claude"


def test_gemini_api_key_is_not_a_gemini_session():
    """A bare API key is a credential, not a session marker."""
    env = {"GEMINI_API_KEY": "k"}
    assert host_detect.in_host_session("gemini", env=env) is False
    assert host_detect.current_host(env=env) is None


def test_codex_session_detected():
    env = {"CODEX_SANDBOX": "seatbelt"}
    assert host_detect.current_host(env=env) == "codex"


def test_no_host_when_nothing_set():
    assert host_detect.current_host(env={}) is None


def test_claude_outranks_codex_when_both_present():
    env = {"CLAUDECODE": "1", "CODEX_SANDBOX": "seatbelt"}
    assert host_detect.current_host(env=env) == "claude"


def test_hermes_session_via_hermes_detect(monkeypatch):
    monkeypatch.setattr(host_detect.hermes_detect, "in_hermes_session", lambda: True)
    # env has no other host markers, so hermes wins.
    assert host_detect.in_host_session("hermes", env={}) is True
    assert host_detect.current_host(env={}) == "hermes"
