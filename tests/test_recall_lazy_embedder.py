"""The embedder costs ~0.92s of cold start per hook process and cannot be made
cheaper (import 0.36s + ONNX session 0.55s, both unavoidable per process).
Measured on a real vault, it earns that cost only when keyword search finds
nothing: for 'why do wiki pages become orphans' fts returns 0 and the embedder
finds the right page, while on prompts fts already answers, half of what the
embedder adds is noise. So pay for it on a miss, not on every prompt.
"""
import sqlite3

from scripts import embed, recall, search_index


def _vault(monkeypatch, tmp_path, strategy="hybrid"):
    from scripts import config, paths
    db = tmp_path / "registry.db"
    db.touch()
    monkeypatch.setattr(paths, "registry_path", lambda: db)
    monkeypatch.setattr(config, "load_config", lambda: {
        "recall": {"strategy": strategy, "embedding": {"provider": "fake", "dim": 8}}})
    monkeypatch.setattr(recall, "_active", lambda _db: {"id": 7})
    return db


def test_a_keyword_hit_never_builds_the_embedder(monkeypatch, tmp_path):
    _vault(monkeypatch, tmp_path)
    def boom(*a, **k):
        raise AssertionError("embedder built despite a keyword hit")
    monkeypatch.setattr(embed, "active_embedder", boom)
    monkeypatch.setattr(search_index, "query", lambda *a, **k: [
        {"relpath": "wiki/concepts/kiwi.md", "title": "Kiwi", "score": 9.0}])
    hits = recall._hits("kiwi 형태소 분석기가 뭐야", 3)
    assert [h["relpath"] for h in hits] == ["wiki/concepts/kiwi.md"]


def test_a_keyword_miss_falls_through_to_the_embedder(monkeypatch, tmp_path):
    _vault(monkeypatch, tmp_path)
    built = []
    monkeypatch.setattr(embed, "active_embedder",
                        lambda db, cfg: built.append(1) or object())
    monkeypatch.setattr(search_index, "query", lambda *a, **k: [])
    monkeypatch.setattr(search_index, "search_strategy", lambda *a, **k: [
        {"relpath": "wiki/entities/wiki-librarian.md", "title": "wiki-librarian",
         "score": 0.6}])
    hits = recall._hits("위키 페이지가 고아가 되는 이유", 3)
    assert built, "the embedder must run when keyword search found nothing"
    assert [h["relpath"] for h in hits] == ["wiki/entities/wiki-librarian.md"]


def test_the_semantic_arm_still_gets_the_quality_gate(monkeypatch, tmp_path):
    _vault(monkeypatch, tmp_path)
    seen = {}
    monkeypatch.setattr(embed, "active_embedder", lambda db, cfg: object())
    monkeypatch.setattr(search_index, "query", lambda *a, **k: [])
    monkeypatch.setattr(search_index, "search_strategy",
                        lambda *a, **k: seen.update(k) or [])
    recall._hits("무언가", 3)
    assert seen["quality_gate"] is True and seen["strategy"] == "hybrid"


def test_the_fts_strategy_is_unchanged(monkeypatch, tmp_path):
    """An fts-configured vault never had an embedder to skip."""
    _vault(monkeypatch, tmp_path, strategy="fts")
    def boom(*a, **k):
        raise AssertionError("embedder built for an fts vault")
    monkeypatch.setattr(embed, "active_embedder", boom)
    monkeypatch.setattr(search_index, "query", lambda *a, **k: [])
    assert recall._hits("무언가", 3) == []


def test_keyword_hits_are_gated_before_counting_as_a_hit(monkeypatch, tmp_path):
    """A keyword result that names nothing is not an answer — escalate anyway."""
    _vault(monkeypatch, tmp_path)
    built = []
    monkeypatch.setattr(embed, "active_embedder",
                        lambda db, cfg: built.append(1) or object())
    monkeypatch.setattr(search_index, "query", lambda *a, **k: [
        {"relpath": "raw/unrelated.md", "title": "Unrelated", "score": 12.0}])
    monkeypatch.setattr(search_index, "search_strategy", lambda *a, **k: [])
    recall._hits("페르소나 번들", 3)
    assert built, "a keyword result that fails the name gate must not block escalation"


def test_a_broken_keyword_arm_does_not_disable_the_semantic_one(monkeypatch, tmp_path):
    """The keyword arm now gates the semantic one, so its failure must read as
    'found nothing' rather than taking retrieval down with it."""
    _vault(monkeypatch, tmp_path)
    def boom(*a, **k):
        # what a missing FTS table actually raises
        raise sqlite3.OperationalError("no such table: notes_fts")
    monkeypatch.setattr(search_index, "query", boom)
    monkeypatch.setattr(embed, "active_embedder", lambda db, cfg: object())
    monkeypatch.setattr(search_index, "search_strategy", lambda *a, **k: [
        {"relpath": "wiki/entities/wiki-librarian.md", "score": 0.6}])
    hits = recall._hits("위키 페이지가 고아가 되는 이유", 3)
    assert [h["relpath"] for h in hits] == ["wiki/entities/wiki-librarian.md"]


# --- score scales must not cross arms ---------------------------------------
# The keyword arm returns raw BM25 (live values 5-12); the semantic arm returns
# 0..1. Thresholding a BM25 score against the hybrid floor of 0.34 disables the
# floor, and merging the two by raw score lets keyword hits evict every semantic
# hit the escalation just paid for.

def test_a_weak_keyword_hit_is_not_injected_on_a_hybrid_vault(monkeypatch, tmp_path):
    _vault(monkeypatch, tmp_path)
    monkeypatch.setattr(recall, "effective_strategy", lambda s, quiet=True: "hybrid")
    monkeypatch.setattr(recall, "_hits", lambda text, k: [
        {"relpath": "wiki/concepts/x.md", "title": "X", "score": 0.5, "_arm": "fts"}])
    body = recall._recall_body(
        {"mode": "auto", "strategy": "hybrid", "top_k": 3, "min_score": 1.0},
        "무언가")
    assert "wiki/concepts/x.md" not in body


def test_hits_carry_the_arm_that_produced_them(monkeypatch, tmp_path):
    _vault(monkeypatch, tmp_path)
    monkeypatch.setattr(embed, "active_embedder", lambda db, cfg: object())
    monkeypatch.setattr(search_index, "query", lambda *a, **k: [
        {"relpath": "wiki/concepts/kiwi.md", "title": "Kiwi", "score": 9.0}])
    assert recall._hits("kiwi 형태소", 3)[0]["_arm"] == "fts"

    monkeypatch.setattr(search_index, "query", lambda *a, **k: [])
    monkeypatch.setattr(search_index, "search_strategy", lambda *a, **k: [
        {"relpath": "wiki/entities/wiki-librarian.md", "score": 0.6}])
    assert recall._hits("고아 페이지", 3)[0]["_arm"] == "hybrid"


def test_the_arm_tag_never_reaches_the_rendered_output(monkeypatch, tmp_path):
    _vault(monkeypatch, tmp_path)
    monkeypatch.setattr(recall, "effective_strategy", lambda s, quiet=True: "hybrid")
    monkeypatch.setattr(recall, "_hits", lambda text, k: [
        {"relpath": "wiki/concepts/x.md", "title": "X", "score": 9.0, "_arm": "fts"}])
    body = recall._recall_body(
        {"mode": "auto", "strategy": "hybrid", "top_k": 3, "min_score": 1.0}, "x")
    assert "wiki/concepts/x.md" in body and "_arm" not in body


def test_a_keyword_hit_below_the_keyword_floor_still_escalates(monkeypatch, tmp_path):
    """One weak keyword hit must not block the semantic arm and then get dropped
    downstream — that would be no escalation AND no output."""
    _vault(monkeypatch, tmp_path)
    built = []
    monkeypatch.setattr(embed, "active_embedder",
                        lambda db, cfg: built.append(1) or object())
    monkeypatch.setattr(search_index, "query", lambda *a, **k: [
        {"relpath": "wiki/concepts/kiwi.md", "title": "Kiwi", "score": 0.001}])
    monkeypatch.setattr(search_index, "search_strategy", lambda *a, **k: [])
    recall._hits("kiwi 형태소", 3)
    assert built


def test_the_embedding_strategy_does_not_take_the_keyword_shortcut(monkeypatch, tmp_path):
    """Choosing 'embedding' is choosing to avoid lexical gating; a keyword
    shortcut would silently make that setting mean something else."""
    _vault(monkeypatch, tmp_path, strategy="embedding")
    built = []
    monkeypatch.setattr(embed, "active_embedder",
                        lambda db, cfg: built.append(1) or object())
    monkeypatch.setattr(search_index, "query", lambda *a, **k: [
        {"relpath": "wiki/concepts/kiwi.md", "title": "Kiwi", "score": 9.0}])
    monkeypatch.setattr(search_index, "search_strategy", lambda *a, **k: [])
    recall._hits("kiwi 형태소", 3)
    assert built, "an embedding vault must always use the semantic arm"
