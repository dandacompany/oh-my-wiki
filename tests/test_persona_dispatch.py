"""wiki-auditor persona (gap G1) + persona auto-dispatch wiring (the omw-personas
managed block now carries a routing table + a host-universal dispatch policy with a
session-sticky 'auto' choice)."""
from pathlib import Path

from scripts import persona_export as pe
from scripts import personas

REPO = Path(__file__).resolve().parents[1]


# ── A. wiki-auditor persona ──────────────────────────────────────────────────

def test_wiki_auditor_persona_loads_and_validates():
    spec = personas.load_persona("wiki-auditor")
    assert spec["name"] == "wiki-auditor"
    assert spec["output_kind"] == "stdout"        # diagnoses to stdout, never mutates
    assert spec["tools"] == []
    assert spec["triggers"]                        # routable


def test_persona_audit_card_exists():
    assert (REPO / "commands" / "persona-audit.md").is_file()


def test_no_dangling_wiki_auditor_reference():
    # wiki-librarian.md names wiki-auditor as its pair — that file must now exist
    assert (REPO / "personas" / "wiki-auditor.md").is_file()
    assert "wiki-auditor" in (REPO / "personas" / "wiki-librarian.md").read_text(encoding="utf-8")


# ── B. routing + dispatch policy in the managed block ────────────────────────

def test_list_personas_exposes_triggers():
    entries = {p["name"]: p for p in personas.list_personas()}
    assert "triggers" in entries["wiki-auditor"]
    assert isinstance(entries["wiki-auditor"]["triggers"], list)


def test_render_block_includes_routing_table_and_dispatch_policy():
    routes = {"wiki-auditor": ["audit the wiki", "위키 점검"],
              "curator": ["sync the index"]}
    block = pe.render_block(
        ["wiki-auditor", "curator"], "wiki-auditor",
        {"wiki-auditor": "Diagnose what's sick", "curator": "Sync the index"},
        routes=routes,
    )
    # routing table surfaces each persona's trigger phrases
    assert "audit the wiki" in block and "sync the index" in block
    # dispatch policy: delegate-vs-host choice via the host's question tool
    low = block.lower()
    assert "delegate" in low and "host" in low
    assert "askuserquestion" in low or "clarify" in low or "question tool" in low
    # session-sticky auto choice — don't re-ask after the user picks auto
    assert "session" in low and "auto" in low


def test_render_block_backward_compatible_without_routes():
    block = pe.render_block(["curator"], "curator", {"curator": "Sync the index"})
    assert "<!-- omw-personas:start -->" in block
    assert "Main persona: **curator**" in block
    # the dispatch policy is present even when no routes are passed
    assert "delegate" in block.lower()
