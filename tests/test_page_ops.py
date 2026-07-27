from pathlib import Path

from scripts import links, page_ops, registry
from scripts.paths import fallback_trash_root
from tests.conftest import make_vault_with_pages


def test_wiki_soft_delete_moves_to_trash_and_rewrites_backlinks(tmp_path, monkeypatch):
    db, vault_id = make_vault_with_pages(tmp_path, monkeypatch, pages={
        "wiki/concepts/target.md": "# Target\n",
        "wiki/summaries/source.md": "# Source\n\nSee [[target|the target]].\n",
    })
    root = tmp_path / "vault"
    (root / ".trash").mkdir()

    result = page_ops.delete(
        db, vault_id=vault_id, relpath="wiki/concepts/target.md", hard=False
    )

    assert result["trash"].startswith(".trash/")
    assert (root / result["trash"]).is_file()
    assert not (root / "wiki/concepts/target.md").exists()
    assert "See the target." in (root / "wiki/summaries/source.md").read_text()
    assert links.broken_links(db, vault_id) == []
    assert all(r["relpath"] != "wiki/concepts/target.md"
               for r in registry.list_notes(db, vault_id=vault_id))


def test_wiki_soft_delete_uses_registry_side_fallback(tmp_path, monkeypatch):
    db, vault_id = make_vault_with_pages(tmp_path, monkeypatch, pages={
        "wiki/concepts/target.md": "# Target\n",
    })
    fallback = fallback_trash_root("default")
    fallback.mkdir(parents=True)
    registry.update_mode_config(
        db, "default", config_json='{"trash_dir": "' + str(fallback) + '"}'
    )

    result = page_ops.delete(
        db, vault_id=vault_id, relpath="wiki/concepts/target.md", hard=False
    )

    assert Path(result["trash"]).parent == fallback
    assert Path(result["trash"]).is_file()


def test_wiki_delete_removes_frontmatter_and_inline_relations(tmp_path, monkeypatch):
    db, vault_id = make_vault_with_pages(tmp_path, monkeypatch, pages={
        "wiki/concepts/target.md": "# Target\n",
        "wiki/concepts/source.md": (
            "---\nrelations:\n  uses:\n    - '[[target]]'\n---\n"
            "# Source\n\nuses:: [[target]]\n"
        ),
    })
    root = tmp_path / "vault"
    (root / ".trash").mkdir()

    result = page_ops.delete(
        db, vault_id=vault_id, relpath="wiki/concepts/target.md", hard=False
    )

    text = (root / "wiki/concepts/source.md").read_text(encoding="utf-8")
    assert "[[target]]" not in text
    assert "uses::" not in text
    assert result["backlinks_skipped"] == []
    assert links.broken_links(db, vault_id) == []
