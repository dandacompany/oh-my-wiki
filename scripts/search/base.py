"""Search provider base: stdlib HTTP helper, protocol, registry."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Protocol

from scripts import net_hints


class SearchError(Exception):
    pass


class Provider(Protocol):
    def search(self, query: str, *, limit: int = 10) -> list[dict]: ...


def _http_json(url, *, method="GET", headers=None, body=None, timeout=15):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raise SearchError(f"HTTP {exc.code} from {url}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise SearchError(f"network error to {url}: {exc}{net_hints.hint_for(exc)}") from exc
    except json.JSONDecodeError as exc:
        raise SearchError(f"non-JSON response from {url}") from exc


def _http_text(url, *, method="GET", headers=None, body=None, timeout=15):
    """Like _http_json but returns the raw response body as text (no JSON decode).
    Used by scrape() paths that fetch HTML rather than a JSON API."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raise SearchError(f"HTTP {exc.code} from {url}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise SearchError(f"network error to {url}: {exc}{net_hints.hint_for(exc)}") from exc
