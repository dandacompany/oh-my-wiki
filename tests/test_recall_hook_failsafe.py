"""Recall hooks must NEVER block a host session (the recurring-lockout class of
bug). The generated hook command bakes a fixed CLI invocation; whenever the
`omw recall` arg contract drifts, an unguarded command exits non-zero and blocks
the host's UserPromptSubmit/PreToolUse gate. The fix: every generated hook
command is fail-safe (ends with `|| true` → exit 0 regardless), so arg drift can
only no-op recall, never lock the session."""
from scripts import recall


def test_json_hook_commands_are_failsafe():
    for host in ("claude", "codex", "gemini"):
        specs = recall._recall_hook_specs(host)
        assert specs, f"{host} should have recall hook events"
        for event, (cmd, _status) in specs.items():
            assert cmd.rstrip().endswith("|| true"), (host, event, cmd)
            assert " recall " in cmd, (host, event, cmd)
