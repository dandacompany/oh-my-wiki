"""End-to-end Plan C scenario: wiki-setup → ingest paste → ingest pdf → query+synthesis → wiki_lint."""
from pathlib import Path

import pytest

from scripts import (
    adapters, ingest, lint, query, registry, reindex, wiki_lint,
)
from scripts import search_index as search

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fresh_db(tmp_db):
    registry.init_db(tmp_db)
    return tmp_db


def test_full_wiki_workflow(fresh_db, tmp_path):
    db = fresh_db
    root = tmp_path / "research"

    # vault-setup
    adapters.get_adapter("markdown").init_vault(root, "wiki")
    vault = registry.add_vault(
        db, name="research", path=root, type_="markdown", mode="wiki"
    )
    registry.set_active(db, "research")
    reindex.full(db, vault_id=vault["id"])

    # ingest paste
    raw_rel = ingest.save_raw(
        db, vault_id=vault["id"],
        content="Karpathy on building an LLM wiki: capture sources, write summaries, link entities.",
        ext="md", title="Karpathy LLM Wiki", date_str="2026-05-25",
    )
    assert raw_rel == "raw/2026-05-25-karpathy-llm-wiki.md"

    # ingest pdf
    pdf_bytes = (FIXTURES / "tiny.pdf").read_bytes()
    pdf_rel, extracted = ingest.save_raw_pdf(
        db, vault_id=vault["id"],
        pdf_bytes=pdf_bytes,
        title="Tiny Source", date_str="2026-05-25",
    )
    assert pdf_rel == "raw/2026-05-25-tiny-source.pdf"
    assert "PDF FIXTURE" in extracted

    # write summary + entity + concept (bodies must be ≥ 50 chars for wiki_lint)
    summary_rel = ingest.write_wiki_page(
        db, vault_id=vault["id"],
        layer="summaries", title="Karpathy LLM Wiki",
        body="Karpathy describes wiki-as-knowledge-artifact. Capture sources, write summaries, link entities.",
        tags=["karpathy", "llm"], date_str="2026-05-25",
        extra_meta={"source_raw": [raw_rel]},   # a summary must name the source it condenses
    )
    entity_rel = ingest.write_wiki_page(
        db, vault_id=vault["id"],
        layer="entities", title="Andrej Karpathy",
        body="## Summary\n\nAI researcher and educator. Former director of AI at Tesla and researcher at OpenAI.",
        tags=["person"], date_str="2026-05-25",
    )
    concept_rel = ingest.write_wiki_page(
        db, vault_id=vault["id"],
        layer="concepts", title="Compounding Knowledge",
        body="Knowledge compounds when written down and linked. Wiki structure preserves accumulated insight.",
        tags=["idea"], date_str="2026-05-25",
    )

    # update_index + append_log
    ingest.update_index(
        db, vault_id=vault["id"],
        entries=[
            ("summaries", "karpathy-llm-wiki", "Karpathy on building an LLM wiki"),
            ("entities", "andrej-karpathy", "Andrej Karpathy — AI researcher"),
            ("concepts", "compounding-knowledge", "Knowledge as compounding artifact"),
        ],
    )
    ingest.append_log(
        db, vault_id=vault["id"],
        op="ingest", title="Karpathy LLM Wiki", date_str="2026-05-25",
    )
    reindex.incremental(db, vault_id=vault["id"])

    # search finds the summary
    hits = search.query(db, vault_id=vault["id"], query="karpathy", limit=5)
    assert any(h["relpath"] == summary_rel for h in hits)

    # query write_synthesis (file-back)
    syn_rel = query.write_synthesis(
        db, vault_id=vault["id"],
        title="Why wiki beats notes",
        body="Linking compounds. Summaries decay. Wiki structure preserves value.",
        citations=[summary_rel, concept_rel],
        tags=["argument"], date_str="2026-05-25",
    )
    assert syn_rel == "wiki/syntheses/why-wiki-beats-notes.md"

    ingest.update_index(
        db, vault_id=vault["id"],
        entries=[("syntheses", "why-wiki-beats-notes", "Linking compounds, notes decay")],
    )
    ingest.append_log(
        db, vault_id=vault["id"],
        op="synthesis", title="Why wiki beats notes", date_str="2026-05-25",
    )
    reindex.incremental(db, vault_id=vault["id"])

    # lint (common) — no issues
    common = lint.check(db, vault_id=vault["id"])
    assert common["frontmatter_issues"] == []
    assert common["drift"]["missing_files"] == []

    # wiki_lint — recently-written pages: no orphans (grace period), no missing concepts, no empties
    structural = wiki_lint.check(db, vault_id=vault["id"])
    assert structural["orphan_pages"] == []
    assert structural["missing_concepts"] == []
    assert structural["empty_data"] == []
    assert structural["dangling_links"] == []
