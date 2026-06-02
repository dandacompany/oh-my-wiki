"""SPA rendering via Playwright/chromium. Optional — lazy-imported, never a hard dep."""
from __future__ import annotations

from scripts.fetch_errors import FetchError, NeedsChromium


def available() -> bool:
    """True if the playwright Python package is importable."""
    try:
        import playwright.sync_api  # noqa: F401
        return True
    except ImportError:
        return False


def render(url: str, *, timeout_ms: int = 20000) -> tuple[str, str]:
    """Return (title, visible_text) after a chromium render.
    Raises NeedsChromium if Playwright/chromium isn't installed."""
    if not available():
        raise NeedsChromium("playwright/chromium is not installed")
    from playwright.sync_api import sync_playwright  # lazy
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(url, wait_until="networkidle", timeout=timeout_ms)
                title = page.title() or url
                text = page.inner_text("body")
                return title, text
            finally:
                browser.close()
    except NeedsChromium:
        raise
    except Exception as exc:  # playwright launch/runtime errors (e.g. browser not downloaded)
        raise FetchError(f"chromium render failed: {exc}") from exc
