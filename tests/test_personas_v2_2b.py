"""Tests for v2.2b additions: sibling_suffix output_kind."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import personas


@pytest.fixture
def tmp_persona_factcheck(tmp_path, monkeypatch):
    """Install a minimal fact-checker stub persona at personas/."""
    root = tmp_path / "personas"
    root.mkdir()
    (root / "stub-reviewer.md").write_text(
        "---\n"
        "name: stub-reviewer\n"
        "description: Stub for sibling_suffix tests\n"
        "capabilities: [review]\n"
        "tools: []\n"
        "model_hint: standard\n"
        "input_kinds: [file]\n"
        "output_kind: sibling_suffix\n"
        "access: read-only\n"
        "---\n"
        "stub body\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(personas, "PERSONAS_ROOT", root)
    return root


def test_sibling_suffix_output_path(tmp_path, tmp_persona_factcheck):
    persona = personas.load_persona("stub-reviewer")
    source = tmp_path / "page.md"
    source.write_text("body\n", encoding="utf-8")
    target = personas.resolve_output_path(
        persona=persona,
        source_meta={"kind": "file", "origin": source},
        suffix="factcheck",
    )
    assert target == source.with_name("page.factcheck.md")


def test_sibling_suffix_requires_suffix(tmp_path, tmp_persona_factcheck):
    persona = personas.load_persona("stub-reviewer")
    source = tmp_path / "page.md"
    source.write_text("body\n", encoding="utf-8")
    with pytest.raises(personas.PersonaError, match="suffix"):
        personas.resolve_output_path(
            persona=persona,
            source_meta={"kind": "file", "origin": source},
        )


def test_sibling_suffix_requires_origin(tmp_persona_factcheck):
    persona = personas.load_persona("stub-reviewer")
    with pytest.raises(personas.PersonaError, match="origin"):
        personas.resolve_output_path(
            persona=persona,
            source_meta={"kind": "text", "origin": None},
            suffix="factcheck",
        )


def test_sibling_suffix_cli_end_to_end(tmp_path, monkeypatch):
    """Full CLI: persona definition + source file → sibling_suffix file produced."""
    project_root = Path(__file__).resolve().parents[1]
    personas_dir = project_root / "personas"
    stub = personas_dir / "stub-reviewer-cli.md"
    stub.write_text(
        "---\n"
        "name: stub-reviewer-cli\n"
        "description: CLI stub\n"
        "capabilities: [review]\n"
        "tools: []\n"
        "model_hint: standard\n"
        "input_kinds: [file]\n"
        "output_kind: sibling_suffix\n"
        "access: read-only\n"
        "---\n"
        "stub body\n",
        encoding="utf-8",
    )
    try:
        source = tmp_path / "page.md"
        source.write_text("source body\n", encoding="utf-8")
        output = tmp_path / "llm-output.md"
        output.write_text("# Fact-check report\n", encoding="utf-8")
        result = subprocess.run(
            [sys.executable, "-m", "scripts.personas", "run", "stub-reviewer-cli",
             "--file", str(source),
             "--suffix", "factcheck",
             "--output-file", str(output)],
            capture_output=True, text=True, cwd=project_root,
        )
        assert result.returncode == 0, result.stderr
        produced = source.with_name("page.factcheck.md")
        assert produced.exists()
        assert produced.read_text(encoding="utf-8") == "# Fact-check report\n"
    finally:
        stub.unlink(missing_ok=True)


def test_fact_checker_persona_loads():
    persona = personas.load_persona("fact-checker")
    assert persona["name"] == "fact-checker"
    assert persona["output_kind"] == "sibling_suffix"
    assert "vault_page" in persona["input_kinds"]
    assert "file" in persona["input_kinds"]
    assert "mcp__brightdata__search_engine" in persona["tools"]
    assert len(persona["body"]) > 500  # substantive prompt
    assert "atomic claim" in persona["body"].lower()
    assert "confidence" in persona["body"].lower()
    assert persona["model_hint"] == "most_capable"


def test_consistency_checker_persona_loads():
    persona = personas.load_persona("consistency-checker")
    assert persona["name"] == "consistency-checker"
    assert persona["output_kind"] == "stdout"
    assert "vault_page" in persona["input_kinds"]
    assert len(persona["body"]) > 400
    assert "contradiction" in persona["body"].lower()
    assert persona["model_hint"] == "standard"


def test_terminology_manager_persona_loads():
    persona = personas.load_persona("terminology-manager")
    assert persona["name"] == "terminology-manager"
    assert persona["output_kind"] == "stdout"
    assert len(persona["body"]) > 400
    assert "glossary" in persona["body"].lower()
    assert "canonical" in persona["body"].lower()
    assert persona["model_hint"] == "standard"
