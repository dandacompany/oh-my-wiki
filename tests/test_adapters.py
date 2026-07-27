from unittest.mock import patch

import pytest

from scripts import adapters


def test_get_adapter_returns_markdown(tmp_path):
    a = adapters.get_adapter("markdown")
    assert isinstance(a, adapters.MarkdownAdapter)


def test_get_adapter_unknown_type_raises():
    with pytest.raises(adapters.AdapterError):
        adapters.get_adapter("notion")


def test_markdown_link_syntax_uses_standard_markdown():
    a = adapters.MarkdownAdapter()
    assert a.link_syntax("concepts/karpathy") == "[karpathy](./concepts/karpathy.md)"


def test_markdown_is_valid_accepts_existing_dir(markdown_vault_path):
    a = adapters.MarkdownAdapter()
    assert a.is_valid(markdown_vault_path) is True


def test_markdown_is_valid_rejects_nonexistent(tmp_path):
    a = adapters.MarkdownAdapter()
    assert a.is_valid(tmp_path / "missing") is False


def test_markdown_init_vault_memo_mode_creates_inbox_and_trash(tmp_path):
    a = adapters.MarkdownAdapter()
    root = tmp_path / "new-vault"
    a.init_vault(root, mode="memo")
    assert (root / "inbox").is_dir()
    assert (root / ".trash").is_dir()


def test_markdown_init_vault_wiki_mode_creates_three_layers(tmp_path):
    a = adapters.MarkdownAdapter()
    root = tmp_path / "wv"
    a.init_vault(root, mode="wiki")
    assert (root / "raw").is_dir()
    assert (root / "wiki").is_dir()
    assert (root / "wiki" / "index.md").is_file()
    assert (root / "wiki" / "log.md").is_file()


def test_markdown_init_vault_falls_back_when_local_trash_is_reserved(
        tmp_path, monkeypatch):
    monkeypatch.setenv("OMW_HOME", str(tmp_path / "home"))
    root = tmp_path / "nas" / "course"
    original_mkdir = adapters.Path.mkdir

    def smb_mkdir(path, *args, **kwargs):
        if path == root / ".trash":
            raise FileNotFoundError("reserved by smbfs")
        return original_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(adapters.Path, "mkdir", smb_mkdir)
    trash = adapters.get_adapter("markdown", vault_name="inflearn-course").init_vault(
        root, "wiki"
    )

    assert root.is_dir()
    assert (root / "wiki" / "index.md").is_file()
    assert trash == tmp_path / "home" / ".trash" / "inflearn-course"
    assert trash.is_dir()


def test_markdown_open_invokes_os_open(tmp_path):
    a = adapters.MarkdownAdapter()
    target = tmp_path / "note.md"
    target.write_text("hi")
    with patch("scripts.adapters.subprocess.run") as run:
        a.open(target)
        assert run.called


def test_markdown_init_vault_unknown_mode_raises(tmp_path):
    a = adapters.MarkdownAdapter()
    with pytest.raises(adapters.AdapterError, match="unknown mode"):
        a.init_vault(tmp_path / "x", mode="invalid")


def test_obsidian_link_syntax_uses_wikilink():
    a = adapters.ObsidianAdapter()
    assert a.link_syntax("concepts/karpathy") == "[[concepts/karpathy]]"
    assert a.link_syntax("karpathy.md") == "[[karpathy]]"


def test_obsidian_is_valid_requires_dot_obsidian(obsidian_vault_path, tmp_path):
    a = adapters.ObsidianAdapter()
    assert a.is_valid(obsidian_vault_path) is True
    plain = tmp_path / "plain"
    plain.mkdir()
    assert a.is_valid(plain) is False


def test_obsidian_init_vault_creates_dot_obsidian(tmp_path):
    a = adapters.ObsidianAdapter()
    root = tmp_path / "ob-vault"
    a.init_vault(root, mode="wiki")
    assert (root / ".obsidian").is_dir()
    assert (root / "wiki" / "index.md").exists()


def test_obsidian_open_uses_uri_scheme(tmp_path):
    a = adapters.ObsidianAdapter(vault_name="research")
    target = tmp_path / "research" / "concepts" / "x.md"
    target.parent.mkdir(parents=True)
    target.write_text("hi")
    with patch("scripts.adapters.subprocess.run") as run:
        a.open(target, vault_root=tmp_path / "research")
        args = run.call_args.args[0]
        assert any("obsidian://open" in arg for arg in args)
        assert any("vault=research" in arg for arg in args)


def test_obsidian_open_preserves_slash_in_nested_path(tmp_path):
    a = adapters.ObsidianAdapter(vault_name="research")
    nested = tmp_path / "research" / "concepts" / "deep" / "x.md"
    nested.parent.mkdir(parents=True)
    nested.write_text("hi")
    with patch("scripts.adapters.subprocess.run") as run:
        a.open(nested, vault_root=tmp_path / "research")
        args = run.call_args.args[0]
        # The file= portion must preserve forward slashes for Obsidian to resolve nested paths
        assert any("file=concepts/deep/x.md" in arg for arg in args)
        assert not any("%2F" in arg for arg in args)
