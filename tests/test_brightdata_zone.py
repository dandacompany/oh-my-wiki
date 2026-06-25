"""Bright Data zone management helpers (auto-detect / auto-create) — hermetic.

These patch scripts.search.base._http_json so no live network is touched.
"""
import pytest

from scripts.search import base
from scripts.search.providers import brightdata
from scripts import config, omw_cli


def test_list_zones_parses_name_type(monkeypatch):
    captured = {}

    def fake_http_json(url, *, method="GET", headers=None, body=None, timeout=15):
        captured["url"] = url
        captured["method"] = method
        captured["headers"] = headers
        return [{"name": "z1", "type": "serp"}, {"name": "z2", "type": "unblocker"}]

    monkeypatch.setattr(base, "_http_json", fake_http_json)
    zones = brightdata.list_zones("KEY")
    assert zones == [{"name": "z1", "type": "serp"}, {"name": "z2", "type": "unblocker"}]
    assert captured["url"] == "https://api.brightdata.com/zone/get_active_zones"
    assert captured["method"] == "GET"
    assert captured["headers"]["Authorization"] == "Bearer KEY"


def test_create_zone_posts_documented_body_and_returns_name(monkeypatch):
    captured = {}

    def fake_http_json(url, *, method="GET", headers=None, body=None, timeout=15):
        captured["url"] = url
        captured["method"] = method
        captured["body"] = body
        return {"zone": {"name": "omw_unlocker"}}

    monkeypatch.setattr(base, "_http_json", fake_http_json)
    name = brightdata.create_zone("KEY")
    assert name == "omw_unlocker"
    assert captured["url"] == "https://api.brightdata.com/zone"
    assert captured["method"] == "POST"
    # The plan must be an unblocker zone with serp enabled (serves search AND scrape).
    assert captured["body"]["zone"] == {"name": "omw_unlocker", "type": "serp"}
    assert captured["body"]["plan"]["type"] == "unblocker"
    assert captured["body"]["plan"]["serp"] is True


def test_create_zone_custom_name(monkeypatch):
    monkeypatch.setattr(base, "_http_json",
                        lambda url, **k: None)
    assert brightdata.create_zone("KEY", name="my_zone") == "my_zone"


def test_create_zone_prefers_server_returned_name(monkeypatch):
    """If Bright Data sanitizes/renames the zone, trust the name it returns."""
    monkeypatch.setattr(base, "_http_json",
                        lambda url, **k: {"zone": {"name": "omw_unlocker_2"}})
    assert brightdata.create_zone("KEY", name="omw_unlocker") == "omw_unlocker_2"


def test_list_zones_propagates_search_error(monkeypatch):
    def boom(url, **k):
        raise base.SearchError("HTTP 401 from ...")

    monkeypatch.setattr(base, "_http_json", boom)
    with pytest.raises(base.SearchError):
        brightdata.list_zones("BADKEY")


# ── setup_search brightdata zone auto-detect (non-interactive) ────────────────

def _run_setup(*extra):
    return omw_cli.main(["setup", "search", "--noninteractive",
                         "--provider", "brightdata", "--api-key", "K", *extra])


def test_autodetect_picks_serp_zone(monkeypatch):
    monkeypatch.delenv("BRIGHTDATA_ZONE", raising=False)
    monkeypatch.setattr(brightdata, "list_zones",
                        lambda key: [{"name": "u1", "type": "unblocker"},
                                     {"name": "s1", "type": "serp"}])
    rc = _run_setup()
    assert rc == 0
    cfg = config.load_config()
    assert cfg["search"]["enabled"] is True
    assert config.read_secret("BRIGHTDATA_ZONE") == "s1"


def test_unblocker_only_defers_with_serp_guidance(monkeypatch, capsys):
    """A non-SERP unblocker zone can't serve `omw search` — defer instead of enabling
    a config we predict won't work; nudge the user to --create-zone."""
    monkeypatch.delenv("BRIGHTDATA_ZONE", raising=False)
    monkeypatch.setattr(brightdata, "list_zones",
                        lambda key: [{"name": "u1", "type": "unblocker"}])
    rc = _run_setup()
    assert rc == 0
    assert config.load_config()["search"]["enabled"] is False  # not a search-ready zone
    out = capsys.readouterr().out.lower()
    assert "serp" in out and "create-zone" in out


def test_no_zone_no_create_flag_defers(monkeypatch):
    """Empty zone list + non-interactive without --create-zone → defer, no charge."""
    monkeypatch.delenv("BRIGHTDATA_ZONE", raising=False)
    monkeypatch.setattr(brightdata, "list_zones", lambda key: [])
    created = []
    monkeypatch.setattr(brightdata, "create_zone",
                        lambda key, **k: created.append(1) or "x")
    rc = _run_setup()
    assert rc == 0
    assert config.load_config()["search"]["enabled"] is False
    assert created == []  # never auto-created without opt-in


def test_create_zone_flag_creates_when_empty(monkeypatch):
    monkeypatch.delenv("BRIGHTDATA_ZONE", raising=False)
    monkeypatch.setattr(brightdata, "list_zones", lambda key: [])
    monkeypatch.setattr(brightdata, "create_zone",
                        lambda key, **k: "omw_unlocker")
    rc = _run_setup("--create-zone")
    assert rc == 0
    assert config.read_secret("BRIGHTDATA_ZONE") == "omw_unlocker"
    assert config.load_config()["search"]["enabled"] is True


def test_manual_zone_overrides_detection(monkeypatch):
    called = []
    monkeypatch.setattr(brightdata, "list_zones",
                        lambda key: called.append(1) or [])
    rc = omw_cli.main(["setup", "search", "--noninteractive",
                       "--provider", "brightdata", "--api-key", "K", "--zone", "manual"])
    assert rc == 0
    assert config.read_secret("BRIGHTDATA_ZONE") == "manual"
    assert called == []  # detection skipped entirely


def test_list_zones_error_defers_gracefully(monkeypatch):
    monkeypatch.delenv("BRIGHTDATA_ZONE", raising=False)

    def boom(key):
        raise base.SearchError("HTTP 401")

    monkeypatch.setattr(brightdata, "list_zones", boom)
    rc = _run_setup()
    assert rc == 0
    assert config.load_config()["search"]["enabled"] is False
