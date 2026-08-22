"""`omw report` surfaces how much of the wiki is traceable back to a source.

Complements the schema rule: schemas/summary.yml makes a missing `source_raw` a lint
issue for summaries only (where an untraceable page is unambiguously a defect). For
concepts/entities a hand-written page with no raw source is legitimate, so those are
reported as a coverage number rather than judged as findings.
"""
import pytest

from scripts import adapters, ingest, registry, reindex, report


@pytest.fixture
def wiki_vault(tmp_path, tmp_db):
    registry.init_db(tmp_db)
    root = tmp_path / "wiki"
    adapters.get_adapter("markdown").init_vault(root, "wiki")
    vault = registry.add_vault(tmp_db, name="w", path=root, type_="markdown", mode="wiki")
    reindex.full(tmp_db, vault_id=vault["id"])
    return tmp_db, vault, root


def _write(db, vid, layer, title, **extra):
    ingest.write_wiki_page(db, vault_id=vid, layer=layer, title=title,
                           body="A body long enough to satisfy wiki_lint's minimum length.",
                           tags=["t"], date_str="2026-05-25", **extra)


def test_counts_pages_naming_a_source(wiki_vault):
    db, vault, _ = wiki_vault
    vid = vault["id"]
    _write(db, vid, "concepts", "Traced", extra_meta={"source_raw": ["raw/a.md"]})
    _write(db, vid, "concepts", "Untraced")
    _write(db, vid, "entities", "Also traced", extra_meta={"source_raw": ["raw/a.md"]})
    reindex.full(db, vault_id=vid)

    prov = report._provenance(db, vid)
    assert prov == {"with_source": 2, "total": 3}


def test_syntheses_are_excluded(wiki_vault):
    """A synthesis derives from pages, not a raw source — `synthesizes` is its link."""
    db, vault, _ = wiki_vault
    vid = vault["id"]
    _write(db, vid, "syntheses", "Woven",
           extra_meta={"synthesizes": ["wiki/concepts/a.md"]})
    reindex.full(db, vault_id=vid)

    assert report._provenance(db, vid) == {"with_source": 0, "total": 0}


def test_render_shows_provenance_line(wiki_vault):
    db, vault, _ = wiki_vault
    vid = vault["id"]
    _write(db, vid, "concepts", "Traced", extra_meta={"source_raw": ["raw/a.md"]})
    _write(db, vid, "concepts", "Untraced")
    reindex.full(db, vault_id=vid)

    text = report.render(report.build(db, vid, today="2026-05-25", no_reindex=True))
    assert "Provenance" in text
    assert "1/2" in text


def test_empty_vault_reports_zero_not_a_crash(wiki_vault):
    db, vault, _ = wiki_vault
    assert report._provenance(db, vault["id"]) == {"with_source": 0, "total": 0}
