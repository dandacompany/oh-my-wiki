"""Single home for Korean search-text normalization (the analyzer seam).

The FTS index, the token-scorer fallback, and the recall query path all route
text through `normalize_text` so the index and queries are analyzed identically
(the IR invariant). Today the only provider is the dependency-free josa-strip
heuristic; a future `kiwi` provider plugs into `normalize_text` behind an
optional import and bumps `analyzer_version()`. Pure stdlib, never raises.
"""
from __future__ import annotations

import re
import unicodedata

from scripts.text_match import _JOSA

_JOSA_LONGEST_FIRST = sorted(_JOSA, key=len, reverse=True)
_HANGUL_END = re.compile(r"[가-힣]$")
_HANGUL = re.compile(r"[가-힣]")
#: one run of Hangul, or one run of everything else — the routing unit.
_SCRIPT_RUN = re.compile(r"[가-힣]+|[^가-힣\s]+")

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
            elif want == "kiwi":
                from scripts import kiwi_install
                if kiwi_install.kiwi_available():
                    prov = "kiwi"
        except Exception:
            prov = "heuristic"
        _PROVIDER_CACHE = prov
    return _PROVIDER_CACHE


#: bump when the kiwi provider's routing rule changes, so existing indexes are
#: rebuilt instead of silently disagreeing with newly normalized queries.
#: r3 = NFC fold at the seam, then route by script RUN (Hangul to Kiwi, the
#: rest left intact) so identifiers survive inside Korean words.
_KIWI_RULE = "r3"


def _kiwipiepy_version() -> str:
    """Installed kiwipiepy version, or 'unknown'. Never raises."""
    try:
        from importlib.metadata import version
        return version("kiwipiepy")
    except Exception:
        return "unknown"


def analyzer_version() -> str:
    """Index-invalidation key, DERIVED from the effective provider (cached).
    heuristic → 'heuristic-1'; kiwi → 'kiwi-<kiwipiepy version>-<rule>'. Any
    provider, library, or rule change bumps this so the FTS gate auto-rebuilds.
    Never raises."""
    global _VERSION_CACHE
    if _VERSION_CACHE is None:
        if _provider() == "kiwi":
            _VERSION_CACHE = f"kiwi-{_kiwipiepy_version()}-{_KIWI_RULE}"
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


_KIWI = None  # lazy singleton Kiwi() instance
#: Sejong content tags to keep. V* (verb/adjective) emit dictionary form (stem+다).
_KIWI_KEEP = {"NNG", "NNP", "SL", "SN", "MAG", "VV", "VA"}
_KIWI_VERB = {"VV", "VA"}

#: dictionaries Kiwi loads by default that this analyzer never benefits from.
#: Measured on a real vault: skipping them halves model load (1.46s -> 0.77s)
#: and left the normalized output of all 25 sampled documents byte-identical.
_KIWI_SKIP_DICTS = {"load_multi_dict": False, "load_typo_dict": False}


def _new_kiwi():
    """Construct Kiwi without the dictionaries this analyzer does not use.
    Older kiwipiepy builds lack those keyword arguments — fall back rather than
    let a TypeError silently demote every Korean text to the heuristic."""
    from kiwipiepy import Kiwi
    try:
        return Kiwi(**_KIWI_SKIP_DICTS)
    except TypeError as exc:
        # Only retry for "this build has no such argument". A TypeError raised
        # from inside a working Kiwi.__init__ must surface, not cost a second
        # full model load and then get swallowed into a silent heuristic demotion.
        if not any(name in str(exc) for name in _KIWI_SKIP_DICTS):
            raise
        return Kiwi()


def _kiwi_text(text: str) -> str:
    """Kiwi text normalizer: keep content morphemes as lemmas (nouns as-is,
    verbs/adjectives → dictionary form stem+다), drop josa/endings/symbols.
    Any kiwipiepy failure falls back to the heuristic for this call (never raises)."""
    global _KIWI
    try:
        if _KIWI is None:
            _KIWI = _new_kiwi()
        out = []
        for tok in _KIWI.tokenize(text):
            base = tok.tag.split("-")[0]
            if base in _KIWI_KEEP:
                out.append(tok.form + "다" if base in _KIWI_VERB else tok.form)
        return " ".join(out)
    except Exception:
        return _heuristic_text(text)


def _by_script(text: str) -> str:
    """Route each run of Hangul to Kiwi and everything else to the heuristic.
    Both sides of the IR invariant call this, so index and query stay comparable.

    Kiwi is a Korean morphological analyzer and mangles Latin identifiers —
    'recall.py' becomes 'r ecall.py', 'node_modules' becomes 'node modules'.
    Sending only Hangul through it keeps identifiers searchable as written, and
    lets an all-Latin query (a file path, say) skip the model load altogether.

    Splitting by *run* rather than by whitespace token matters: Korean technical
    prose is full of 'recall.py에서' and 'AGENTS.md에', where a per-token rule
    would send the identifier back through Kiwi — worse than before, since the
    query side would now leave it intact.

    Hangul runs are analyzed in one call so Kiwi keeps its context, which means
    the output is REGROUPED, not in source order. Safe here because every
    consumer is token-set based (`fts._match_query` OR-joins single tokens);
    do not use this output where adjacency or phrase order matters.
    """
    hangul, other = [], []
    for token in text.split():
        if not _HANGUL.search(token):
            other.append(token)
            continue
        # 'node_modules를' / 'AGENTS.md에' — a Latin identifier wearing a
        # postposition. Strip it here; splitting into runs first would hand the
        # bare '를' to Kiwi, which analyzes it into a spurious token.
        stripped = _heuristic_token(token)
        if not _HANGUL.search(stripped):
            other.append(stripped)
            continue
        for run in _SCRIPT_RUN.findall(token):
            (hangul if _HANGUL.match(run) else other).append(run)
    parts = []
    if hangul:
        parts.append(_kiwi_text(" ".join(hangul)))
    if other:
        parts.append(_heuristic_text(" ".join(other)))
    return " ".join(p for p in parts if p)


#: provider id → text-level normalizer (str) -> str. dispatch falls back to
#: heuristic for unknown providers.
_NORMALIZERS = {"heuristic": _heuristic_text, "kiwi": _by_script}


def normalize_text(text: str | None) -> str:
    """Normalize free text for indexing or querying under the active provider.
    Index and query route through the same provider (the IR invariant).

    Leaves text without Hangul untouched beyond whitespace collapsing — that
    was claimed here before it was true: the kiwi provider used to run Latin
    text through the morphological analyzer, which split 'recall.py' into
    'r ecall.py'. See `_by_script`. Never raises."""
    if not text:
        return ""
    try:
        # Fold to NFC first: decomposed Hangul (macOS SMB vaults write NFD
        # filenames) carries no 가-힣 codepoints, so every script test below —
        # and the heuristic's own josa stripper — would miss it entirely.
        text = unicodedata.normalize("NFC", text)
        return _NORMALIZERS.get(_provider(), _heuristic_text)(text)
    except Exception:
        return _heuristic_text(text)


def strip_josa(word: str) -> str:
    """Drop one trailing Korean postposition, deterministically.

    Provider-independent on purpose: callers that need the bare stem (matching a
    prompt's '번들을' against a title's '번들') must not route through Kiwi,
    which re-analyzes the word into morphemes instead of just unsuffixing it."""
    return _heuristic_token(word) if word else ""


def normalize_token(tok: str) -> str:
    """Normalize one token under the active provider. Never raises."""
    if not tok:
        return ""
    return normalize_text(tok)
