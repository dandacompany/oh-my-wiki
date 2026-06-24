from scripts import links
from scripts import schema as _schema

_SCHEMAS = None


def _schemas():
    global _SCHEMAS
    if _SCHEMAS is None:
        _SCHEMAS = _schema.load_schemas()
    return _SCHEMAS


def test_new_relation_verbs_extracted():
    meta = {"relations": {"derived-from": ["b"], "extends": ["c"], "see-also": ["d"]}}
    rels = {(s, r) for s, r, _ in links.extract_relations(meta)}
    assert ("b", "derived-from") in rels
    assert ("c", "extends") in rels
    assert ("d", "see-also") in rels


def test_unknown_relation_ignored():
    meta = {"relations": {"frobnicate": ["x"], "uses": ["y"]}}
    rels = {r for _, r, _ in links.extract_relations(meta)}
    assert "uses" in rels and "frobnicate" not in rels


def test_inline_new_relation_extracted():
    body = "intro\n\nderived-from:: [[b]]\n"
    rels = {(s, r) for s, r, _ in links.extract_inline_relations(body)}
    assert ("b", "derived-from") in rels


# ---------------------------------------------------------------------------
# Task 2 (F2/F3): synthesis/comparison schema contracts + source_raw field
# ---------------------------------------------------------------------------

def test_synthesis_requires_synthesizes_and_sources():
    issues = _schema.validate(
        {"type": "synthesis", "title": "t", "date": "2026-01-01", "tags": []},
        "no sources here",
        schemas=_schemas(),
    )
    kinds = [i["issue"] for i in issues]
    assert any(k.startswith("missing_field:synthesizes") for k in kinds)
    assert any(k.startswith("missing_section:## Sources") for k in kinds)


def test_wellformed_synthesis_clean():
    meta = {
        "type": "synthesis",
        "title": "t",
        "date": "2026-01-01",
        "tags": [],
        "synthesizes": ["a", "b"],
    }
    issues = _schema.validate(meta, "## Sources\n- a\n- b\n", schemas=_schemas())
    kinds = [i["issue"] for i in issues]
    assert not any("synthesizes" in k or "## Sources" in k for k in kinds)


def test_comparison_requires_compared_items():
    issues = _schema.validate(
        {"type": "comparison", "title": "t", "date": "2026-01-01", "tags": []},
        "",
        schemas=_schemas(),
    )
    assert any(i["issue"].startswith("missing_field:compared_items") for i in issues)


def test_source_raw_validates_as_list():
    base_ok = _schema.validate(
        {"type": "note", "title": "t", "date": "2026-01-01", "tags": [],
         "source_raw": ["raw/x.md"]},
        "",
        schemas=_schemas(),
    )
    assert not any(i["issue"].startswith("wrong_type:source_raw") for i in base_ok)

    bad = _schema.validate(
        {"type": "note", "title": "t", "date": "2026-01-01", "tags": [],
         "source_raw": "raw/x.md"},
        "",
        schemas=_schemas(),
    )
    assert any(i["issue"].startswith("wrong_type:source_raw") for i in bad)


# ---------------------------------------------------------------------------
# Task 3 (F2): advisory per-type valid_relations check
# ---------------------------------------------------------------------------

def test_valid_relations_flags_unexpected():
    meta = {"type": "comparison", "title": "t", "date": "2026-01-01", "tags": [],
            "compared_items": ["a", "b"], "relations": {"applies-to": ["x"]}}
    issues = _schema.validate(meta, "", schemas=_schemas())
    assert any(i["issue"].startswith("unexpected_relation:applies-to") for i in issues)


def test_valid_relations_allows_listed():
    meta = {"type": "comparison", "title": "t", "date": "2026-01-01", "tags": [],
            "compared_items": ["a", "b"], "relations": {"uses": ["x"]}}
    issues = _schema.validate(meta, "", schemas=_schemas())
    assert not any(i["issue"].startswith("unexpected_relation") for i in issues)


def test_type_without_valid_relations_never_flagged():
    meta = {"type": "note", "title": "t", "date": "2026-01-01", "tags": [],
            "relations": {"applies-to": ["x"]}}
    issues = _schema.validate(meta, "", schemas=_schemas())
    assert not any(i["issue"].startswith("unexpected_relation") for i in issues)
