from __future__ import annotations
from scripts.search import base

SECRETS = {"api_key": "FIRECRAWL_API_KEY"}


class FirecrawlProvider:
    name = "firecrawl"

    def __init__(self, *, api_key: str):
        self.api_key = api_key

    def search(self, query: str, *, limit: int = 10) -> list[dict]:
        data = base._http_json(
            "https://api.firecrawl.dev/v2/search", method="POST",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            body={"query": query, "limit": min(limit, 100)},
        )
        results = data.get("data") or []
        if isinstance(results, dict):          # v2: {"data": {"web": [...]}}
            results = results.get("web") or []
        # v1: {"data": [...]} -> results is already a list
        return [{"title": r.get("title", ""), "url": r.get("url", ""),
                 "snippet": r.get("description", "")} for r in results][:limit]

    def scrape(self, url: str) -> dict:
        data = base._http_json(
            "https://api.firecrawl.dev/v2/scrape", method="POST",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            body={"url": url, "formats": ["markdown"]},
        )
        payload = (data.get("data") if isinstance(data, dict) else None) or {}
        md = payload.get("markdown") or ""
        title = (payload.get("metadata") or {}).get("title") or url
        return {"markdown": md, "title": title}
