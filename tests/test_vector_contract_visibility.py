"""A vector-contract mismatch disables vector search entirely. These pin that
the user can actually find that out — every diagnostic surface once reported
"no problems" while `vector_index.query` returned nothing at all.
"""
import pytest

from scripts import embed, embed_admin, setup_wizard, vector_index


class _Embedder:
    model = "test-model"
    dim = 8


@pytest.fixture
def skewed(monkeypatch, tmp_path):
    """An index built by a different embedding runtime than the one querying."""
    # The recall notice writes a rate-limit stamp under OMW_HOME; without this
    # a test run would silence the real user's notice for hours.
    monkeypatch.setenv("OMW_HOME", str(tmp_path / ".omw-isolated"))
    monkeypatch.setattr(vector_index, "available", lambda: True)
    monkeypatch.setattr(vector_index, "meta", lambda db: {
        "model": "test-model", "dim": 8, "prefix_scheme": "none",
        "fingerprint": "FastEmbed|test-model|8|none|0.8.0",
        "distance_metric": "cosine",
    })
    monkeypatch.setattr(embed, "get_embedder", lambda cfg: _Embedder())
    monkeypatch.setattr(embed, "prefix_scheme", lambda e: "none")
    monkeypatch.setattr(embed, "embedding_fingerprint",
                        lambda e: "FastEmbed|test-model|8|none|0.9.0")


def test_contract_mismatch_is_reported(skewed, tmp_path):
    report = vector_index.contract_report(tmp_path / "r.db", _Embedder())
    assert report["matches"] is False
    assert "fingerprint" in report["mismatched"]
    assert report["mismatched"]["fingerprint"] == {
        "indexed": "FastEmbed|test-model|8|none|0.8.0",
        "current": "FastEmbed|test-model|8|none|0.9.0",
    }


def test_a_matching_contract_reports_no_mismatch(monkeypatch, tmp_path):
    monkeypatch.setattr(vector_index, "available", lambda: True)
    monkeypatch.setattr(vector_index, "meta", lambda db: {
        "model": "test-model", "dim": 8, "prefix_scheme": "none",
        "fingerprint": "same", "distance_metric": "cosine"})
    monkeypatch.setattr(embed, "prefix_scheme", lambda e: "none")
    monkeypatch.setattr(embed, "embedding_fingerprint", lambda e: "same")
    report = vector_index.contract_report(tmp_path / "r.db", _Embedder())
    assert report["matches"] is True and report["mismatched"] == {}


def test_embed_status_surfaces_the_mismatch(skewed, monkeypatch, tmp_path):
    """status used to compare only model and dim — the two fields that match."""
    from tests.conftest import make_vault_with_pages
    db, _ = make_vault_with_pages(tmp_path, monkeypatch, pages={"wiki/a.md": "# A\n\nx"})
    st = embed_admin.status(db)
    assert any("fingerprint" in d for d in st["diagnostics"]), st["diagnostics"]
    assert st["index_fingerprint"] != st["fingerprint"]


def test_doctor_reports_the_mismatch(skewed, tmp_path, monkeypatch):
    """`omw doctor` is the command you run when something feels wrong — a fault
    that disables vector search cannot be absent from it."""
    from tests.conftest import make_vault_with_pages
    make_vault_with_pages(tmp_path, monkeypatch, pages={"wiki/a.md": "# A\n\nx"})
    checks = setup_wizard.doctor_checks()
    item = next((i for i in checks["items"] if "vector" in i["name"].lower()), None)
    assert item is not None, [i["name"] for i in checks["items"]]
    assert item["ok"] is False
    assert "omw embed reindex" in f"{item.get('detail', '')} {item.get('hint', '')}"


def test_doctor_stays_quiet_when_the_contract_matches(monkeypatch, tmp_path):
    from tests.conftest import make_vault_with_pages
    monkeypatch.setattr(vector_index, "available", lambda: True)
    monkeypatch.setattr(vector_index, "meta", lambda db: {
        "model": "test-model", "dim": 8, "prefix_scheme": "none",
        "fingerprint": "same", "distance_metric": "cosine"})
    monkeypatch.setattr(embed, "get_embedder", lambda cfg: _Embedder())
    monkeypatch.setattr(embed, "prefix_scheme", lambda e: "none")
    monkeypatch.setattr(embed, "embedding_fingerprint", lambda e: "same")
    make_vault_with_pages(tmp_path, monkeypatch, pages={"wiki/a.md": "# A\n\nx"})
    checks = setup_wizard.doctor_checks()
    item = next((i for i in checks["items"] if "vector" in i["name"].lower()), None)
    assert item is None or item["ok"] is True


# --- the hook surface -------------------------------------------------------
# Hooks discard stderr, so a contract mismatch there is invisible by
# construction. stdout is the one channel the host actually reads.

def test_recall_tells_the_user_when_vector_search_is_disabled(skewed, monkeypatch):
    from scripts import recall
    monkeypatch.setattr(recall, "_hits", lambda text, k: [])
    monkeypatch.setattr(recall, "effective_strategy", lambda s, quiet=True: "hybrid")
    body = recall._recall_body(
        {"mode": "auto", "strategy": "hybrid", "top_k": 3, "min_score": 0.3},
        "에이전트 메모리")
    assert "omw embed reindex" in body


def test_recall_says_nothing_extra_when_the_contract_is_fine(monkeypatch):
    from scripts import recall
    monkeypatch.setattr(vector_index, "available", lambda: True)
    monkeypatch.setattr(vector_index, "contract_report",
                        lambda db, e: {"matches": True, "mismatched": {},
                                       "indexed": {}, "current": {}})
    monkeypatch.setattr(recall, "_hits", lambda text, k: [])
    monkeypatch.setattr(recall, "effective_strategy", lambda s, quiet=True: "hybrid")
    body = recall._recall_body(
        {"mode": "auto", "strategy": "hybrid", "top_k": 3, "min_score": 0.3},
        "에이전트 메모리")
    assert "omw embed reindex" not in body


def test_the_fts_strategy_does_not_mention_the_vector_contract(skewed, monkeypatch):
    """An fts-only vault does not use the vector index, so the notice is noise."""
    from scripts import recall
    monkeypatch.setattr(recall, "_hits", lambda text, k: [])
    monkeypatch.setattr(recall, "effective_strategy", lambda s, quiet=True: "fts")
    body = recall._recall_body(
        {"mode": "auto", "strategy": "fts", "top_k": 3, "min_score": 1.0}, "x")
    assert "omw embed reindex" not in body


def test_doctor_actually_prints_the_mismatch(skewed, tmp_path, monkeypatch, capsys):
    """doctor() renders items by name, so a check can exist in doctor_checks()
    and still never reach the screen — which is the failure being fixed."""
    from tests.conftest import make_vault_with_pages
    make_vault_with_pages(tmp_path, monkeypatch, pages={"wiki/a.md": "# A\n\nx"})
    setup_wizard.doctor()
    out = capsys.readouterr().out
    assert "vector" in out.lower() and "omw embed reindex" in out


# --- false-positive guards --------------------------------------------------

def test_an_unindexed_vault_is_not_a_mismatch():
    """No stored contract means nothing to compare, not a fault."""
    report = vector_index.contract_from_meta(None, _Embedder())
    assert report["matches"] is True and report["compared"] is False


def test_the_current_side_is_reported_even_with_no_stored_contract(monkeypatch):
    """status reads prefix_scheme off the report; an empty side made it null."""
    monkeypatch.setattr(embed, "prefix_scheme", lambda e: "none")
    monkeypatch.setattr(embed, "embedding_fingerprint", lambda e: "fp")
    report = vector_index.contract_from_meta(None, _Embedder())
    assert report["current"]["prefix_scheme"] == "none"


def test_status_keeps_prefix_scheme_a_string_before_any_reindex(monkeypatch, tmp_path):
    from tests.conftest import make_vault_with_pages
    monkeypatch.setattr(vector_index, "available", lambda: True)
    monkeypatch.setattr(vector_index, "meta", lambda db: None)
    monkeypatch.setattr(embed, "active_embedder", lambda db, cfg: _Embedder())
    monkeypatch.setattr(embed, "prefix_scheme", lambda e: "none")
    monkeypatch.setattr(embed, "embedding_fingerprint", lambda e: "fp")
    db, _ = make_vault_with_pages(tmp_path, monkeypatch, pages={"wiki/a.md": "# A\n\nx"})
    st = embed_admin.status(db)
    assert st["prefix_scheme"] == "none"
    assert st["diagnostics"] == []


def test_a_recovered_model_switch_is_not_reported_as_a_fault(monkeypatch, tmp_path):
    """active_embedder returns the embedder matching the index after an
    interrupted model switch — vector search works, so doctor must stay quiet
    even though config still names the other model."""
    from tests.conftest import make_vault_with_pages
    monkeypatch.setattr(vector_index, "available", lambda: True)
    monkeypatch.setattr(vector_index, "meta", lambda db: {
        "model": "indexed-model", "dim": 8, "prefix_scheme": "none",
        "fingerprint": "indexed-fp", "distance_metric": "cosine"})

    class _Recovered:
        model = "indexed-model"
        dim = 8
    monkeypatch.setattr(embed, "active_embedder", lambda db, cfg: _Recovered())
    monkeypatch.setattr(embed, "get_embedder", lambda cfg: _Embedder())  # config's model
    monkeypatch.setattr(embed, "prefix_scheme", lambda e: "none")
    monkeypatch.setattr(embed, "embedding_fingerprint",
                        lambda e: "indexed-fp" if e.model == "indexed-model" else "other-fp")
    make_vault_with_pages(tmp_path, monkeypatch, pages={"wiki/a.md": "# A\n\nx"})
    item = next((i for i in setup_wizard.doctor_checks()["items"]
                 if i["name"] == "vector contract"), None)
    assert item is None or item["ok"] is True


def test_doctor_says_so_when_it_cannot_check(monkeypatch, tmp_path):
    from tests.conftest import make_vault_with_pages
    monkeypatch.setattr(vector_index, "available", lambda: True)
    def boom(*a, **k):
        raise RuntimeError("vec store unreadable")
    monkeypatch.setattr(embed, "active_embedder", boom)
    make_vault_with_pages(tmp_path, monkeypatch, pages={"wiki/a.md": "# A\n\nx"})
    item = next((i for i in setup_wizard.doctor_checks()["items"]
                 if i["name"] == "vector contract"), None)
    assert item is not None and "could not check" in item["detail"]


def test_the_recall_notice_does_not_repeat_every_prompt(skewed, monkeypatch, tmp_path):
    from scripts import recall
    monkeypatch.setenv("OMW_HOME", str(tmp_path / ".omw"))
    monkeypatch.setattr(embed, "active_embedder", lambda db, cfg: _Embedder())
    monkeypatch.setattr(recall, "_hits", lambda text, k: [])
    monkeypatch.setattr(recall, "effective_strategy", lambda s, quiet=True: "hybrid")
    cfg = {"mode": "auto", "strategy": "hybrid", "top_k": 3, "min_score": 0.3}
    first = recall._recall_body(cfg, "에이전트 메모리")
    second = recall._recall_body(cfg, "에이전트 메모리")
    assert "omw embed reindex" in first
    assert "omw embed reindex" not in second
