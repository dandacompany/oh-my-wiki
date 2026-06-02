# tests/test_omw_cli_inbox.py
import json

from scripts import omw_cli, registry
from scripts.paths import ensure_home, registry_path


def _seed(tmp_path):
    ensure_home()
    db = registry_path()
    root = tmp_path / "v"
    (root / "raw").mkdir(parents=True)
    (root / "wiki").mkdir(parents=True)
    registry.init_db(db)
    registry.add_vault(db, name="v", path=root, type_="markdown", mode="wiki")
    registry.set_active(db, "v")
    return db, root


def test_inbox_add_and_list(tmp_path, capsys):
    _seed(tmp_path)
    assert omw_cli.main(["inbox", "add", "https://example.com/a"]) == 0
    capsys.readouterr()
    assert omw_cli.main(["inbox", "list"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert len(out) == 1 and out[0]["status"] == "queued"


def test_inbox_run_invokes_fetch(tmp_path, monkeypatch, capsys):
    _seed(tmp_path)
    omw_cli.main(["inbox", "add", "https://example.com/a"])
    capsys.readouterr()
    from scripts import fetch
    monkeypatch.setattr(fetch, "fetch_url", lambda url, *, html_backend="auto": {
        "text": "body", "title": "T", "content_type": "text/plain",
        "backend": "urllib", "source_url": url})
    assert omw_cli.main(["inbox", "run"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert len(out["fetched"]) == 1


def test_fetch_single_shot(tmp_path, monkeypatch, capsys):
    _seed(tmp_path)
    from scripts import fetch
    monkeypatch.setattr(fetch, "fetch_url", lambda url, *, html_backend="auto": {
        "text": "body text", "title": "T", "content_type": "text/plain",
        "backend": "urllib", "source_url": url})
    assert omw_cli.main(["fetch", "https://example.com/a"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["raw_relpath"].startswith("raw/")
    assert out["backend"] == "urllib"


def test_fetch_cloud_no_provider_clean_error(tmp_path, monkeypatch, capsys):
    _seed(tmp_path)
    from scripts import fetch, search
    def boom(url, *, html_backend="auto"):
        raise search.SearchError("no search provider configured")
    monkeypatch.setattr(fetch, "fetch_url", boom)
    rc = omw_cli.main(["fetch", "https://example.com/a", "--backend", "cloud"])
    assert rc == 1  # clean error, not a traceback
    assert "error:" in capsys.readouterr().err
