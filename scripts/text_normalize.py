"""Single home for Korean search-text normalization (the analyzer seam).

The FTS index, the token-scorer fallback, and the recall query path all route
text through `normalize_text` so the index and queries are analyzed identically
(the IR invariant). Today the only provider is the dependency-free josa-strip
heuristic; a future `kiwi` provider plugs into `normalize_text` behind an
optional import and bumps `analyzer_version()`. Pure stdlib, never raises.
"""
from __future__ import annotations

import re

from scripts.text_match import _JOSA

_JOSA_LONGEST_FIRST = sorted(_JOSA, key=len, reverse=True)
_HANGUL_END = re.compile(r"[가-힣]$")

_PROVIDER_CACHE: str | None = None
_VERSION_CACHE: str | None = None


def _provider() -> str:
    """Resolve the active normalizer provider (cached) — the provider that will
    ACTUALLY run, so analyzer_version() always matches. Only 'heuristic' today
    (the 'kiwi' branch is added in the kiwi-provider task). Never raises."""
    global _PROVIDER_CACHE
    if _PROVIDER_CACHE is None:
        prov = "heuristic"
        try:
            from scripts import config
            want = (config.load_config() or {}).get("recall", {}).get("normalizer")
            if want == "heuristic":
                prov = want
        except Exception:
            prov = "heuristic"
        _PROVIDER_CACHE = prov
    return _PROVIDER_CACHE


def analyzer_version() -> str:
    """Index-invalidation key, DERIVED from the effective provider (cached).
    heuristic → 'heuristic-1'; kiwi → 'kiwi-<kiwipiepy version>'. Any provider or
    version change bumps this so the FTS gate auto-rebuilds. Never raises."""
    global _VERSION_CACHE
    if _VERSION_CACHE is None:
        if _provider() == "kiwi":
            try:
                from importlib.metadata import version
                _VERSION_CACHE = f"kiwi-{version('kiwipiepy')}"
            except Exception:
                _VERSION_CACHE = "heuristic-1"
        else:
            _VERSION_CACHE = "heuristic-1"
    return _VERSION_CACHE


def _reset_provider_cache() -> None:
    """Test helper: drop cached provider + version so config changes take effect."""
    global _PROVIDER_CACHE, _VERSION_CACHE
    _PROVIDER_CACHE = None
    _VERSION_CACHE = None


def _heuristic_token(tok: str) -> str:
    """Drop one trailing Korean postposition from a Hangul-ending token when at
    least 2 chars remain. Mirrors the original recall._strip_josa."""
    if not _HANGUL_END.search(tok):
        return tok
    for j in _JOSA_LONGEST_FIRST:
        if tok.endswith(j) and len(tok) - len(j) >= 2:
            return tok[: -len(j)]
    return tok


def _heuristic_text(text: str) -> str:
    """Heuristic text normalizer: split on whitespace, josa-strip each token, rejoin."""
    return " ".join(_heuristic_token(t) for t in text.split())


#: provider id → text-level normalizer (str) -> str. 'kiwi' is added by the
#: kiwi-provider task. dispatch falls back to heuristic for unknown providers.
_NORMALIZERS = {"heuristic": _heuristic_text}


def normalize_text(text: str | None) -> str:
    """Normalize free text for indexing or querying under the active provider.
    Index and query route through the same provider (the IR invariant).
    Idempotent on ASCII. Never raises."""
    if not text:
        return ""
    return _NORMALIZERS.get(_provider(), _heuristic_text)(text)


def normalize_token(tok: str) -> str:
    """Normalize one token under the active provider. Never raises."""
    if not tok:
        return ""
    return normalize_text(tok)


#: Keep the old constant as an alias for any external code that still reads it.
ANALYZER_VERSION = "heuristic-1"
