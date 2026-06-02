"""Pure URL utilities: normalization (for dedup), YouTube detection, SSRF guard."""
from __future__ import annotations

import ipaddress
import re
import socket
import urllib.parse

_TRACKING_PREFIXES = ("utm_",)
_TRACKING_KEYS = {"fbclid", "gclid", "mc_eid"}
_YT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def youtube_id(url: str) -> str | None:
    """Extract an 11-char YouTube video id from watch/youtu.be/shorts/embed URLs."""
    p = urllib.parse.urlsplit(url)
    host = p.hostname or ""
    if host == "youtu.be" or host.endswith(".youtu.be"):
        vid = p.path.lstrip("/").split("/")[0]
        return vid if _YT_ID_RE.match(vid) else None
    if host == "youtube.com" or host.endswith(".youtube.com"):
        qs = urllib.parse.parse_qs(p.query)
        if "v" in qs and _YT_ID_RE.match(qs["v"][0]):
            return qs["v"][0]
        m = re.match(r"^/(?:shorts|embed)/([A-Za-z0-9_-]{11})", p.path)
        if m:
            return m.group(1)
    return None


def is_youtube(url: str) -> bool:
    return youtube_id(url) is not None


def normalize_url(url: str) -> str:
    """Canonical form for dedup: lowercase scheme/host, drop fragment + tracking
    params, and canonicalize YouTube to https://www.youtube.com/watch?v=<id>."""
    vid = youtube_id(url)
    if vid:
        return f"https://www.youtube.com/watch?v={vid}"
    p = urllib.parse.urlsplit(url)
    scheme = p.scheme.lower()
    host = (p.hostname or "").lower()
    netloc = host + (f":{p.port}" if p.port else "")
    kept = [
        (k, v) for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=True)
        if k not in _TRACKING_KEYS and not k.startswith(_TRACKING_PREFIXES)
    ]
    query = urllib.parse.urlencode(kept)
    return urllib.parse.urlunsplit((scheme, netloc, p.path, query, ""))


def is_blocked_url(url: str) -> bool:
    """SSRF guard: block non-http(s) schemes and loopback/private/link-local hosts.
    Also catches obfuscated IPv4 literals (decimal/hex/abbreviated) that resolve to
    a blocked range but that ipaddress.ip_address() does not parse canonically."""
    p = urllib.parse.urlsplit(url)
    if p.scheme.lower() not in ("http", "https"):
        return True
    host = (p.hostname or "").lower()
    if host in ("localhost", ""):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        # Not a canonical IP. Obfuscated IPv4 (2130706433 / 0x7f000001 / 127.1) is
        # accepted by inet_aton → canonicalize and re-check; otherwise it's a hostname.
        try:
            ip = ipaddress.ip_address(socket.inet_ntoa(socket.inet_aton(host)))
        except (OSError, ValueError):
            return False  # genuine DNS hostname — allowed (no resolution here)
    return ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved
