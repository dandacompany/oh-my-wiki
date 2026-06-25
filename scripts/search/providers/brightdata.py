from __future__ import annotations
import re
import urllib.parse
from scripts.search import base

SECRETS = {"api_key": "BRIGHTDATA_API_KEY", "zone": ("BRIGHTDATA_ZONE", "WEB_UNLOCKER_ZONE")}

#: Default name for the zone omw auto-creates when an account has no usable zone.
DEFAULT_ZONE_NAME = "omw_unlocker"


def _auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


def list_zones(api_key: str) -> list[dict]:
    """Return the account's active zones as [{"name", "type"}, ...].

    GET /zone/get_active_zones. Raises base.SearchError on HTTP/network error.
    """
    data = base._http_json(
        "https://api.brightdata.com/zone/get_active_zones",
        method="GET", headers=_auth(api_key),
    )
    return data if isinstance(data, list) else []


def create_zone(api_key: str, name: str = DEFAULT_ZONE_NAME) -> str:
    """Create an unblocker zone with SERP enabled (serves both search and scrape).

    POST /zone with the documented unblocker+serp plan. Returns the zone name —
    preferring the name the server echoes back (it may sanitize/rename), else the
    requested `name`. Raises base.SearchError on HTTP/network error (e.g. 403 if the
    key lacks the Admin/Ops role required to create zones).

    Body verbatim from the official "Add a Zone" docs (SERP API plan example):
    https://docs.brightdata.com/api-reference/account-management-api/Add_a_Zone
    """
    data = base._http_json(
        "https://api.brightdata.com/zone",
        method="POST", headers=_auth(api_key),
        body={
            "zone": {"name": name, "type": "serp"},
            "plan": {"type": "unblocker", "serp": True, "country": "any",
                     "solve_captcha_disable": True, "custom_headers": False},
        },
    )
    if isinstance(data, dict):
        returned = data.get("zone", {}).get("name") if isinstance(data.get("zone"), dict) else None
        if returned:
            return returned
    return name


class BrightDataProvider:
    name = "brightdata"

    def __init__(self, *, api_key: str, zone: str):
        self.api_key = api_key
        self.zone = zone

    def search(self, query: str, *, limit: int = 10) -> list[dict]:
        target = "https://www.google.com/search?" + urllib.parse.urlencode({"q": query}) + "&brd_json=1"
        data = base._http_json(
            "https://api.brightdata.com/request", method="POST",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            body={"zone": self.zone, "url": target, "format": "raw"},
        )
        organic = data.get("organic") if isinstance(data, dict) else None
        if organic is None:
            raise base.SearchError(
                "Bright Data returned no 'organic' results — ensure the configured zone "
                "serves brd_json SERP output. Set BRIGHTDATA_ZONE (or WEB_UNLOCKER_ZONE) "
                "via `omw setup search`."
            )
        return [{"title": r.get("title", ""), "url": r.get("link", ""),
                 "snippet": r.get("description", "")} for r in organic][:limit]

    def scrape(self, url: str) -> dict:
        # Web Unlocker: fetch the rendered page as raw HTML, then strip to text.
        html = base._http_text(
            "https://api.brightdata.com/request", method="POST",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            body={"zone": self.zone, "url": url, "format": "raw"},
        )
        title_m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        title = title_m.group(1).strip() if title_m else url
        text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.I | re.S)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return {"markdown": text, "title": title}
