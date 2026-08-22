"""Lifecycle chain: static map integrity + deterministic state-aware resolver."""
from scripts import chain
from scripts import ops_registry as reg


def test_chain_map_references_real_ops():
    for op, succs in chain.CHAIN.items():
        assert reg.get(op) is not None, f"unknown chain key: {op}"
        for s in succs:
            assert reg.get(s) is not None, f"unknown successor: {s}"


def test_unmapped_op_has_no_successor():
    assert chain.next_after("status", {}) == []
    assert chain.next_after("version", {}) == []


def test_static_successor_when_state_neutral():
    # ingest → summary is always endorsed (no state gate)
    out = chain.next_after("ingest", {})
    assert [s["op"] for s in out] == ["summary"]
    assert out[0]["command"] == "omw summary"
    assert out[0]["phase"] == "structure"


def test_synthesis_gated_on_clusters():
    # summary → synthesis only when the vault has clusters
    assert chain.next_after("summary", {"clusters": 0}) == []
    out = chain.next_after("summary", {"clusters": 2})
    assert [s["op"] for s in out] == ["synthesis"]


def test_lint_gated_on_lint_issues():
    # synthesis → lint only when there are lint issues
    assert chain.next_after("synthesis", {"lint_issues": 0}) == []
    assert [s["op"] for s in chain.next_after("synthesis", {"lint_issues": 3})] == ["lint"]


def test_review_gated_on_stale_or_expired():
    assert chain.next_after("lint", {"stale": 0, "expired": 0}) == []
    assert [s["op"] for s in chain.next_after("lint", {"stale": 1})] == ["review"]
    assert [s["op"] for s in chain.next_after("lint", {"expired": 2})] == ["review"]


def test_direct_page_writes_chain_to_lint():
    """Writing a page is the most common way to create orphan / index-drift findings,
    but `page`/`edit`/`distill` had no chain entry, so nothing was ever offered after
    one — the user only learned by remembering to run lint themselves."""
    for op in ("page", "edit", "distill"):
        assert [s["op"] for s in chain.next_after(op, {"lint_issues": 2})] == ["lint"], op
        # the lint_issues gate keeps a clean vault quiet
        assert chain.next_after(op, {"lint_issues": 0}) == [], op


def test_ingest_also_offers_lint():
    """ingest touches 10-15 pages per run — by far the biggest write — yet only led
    to `summary`."""
    ops = [s["op"] for s in chain.next_after("ingest", {"lint_issues": 4})]
    assert ops == ["summary", "lint"]


def test_deterministic_same_input_same_output():
    sig = {"clusters": 1, "lint_issues": 0, "stale": 0, "expired": 0}
    assert chain.next_after("summary", sig) == chain.next_after("summary", sig)


def test_search_and_fetch_lead_to_ingest():
    assert [s["op"] for s in chain.next_after("search", {})] == ["ingest"]
    assert [s["op"] for s in chain.next_after("fetch", {})] == ["ingest"]


def test_new_ops_are_procedures_with_slash_skills_and_cards():
    from pathlib import Path

    from scripts import agent_skills
    root = Path(__file__).resolve().parent.parent
    for op in ("summary", "synthesis"):
        assert op in reg.procedures()
        assert f"omw-{op}" in agent_skills.op_skill_names()
        assert (root / "commands" / f"{op}.md").is_file()


def test_skill_md_has_lifecycle_chaining_rule():
    from pathlib import Path
    text = (Path(__file__).resolve().parent.parent / "SKILL.md").read_text(encoding="utf-8")
    assert "omw next --after" in text
    assert "safe default = stop" in text
