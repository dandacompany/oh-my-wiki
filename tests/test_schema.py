# tests/test_schema.py
from pathlib import Path

from scripts import schema

BASE = {
    "required_fields": ["title", "date", "type", "tags"],
    "field_types": {"tags": "list", "title": "str", "date": "str"},
    "required_sections": [],
}
ENTITY = {
    "required_fields": ["title", "date", "type", "tags"],
    "field_types": {"tags": "list", "title": "str", "date": "str"},
    "required_sections": ["## Summary"],
}
SCHEMAS = {"base": BASE, "entity": ENTITY, "concept": BASE}


def _issues(meta, body="", schemas=SCHEMAS):
    return {i["issue"] for i in schema.validate(meta, body, schemas=schemas)}


def test_validate_clean_page_returns_empty():
    meta = {"title": "T", "date": "2026-01-01", "type": "concept", "tags": ["a"]}
    assert schema.validate(meta, "body", schemas=SCHEMAS) == []


def test_validate_missing_field():
    meta = {"title": "T", "type": "concept", "tags": ["a"]}  # no date
    assert "missing_field:date" in _issues(meta)


def test_validate_missing_type_uses_base_and_flags_type():
    meta = {"title": "T", "date": "2026-01-01", "tags": ["a"]}  # no type
    assert "missing_field:type" in _issues(meta)


def test_validate_invalid_type():
    meta = {"title": "T", "type": "bogus", "tags": ["a"]}  # bogus type + missing date
    issues = _issues(meta)
    assert "invalid_type" in issues
    assert "missing_field:date" in issues


def test_validate_wrong_type_tags_not_list():
    meta = {"title": "T", "date": "2026-01-01", "type": "concept", "tags": "a"}
    assert "wrong_type:tags" in _issues(meta)


def test_validate_missing_required_section():
    meta = {"title": "T", "date": "2026-01-01", "type": "entity", "tags": ["a"]}
    assert "missing_section:## Summary" in _issues(meta, body="no heading here")


def test_validate_section_present_passes():
    meta = {"title": "T", "date": "2026-01-01", "type": "entity", "tags": ["a"]}
    body = "intro\n\n## Summary\n\ntext"
    assert schema.validate(meta, body, schemas=SCHEMAS) == []


def _write(dir_path: Path, name: str, text: str):
    dir_path.mkdir(parents=True, exist_ok=True)
    (dir_path / name).write_text(text, encoding="utf-8")


def test_load_dir_reads_yaml_by_stem(tmp_path):
    _write(tmp_path, "entity.yml", "extends: base\nrequired_sections: ['## Summary']\n")
    loaded, errors = schema._load_dir(tmp_path)
    assert "entity" in loaded
    assert loaded["entity"]["required_sections"] == ["## Summary"]
    assert errors == []


def test_load_dir_missing_returns_empty(tmp_path):
    loaded, errors = schema._load_dir(tmp_path / "nope")
    assert loaded == {}
    assert errors == []


def test_load_schemas_resolves_extends_base(tmp_path, monkeypatch):
    monkeypatch.setattr(schema, "_BUNDLED_DIR", tmp_path / "bundled")
    _write(tmp_path / "bundled", "base.yml",
           "required_fields: [title, date, type, tags]\n"
           "field_types: {tags: list}\nrequired_sections: []\n")
    _write(tmp_path / "bundled", "entity.yml",
           "extends: base\nrequired_sections: ['## Summary']\n")
    schemas = schema.load_schemas()
    # entity inherits base required_fields AND keeps its own section
    assert set(schemas["entity"]["required_fields"]) == {"title", "date", "type", "tags"}
    assert schemas["entity"]["required_sections"] == ["## Summary"]


def test_load_schemas_vault_override_wins_and_adds(tmp_path, monkeypatch):
    monkeypatch.setattr(schema, "_BUNDLED_DIR", tmp_path / "bundled")
    _write(tmp_path / "bundled", "base.yml",
           "required_fields: [title, type]\nfield_types: {}\nrequired_sections: []\n")
    _write(tmp_path / "bundled", "concept.yml", "extends: base\n")
    vault = tmp_path / "vault"
    _write(vault / "schemas", "concept.yml",
           "extends: base\nrequired_sections: ['## Definition']\n")  # override
    _write(vault / "schemas", "recipe.yml",
           "required_fields: [title, servings]\n")  # brand-new type
    schemas = schema.load_schemas(vault_path=vault)
    assert schemas["concept"]["required_sections"] == ["## Definition"]
    assert "recipe" in schemas
    assert "title" in schemas["recipe"]["required_fields"]


def test_valid_types_excludes_base(tmp_path, monkeypatch):
    monkeypatch.setattr(schema, "_BUNDLED_DIR", tmp_path / "bundled")
    _write(tmp_path / "bundled", "base.yml", "required_fields: []\n")
    _write(tmp_path / "bundled", "note.yml", "extends: base\n")
    schemas = schema.load_schemas()
    assert schema.valid_types(schemas) == {"note"}


def test_bundled_defaults_cover_known_types():
    schemas = schema.load_schemas()  # reads the real schemas/ dir
    types = schema.valid_types(schemas)
    expected = {
        "article", "link", "note", "paper", "video", "book", "doc",
        "summary", "entity", "concept", "comparison", "synthesis", "meta",
    }
    assert expected <= types
    # base baseline is inherited by extends:base types
    assert set(schemas["concept"]["required_fields"]) == {"title", "date", "type", "tags"}
    assert schemas["entity"]["required_sections"] == ["## Summary"]
    # meta is intentionally minimal
    assert schemas["meta"]["required_fields"] == []


def test_load_dir_skips_malformed_yaml(tmp_path):
    # A broken vault schema file must not crash the loader (would otherwise
    # halt lint AND reindex). It is skipped; valid siblings still load.
    _write(tmp_path, "good.yml", "extends: base\n")
    _write(tmp_path, "bad.yml", "{ unclosed: true")  # invalid YAML
    loaded, errors = schema._load_dir(tmp_path)
    assert "good" in loaded
    assert "bad" not in loaded
    assert any("bad.yml" in e["path"] for e in errors)


ALLOWED = {
    "base": {
        "required_fields": ["title", "type"],
        "field_types": {},
        "required_sections": [],
        "allowed_values": {"confidence": ["high", "medium", "low"],
                           "status": ["draft", "processed", "superseded"]},
    },
}
ALLOWED["concept"] = dict(ALLOWED["base"])


def test_validate_invalid_value_confidence():
    meta = {"title": "T", "type": "concept", "confidence": "bogus"}
    issues = {i["issue"] for i in schema.validate(meta, "", schemas=ALLOWED)}
    assert "invalid_value:confidence" in issues


def test_validate_allowed_value_ok_and_optional():
    # valid value → no issue; absent optional field → no issue
    ok = {"title": "T", "type": "concept", "confidence": "high"}
    assert all(not i["issue"].startswith("invalid_value")
               for i in schema.validate(ok, "", schemas=ALLOWED))
    absent = {"title": "T", "type": "concept"}
    assert all(not i["issue"].startswith("invalid_value")
               for i in schema.validate(absent, "", schemas=ALLOWED))


def test_validate_invalid_status_value():
    meta = {"title": "T", "type": "concept", "status": "weird"}
    issues = {i["issue"] for i in schema.validate(meta, "", schemas=ALLOWED)}
    assert "invalid_value:status" in issues


def test_load_schemas_merges_allowed_values(tmp_path, monkeypatch):
    monkeypatch.setattr(schema, "_BUNDLED_DIR", tmp_path / "bundled")
    _write(tmp_path / "bundled", "base.yml",
           "required_fields: [title]\nallowed_values: {confidence: [high, low]}\n")
    _write(tmp_path / "bundled", "concept.yml", "extends: base\n")
    schemas = schema.load_schemas()
    assert schemas["concept"]["allowed_values"]["confidence"] == ["high", "low"]


def test_validate_review_must_be_dict():
    schemas = schema.load_schemas()  # bundled defaults
    bad = {"title": "T", "date": "2026-01-01", "type": "concept", "tags": ["a"],
           "review": "notadict"}
    issues = {i["issue"] for i in schema.validate(bad, "", schemas=schemas)}
    assert "wrong_type:review" in issues
    good = dict(bad); good["review"] = {"due": "2026-01-01"}
    issues2 = {i["issue"] for i in schema.validate(good, "", schemas=schemas)}
    assert "wrong_type:review" not in issues2


def test_validate_aliases_must_be_list():
    schemas = schema.load_schemas()
    bad = {"title": "T", "date": "2026-01-01", "type": "concept", "tags": ["a"], "aliases": "x"}
    issues = {i["issue"] for i in schema.validate(bad, "", schemas=schemas)}
    assert "wrong_type:aliases" in issues
    good = dict(bad); good["aliases"] = ["x"]
    assert "wrong_type:aliases" not in {i["issue"] for i in schema.validate(good, "", schemas=schemas)}


# ---------------------------------------------------------------------------
# Task 4: load_schemas_with_errors surfaces malformed schema files
# ---------------------------------------------------------------------------

def test_load_schemas_with_errors_reports_malformed(tmp_path):
    vault = tmp_path / "v"
    (vault / "schemas").mkdir(parents=True)
    (vault / "schemas" / "broken.yml").write_text("a: : : not valid\n", encoding="utf-8")
    schemas, errors = schema.load_schemas_with_errors(vault_path=vault)
    assert any("broken.yml" in e["path"] for e in errors)
    assert "base" in schemas   # bundled schemas still load


def test_load_schemas_backcompat_drops_errors(tmp_path):
    vault = tmp_path / "v"
    (vault / "schemas").mkdir(parents=True)
    (vault / "schemas" / "broken.yml").write_text("x: : :\n", encoding="utf-8")
    out = schema.load_schemas(vault_path=vault)   # still returns just a dict, no crash
    assert isinstance(out, dict) and "base" in out
