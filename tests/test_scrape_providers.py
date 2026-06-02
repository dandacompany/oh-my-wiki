from scripts.search.providers import brightdata, firecrawl


def test_firecrawl_scrape_parses_markdown(monkeypatch):
    captured = {}

    def fake_http_json(url, *, method, headers, body, timeout=15):
        captured["url"] = url
        captured["body"] = body
        return {"data": {"markdown": "# Title\n\nbody", "metadata": {"title": "Title"}}}

    monkeypatch.setattr(firecrawl.base, "_http_json", fake_http_json)
    prov = firecrawl.FirecrawlProvider(api_key="k")
    out = prov.scrape("https://example.com/x")
    assert out["title"] == "Title"
    assert "body" in out["markdown"]
    assert captured["body"]["url"] == "https://example.com/x"


def test_brightdata_scrape_returns_markdown(monkeypatch):
    def fake_http_text(url, *, method, headers, body, timeout=15):
        return "<html><title>T</title><body>hi</body></html>"

    monkeypatch.setattr(brightdata.base, "_http_text", fake_http_text)
    prov = brightdata.BrightDataProvider(api_key="k", zone="z")
    out = prov.scrape("https://example.com/x")
    assert out["title"] == "T"
    assert "hi" in out["markdown"]
