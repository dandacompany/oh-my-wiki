from pathlib import Path

import pytest

from scripts import registry, adapters, reindex, ingest

FIXTURES = Path(__file__).parent / "fixtures"


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


def test_save_raw_md(wiki_vault):
    db, vault, root = wiki_vault
    rel = ingest.save_raw(
        db, vault_id=vault["id"],
        content="# Heading\n\nbody",
        ext="md", title="My Source", date_str="2026-05-25",
    )
    assert rel == "raw/2026-05-25-my-source.md"
    text = (root / rel).read_text(encoding="utf-8")
    assert text == "# Heading\n\nbody"


def test_save_raw_txt(wiki_vault):
    db, vault, root = wiki_vault
    rel = ingest.save_raw(
        db, vault_id=vault["id"],
        content="plain text",
        ext="txt", title="A Note", date_str="2026-05-25",
    )
    assert rel == "raw/2026-05-25-a-note.txt"
    assert (root / rel).read_text(encoding="utf-8") == "plain text"


def test_save_raw_md_records_source_url_frontmatter(wiki_vault):
    db, vault, root = wiki_vault
    rel = ingest.save_raw(
        db, vault_id=vault["id"], content="# Body", ext="md",
        title="Web Source", date_str="2026-07-27",
        source_url="https://example.com/article",
    )
    meta, body = ingest.frontmatter.parse((root / rel).read_text(encoding="utf-8"))
    assert meta["source_url"] == "https://example.com/article"
    assert body == "# Body"
    assert ingest.find_raw_by_source_url(
        db, vault_id=vault["id"], source_url="https://example.com/article"
    ) == rel


def test_save_raw_collision(wiki_vault):
    db, vault, root = wiki_vault
    ingest.save_raw(
        db, vault_id=vault["id"], content="a",
        ext="md", title="dup", date_str="2026-05-25",
    )
    second = ingest.save_raw(
        db, vault_id=vault["id"], content="b",
        ext="md", title="dup", date_str="2026-05-25",
    )
    assert second == "raw/2026-05-25-dup-2.md"


def test_save_raw_pdf_returns_relpath_and_extracted_text(wiki_vault):
    db, vault, root = wiki_vault
    pdf_bytes = (FIXTURES / "tiny.pdf").read_bytes()
    rel, text = ingest.save_raw_pdf(
        db, vault_id=vault["id"],
        pdf_bytes=pdf_bytes,
        title="Tiny", date_str="2026-05-25",
    )
    assert rel == "raw/2026-05-25-tiny.pdf"
    # bytes preserved verbatim
    assert (root / rel).read_bytes() == pdf_bytes
    # text extracted
    assert "PDF FIXTURE" in text


def test_write_wiki_page_summary(wiki_vault):
    db, vault, root = wiki_vault
    rel = ingest.write_wiki_page(
        db, vault_id=vault["id"],
        layer="summaries",
        title="Karpathy LLM Wiki",
        body="One-paragraph summary.",
        tags=["karpathy", "llm"],
        date_str="2026-05-25",
    )
    assert rel == "wiki/summaries/karpathy-llm-wiki.md"
    text = (root / rel).read_text(encoding="utf-8")
    assert "title: Karpathy LLM Wiki" in text
    assert "type: summary" in text
    assert "One-paragraph summary." in text


def test_write_wiki_page_entity(wiki_vault):
    db, vault, root = wiki_vault
    rel = ingest.write_wiki_page(
        db, vault_id=vault["id"],
        layer="entities",
        title="Andrej Karpathy",
        body="AI researcher.",
        tags=["person"],
        date_str="2026-05-25",
    )
    assert rel == "wiki/entities/andrej-karpathy.md"
    text = (root / rel).read_text(encoding="utf-8")
    assert "type: entity" in text


def test_write_wiki_page_rejects_bad_layer(wiki_vault):
    db, vault, root = wiki_vault
    with pytest.raises(ValueError, match="layer"):
        ingest.write_wiki_page(
            db, vault_id=vault["id"],
            layer="not-a-layer",
            title="x", body="", tags=[], date_str="2026-05-25",
        )


def test_update_index_adds_under_correct_section(wiki_vault):
    db, vault, root = wiki_vault
    ingest.update_index(
        db, vault_id=vault["id"],
        entries=[("entities", "andrej-karpathy", "Andrej Karpathy — AI researcher")],
    )
    text = (root / "wiki/index.md").read_text(encoding="utf-8")
    assert "## Entities" in text
    assert "- [[andrej-karpathy]] — Andrej Karpathy — AI researcher" in text


def test_update_index_is_idempotent(wiki_vault):
    db, vault, root = wiki_vault
    entry = ("concepts", "compounding", "Compounding knowledge")
    ingest.update_index(db, vault_id=vault["id"], entries=[entry])
    ingest.update_index(db, vault_id=vault["id"], entries=[entry])
    text = (root / "wiki/index.md").read_text(encoding="utf-8")
    assert text.count("- [[compounding]]") == 1


def test_update_index_creates_missing_section(wiki_vault):
    db, vault, root = wiki_vault
    ingest.update_index(
        db, vault_id=vault["id"],
        entries=[("comparisons", "tdd-vs-bdd", "TDD vs BDD")],
    )
    text = (root / "wiki/index.md").read_text(encoding="utf-8")
    assert "## Comparisons" in text
    assert "- [[tdd-vs-bdd]] — TDD vs BDD" in text


def test_append_log_writes_line(wiki_vault):
    db, vault, root = wiki_vault
    ingest.append_log(
        db, vault_id=vault["id"],
        op="ingest", title="My Source", date_str="2026-05-25",
    )
    text = (root / "wiki/log.md").read_text(encoding="utf-8")
    assert "## [2026-05-25] ingest | My Source" in text
