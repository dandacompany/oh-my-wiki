"""omw search abstraction. search() / resolve_provider() / SearchError.

MCP search stays LLM-mediated (not wrapped here). This is the Python provider
layer for the native CLI / server contexts where no host MCP exists.
"""
from __future__ import annotations

from scripts import config
from scripts.search.base import Provider, SearchError
from scripts.search.providers.brave import BraveProvider, SECRETS as _BRAVE_SECRETS
from scripts.search.providers.brightdata import BrightDataProvider, SECRETS as _BD_SECRETS
from scripts.search.providers.exa import ExaProvider, SECRETS as _EXA_SECRETS
from scripts.search.providers.firecrawl import FirecrawlProvider, SECRETS as _FC_SECRETS
from scripts.search.providers.tavily import TavilyProvider, SECRETS as _TAVILY_SECRETS

PROVIDERS = {
    "brave": (BraveProvider, _BRAVE_SECRETS),
    "brightdata": (BrightDataProvider, _BD_SECRETS),
    "tavily": (TavilyProvider, _TAVILY_SECRETS),
    "exa": (ExaProvider, _EXA_SECRETS),
    "firecrawl": (FirecrawlProvider, _FC_SECRETS),
}


def resolve_provider(name: str | None = None) -> Provider:
    cfg = config.load_config()
    name = name or (cfg.get("search") or {}).get("provider")
    if not name:
        raise SearchError("no search provider configured — run `omw setup search`")
    entry = PROVIDERS.get(name)
    if entry is None:
        raise SearchError(f"unknown search provider {name!r}; have: {', '.join(PROVIDERS)}")
    cls, secret_spec = entry
    kwargs = {}
    for kw, env_vars in secret_spec.items():
        env_vars = (env_vars,) if isinstance(env_vars, str) else env_vars
        val = next((s for v in env_vars if (s := config.read_secret(v))), None)
        if not val:
            raise SearchError(
                f"missing API key for {name!r} ({' or '.join(env_vars)}) — run `omw setup search`"
            )
        kwargs[kw] = val
    return cls(**kwargs)


def resolve_scrape_provider(name: str | None = None) -> Provider:
    """Resolve a provider that supports scrape(url). Raises SearchError if the
    configured provider lacks scrape() or no key is set."""
    prov = resolve_provider(name)
    if not hasattr(prov, "scrape"):
        raise SearchError(
            f"provider {type(prov).__name__} has no scrape(); use firecrawl or brightdata"
        )
    return prov


def search(query: str, *, provider: str | None = None, limit: int = 10) -> list[dict]:
    return resolve_provider(provider).search(query, limit=limit)


def available_providers() -> list[str]:
    """Provider names whose secrets all resolve, in PROVIDERS declaration order."""
    out = []
    for name, (_cls, secret_spec) in PROVIDERS.items():
        ok = True
        for env_vars in secret_spec.values():
            env_vars = (env_vars,) if isinstance(env_vars, str) else env_vars
            if not any(config.read_secret(v) for v in env_vars):
                ok = False
                break
        if ok:
            out.append(name)
    return out


def search_with_fallback(query: str, *, provider: str | None = None,
                         limit: int = 10) -> dict:
    """Try the configured/named provider, then remaining available providers on
    SearchError or empty results. Returns {results, provider, tried}; raises
    SearchError naming the tried providers if all fail."""
    cfg = config.load_config()
    configured = provider or (cfg.get("search") or {}).get("provider")
    avail = available_providers()
    order: list[str] = []
    if configured:
        order.append(configured)
    for name in avail:
        if name not in order:
            order.append(name)
    if not order:
        raise SearchError("no search provider configured — run `omw setup search`")

    tried: list[str] = []
    failures: list[str] = []
    for name in order:
        tried.append(name)
        try:
            results = resolve_provider(name).search(query, limit=limit)
        except SearchError as exc:
            failures.append(f"{name}({exc})")
            continue
        if not results:
            failures.append(f"{name}(empty)")
            continue
        return {"results": results, "provider": name, "tried": tried}
    raise SearchError("all search providers failed: " + ", ".join(failures))
