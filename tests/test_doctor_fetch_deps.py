# tests/test_doctor_fetch_deps.py
from scripts import setup_wizard


def test_doctor_reports_fetch_deps(capsys, monkeypatch):
    monkeypatch.setattr("scripts.setup_wizard.shutil.which", lambda _: None)
    monkeypatch.setattr("scripts.fetch_chromium.available", lambda: False)
    setup_wizard.doctor()
    out = capsys.readouterr().out
    assert "yt-dlp" in out
    assert "chromium" in out
