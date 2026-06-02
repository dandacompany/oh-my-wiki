"""Typed errors for the fetch engine. No imports → safe for any module to use."""
from __future__ import annotations


class FetchError(Exception):
    """A URL could not be fetched (network, HTTP, extraction failure)."""


class NeedsYtDlp(FetchError):
    """A YouTube URL was requested but the `yt-dlp` CLI is not installed."""


class NeedsChromium(FetchError):
    """An SPA render was requested but Playwright/chromium is not installed."""


class SSRFBlocked(FetchError):
    """The URL targets a blocked host/scheme (loopback, private, non-http)."""
