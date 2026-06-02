# tests/test_fetch.py
import pytest

from scripts import fetch
from scripts.fetch_errors import SSRFBlocked


def test_blocked_url_raises_ssrf():
    with pytest.raises(SSRFBlocked):
        fetch.fetch_url("http://127.0.0.1/secret")


def test_youtube_uses_transcript(monkeypatch):
    monkeypatch.setattr(fetch.fetch_youtube, "fetch_transcript",
                        lambda url: ("Vid Title", "the transcript text"))
    r = fetch.fetch_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert r["backend"] == "youtube"
    assert r["title"] == "Vid Title"
    assert r["text"] == "the transcript text"
    assert r["source_url"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def test_static_url_uses_urllib(monkeypatch):
    monkeypatch.setattr(fetch, "_http_get_text",
                        lambda url: ("text/plain", "plain body text", "plain body text"))
    r = fetch.fetch_url("https://example.com/page.txt", html_backend="urllib")
    assert r["backend"] == "urllib"
    assert "plain body text" in r["text"]


def test_auto_escalates_to_cloud_when_html_thin(monkeypatch):
    monkeypatch.setattr(fetch, "_http_get_text",
                        lambda url: ("text/html", "<html><body></body></html>", ""))
    monkeypatch.setattr(fetch.fetch_chromium, "available", lambda: False)

    class _Prov:
        def scrape(self, url):
            return {"markdown": "rendered cloud content", "title": "Cloud"}

    monkeypatch.setattr(fetch.search, "resolve_scrape_provider", lambda: _Prov())
    r = fetch.fetch_url("https://spa.example.com/app", html_backend="auto")
    assert r["backend"] == "cloud"
    assert r["text"] == "rendered cloud content"


def test_redirect_to_blocked_url_is_rejected():
    import urllib.request
    from scripts.fetch_errors import FetchError
    h = fetch._SSRFSafeRedirectHandler()
    req = urllib.request.Request("https://example.com/")
    with pytest.raises(FetchError):
        h.redirect_request(req, None, 301, "Moved", {},
                           "http://169.254.169.254/latest/meta-data/")


def test_auto_chromium_failure_falls_through_to_cloud(monkeypatch):
    from scripts.fetch_errors import FetchError
    monkeypatch.setattr(fetch, "_http_get_text",
                        lambda url: ("text/html", "<html></html>", ""))
    monkeypatch.setattr(fetch.fetch_chromium, "available", lambda: True)

    def boom(url):
        raise FetchError("chromium crashed")

    monkeypatch.setattr(fetch.fetch_chromium, "render", boom)

    class _Prov:
        def scrape(self, url):
            return {"markdown": "cloud content", "title": "C"}

    monkeypatch.setattr(fetch.search, "resolve_scrape_provider", lambda: _Prov())
    r = fetch.fetch_url("https://spa.example.com/app", html_backend="auto")
    assert r["backend"] == "cloud"
    assert r["text"] == "cloud content"
