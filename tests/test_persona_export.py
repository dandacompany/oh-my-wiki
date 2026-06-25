from pathlib import Path  # noqa: F401  # used in test_persona_export_hermes_profile

from scripts import persona_export as pe


def test_render_block_lists_enabled_main_and_invocation():
    block = pe.render_block(
        ["researcher", "curator"], "researcher",
        {"researcher": "Research a topic", "curator": "Sync the index"},
    )
    assert "<!-- omw-personas:start -->" in block
    assert "<!-- omw-personas:end -->" in block
    assert "**researcher**" in block and "**curator**" in block
    assert "Main persona: **researcher**" in block
    assert "omw skill" in block


def test_upsert_marker_creates_file(tmp_path):
    p = tmp_path / "AGENTS.md"
    pe.upsert_marker(p, pe.render_block(["researcher"], "researcher", {"researcher": "x"}))
    text = p.read_text()
    assert text.count("<!-- omw-personas:start -->") == 1
    assert text.count("<!-- omw-personas:end -->") == 1


def test_upsert_marker_preserves_other_content_and_is_idempotent(tmp_path):
    p = tmp_path / "CLAUDE.md"
    p.write_text("# My project\n\nExisting guidance.\n", encoding="utf-8")
    block1 = pe.render_block(["researcher"], "researcher", {"researcher": "v1"})
    pe.upsert_marker(p, block1)
    block2 = pe.render_block(["researcher", "curator"], "curator",
                             {"researcher": "v2", "curator": "c"})
    pe.upsert_marker(p, block2)  # re-run replaces, not appends
    text = p.read_text()
    assert "# My project" in text and "Existing guidance." in text   # preserved
    assert text.count("<!-- omw-personas:start -->") == 1            # no dup
    assert "Main persona: **curator**" in text                       # replaced
    assert "v1" not in text                                          # old block gone


def test_export_personas_writes_all_hosts_and_no_claude_native(tmp_path):
    written = pe.export_personas(
        enabled=["researcher"], main="researcher",
        descriptions={"researcher": "Research a topic"},
        base_dir=tmp_path, hosts=["claude", "codex", "gemini"],
    )
    assert {p.name for p in written} == {"CLAUDE.md", "AGENTS.md", "GEMINI.md"}
    for f in ("CLAUDE.md", "AGENTS.md", "GEMINI.md"):
        assert "<!-- omw-personas:start -->" in (tmp_path / f).read_text()
    # universality guard: NO claude-native subagent dir/files created
    assert not (tmp_path / ".claude").exists()


def test_export_personas_rejects_unknown_host(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        pe.export_personas(enabled=["researcher"], main="researcher",
                           descriptions={}, base_dir=tmp_path, hosts=["notion"])


def test_codex_opencode_dedup_single_agents_block(tmp_path):
    from scripts import persona_export
    persona_export.export_personas(
        enabled=["wiki-librarian"], main="wiki-librarian", descriptions={},
        base_dir=tmp_path, hosts=["codex", "opencode"])
    agents = (tmp_path / "AGENTS.md").read_text()
    assert agents.count("<!-- omw-personas:start -->") == 1   # written once, not twice
    assert not (tmp_path / "CLAUDE.md").exists()


def test_persona_export_hermes_profile(tmp_path, monkeypatch):
    from scripts import persona_export
    home = tmp_path / "home"
    (home / ".hermes" / "profiles" / "iris").mkdir(parents=True)
    (home / ".hermes" / "profiles" / "iris" / "SOUL.md").write_text("# Identity\n\nexisting\n")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    persona_export.export_personas(
        enabled=["wiki-librarian"], main="wiki-librarian", descriptions={},
        base_dir=tmp_path, hosts=["hermes"], profile="iris")
    soul = (home / ".hermes" / "profiles" / "iris" / "SOUL.md").read_text()
    assert "# Identity" in soul and "existing" in soul   # host content preserved
    assert "<!-- omw-personas:start -->" in soul         # managed block added
