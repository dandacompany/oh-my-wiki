import builtins

from scripts import setup_wizard


def test_checkbox_spec_plain_strings():
    names, checked, has_flag = setup_wizard._checkbox_spec(["a", "b", "c"])
    assert names == ["a", "b", "c"]
    assert checked == []
    assert has_flag is False


def test_checkbox_spec_dicts():
    names, checked, has_flag = setup_wizard._checkbox_spec(
        [{"name": "main", "checked": True}, {"name": "iris", "checked": False}])
    assert names == ["main", "iris"]
    assert checked == ["main"]
    assert has_flag is True


def test_prompt_checkbox_fallback_blank_keeps_checked(monkeypatch):
    # Force the input() fallback by hiding questionary.
    monkeypatch.setitem(__import__("sys").modules, "questionary", None)
    monkeypatch.setattr(builtins, "input", lambda *_a, **_k: "")
    out = setup_wizard._prompt("checkbox", "pick",
                               choices=[{"name": "main", "checked": True},
                                        {"name": "iris", "checked": False}])
    assert out == ["main"]


def test_prompt_checkbox_fallback_blank_all_for_plain(monkeypatch):
    monkeypatch.setitem(__import__("sys").modules, "questionary", None)
    monkeypatch.setattr(builtins, "input", lambda *_a, **_k: "")
    out = setup_wizard._prompt("checkbox", "pick", choices=["a", "b"])
    assert out == ["a", "b"]


def test_prompt_checkbox_fallback_typed_subset(monkeypatch):
    monkeypatch.setitem(__import__("sys").modules, "questionary", None)
    monkeypatch.setattr(builtins, "input", lambda *_a, **_k: "iris")
    out = setup_wizard._prompt("checkbox", "pick",
                               choices=[{"name": "main", "checked": True},
                                        {"name": "iris", "checked": False}])
    assert out == ["iris"]


from pathlib import Path

from scripts import agent_skills


def _fake_targets(tmp_path, installed):
    """Build target dicts pointing at tmp dirs; `installed` = set of names."""
    base = tmp_path / ".hermes"
    targets = []
    for name in ["main", "iris", "mark"]:
        skills = (base / "skills") if name == "main" else (base / "profiles" / name / "skills")
        skills.mkdir(parents=True, exist_ok=True)
        if name in installed:
            (skills / "oh-my-wiki").mkdir(parents=True, exist_ok=True)
        targets.append({"name": name, "skills_dir": skills, "installed": name in installed})
    return targets


def test_install_hermes_noninteractive_refreshes_installed_only(tmp_path, monkeypatch):
    targets = _fake_targets(tmp_path, installed={"main", "mark"})
    monkeypatch.setattr(agent_skills, "hermes_profile_targets", lambda hermes_home=None: targets)
    results = setup_wizard._install_hermes_profiles(interactive=False)
    done = {r["name"] for r in results if r["ok"]}
    assert done == {"main", "mark"}
    # the un-installed profile 'iris' was not touched
    assert not (tmp_path / ".hermes" / "profiles" / "iris" / "skills" / "oh-my-wiki").exists()
    # the installed ones now contain the freshly copied bundle
    assert (tmp_path / ".hermes" / "skills" / "oh-my-wiki" / "SKILL.md").exists()


def test_install_hermes_noninteractive_main_fallback_when_none_installed(tmp_path, monkeypatch):
    targets = _fake_targets(tmp_path, installed=set())
    monkeypatch.setattr(agent_skills, "hermes_profile_targets", lambda hermes_home=None: targets)
    results = setup_wizard._install_hermes_profiles(interactive=False)
    assert {r["name"] for r in results if r["ok"]} == {"main"}
    assert (tmp_path / ".hermes" / "skills" / "oh-my-wiki" / "SKILL.md").exists()


def test_install_hermes_interactive_uses_selector(tmp_path, monkeypatch):
    targets = _fake_targets(tmp_path, installed={"main"})
    monkeypatch.setattr(agent_skills, "hermes_profile_targets", lambda hermes_home=None: targets)
    # selector returns the user's pick
    monkeypatch.setattr(setup_wizard, "_prompt", lambda *a, **k: ["main", "iris"])
    results = setup_wizard._install_hermes_profiles(interactive=True)
    assert {r["name"] for r in results if r["ok"]} == {"main", "iris"}
    assert (tmp_path / ".hermes" / "profiles" / "iris" / "skills" / "oh-my-wiki" / "SKILL.md").exists()


def test_setup_agents_routes_hermes_per_profile(tmp_path, monkeypatch, capsys):
    targets = _fake_targets(tmp_path, installed={"main"})
    monkeypatch.setattr(agent_skills, "detect_agents", lambda: ["hermes"])
    monkeypatch.setattr(agent_skills, "hermes_profile_targets", lambda hermes_home=None: targets)
    rc = setup_wizard.setup_agents(agents=["hermes"], noninteractive=True)
    assert rc == 0
    out = capsys.readouterr().out
    assert "hermes/main" in out
