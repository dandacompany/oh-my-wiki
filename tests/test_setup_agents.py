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
