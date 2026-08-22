"""Every page omw writes must pass omw's own lint.

Three frontmatter fields drifted from the schemas before this test existed:
`summary` (written by ingest, read by the FTS scorer), `relations` (written by
page_ops/merge, read by links), and `citations` (written by write_synthesis and read
by nothing). None were declared in schemas/. The writers and the validator are the
two halves of one contract; this pins them together so a writer cannot introduce an
undeclared field without a schema change.
"""
import pytest

from scripts import adapters, ingest, lint, query, registry, reindex


@pytest.fixture
def wiki_vault(tmp_path, tmp_db):
    registry.init_db(tmp_db)
    root = tmp_path / "wiki"
    adapters.get_adapter("markdown").init_vault(root, "wiki")
    vault = registry.add_vault(tmp_db, name="w", path=root, type_="markdown", mode="wiki")
    reindex.full(tmp_db, vault_id=vault["id"])
    return tmp_db, vault, root


def _issues(db, vault_id):
    reindex.full(db, vault_id=vault_id)
    return lint.check(db, vault_id=vault_id)["frontmatter_issues"]


def test_write_synthesis_output_passes_lint(wiki_vault):
    db, vault, _ = wiki_vault
    query.write_synthesis(
        db, vault_id=vault["id"], title="TDD beats no-tests", body="Argument...",
        citations=["wiki/summaries/tdd-paper.md"], tags=["tdd"], date_str="2026-05-25",
        summary="A one-line abstract.",
    )
    assert _issues(db, vault["id"]) == []


def test_write_wiki_page_with_summary_passes_lint(wiki_vault):
    """`summary` lands in frontmatter (ingest.py) and is read by fts/hot_cache."""
    db, vault, _ = wiki_vault
    ingest.write_wiki_page(
        db, vault_id=vault["id"], layer="concepts", title="Red green refactor",
        body="Body.", tags=["tdd"], date_str="2026-05-25",
        summary="Write the failing test first.",
    )
    assert _issues(db, vault["id"]) == []


def test_write_wiki_page_with_relations_passes_lint(wiki_vault):
    """`relations` is written by page_ops/merge and read by links.relations()."""
    db, vault, _ = wiki_vault
    ingest.write_wiki_page(
        db, vault_id=vault["id"], layer="concepts", title="Fakes over mocks",
        body="Body.", tags=["testing"], date_str="2026-05-25",
        extra_meta={"relations": {"see-also": ["red-green-refactor"]},
                    "source_raw": ["raw/2026-05-25-source.md"]},
    )
    assert _issues(db, vault["id"]) == []


def test_summary_layer_requires_source_raw(wiki_vault):
    """A summary is a condensation of ONE source, so an untraceable one is a defect."""
    db, vault, _ = wiki_vault
    ingest.write_wiki_page(
        db, vault_id=vault["id"], layer="summaries", title="Orphaned summary",
        body="Body.", tags=["x"], date_str="2026-05-25",
    )
    assert any(i["issue"] == "missing_field:source_raw" for i in _issues(db, vault["id"]))


def test_undeclared_field_is_reported(wiki_vault):
    """A field no schema declares (a typo, or an import artefact) must not pass silently."""
    db, vault, _ = wiki_vault
    ingest.write_wiki_page(
        db, vault_id=vault["id"], layer="concepts", title="Typo field",
        body="Body.", tags=["x"], date_str="2026-05-25",
        extra_meta={"tag": ["oops"]},          # `tag`, not `tags`
    )
    issues = _issues(db, vault["id"])
    assert any(i["issue"] == "unknown_field:tag" for i in issues), issues
