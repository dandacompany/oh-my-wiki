"""Persona registry + I/O runtime."""
from pathlib import Path

import pytest

from scripts import personas


def test_list_personas_returns_full_roster():
    names = {p["name"] for p in personas.list_personas()}
    assert names == {
        "wiki-librarian", "wiki-auditor", "curator", "fact-checker",
        "consistency-checker", "terminology-manager",
    }


def test_list_personas_entries_have_required_keys():
    for p in personas.list_personas():
        for key in ("name", "description", "capabilities", "tools",
                    "model_hint", "input_kinds", "output_kind"):
            assert key in p, f"persona {p.get('name')!r} missing {key}"


def test_load_persona_unknown_raises():
    with pytest.raises(personas.PersonaError, match="unknown"):
        personas.load_persona("nonexistent")


def test_load_persona_fact_checker_has_body():
    p = personas.load_persona("fact-checker")
    assert p["name"] == "fact-checker"
    assert p["output_kind"] == "sibling_suffix"
    assert "body" in p
    assert isinstance(p["body"], str)
    assert len(p["body"]) > 0


def test_load_persona_validates_output_kind():
    """A persona with an invalid output_kind raises PersonaError."""
    bad_text = """---
name: bad-persona
description: x
capabilities: []
tools: []
model_hint: standard
input_kinds: [text]
output_kind: nonsense
---
body
"""
    with pytest.raises(personas.PersonaError, match="output_kind"):
        personas._parse_persona_text(bad_text)


from scripts import registry, adapters, reindex


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


def test_resolve_input_text_mode():
    content, meta = personas.resolve_input(text="hello world")
    assert content == "hello world"
    assert meta["kind"] == "text"
    assert meta["origin"] is None


def test_resolve_input_file_mode(tmp_path):
    p = tmp_path / "input.md"
    p.write_text("file content", encoding="utf-8")
    content, meta = personas.resolve_input(file_path=p)
    assert content == "file content"
    assert meta["kind"] == "file"
    assert meta["origin"] == p


def test_resolve_input_file_not_found(tmp_path):
    with pytest.raises(personas.PersonaError, match="not found"):
        personas.resolve_input(file_path=tmp_path / "nope.md")


def test_resolve_input_vault_page_mode(wiki_vault):
    db, vault, root = wiki_vault
    page = root / "wiki" / "summaries" / "demo.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text("vault page content", encoding="utf-8")
    content, meta = personas.resolve_input(
        vault_relpath="wiki/summaries/demo.md",
        db_path=db, vault_id=vault["id"],
    )
    assert content == "vault page content"
    assert meta["kind"] == "vault_page"
    assert meta["origin"] == page


def test_resolve_input_no_input_raises():
    with pytest.raises(personas.PersonaError, match="no input"):
        personas.resolve_input()


def test_resolve_input_multiple_inputs_raises(tmp_path):
    with pytest.raises(personas.PersonaError, match="exactly one"):
        personas.resolve_input(text="x", file_path=tmp_path / "y.md")


def test_resolve_output_path_sibling_suffix_for_fact_checker(wiki_vault):
    db, vault, root = wiki_vault
    src = root / "wiki" / "summaries" / "demo.md"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("x", encoding="utf-8")
    persona = personas.load_persona("fact-checker")
    path = personas.resolve_output_path(
        persona=persona,
        source_meta={"kind": "vault_page", "origin": src},
        suffix="factcheck",
    )
    assert path == src.with_name("demo.factcheck.md")


def test_resolve_output_path_sibling_suffix_requires_suffix(wiki_vault):
    db, vault, root = wiki_vault
    src = root / "wiki" / "summaries" / "demo.md"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("x", encoding="utf-8")
    persona = personas.load_persona("fact-checker")
    with pytest.raises(personas.PersonaError, match="suffix"):
        personas.resolve_output_path(
            persona=persona,
            source_meta={"kind": "vault_page", "origin": src},
        )


def test_resolve_output_path_inplace_machinery(tmp_path):
    src = tmp_path / "draft.md"
    src.write_text("x", encoding="utf-8")
    persona = {"output_kind": "inplace"}
    path = personas.resolve_output_path(
        persona=persona,
        source_meta={"kind": "file", "origin": src},
    )
    assert path == src


def test_resolve_output_path_new_page_machinery(wiki_vault):
    db, vault, root = wiki_vault
    persona = {"output_kind": "new_page"}
    path = personas.resolve_output_path(
        persona=persona,
        source_meta={"kind": "text", "origin": None},
        db_path=db,
        vault_id=vault["id"],
        title="My New Topic",
    )
    assert path == root / "wiki" / "syntheses" / "my-new-topic.md"


def test_resolve_output_path_new_page_requires_title(wiki_vault):
    db, vault, root = wiki_vault
    persona = {"output_kind": "new_page"}
    with pytest.raises(personas.PersonaError, match="title"):
        personas.resolve_output_path(
            persona=persona,
            source_meta={"kind": "text", "origin": None},
            db_path=db, vault_id=vault["id"],
        )


def test_resolve_output_path_stdout_for_consistency_checker():
    persona = personas.load_persona("consistency-checker")
    path = personas.resolve_output_path(
        persona=persona,
        source_meta={"kind": "text", "origin": None},
    )
    assert path is None


from datetime import datetime


def test_write_output_sibling_suffix_creates_file(wiki_vault):
    db, vault, root = wiki_vault
    src = root / "wiki" / "summaries" / "demo.md"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("---\ntitle: Demo\n---\nbody", encoding="utf-8")
    persona = personas.load_persona("fact-checker")
    out_path = personas.resolve_output_path(
        persona=persona,
        source_meta={"kind": "vault_page", "origin": src},
        suffix="factcheck",
    )
    result = personas.write_output(
        persona=persona,
        target_path=out_path,
        content="---\ntitle: Demo\n---\nfact-check report",
        source_meta={"kind": "vault_page", "origin": src},
    )
    assert result == out_path
    assert out_path.exists()
    assert "fact-check report" in out_path.read_text(encoding="utf-8")


def test_write_output_inplace_backs_up_original(tmp_path):
    src = tmp_path / "draft.md"
    src.write_text("original prose", encoding="utf-8")
    backup_dir = tmp_path / ".trash"
    persona = {"output_kind": "inplace"}
    result = personas.write_output(
        persona=persona,
        target_path=src,
        content="polished prose",
        source_meta={"kind": "file", "origin": src},
        backup_dir=backup_dir,
    )
    assert result == src
    assert src.read_text(encoding="utf-8") == "polished prose"
    backups = list(backup_dir.glob("*draft*.md"))
    assert backups, "expected at least one backup file"
    assert backups[0].read_text(encoding="utf-8") == "original prose"


def test_write_output_inplace_skips_backup_when_no_backup_dir(tmp_path):
    src = tmp_path / "draft.md"
    src.write_text("original", encoding="utf-8")
    persona = {"output_kind": "inplace"}
    result = personas.write_output(
        persona=persona,
        target_path=src,
        content="updated",
        source_meta={"kind": "file", "origin": src},
        backup_dir=None,
    )
    assert result == src
    assert src.read_text(encoding="utf-8") == "updated"


def test_write_output_new_page_writes_to_wiki_syntheses(wiki_vault):
    db, vault, root = wiki_vault
    persona = {"output_kind": "new_page"}
    out_path = personas.resolve_output_path(
        persona=persona,
        source_meta={"kind": "text", "origin": None},
        db_path=db, vault_id=vault["id"],
        title="My Outline",
    )
    result = personas.write_output(
        persona=persona,
        target_path=out_path,
        content="---\ntitle: My Outline\ntype: synthesis\n---\n## Section 1\n## Section 2\n",
        source_meta={"kind": "text", "origin": None},
    )
    assert result == out_path
    assert out_path.exists()
    assert out_path == root / "wiki" / "syntheses" / "my-outline.md"


def test_write_output_stdout_returns_none(tmp_path):
    persona = personas.load_persona("consistency-checker")
    result = personas.write_output(
        persona=persona,
        target_path=None,
        content="some output",
        source_meta={"kind": "text", "origin": None},
    )
    assert result is None


import subprocess
import sys
import json as _json


def test_cli_list_returns_full_roster():
    REPO_ROOT = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.personas", "list"],
        capture_output=True, text=True, check=False, cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, proc.stderr
    data = _json.loads(proc.stdout)
    names = {p["name"] for p in data}
    assert names == {
        "wiki-librarian", "wiki-auditor", "curator", "fact-checker",
        "consistency-checker", "terminology-manager",
    }


def test_cli_show_returns_persona_spec():
    REPO_ROOT = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.personas", "show", "fact-checker"],
        capture_output=True, text=True, check=False, cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, proc.stderr
    data = _json.loads(proc.stdout)
    assert data["name"] == "fact-checker"
    assert "body" in data


def test_cli_run_fact_checker_sibling_suffix(wiki_vault, tmp_path):
    db, vault, root = wiki_vault
    REPO_ROOT = Path(__file__).resolve().parents[1]
    src = root / "wiki" / "summaries" / "demo.md"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("---\ntitle: Demo\n---\nEnglish body", encoding="utf-8")
    out = tmp_path / "report.md"
    out.write_text("---\ntitle: Demo\n---\nfact-check report", encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable, "-m", "scripts.personas", "run", "fact-checker",
            "--db", str(db),
            "--vault-id", str(vault["id"]),
            "--vault-relpath", "wiki/summaries/demo.md",
            "--suffix", "factcheck",
            "--output-file", str(out),
        ],
        capture_output=True, text=True, check=False, cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, proc.stderr
    final_path = proc.stdout.strip()
    assert final_path.endswith("demo.factcheck.md")
    written = Path(final_path)
    assert written.exists()
    assert "fact-check report" in written.read_text(encoding="utf-8")


def test_cli_run_consistency_checker_stdout(tmp_path):
    REPO_ROOT = Path(__file__).resolve().parents[1]
    out = tmp_path / "report.json"
    out.write_text(
        '{"one_line":"x","one_paragraph":"y","detailed":"z"}',
        encoding="utf-8",
    )
    proc = subprocess.run(
        [
            sys.executable, "-m", "scripts.personas", "run", "consistency-checker",
            "--text", "some body",
            "--output-file", str(out),
        ],
        capture_output=True, text=True, check=False, cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, proc.stderr
    assert "one_line" in proc.stdout


def test_fact_checker_persona_loads():
    p = personas.load_persona("fact-checker")
    assert p["output_kind"] == "sibling_suffix"
    assert set(p["input_kinds"]) == {"text", "file", "vault_page"}
    assert p["body"].strip()


def test_terminology_manager_persona_loads():
    p = personas.load_persona("terminology-manager")
    assert p["output_kind"] == "stdout"
    assert set(p["input_kinds"]) == {"text", "file", "vault_page"}
    assert p["body"].strip()


def test_consistency_checker_persona_loads():
    p = personas.load_persona("consistency-checker")
    assert p["output_kind"] == "stdout"
    assert set(p["input_kinds"]) == {"text", "file", "vault_page"}
    assert p["body"].strip()


def test_wiki_librarian_persona_loads():
    p = personas.load_persona("wiki-librarian")
    assert p["output_kind"] == "stdout"
    assert set(p["input_kinds"]) == {"text", "vault_page"}
    assert p["body"].strip()


def test_curator_persona_loads():
    p = personas.load_persona("curator")
    assert p["output_kind"] == "stdout"
    assert set(p["input_kinds"]) == {"text", "vault_page"}
    assert p["body"].strip()


def test_all_kept_personas_present():
    names = {p["name"] for p in personas.list_personas()}
    assert names == {"wiki-librarian", "wiki-auditor", "curator", "fact-checker",
                     "consistency-checker", "terminology-manager"}


def test_resolve_input_invalid_vault_id_raises_persona_error(tmp_path):
    """Invalid vault_id must surface as PersonaError, not VaultError (regression guard)."""
    db = tmp_path / "registry.db"
    registry.init_db(db)
    # vault_id 9999 never added → registry.get_vault_root raises VaultError
    # personas.resolve_input must catch it and re-raise as PersonaError.
    with pytest.raises(personas.PersonaError, match="unknown vault_id=9999"):
        personas.resolve_input(
            vault_relpath="wiki/summaries/demo.md",
            db_path=db,
            vault_id=9999,
        )
    # Confirm it does NOT leak VaultError at the top level.
    from scripts.registry import VaultError
    try:
        personas.resolve_input(
            vault_relpath="wiki/summaries/demo.md",
            db_path=db,
            vault_id=9999,
        )
    except VaultError:
        pytest.fail("VaultError leaked past PersonaError boundary in resolve_input")
    except personas.PersonaError:
        pass  # expected


def test_resolve_output_path_new_page_invalid_vault_id_raises_persona_error(tmp_path):
    """resolve_output_path new_page with invalid vault_id must raise PersonaError."""
    db = tmp_path / "registry.db"
    registry.init_db(db)
    persona = {"output_kind": "new_page"}
    with pytest.raises(personas.PersonaError, match="unknown vault_id=9999"):
        personas.resolve_output_path(
            persona=persona,
            source_meta={"kind": "text", "origin": None},
            db_path=db,
            vault_id=9999,
            title="Some Title",
        )
    from scripts.registry import VaultError
    try:
        personas.resolve_output_path(
            persona=persona,
            source_meta={"kind": "text", "origin": None},
            db_path=db,
            vault_id=9999,
            title="Some Title",
        )
    except VaultError:
        pytest.fail("VaultError leaked past PersonaError boundary in resolve_output_path")
    except personas.PersonaError:
        pass  # expected
