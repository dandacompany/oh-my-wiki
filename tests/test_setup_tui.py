import scripts.setup_wizard as sw
from scripts import platform_env


def test_ensure_present_no_install(monkeypatch):
    monkeypatch.setattr(sw, "_WIZARD_UI_TRIED", False)
    monkeypatch.setattr(sw, "_questionary_available", lambda: True)
    called = []
    monkeypatch.setattr(sw.subprocess, "run", lambda *a, **k: called.append(a))
    assert sw.ensure_wizard_ui() is True
    assert called == []


def test_ensure_non_tty_no_install(monkeypatch):
    monkeypatch.setattr(sw, "_WIZARD_UI_TRIED", False)
    monkeypatch.setattr(sw, "_questionary_available", lambda: False)
    monkeypatch.delenv("OMW_BOOTSTRAP_YES", raising=False)
    monkeypatch.setattr(sw.sys.stdin, "isatty", lambda: False)
    called = []
    monkeypatch.setattr(sw.subprocess, "run", lambda *a, **k: called.append(a))
    assert sw.ensure_wizard_ui() is False
    assert called == []


def test_ensure_confirmed_install_runs_pip(monkeypatch):
    monkeypatch.setattr(sw, "_WIZARD_UI_TRIED", False)
    monkeypatch.setattr(sw, "_questionary_available", lambda: False)  # stays missing in test env
    monkeypatch.setenv("OMW_BOOTSTRAP_YES", "1")
    monkeypatch.setattr(platform_env, "pip_install_argv", lambda p: ["pipx", "inject", "oh-my-wiki", p])
    runs = []
    import subprocess as _sp
    monkeypatch.setattr(sw.subprocess, "run", lambda cmd, **k: runs.append(cmd) or _sp.CompletedProcess(cmd, 0))
    inval = []
    monkeypatch.setattr(sw.importlib, "invalidate_caches", lambda: inval.append(True))
    sw.ensure_wizard_ui()
    assert runs == [["pipx", "inject", "oh-my-wiki", "questionary"]]
    assert inval == [True]


def test_ensure_one_attempt_per_process(monkeypatch):
    monkeypatch.setattr(sw, "_WIZARD_UI_TRIED", False)
    monkeypatch.setattr(sw, "_questionary_available", lambda: False)
    monkeypatch.setenv("OMW_BOOTSTRAP_YES", "1")
    monkeypatch.setattr(platform_env, "pip_install_argv", lambda p: ["x"])
    runs = []
    import subprocess as _sp
    monkeypatch.setattr(sw.subprocess, "run", lambda cmd, **k: runs.append(cmd) or _sp.CompletedProcess(cmd, 0))
    monkeypatch.setattr(sw.importlib, "invalidate_caches", lambda: None)
    sw.ensure_wizard_ui()
    sw.ensure_wizard_ui()
    assert len(runs) == 1  # second call short-circuits on the flag


def test_prompt_invokes_ensure(monkeypatch):
    spy = []
    monkeypatch.setattr(sw, "ensure_wizard_ui", lambda: spy.append(True) or True)
    # Use a kind whose fallback needs no input(): patch input to avoid blocking if questionary absent.
    monkeypatch.setattr("builtins.input", lambda *a, **k: "")
    sw._prompt("text", "Vault name", default="v")
    assert spy == [True]


def test_run_interactive_uses_selectors(monkeypatch, tmp_path):
    monkeypatch.setenv("OMW_HOME", str(tmp_path / ".omw"))
    calls = []

    def fake_prompt(kind, message, *, choices=None, default=None):
        calls.append((kind, tuple(choices) if choices else None))
        return default

    monkeypatch.setattr(sw, "_prompt", fake_prompt)
    monkeypatch.setattr(sw, "ensure_home", lambda: None)
    monkeypatch.setattr(sw, "_ensure_vault", lambda *a, **k: None)
    monkeypatch.setattr(sw, "_write_config", lambda *a, **k: None)

    rc = sw._run_interactive("demo", "wiki", "obsidian", "global", in_wizard=True)
    assert rc == 0
    kinds = {c[0] for c in calls}
    # mode/type/location are selectors; name is text
    assert ("select", ("wiki", "memo")) in calls
    assert ("select", ("obsidian", "markdown")) in calls
    assert any(c[0] == "select" and c[1] and "global" in c[1] for c in calls)
    assert any(c[0] == "text" for c in calls)  # vault name


def test_run_interactive_custom_location_asks_path(monkeypatch, tmp_path):
    monkeypatch.setenv("OMW_HOME", str(tmp_path / ".omw"))
    seq = iter([
        ("text", "demo"),          # name
        ("select", "wiki"),        # mode
        ("select", "obsidian"),    # type
        ("select", "custom path…"),  # location choice → triggers a text path prompt
        ("text", "/abs/vault"),    # custom path
    ])
    captured = []

    def fake_prompt(kind, message, *, choices=None, default=None):
        captured.append(kind)
        try:
            return next(seq)[1]
        except StopIteration:
            return default

    monkeypatch.setattr(sw, "_prompt", fake_prompt)
    monkeypatch.setattr(sw, "ensure_home", lambda: None)
    captured_loc = {}
    monkeypatch.setattr(sw, "_ensure_vault", lambda name, mode, type_, location: captured_loc.update(loc=location))
    monkeypatch.setattr(sw, "_write_config", lambda *a, **k: None)

    sw._run_interactive("demo", "wiki", "obsidian", "global", in_wizard=True)
    assert captured_loc["loc"] == "/abs/vault"      # the custom text path was used
    assert captured.count("text") == 2              # name + custom path
