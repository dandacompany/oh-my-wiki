"""omw-ask convention: a host-universal 'ask the user for judgment' managed block.

Maps one abstract ask shape onto each host's native surface (AskUserQuestion /
ask_user / question / clarify / requestUserInput / requireApproval), enumerates the
wiki-lifecycle decision classes with their safe defaults, and degrades cleanly when
no interactive surface exists.
"""
from pathlib import Path

from scripts import ask

REPO = Path(__file__).resolve().parents[1]
ALL_HOSTS = ("claude", "codex", "gemini", "hermes", "opencode", "openclaw")
NATIVE_TOOLS = ("AskUserQuestion", "ask_user", "question", "clarify",
                "requestUserInput", "requireApproval")


# ── ASK descriptor SSOT ──────────────────────────────────────────────────────

def test_ask_ssot_covers_all_six_hosts():
    assert set(ask.ASK) == set(ALL_HOSTS)
    for host in ALL_HOSTS:
        assert ask.ASK[host].get("tool")


def test_ask_ssot_tool_names_match_survey():
    assert {ask.ASK[h]["tool"] for h in ALL_HOSTS} == set(NATIVE_TOOLS)


# ── decision-class taxonomy ──────────────────────────────────────────────────

def test_taxonomy_has_core_decision_classes():
    keys = {d.key for d in ask.TAXONOMY}
    for k in ("duplicate-ingest", "candidate-approval", "new-vs-update", "stale-page", "merge-candidates",
              "supersede", "visibility-publish", "persona-delegate", "export-scope"):
        assert k in keys, f"missing decision class {k!r}"


def test_every_decision_has_safe_default_among_its_options():
    for d in ask.TAXONOMY:
        assert d.options, f"{d.key} has no options"
        assert d.safe_default in d.options, f"{d.key} safe_default not an option"
        # safe default must be offered FIRST (recommended-first idiom across all hosts)
        assert d.options[0] == d.safe_default, f"{d.key} safe_default not listed first"


def test_destructive_classes_are_never_session_sticky():
    # destructive decisions (merge/supersede/delete) must re-ask every time —
    # session 'auto' may only skip re-prompts for non-destructive proposal application.
    destructive = [d for d in ask.TAXONOMY if d.destructive]
    assert destructive
    for d in destructive:
        assert d.sticky is False, f"destructive {d.key} must not be session-sticky"


def test_destructive_keys_helper():
    assert "supersede" in ask.destructive_keys()
    assert "merge-candidates" in ask.destructive_keys()


# ── rendered managed block ───────────────────────────────────────────────────

def test_render_block_has_markers_and_all_host_tools():
    block = ask.render_block()
    assert "<!-- omw-ask:start -->" in block and "<!-- omw-ask:end -->" in block
    for tool in NATIVE_TOOLS:
        assert tool in block, f"host tool {tool} missing from block"


def test_render_block_states_degrade_and_sticky_and_subagent_rules():
    low = ask.render_block().lower()
    # universal degrade rule (non-interactive → safe default, never block)
    assert "safe default" in low and ("non-interactive" in low or "headless" in low)
    # session-sticky reuse
    assert "session" in low
    # propose→confirm→execute tie-in + subagent rule (ask in host, not the worker)
    assert "propose" in low and "subagent" in low
    # destructive ops always ask / never auto-applied
    assert "destructive" in low


def test_render_block_lists_decision_classes():
    block = ask.render_block()
    for k in ("new-vs-update", "supersede", "visibility-publish"):
        assert k in block


# ── export into host instruction files (mirror commandmap.export) ────────────

def test_export_writes_block_idempotently(tmp_path):
    ask.export(tmp_path, ["claude", "codex"])
    claude = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert "<!-- omw-ask:start -->" in claude
    ask.export(tmp_path, ["claude", "codex"])  # re-run replaces, not appends
    claude2 = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert claude2.count("<!-- omw-ask:start -->") == 1


def test_uninstall_knows_the_ask_marker():
    from scripts import uninstall
    assert ask.MARKER in uninstall.MARKERS
