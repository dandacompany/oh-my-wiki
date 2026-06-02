# tests/test_fetch_chromium.py
import builtins

import pytest

from scripts import fetch_chromium
from scripts.fetch_errors import NeedsChromium


def test_available_false_when_playwright_missing(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name.startswith("playwright"):
            raise ImportError("no playwright")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert fetch_chromium.available() is False


def test_render_raises_needs_chromium_when_missing(monkeypatch):
    monkeypatch.setattr(fetch_chromium, "available", lambda: False)
    with pytest.raises(NeedsChromium):
        fetch_chromium.render("https://example.com")
