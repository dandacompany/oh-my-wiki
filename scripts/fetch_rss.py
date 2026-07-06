"""Parse RSS 2.0 / Atom feeds (stdlib XML) into [{title, link}] entries, and
fetch a feed URL. Feeds are a bulk source of URLs for the inbox; parsing is
namespace-tolerant and returns [] on malformed XML (never raises from parse)."""
from __future__ import annotations

import urllib.error
import urllib.request
from xml.etree import ElementTree as ET

from scripts import fetch, net_hints, urls

MAX_FEED_BYTES = 5_000_000


class FeedError(Exception):
    """Raised when a feed URL cannot be fetched."""


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def parse_feed(xml_text: str) -> list[dict]:
    """Return [{title, link}] for RSS <item> or Atom <entry>. [] on malformed XML
    or entries lacking a link.

    Security: feeds are untrusted network input. `xml.etree.ElementTree` is
    vulnerable to entity-expansion DoS (billion-laughs / quadratic-blowup), which
    REQUIRES a DOCTYPE with <!ENTITY> declarations. Legitimate RSS/Atom feeds never
    use a DOCTYPE, so we reject any document declaring one before parsing — a
    stdlib-only equivalent of defusedxml's forbid_dtd. (ElementTree does not resolve
    external entities, so XXE file-read is not a vector.)"""
    if "<!DOCTYPE" in xml_text or "<!ENTITY" in xml_text:
        return []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    out: list[dict] = []
    for el in root.iter():
        name = _localname(el.tag)
        if name not in ("item", "entry"):
            continue
        title, link = "", ""
        for child in el:
            cn = _localname(child.tag)
            if cn == "title" and not title:
                title = (child.text or "").strip()
            elif cn == "link":
                href = child.get("href")          # Atom: <link href=...>
                if href:
                    rel = child.get("rel")
                    if rel in (None, "alternate") or not link:
                        link = href.strip()
                elif (child.text or "").strip():   # RSS: <link>text</link>
                    link = child.text.strip()
        if link:
            out.append({"title": title, "link": link})
    return out


def fetch_feed(url: str) -> list[dict]:
    """GET a feed URL and parse it. Raises FeedError on network/HTTP/SSRF failure."""
    if urls.is_blocked_url(url):
        raise FeedError(f"blocked feed URL (SSRF guard): {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "oh-my-wiki/omw"})
    try:
        with fetch._OPENER.open(req, timeout=20) as resp:
            body = resp.read(MAX_FEED_BYTES + 1)
    except fetch.SSRFBlocked as exc:
        raise FeedError(f"blocked feed URL (SSRF guard): {url}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise FeedError(f"could not fetch feed {url}: {exc}{net_hints.hint_for(exc)}") from exc
    if len(body) > MAX_FEED_BYTES:
        raise FeedError(f"feed too large (> {MAX_FEED_BYTES} bytes): {url}")
    return parse_feed(body.decode("utf-8", "replace"))
