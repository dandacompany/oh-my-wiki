from pathlib import Path

import pytest

from scripts import registry, adapters, reindex, query


@pytest.fixture
def wiki_vault(tmp_path, tmp_db):
    registry.init_db(tmp_db)
    root = tmp_path / "wiki"
    adapters.get_adapter("markdown").init_vault(root, "wiki")
    vault = registry.add_vault(
        tmp_db, name="w", path=root, type_="markdown", mode="wiki"
    )
    reindex.full(tmp_db, vault_id=vault["id"])
    return tmp_db, vault, root


def test_write_synthesis_creates_page(wiki_vault):
    db, vault, root = wiki_vault
    rel = query.write_synthesis(
        db, vault_id=vault["id"],
        title="TDD beats no-tests",
        body="Argument...",
        citations=["wiki/summaries/tdd-paper.md", "wiki/concepts/red-green.md"],
        tags=["tdd"],
        date_str="2026-05-25",
    )
    assert rel == "wiki/syntheses/tdd-beats-no-tests.md"
    text = (root / rel).read_text(encoding="utf-8")
    assert "type: synthesis" in text
    assert "synthesizes:" in text
    assert "citations:" not in text   # dead duplicate field, removed 2026-08-22
    assert "wiki/summaries/tdd-paper.md" in text
    assert "Argument..." in text


def test_write_synthesis_collision_resolves(wiki_vault):
    db, vault, root = wiki_vault
    query.write_synthesis(
        db, vault_id=vault["id"],
        title="dup", body="a", citations=[], tags=[],
        date_str="2026-05-25",
    )
    rel2 = query.write_synthesis(
        db, vault_id=vault["id"],
        title="dup", body="b", citations=[], tags=[],
        date_str="2026-05-25",
    )
    assert rel2 == "wiki/syntheses/dup-2.md"
