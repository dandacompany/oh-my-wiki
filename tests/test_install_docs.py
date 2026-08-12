from pathlib import Path


REPO = Path(__file__).resolve().parents[1]


def test_no_plugin_marketplace_in_install_docs():
    for name in ["README.md", "TUTORIAL.md", "TUTORIAL.ko.md", "SKILL.md"]:
        t = (REPO / name).read_text(encoding="utf-8")
        assert "/plugin marketplace" not in t, f"{name} still has marketplace install"
        assert "oh-my-wiki-marketplace" not in t, f"{name} still references the marketplace"


def test_readme_orders_pypi_first():
    t = (REPO / "README.md").read_text(encoding="utf-8")
    assert t.index("pipx install oh-my-wiki") < t.index("git clone https://github.com/dandacompany/oh-my-wiki")


def test_readme_discloses_recall_capture_and_codex_trust():
    text = (REPO / "README.md").read_text(encoding="utf-8")
    for required in (
        "PreToolUse", "PreCompact", "session_captures",
        "--session-capture off", "`/hooks`", "30 days", "untrusted JSON data",
    ):
        assert required in text, f"README.md omits recall contract {required!r}"
    assert "The 18 CLI subcommands" not in text
    assert "Run `omw help`" in text


def test_tutorials_use_current_session_and_search_contract():
    for name in ("TUTORIAL.md", "TUTORIAL.ko.md"):
        text = (REPO / name).read_text(encoding="utf-8")
        for required in ("PreToolUse", "PreCompact", "omw recall sessions", "--session-capture off"):
            assert required in text, f"{name} omits {required!r}"
        assert "python3 -m scripts.hot_cache" not in text
        assert "not full body text" not in text
        assert "본문 전체가 아니라" not in text


def test_skill_docs_use_cli_and_do_not_repeat_stale_release_status():
    skill = (REPO / "SKILL.md").read_text(encoding="utf-8")
    alias = (REPO / "omw" / "SKILL.md").read_text(encoding="utf-8")
    assert "\nomw status\n" in skill
    assert "python3 -m scripts.wizard status" not in skill
    assert "run its inline `python3" not in skill
    assert "v2 in progress" not in alias


def test_rendered_tutorial_sources_track_current_hook_surface():
    sources = [
        REPO / "docs" / "tutorial-omw" / "build_tutorial_omw.py",
        REPO / "docs" / "tutorial-reference" / "build_tutorial_reference.py",
    ]
    for path in sources:
        text = path.read_text(encoding="utf-8")
        for required in ("PreToolUse", "PreCompact", "omw recall sessions"):
            assert required in text, f"{path.name} omits {required!r}"
        assert "SessionStart + UserPromptSubmit" not in text
        assert "FTS는 본문이 아니라" not in text


def test_legacy_hot_cache_hook_bundle_is_not_distributed():
    assert not (REPO / "hooks" / "hooks.json").exists()
    assert not (REPO / "commands" / "hot-cache.md").exists()
    setup_py = (REPO / "setup.py").read_text(encoding="utf-8")
    manifest = (REPO / "MANIFEST.in").read_text(encoding="utf-8")
    assert '    "hooks",' not in setup_py
    assert "graft hooks" not in manifest
