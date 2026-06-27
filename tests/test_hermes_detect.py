import pytest

from scripts import hermes_detect as hd


def test_in_hermes_session_true_when_session_id(monkeypatch):
    monkeypatch.setenv("HERMES_SESSION_ID", "s-1")
    monkeypatch.delenv("HERMES_PROFILE", raising=False)
    assert hd.in_hermes_session() is True


def test_in_hermes_session_true_when_profile(monkeypatch):
    monkeypatch.delenv("HERMES_SESSION_ID", raising=False)
    monkeypatch.setenv("HERMES_PROFILE", "sophie")
    assert hd.in_hermes_session() is True


def test_in_hermes_session_false_when_neither(monkeypatch):
    monkeypatch.delenv("HERMES_SESSION_ID", raising=False)
    monkeypatch.delenv("HERMES_PROFILE", raising=False)
    assert hd.in_hermes_session() is False


def test_list_profiles_reads_profile_dirs(tmp_path):
    profiles = tmp_path / "profiles"
    (profiles / "sophie").mkdir(parents=True)
    (profiles / "sophie" / "config.yaml").write_text("model: x\n")
    (profiles / "iris").mkdir()
    (profiles / "iris" / "SOUL.md").write_text("soul\n")
    (profiles / "junk").mkdir()  # no config.yaml/SOUL.md -> excluded
    assert hd.list_profiles(home=tmp_path) == ["iris", "sophie"]


def test_resolve_assignee_prefers_explicit(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_PROFILE", "sophie")
    assert hd.resolve_assignee("mark", home=tmp_path) == "mark"


def test_resolve_assignee_uses_env_profile(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_PROFILE", "sophie")
    assert hd.resolve_assignee(home=tmp_path) == "sophie"


def test_resolve_assignee_single_profile_fallback(monkeypatch, tmp_path):
    monkeypatch.delenv("HERMES_PROFILE", raising=False)
    p = tmp_path / "profiles" / "only"
    p.mkdir(parents=True)
    (p / "config.yaml").write_text("model: x\n")
    assert hd.resolve_assignee(home=tmp_path) == "only"


def test_resolve_assignee_ambiguous_raises(monkeypatch, tmp_path):
    monkeypatch.delenv("HERMES_PROFILE", raising=False)
    for n in ("a", "b"):
        d = tmp_path / "profiles" / n
        d.mkdir(parents=True)
        (d / "config.yaml").write_text("model: x\n")
    with pytest.raises(hd.AmbiguousProfile) as exc:
        hd.resolve_assignee(home=tmp_path)
    assert sorted(exc.value.choices) == ["a", "b"]
