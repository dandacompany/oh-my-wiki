"""Single home for Korean search-text normalization (the analyzer seam).

The FTS index, the token-scorer fallback, and the recall query path all route
text through `normalize_text` so the index and queries are analyzed identically
(the IR invariant). Today the only provider is the dependency-free josa-strip
heuristic; a future `kiwi` provider plugs into `normalize_token` behind an
optional import and bumps `ANALYZER_VERSION`. Pure stdlib, never raises.
"""
from __future__ import annotations

import re

from scripts.text_match import _JOSA

#: Index-invalidation key. Encodes provider id + logic version: any change to
#: normalization behavior (or the active provider) MUST bump this so stale
#: indexes are rebuilt (see fts.ensure_fts).
ANALYZER_VERSION = "heuristic-1"

_JOSA_LONGEST_FIRST = sorted(_JOSA, key=len, reverse=True)
_HANGUL_END = re.compile(r"[가-힣]$")

_PROVIDER_CACHE: str | None = None


def _provider() -> str:
    """Resolve the active normalizer provider (cached). The seam: only
    'heuristic' is implemented today; an unknown/unimplemented value degrades to
    'heuristic' so behavior always matches ANALYZER_VERSION. Best-effort —
    never raises."""
    global _PROVIDER_CACHE
    if _PROVIDER_CACHE is None:
        prov = "heuristic"
        try:
            from scripts import config
            want = (config.load_config() or {}).get("recall", {}).get("normalizer")
            if want == "heuristic":   # extend here when 'kiwi' lands
                prov = want
        except Exception:
            prov = "heuristic"
        _PROVIDER_CACHE = prov
    return _PROVIDER_CACHE


def _reset_provider_cache() -> None:
    """Test helper: drop the cached provider so config changes take effect."""
    global _PROVIDER_CACHE
    _PROVIDER_CACHE = None


def _heuristic_token(tok: str) -> str:
    """Drop one trailing Korean postposition from a Hangul-ending token when at
    least 2 chars remain. Mirrors the original recall._strip_josa."""
    if not _HANGUL_END.search(tok):
        return tok
    for j in _JOSA_LONGEST_FIRST:
        if tok.endswith(j) and len(tok) - len(j) >= 2:
            return tok[: -len(j)]
    return tok


def normalize_token(tok: str) -> str:
    """Normalize one whitespace-delimited token under the active provider.
    Provider dispatch is the seam; only 'heuristic' is implemented today."""
    # _provider() == "kiwi" branch plugs in here (optional import) in the future.
    return _heuristic_token(tok)


def normalize_text(text: str | None) -> str:
    """Normalize free text for indexing or querying: split on whitespace,
    normalize each token, rejoin. Idempotent on ASCII. Never raises."""
    if not text:
        return ""
    return " ".join(normalize_token(t) for t in text.split())
