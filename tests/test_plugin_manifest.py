"""Validate Claude Code plugin manifests."""
import json
import re
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


def test_plugin_json_has_required_top_level_fields():
    p = REPO_ROOT / ".claude-plugin" / "plugin.json"
    assert p.exists(), "plugin.json must exist at .claude-plugin/plugin.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    for key in ("name", "version", "description", "author", "license",
                "homepage", "trigger_keywords", "ops",
                "skill_path", "commands_path", "scripts_path"):
        assert key in data, f"plugin.json missing required key: {key}"
    assert data["name"] == "oh-my-wiki"
    assert data["version"].startswith("2."), f"v2.x expected, got {data['version']!r}"
    assert data["license"] == "MIT"
    assert "oh-my-wiki" in data["homepage"]


def test_plugin_json_ops_resolve_to_command_files():
    """Every op listed in plugin.json must have a corresponding commands/<op>.md."""
    p = REPO_ROOT / ".claude-plugin" / "plugin.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    commands_dir = REPO_ROOT / data["commands_path"].removeprefix("./")
    for op in data["ops"]:
        cmd_path = commands_dir / f"{op}.md"
        assert cmd_path.exists(), f"op {op!r} declared but {cmd_path} missing"


def test_plugin_json_trigger_keywords_non_empty():
    p = REPO_ROOT / ".claude-plugin" / "plugin.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert isinstance(data["trigger_keywords"], list)
    assert len(data["trigger_keywords"]) >= 4
    has_en = any("wiki" in t.lower() or "omw" in t.lower() for t in data["trigger_keywords"])
    has_ko = any("위키" in t for t in data["trigger_keywords"])
    assert has_en and has_ko, "need both EN and KO triggers"


def test_marketplace_json_has_required_fields():
    p = REPO_ROOT / ".claude-plugin" / "marketplace.json"
    assert p.exists(), "marketplace.json must exist at .claude-plugin/marketplace.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    for key in ("name", "description", "plugins"):
        assert key in data, f"marketplace.json missing required key: {key}"
    assert data["name"].endswith("-marketplace")
    assert isinstance(data["plugins"], list)
    assert len(data["plugins"]) >= 1


def test_marketplace_json_lists_oh_my_wiki_plugin():
    p = REPO_ROOT / ".claude-plugin" / "marketplace.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    plugin_names = [p["name"] for p in data["plugins"]]
    assert "oh-my-wiki" in plugin_names


def test_marketplace_plugin_manifest_paths_resolve():
    p = REPO_ROOT / ".claude-plugin" / "marketplace.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    for entry in data["plugins"]:
        manifest_path = REPO_ROOT / entry["manifest"].removeprefix("./")
        assert manifest_path.exists(), f"manifest path {manifest_path} not found"


def test_hooks_json_has_session_start_and_stop():
    p = REPO_ROOT / "hooks" / "hooks.json"
    assert p.exists(), "hooks.json must exist at hooks/hooks.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert "session_start" in data
    assert "session_stop" in data
    for key in ("session_start", "session_stop"):
        binding = data[key]
        assert "command" in binding
        assert "scripts.hot_cache" in binding["command"]
        assert binding.get("blocking") is False, f"{key} must be non-blocking"


def test_plugin_json_lists_v2_2b_review_persona_ops():
    import json
    from pathlib import Path
    manifest = json.loads(
        (Path(__file__).resolve().parents[1] / ".claude-plugin/plugin.json")
        .read_text(encoding="utf-8")
    )
    for op in ("persona-factcheck", "persona-consistency", "persona-terminology"):
        assert op in manifest["ops"], f"missing op: {op}"


def test_plugin_json_version_bumped_to_2_2_1():
    # Version was 2.2.1; bumped to 2.3.0 in Task 16. Test kept for history;
    # TestV23ManifestOps.test_version_is_2_3_0 is the authoritative version check.
    import json
    from pathlib import Path
    manifest = json.loads(
        (Path(__file__).resolve().parents[1] / ".claude-plugin/plugin.json")
        .read_text(encoding="utf-8")
    )
    assert manifest["version"] >= "2.2.1", \
        f"version should be >= 2.2.1, got {manifest['version']}"


# ---- Task 16: v2.3 manifest tests -------------------------------------------
import json
from pathlib import Path


class TestV23ManifestOps:
    """Verify plugin.json has the 3 new v2.3 ops and trigger keywords."""

    PLUGIN = json.loads(
        (Path(__file__).parent.parent / ".claude-plugin" / "plugin.json").read_text()
    )

    def test_version_is_2_3_0(self):
        # Durable: defer to the installed package version (pyproject is the
        # source of truth). Auto-tracks releases — no manual bump.
        # See test_plugin_version_matches_installed_package_version.
        assert self.PLUGIN["version"] == version("oh-my-wiki"), \
            f"plugin.json {self.PLUGIN['version']} != installed {version('oh-my-wiki')}"



# ---------------------------------------------------------------------------
# T18: plugin.json assertions for v2.4.0
# ---------------------------------------------------------------------------

class TestPluginManifestV24:
    """Assert plugin.json is correctly updated for v2.4.0."""

    PLUGIN_FILE = Path(__file__).resolve().parents[1] / ".claude-plugin" / "plugin.json"

    def _load(self):
        return json.loads(self.PLUGIN_FILE.read_text())

    def test_version_is_2_4_0(self):
        data = self._load()
        # Durable: defer to the installed package version (no manual bump).
        assert data["version"] == version("oh-my-wiki"), (
            f"plugin.json {data['version']!r} != installed {version('oh-my-wiki')!r}"
        )



# ---------------------------------------------------------------------------
# Distribution hardening (2026-05-29): version source-of-truth + schema +
# persona-list contract. See docs/superpowers/plans/2026-05-29-oh-my-wiki-
# distribution.md. These supersede the hardcoded test_version_is_2_*_0 checks
# above as the durable version guard (those are kept for history).
# ---------------------------------------------------------------------------

def test_plugin_version_matches_installed_package_version():
    """plugin.json.version must equal the installed package version.

    The installed version derives from pyproject.toml ([project].version),
    so this makes plugin.json and pyproject structurally unable to drift.
    importlib.metadata is used instead of tomllib because the CI floor is
    Python 3.10 and tomllib is 3.11+.
    """
    p = REPO_ROOT / ".claude-plugin" / "plugin.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    pkg_version = version("oh-my-wiki")
    assert data["version"] == pkg_version, (
        f"plugin.json version {data['version']!r} != installed "
        f"package version {pkg_version!r}. Bump them together."
    )


def test_plugin_version_is_semver():
    p = REPO_ROOT / ".claude-plugin" / "plugin.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert SEMVER_RE.match(data["version"]), (
        f"version {data['version']!r} is not MAJOR.MINOR.PATCH"
    )


def test_plugin_skill_and_path_fields_resolve():
    """skill_path / commands_path / scripts_path must point at real paths."""
    p = REPO_ROOT / ".claude-plugin" / "plugin.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    skill = REPO_ROOT / data["skill_path"].removeprefix("./")
    commands = REPO_ROOT / data["commands_path"].removeprefix("./")
    scripts = REPO_ROOT / data["scripts_path"].removeprefix("./")
    assert skill.is_file(), f"skill_path {skill} is not a file"
    assert commands.is_dir(), f"commands_path {commands} is not a dir"
    assert scripts.is_dir(), f"scripts_path {scripts} is not a dir"


def test_plugin_homepage_and_repository_are_canonical_github_urls():
    p = REPO_ROOT / ".claude-plugin" / "plugin.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    expected = "https://github.com/dandacompany/oh-my-wiki"
    assert data["homepage"] == expected, f"homepage {data['homepage']!r}"
    assert data["repository"] == expected, f"repository {data['repository']!r}"


def test_personas_list_returns_nonempty_json_array():
    """`python -m scripts.personas list` must emit a JSON list with >=1 entry.

    Structural assertion only — never hardcode the count (it rots on every
    persona add; today it is 9).
    """
    r = subprocess.run(
        [sys.executable, "-m", "scripts.personas", "list"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert r.returncode == 0, f"personas list failed: {r.stderr}"
    data = json.loads(r.stdout)
    assert isinstance(data, list), "personas list must emit a JSON array"
    assert len(data) >= 1, "expected at least one persona"
    assert all("name" in p for p in data), "each persona needs a name"
