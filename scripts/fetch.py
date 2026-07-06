"""URL fetch orchestrator: classify (youtube/static/spa) and run a tiered cascade.

Tiers (per html_backend): urllib (static) → chromium (local SPA) → cloud scrape.
YouTube always uses yt-dlp. Deterministic; no LLM. Returns a FetchResult dict:
{text, title, content_type, backend, source_url}.
"""
from __future__ import annotations

import re
import urllib.error
import urllib.request

from scripts import fetch_chromium, fetch_youtube, net_hints, search, urls
from scripts.fetch_errors import FetchError, SSRFBlocked

_MIN_TEXT = 200  # chars; below this an HTML page is treated as JS-thin → escalate
_UA = "Mozilla/5.0 (compatible; oh-my-wiki/omw fetch)"


class _SSRFSafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Re-validate every redirect target through the SSRF guard before following."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urls.is_blocked_url(newurl):
            raise SSRFBlocked(f"redirect to blocked URL: {newurl}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(_SSRFSafeRedirectHandler())


def _pdf_text(raw: bytes) -> str:
    try:
        import io
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(raw))
        return "\n\n".join((p.extract_text() or "") for p in reader.pages).strip()
    except Exception:
        return ""


def _strip_html(html: str) -> str:
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _http_get_text(url: str) -> tuple[str, str, str]:
    """Return (content_type, raw_body, extracted_text). Raises FetchError on network error."""
    req = urllib.request.Request(url, headers={"User-Agent": _UA}, method="GET")
    try:
        with _OPENER.open(req, timeout=20) as resp:
            ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        raise FetchError(f"HTTP {exc.code} from {url}") from exc
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise FetchError(f"network error to {url}: {exc}{net_hints.hint_for(exc)}") from exc
    if "pdf" in ctype:
        return ctype, "", _pdf_text(raw)
    body = raw.decode("utf-8", errors="replace")
    extracted = _strip_html(body) if "html" in ctype else body
    return ctype, body, extracted


def _scrape_cloud(url: str) -> tuple[str, str]:
    prov = search.resolve_scrape_provider()  # raises SearchError if unavailable
    out = prov.scrape(url)
    return out.get("title") or url, out.get("markdown") or ""


def fetch_url(url: str, *, html_backend: str = "auto") -> dict:
    """Fetch one URL → FetchResult dict. Raises SSRFBlocked / NeedsYtDlp /
    NeedsChromium / FetchError / SearchError on the respective failures."""
    if urls.is_blocked_url(url):
        raise SSRFBlocked(f"blocked URL: {url}")

    if urls.is_youtube(url):
        title, text = fetch_youtube.fetch_transcript(url)
        return {"text": text, "title": title, "content_type": "youtube",
                "backend": "youtube", "source_url": url}

    if html_backend == "chromium":
        title, text = fetch_chromium.render(url)
        return {"text": text, "title": title, "content_type": "text/html",
                "backend": "chromium", "source_url": url}
    if html_backend == "cloud":
        title, text = _scrape_cloud(url)
        return {"text": text, "title": title, "content_type": "text/html",
                "backend": "cloud", "source_url": url}

    # urllib / auto: try a plain GET first
    ctype, _body, text = _http_get_text(url)
    thin = ("html" in ctype) and (len(text) < _MIN_TEXT)
    if html_backend == "urllib" or not thin:
        return {"text": text, "title": url, "content_type": ctype,
                "backend": "urllib", "source_url": url}

    # auto + thin HTML → escalate: chromium (if available) then cloud
    if fetch_chromium.available():
        try:
            title, rendered = fetch_chromium.render(url)
            return {"text": rendered, "title": title, "content_type": "text/html",
                    "backend": "chromium", "source_url": url}
        except FetchError:
            pass  # chromium runtime failure → fall through to cloud
    try:
        title, rendered = _scrape_cloud(url)
        return {"text": rendered, "title": title, "content_type": "text/html",
                "backend": "cloud", "source_url": url}
    except search.SearchError:
        # no chromium, no cloud provider — return what urllib got (better than nothing)
        return {"text": text, "title": url, "content_type": ctype,
                "backend": "urllib", "source_url": url}
