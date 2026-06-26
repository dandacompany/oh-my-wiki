"""fetch (scrape/browser) provider can be configured independently of search.

resolve_scrape_provider resolution order: explicit arg → fetch.provider → search.provider.
Brightdata zone secret is set so the provider constructs; no live network is touched.
"""
import pytest

from scripts import config, search
from scripts.search import SearchError


def _set_brightdata_secrets(monkeypatch):
    monkeypatch.setenv("BRIGHTDATA_API_KEY", "bd-key")
    monkeypatch.setenv("BRIGHTDATA_ZONE", "bd-zone")


def test_fetch_provider_overrides_search_provider(monkeypatch):
    """fetch.provider=brightdata while search.provider=brave → scrape uses brightdata."""
    config.set_config("search.provider", "brave")
    config.set_config("fetch.provider", "brightdata")
    monkeypatch.setenv("BRAVE_API_KEY", "brave-key")
    _set_brightdata_secrets(monkeypatch)
    prov = search.resolve_scrape_provider()
    assert prov.__class__.__name__ == "BrightDataProvider"


def test_falls_back_to_search_provider_when_no_fetch_provider(monkeypatch):
    """No fetch.provider → scrape resolver uses search.provider (today's behavior)."""
    config.set_config("search.provider", "firecrawl")
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-key")
    prov = search.resolve_scrape_provider()
    assert prov.__class__.__name__ == "FirecrawlProvider"


def test_search_only_fetch_provider_raises_with_setup_guidance(monkeypatch):
    """A non-scrape provider configured for fetch → actionable SearchError."""
    config.set_config("fetch.provider", "brave")
    monkeypatch.setenv("BRAVE_API_KEY", "brave-key")
    with pytest.raises(SearchError, match="setup fetch"):
        search.resolve_scrape_provider()


def test_explicit_name_overrides_both_config_keys(monkeypatch):
    config.set_config("search.provider", "brave")
    config.set_config("fetch.provider", "firecrawl")
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-key")
    _set_brightdata_secrets(monkeypatch)
    prov = search.resolve_scrape_provider("brightdata")
    assert prov.__class__.__name__ == "BrightDataProvider"


# ── omw setup fetch (scrape-capable providers only) ──────────────────────────

def test_setup_fetch_firecrawl_writes_fetch_provider_not_search(monkeypatch):
    from scripts import omw_cli
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    rc = omw_cli.main(["setup", "fetch", "--noninteractive",
                       "--provider", "firecrawl", "--api-key", "K"])
    assert rc == 0
    cfg = config.load_config()
    assert cfg["fetch"]["provider"] == "firecrawl"
    assert cfg["fetch"]["enabled"] is True
    assert config.read_secret("FIRECRAWL_API_KEY") == "K"
    # search provider must be left untouched by `setup fetch`
    assert (cfg.get("search") or {}).get("provider") is None


def test_setup_fetch_brightdata_autodetects_zone(monkeypatch):
    from scripts import omw_cli
    from scripts.search.providers import brightdata
    monkeypatch.delenv("BRIGHTDATA_ZONE", raising=False)
    monkeypatch.setattr(brightdata, "list_zones",
                        lambda key: [{"name": "fetch_serp", "type": "serp"}])
    rc = omw_cli.main(["setup", "fetch", "--noninteractive",
                       "--provider", "brightdata", "--api-key", "K"])
    assert rc == 0
    assert config.load_config()["fetch"]["provider"] == "brightdata"
    assert config.read_secret("BRIGHTDATA_ZONE") == "fetch_serp"


def test_setup_fetch_rejects_search_only_provider(monkeypatch, capsys):
    from scripts import omw_cli
    rc = omw_cli.main(["setup", "fetch", "--noninteractive",
                       "--provider", "brave", "--api-key", "K"])
    assert rc == 1
    assert "brightdata" in capsys.readouterr().err.lower()
    assert (config.load_config().get("fetch") or {}).get("provider") is None


def test_scrape_providers_are_a_subset_of_known_secrets():
    """Guard: every _SCRAPE_PROVIDERS entry must have a secret spec, else the setup
    loop KeyErrors. Prevents a future provider rename from breaking `setup fetch`."""
    from scripts.setup_wizard import _PROVIDER_SECRETS, _SCRAPE_PROVIDERS
    assert set(_SCRAPE_PROVIDERS) <= set(_PROVIDER_SECRETS)


def test_setup_fetch_warns_when_search_also_brightdata(monkeypatch, capsys):
    """search + fetch both on brightdata share the single BRIGHTDATA_ZONE secret —
    warn so the user knows a per-role zone isn't possible."""
    from scripts import omw_cli
    from scripts.search.providers import brightdata
    config.set_config("search.provider", "brightdata")
    monkeypatch.delenv("BRIGHTDATA_ZONE", raising=False)
    monkeypatch.setattr(brightdata, "list_zones",
                        lambda key: [{"name": "shared_serp", "type": "serp"}])
    omw_cli.main(["setup", "fetch", "--noninteractive",
                  "--provider", "brightdata", "--api-key", "K"])
    out = capsys.readouterr().out.lower()
    assert "brightdata_zone" in out or "shares" in out or "same zone" in out


def test_setup_fetch_frames_provider_as_optional_escalation(monkeypatch, capsys):
    """`setup fetch` must make clear the provider is optional — built-in/native fetch
    runs first; the provider only backs hard-blocked pages."""
    from scripts import setup_wizard
    setup_wizard.setup_fetch(noninteractive=True)  # no provider → skipped, but framed
    out = capsys.readouterr().out.lower()
    assert "built-in" in out or "native" in out or "optional" in out
