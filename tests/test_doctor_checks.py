from scripts import setup_wizard


def test_doctor_checks_shape(tmp_path, monkeypatch):
    from tests.conftest import make_vault_with_pages
    make_vault_with_pages(tmp_path, monkeypatch, pages={"raw/a.md": "# A\n\nx"})
    d = setup_wizard.doctor_checks()
    assert set(d) >= {"ok", "items", "vaults", "sandbox_warning", "home", "registry"}
    names = [i["name"] for i in d["items"]]
    assert names[:2] == ["omw home", "registry"]
    assert {"yt-dlp", "chromium", "wizard UI"} <= set(names)
    for i in d["items"]:
        assert set(i) >= {"name", "ok", "detail", "hint"}
    # registry exists in a seeded vault → home+registry ok → overall ok
    assert d["ok"] is True
    assert len(d["vaults"]) == 1


def test_doctor_renders_same_lines(tmp_path, monkeypatch, capsys):
    from tests.conftest import make_vault_with_pages
    make_vault_with_pages(tmp_path, monkeypatch, pages={"raw/a.md": "# A\n\nx"})
    rc = setup_wizard.doctor()
    out = capsys.readouterr().out
    assert rc == 0
    # the human-facing lines the regression must preserve
    assert "omw home:" in out
    assert "registry:" in out
    assert "fetch yt-dlp:" in out
    assert "fetch chromium:" in out
    assert "wizard UI:" in out
    assert "(wiki/markdown)" in out  # the seeded vault's (mode/type) marker
