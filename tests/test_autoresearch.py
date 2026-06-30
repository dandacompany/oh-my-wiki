"""Autoresearch: session state, rounds, file-back."""
from pathlib import Path

import pytest

from scripts import registry, adapters, reindex, autoresearch


@pytest.fixture
def wiki_vault(tmp_path, tmp_db):
    registry.init_db(tmp_db)
    root = tmp_path / "wiki"
    adapters.get_adapter("markdown").init_vault(root, "wiki")
    vault = registry.add_vault(
        tmp_db, name="w", path=root, type_="markdown", mode="wiki"
    )
    registry.set_active(tmp_db, "w")
    reindex.full(tmp_db, vault_id=vault["id"])
    return tmp_db, vault, root


@pytest.fixture
def memo_vault(tmp_path, tmp_db):
    registry.init_db(tmp_db)
    root = tmp_path / "memo-vault"
    adapters.get_adapter("markdown").init_vault(root, "memo")
    vault = registry.add_vault(
        tmp_db, name="m", path=root, type_="markdown", mode="memo"
    )
    registry.set_active(tmp_db, "m")
    reindex.full(tmp_db, vault_id=vault["id"])
    return tmp_db, vault, root


def test_init_session_creates_session_dir_and_mission(wiki_vault):
    db, vault, root = wiki_vault
    info = autoresearch.init_session(
        db, vault_id=vault["id"], query="How does attention work?"
    )
    session_dir = Path(info["session_dir"])
    assert session_dir.is_dir()
    assert session_dir.parent == root / ".oh-my-wiki" / "sessions"
    assert "how-does-attention-work" in session_dir.name
    mission_path = session_dir / "mission.json"
    assert mission_path.exists()
    import json
    mission = json.loads(mission_path.read_text(encoding="utf-8"))
    assert mission["query"] == "How does attention work?"
    assert mission["vault_id"] == vault["id"]
    assert mission["max_rounds"] == 3


def test_init_session_rejects_memo_vault(memo_vault):
    db, vault, root = memo_vault
    with pytest.raises(registry.VaultError, match="wiki-mode"):
        autoresearch.init_session(
            db, vault_id=vault["id"], query="anything"
        )


def test_init_session_respects_max_rounds_override(wiki_vault):
    db, vault, root = wiki_vault
    info = autoresearch.init_session(
        db, vault_id=vault["id"], query="q", max_rounds=2
    )
    import json
    mission = json.loads((Path(info["session_dir"]) / "mission.json").read_text())
    assert mission["max_rounds"] == 2


def test_init_session_caps_max_rounds_at_5(wiki_vault):
    db, vault, root = wiki_vault
    info = autoresearch.init_session(
        db, vault_id=vault["id"], query="q", max_rounds=99
    )
    import json
    mission = json.loads((Path(info["session_dir"]) / "mission.json").read_text())
    assert mission["max_rounds"] == 5


def test_record_round_writes_json_with_expected_shape(wiki_vault):
    db, vault, root = wiki_vault
    info = autoresearch.init_session(db, vault_id=vault["id"], query="q")
    session_dir = Path(info["session_dir"])
    p = autoresearch.record_round(
        session_dir,
        round_num=1,
        claims=[
            {"claim": "attention is parallelizable",
             "confidence": "high",
             "sources": ["https://arxiv.org/abs/1706.03762"]},
        ],
        gaps_remaining=["how does multi-head differ from single-head?"],
        notes="search round 1 returned good results on parallelism",
    )
    import json
    assert p == session_dir / "round-1.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["round_num"] == 1
    assert len(data["claims"]) == 1
    assert data["claims"][0]["confidence"] == "high"
    assert "how does multi-head" in data["gaps_remaining"][0]
    assert "recorded_at" in data


def test_record_round_idempotent_overwrite(wiki_vault):
    db, vault, root = wiki_vault
    info = autoresearch.init_session(db, vault_id=vault["id"], query="q")
    session_dir = Path(info["session_dir"])
    autoresearch.record_round(session_dir, round_num=1, claims=[], gaps_remaining=["a"])
    autoresearch.record_round(session_dir, round_num=1, claims=[], gaps_remaining=["b"])
    import json
    data = json.loads((session_dir / "round-1.json").read_text())
    assert data["gaps_remaining"] == ["b"], "second call should overwrite, not append"


def test_record_round_validates_round_num_bounds(wiki_vault):
    db, vault, root = wiki_vault
    info = autoresearch.init_session(db, vault_id=vault["id"], query="q", max_rounds=3)
    session_dir = Path(info["session_dir"])
    with pytest.raises(ValueError, match="round_num"):
        autoresearch.record_round(session_dir, round_num=0, claims=[], gaps_remaining=[])
    with pytest.raises(ValueError, match="round_num"):
        autoresearch.record_round(session_dir, round_num=4, claims=[], gaps_remaining=[])


def test_should_stop_in_progress_when_no_rounds(wiki_vault):
    db, vault, root = wiki_vault
    info = autoresearch.init_session(db, vault_id=vault["id"], query="q")
    session_dir = Path(info["session_dir"])
    stop, reason = autoresearch.should_stop(session_dir)
    assert stop is False
    assert reason == "in_progress"


def test_should_stop_no_gaps_after_round(wiki_vault):
    db, vault, root = wiki_vault
    info = autoresearch.init_session(db, vault_id=vault["id"], query="q")
    session_dir = Path(info["session_dir"])
    autoresearch.record_round(
        session_dir, round_num=1, claims=[], gaps_remaining=[]
    )
    stop, reason = autoresearch.should_stop(session_dir)
    assert stop is True
    assert reason == "no_gaps"


def test_should_stop_max_rounds_reached(wiki_vault):
    db, vault, root = wiki_vault
    info = autoresearch.init_session(
        db, vault_id=vault["id"], query="q", max_rounds=2
    )
    session_dir = Path(info["session_dir"])
    autoresearch.record_round(
        session_dir, round_num=1, claims=[], gaps_remaining=["still need X"]
    )
    autoresearch.record_round(
        session_dir, round_num=2, claims=[], gaps_remaining=["still need X"]
    )
    stop, reason = autoresearch.should_stop(session_dir)
    assert stop is True
    assert reason == "max_rounds"


def test_should_stop_in_progress_when_gaps_remain_and_under_cap(wiki_vault):
    db, vault, root = wiki_vault
    info = autoresearch.init_session(
        db, vault_id=vault["id"], query="q", max_rounds=3
    )
    session_dir = Path(info["session_dir"])
    autoresearch.record_round(
        session_dir, round_num=1, claims=[], gaps_remaining=["gap1"]
    )
    stop, reason = autoresearch.should_stop(session_dir)
    assert stop is False
    assert reason == "in_progress"


def test_file_back_writes_synthesis_and_marks_filed(wiki_vault):
    db, vault, root = wiki_vault
    info = autoresearch.init_session(db, vault_id=vault["id"], query="attention vs RNN")
    session_dir = Path(info["session_dir"])
    autoresearch.record_round(
        session_dir, round_num=1,
        claims=[{"claim": "attention parallelizes", "confidence": "high", "sources": ["src1"]}],
        gaps_remaining=[],
    )
    relpath = autoresearch.file_back(
        db, vault_id=vault["id"],
        session_dir=session_dir,
        title="Why Attention Beats RNN",
        body="Attention parallelizes computation across all token pairs.\n\nSource: src1.",
        citations=["src1"],
        tags=["attention", "transformer"],
        date_str="2026-05-26",
    )
    assert relpath == "wiki/syntheses/why-attention-beats-rnn.md"
    page = (root / relpath).read_text(encoding="utf-8")
    assert "type: synthesis" in page
    assert "Attention parallelizes" in page

    # filed marker exists
    filed_path = session_dir / "filed.json"
    assert filed_path.exists()
    import json
    filed = json.loads(filed_path.read_text(encoding="utf-8"))
    assert filed["synthesis_relpath"] == "wiki/syntheses/why-attention-beats-rnn.md"

    # index + log updated
    index_text = (root / "wiki" / "index.md").read_text(encoding="utf-8")
    assert "why-attention-beats-rnn" in index_text
    log_text = (root / "wiki" / "log.md").read_text(encoding="utf-8")
    assert "autoresearch" in log_text
    assert "Why Attention Beats RNN" in log_text


def test_file_back_is_idempotent(wiki_vault):
    db, vault, root = wiki_vault
    info = autoresearch.init_session(db, vault_id=vault["id"], query="q")
    session_dir = Path(info["session_dir"])
    autoresearch.record_round(
        session_dir, round_num=1, claims=[], gaps_remaining=[]
    )
    first = autoresearch.file_back(
        db, vault_id=vault["id"], session_dir=session_dir,
        title="First Title", body="body", citations=[], tags=[],
        date_str="2026-05-26",
    )
    second = autoresearch.file_back(
        db, vault_id=vault["id"], session_dir=session_dir,
        title="DIFFERENT Title (should be ignored)",
        body="body", citations=[], tags=[],
        date_str="2026-05-26",
    )
    # Same relpath returned both times
    assert first == second
    assert "first-title" in first


def test_session_status_fresh_session(wiki_vault):
    db, vault, root = wiki_vault
    info = autoresearch.init_session(db, vault_id=vault["id"], query="my question")
    session_dir = Path(info["session_dir"])
    s = autoresearch.session_status(session_dir)
    assert s["query"] == "my question"
    assert s["rounds_completed"] == 0
    assert s["max_rounds"] == 3
    assert s["last_gaps"] == []
    assert s["filed"] is False


def test_session_status_after_two_rounds_and_file_back(wiki_vault):
    db, vault, root = wiki_vault
    info = autoresearch.init_session(db, vault_id=vault["id"], query="q")
    session_dir = Path(info["session_dir"])
    autoresearch.record_round(
        session_dir, round_num=1, claims=[], gaps_remaining=["gap-a"]
    )
    autoresearch.record_round(
        session_dir, round_num=2, claims=[], gaps_remaining=[]
    )
    autoresearch.file_back(
        db, vault_id=vault["id"], session_dir=session_dir,
        title="Done", body="b", citations=[], tags=[], date_str="2026-05-26",
    )
    s = autoresearch.session_status(session_dir)
    assert s["rounds_completed"] == 2
    assert s["last_gaps"] == []
    assert s["filed"] is True


import subprocess
import sys


def test_cli_init_then_record_then_status(wiki_vault):
    db, vault, root = wiki_vault
    REPO_ROOT = Path(__file__).resolve().parents[1]
    import json as _json

    # init
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.autoresearch", "init",
         "--db", str(db), "--vault-id", str(vault["id"]),
         "--query", "my CLI query"],
        capture_output=True, text=True, check=False, cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, proc.stderr
    info = _json.loads(proc.stdout)
    session_dir = info["session_dir"]
    assert "my-cli-query" in session_dir

    # record round 1 with empty gaps
    claims_json = '[{"claim":"x","confidence":"high","sources":["s"]}]'
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.autoresearch", "record",
         "--session-dir", session_dir, "--round", "1",
         "--claims-json", claims_json, "--gaps-json", "[]"],
        capture_output=True, text=True, check=False, cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, proc.stderr

    # status
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.autoresearch", "status",
         "--session-dir", session_dir],
        capture_output=True, text=True, check=False, cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, proc.stderr
    status = _json.loads(proc.stdout)
    assert status["query"] == "my CLI query"
    assert status["rounds_completed"] == 1

    # should-stop should report no_gaps
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.autoresearch", "should-stop",
         "--session-dir", session_dir],
        capture_output=True, text=True, check=False, cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, proc.stderr
    result = _json.loads(proc.stdout)
    assert result["stop"] is True
    assert result["reason"] == "no_gaps"


def test_full_autoresearch_loop_3_rounds_then_file_back(wiki_vault):
    db, vault, root = wiki_vault

    # Simulate what commands/autoresearch.md does without invoking MCP
    info = autoresearch.init_session(
        db, vault_id=vault["id"],
        query="How does attention enable parallel training compared to RNN?",
        max_rounds=3,
    )
    session_dir = Path(info["session_dir"])

    # Round 1: 3 claims with mixed confidence, 1 gap remaining
    autoresearch.record_round(
        session_dir, round_num=1,
        claims=[
            {"claim": "attention computes all token pairs in parallel",
             "confidence": "high", "sources": ["https://arxiv.org/abs/1706.03762"]},
            {"claim": "RNN hidden state depends on previous timestep",
             "confidence": "high", "sources": ["nn-textbook-ch5"]},
            {"claim": "multi-head attention adds expressive capacity",
             "confidence": "medium", "sources": ["https://arxiv.org/abs/1706.03762"]},
        ],
        gaps_remaining=["quantify the speedup ratio in practice"],
    )

    # Round 2: 1 more claim, no gaps left
    autoresearch.record_round(
        session_dir, round_num=2,
        claims=[
            {"claim": "in practice attention is ~10x faster at training due to GPU parallelism",
             "confidence": "medium", "sources": ["blog-post-benchmark"]},
        ],
        gaps_remaining=[],
    )

    # should-stop reports no_gaps
    stop, reason = autoresearch.should_stop(session_dir)
    assert stop is True and reason == "no_gaps"

    # status snapshot
    s = autoresearch.session_status(session_dir)
    assert s["rounds_completed"] == 2
    assert s["filed"] is False

    # File back
    body = (
        "Attention enables full parallelism across token pairs, while RNNs serialize\n"
        "computation through their hidden-state recurrence. In practice this yields\n"
        "roughly an order of magnitude speedup at training time on modern GPUs."
    )
    relpath = autoresearch.file_back(
        db, vault_id=vault["id"],
        session_dir=session_dir,
        title="Attention parallelism beats RNN serialism",
        body=body,
        citations=[
            "https://arxiv.org/abs/1706.03762",
            "nn-textbook-ch5",
            "blog-post-benchmark",
        ],
        tags=["attention", "rnn", "transformer", "parallelism"],
        date_str="2026-05-26",
    )

    # Verify the full file-back surface
    assert relpath == "wiki/syntheses/attention-parallelism-beats-rnn-serialism.md"
    page = (root / relpath).read_text(encoding="utf-8")
    assert "type: synthesis" in page
    assert "Attention enables full parallelism" in page
    assert "citations:" in page

    index_text = (root / "wiki" / "index.md").read_text(encoding="utf-8")
    assert "attention-parallelism-beats-rnn-serialism" in index_text

    log_text = (root / "wiki" / "log.md").read_text(encoding="utf-8")
    assert "autoresearch" in log_text
    assert "Attention parallelism beats RNN serialism" in log_text

    # filed.json marker present
    s_final = autoresearch.session_status(session_dir)
    assert s_final["filed"] is True

    # Session dir has the expected artifacts
    expected_files = {
        "mission.json", "round-1.json", "round-2.json", "filed.json",
    }
    actual_files = {p.name for p in session_dir.iterdir()}
    assert expected_files.issubset(actual_files)


# ---------------------------------------------------------------------------
# Contract realignment: claim/source validation + raw-relpath status
# ---------------------------------------------------------------------------

def test_record_round_rejects_invalid_confidence(wiki_vault):
    db, vault, root = wiki_vault
    info = autoresearch.init_session(db, vault_id=vault["id"], query="q")
    with pytest.raises(ValueError, match="confidence"):
        autoresearch.record_round(
            Path(info["session_dir"]),
            round_num=1,
            claims=[{"claim": "x", "confidence": "certain", "sources": []}],
            gaps_remaining=[],
        )


def test_record_round_normalizes_legacy_and_raw_sources(wiki_vault):
    db, vault, root = wiki_vault
    info = autoresearch.init_session(db, vault_id=vault["id"], query="q")
    session_dir = Path(info["session_dir"])
    autoresearch.record_round(
        session_dir,
        round_num=1,
        claims=[{
            "claim": "x",
            "confidence": "high",
            "sources": [
                "https://example.com/a",
                {"url": "https://example.com/b", "title": "B", "raw_relpath": "raw/2026-06-29-b.md"},
            ],
        }],
        gaps_remaining=[],
    )
    import json
    data = json.loads((session_dir / "round-1.json").read_text(encoding="utf-8"))
    sources = data["claims"][0]["sources"]
    assert sources[0] == {
        "label": "https://example.com/a",
        "url": None,
        "title": None,
        "raw_relpath": None,
    }
    assert sources[1]["url"] == "https://example.com/b"
    assert sources[1]["raw_relpath"] == "raw/2026-06-29-b.md"


def test_session_status_reports_raw_relpaths(wiki_vault):
    db, vault, root = wiki_vault
    info = autoresearch.init_session(db, vault_id=vault["id"], query="q")
    session_dir = Path(info["session_dir"])
    autoresearch.record_round(
        session_dir,
        round_num=1,
        claims=[{
            "claim": "x",
            "confidence": "high",
            "sources": [
                {"url": "https://example.com/a", "raw_relpath": "raw/a.md"},
                {"url": "https://example.com/b", "raw_relpath": "raw/b.md"},
            ],
        }],
        gaps_remaining=["more"],
    )
    autoresearch.record_round(
        session_dir,
        round_num=2,
        claims=[{
            "claim": "y",
            "confidence": "medium",
            "sources": [{"url": "https://example.com/a", "raw_relpath": "raw/a.md"}],
        }],
        gaps_remaining=[],
    )
    assert autoresearch.session_status(session_dir)["raw_relpaths"] == ["raw/a.md", "raw/b.md"]
