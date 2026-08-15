from scripts import kiwi_install
from scripts import text_normalize as tn


def test_strips_trailing_josa_on_hangul_token():
    assert tn.normalize_token("학교에서") == "학교"
    assert tn.normalize_token("평가지표를") == "평가지표"
    assert tn.normalize_token("ARIMA와") == "ARIMA"


def test_keeps_token_when_under_two_chars_would_remain():
    # '집에' → stripping '에' leaves '집' (1 char) < 2 → unchanged
    assert tn.normalize_token("집에") == "집에"


def test_ascii_and_short_tokens_unchanged():
    assert tn.normalize_token("Karpathy") == "Karpathy"
    assert tn.normalize_token("n8n") == "n8n"
    assert tn.normalize_token("RAG") == "RAG"


def test_normalize_text_is_symmetric_for_body_and_query():
    body = tn.normalize_text("학교에서 배웠다")
    assert "학교" in body.split()
    assert tn.normalize_text("학교") == "학교"  # query normalizes to the same surface


def test_normalize_text_idempotent():
    x = "학교에서 ARIMA와 평가지표를 봤다"
    once = tn.normalize_text(x)
    assert tn.normalize_text(once) == once


def test_normalize_text_empty_and_none():
    assert tn.normalize_text("") == ""
    assert tn.normalize_text(None) == ""


def test_normalize_text_never_raises_on_weird_input():
    for s in ["!!!", "   ", "한", "가나다라마바사" * 1000]:
        tn.normalize_text(s)  # must not raise


def test_analyzer_version_present_and_provider_tagged():
    tn._reset_provider_cache()
    v = tn.analyzer_version()
    assert isinstance(v, str) and v
    assert tn._provider() in v  # version encodes the provider id


def test_analyzer_version_is_function_and_heuristic_tagged():
    assert callable(tn.analyzer_version)
    tn._reset_provider_cache()
    assert tn.analyzer_version() == "heuristic-1"


def test_heuristic_text_strips_each_token():
    assert tn._heuristic_text("학교에서 평가지표를") == "학교 평가지표"


def test_provider_defaults_to_heuristic():
    tn._reset_provider_cache()
    assert tn._provider() == "heuristic"


def test_normalize_token_empty_and_none():
    """FIX 1: normalize_token must handle None and empty strings (contract: never raise)."""
    assert tn.normalize_token("") == ""
    assert tn.normalize_token(None) == ""


def test_normalize_token_dispatches_via_provider():
    """FIX 2: normalize_token must route through the provider dispatch table."""
    tn._reset_provider_cache()
    assert tn.normalize_token("학교에서") == "학교"   # routes through _NORMALIZERS[_provider()]
    assert "heuristic" in tn._NORMALIZERS


def _use_fake_kiwi(monkeypatch, config_value="kiwi"):
    monkeypatch.setattr(kiwi_install, "kiwi_available", lambda: True)
    monkeypatch.setitem(tn._NORMALIZERS, "kiwi", lambda t: "LEMMA:" + " ".join(t.split()))
    from scripts import config
    monkeypatch.setattr(config, "load_config",
                        lambda: {"recall": {"normalizer": config_value}})
    tn._reset_provider_cache()


def test_provider_is_kiwi_when_configured_and_available(monkeypatch):
    _use_fake_kiwi(monkeypatch)
    assert tn._provider() == "kiwi"
    assert tn.normalize_text("학교에서 먹었다") == "LEMMA:학교에서 먹었다"


def test_provider_falls_back_to_heuristic_when_kiwi_unavailable(monkeypatch):
    from scripts import config
    monkeypatch.setattr(kiwi_install, "kiwi_available", lambda: False)
    monkeypatch.setattr(config, "load_config",
                        lambda: {"recall": {"normalizer": "kiwi"}})
    tn._reset_provider_cache()
    assert tn._provider() == "heuristic"          # config=kiwi but unavailable
    assert tn.analyzer_version() == "heuristic-1"  # version matches the ACTUAL provider
    assert tn.normalize_text("학교에서") == "학교"  # heuristic still runs


# --- script routing: Hangul goes to Kiwi, everything else does not ----------
# Kiwi mangles Latin identifiers ('recall.py' -> 'r ecall.py'). That used to be
# survivable only because index and query were mangled identically. Routing by
# script keeps identifiers intact on BOTH sides and lets an ASCII-only query
# skip the 1.4s Kiwi model load entirely.

def _real_kiwi_provider(monkeypatch):
    """Select the kiwi provider with a stand-in that is obvious in output."""
    monkeypatch.setattr(kiwi_install, "kiwi_available", lambda: True)
    from scripts import config
    monkeypatch.setattr(config, "load_config",
                        lambda: {"recall": {"normalizer": "kiwi"}})
    tn._reset_provider_cache()


def test_ascii_only_text_never_loads_kiwi(monkeypatch):
    _real_kiwi_provider(monkeypatch)
    def boom(_):
        raise AssertionError("Kiwi loaded for ASCII-only text")
    monkeypatch.setattr(tn, "_kiwi_text", boom)
    assert tn.normalize_text("recall.py key-rotation") == "recall.py key-rotation"


def test_latin_identifiers_survive_inside_korean_text(monkeypatch):
    _real_kiwi_provider(monkeypatch)
    monkeypatch.setattr(tn, "_kiwi_text", lambda t: "KIWI(" + t + ")")
    out = tn.normalize_text("omw의 recall.py 훅은 node_modules 없이")
    assert "recall.py" in out.split() and "node_modules" in out.split()


def test_hangul_tokens_still_reach_kiwi(monkeypatch):
    _real_kiwi_provider(monkeypatch)
    seen = []
    monkeypatch.setattr(tn, "_kiwi_text", lambda t: seen.append(t) or t)
    tn.normalize_text("omw의 recall.py 훅은 node_modules 없이")
    assert seen and "훅은" in seen[0] and "recall.py" not in seen[0]


def test_a_document_and_a_query_share_tokens_for_the_same_identifier(monkeypatch):
    """The IR invariant, stated as the behaviour that actually matters."""
    _real_kiwi_provider(monkeypatch)
    monkeypatch.setattr(tn, "_kiwi_text", lambda t: " ".join(t.split()))
    doc = tn.normalize_text("omw의 recall.py 훅은 key-rotation 로직을 처리한다")
    query = tn.normalize_text("recall.py")
    assert set(query.split()) <= set(doc.split())


def test_analyzer_version_encodes_the_routing_rule(monkeypatch):
    """A rule change must invalidate existing indexes, not silently mismatch."""
    _real_kiwi_provider(monkeypatch)
    version = tn.analyzer_version()
    assert version.startswith("kiwi-")
    assert version != "kiwi-" + tn._kiwipiepy_version()


def test_kiwi_text_failure_falls_back_to_heuristic(monkeypatch):
    # if the real _kiwi_text raises, the call must not raise — fall back
    monkeypatch.setattr(kiwi_install, "kiwi_available", lambda: True)
    from scripts import config
    monkeypatch.setattr(config, "load_config",
                        lambda: {"recall": {"normalizer": "kiwi"}})
    def boom(_):
        raise RuntimeError("kiwi broke")
    monkeypatch.setitem(tn._NORMALIZERS, "kiwi", boom)
    tn._reset_provider_cache()
    # normalize_text must swallow and not raise
    out = tn.normalize_text("학교에서")
    assert isinstance(out, str)


def test_latin_survives_a_token_that_also_has_korean(monkeypatch):
    """Korean technical prose is full of 'recall.py에서' — routing per whitespace
    token would send the whole thing to Kiwi and split the identifier again."""
    _real_kiwi_provider(monkeypatch)
    monkeypatch.setattr(tn, "_kiwi_text", lambda t: "<" + t + ">")
    for token, latin in [("recall.py에서", "recall.py"),
                         ("node_modules를", "node_modules"),
                         ("AGENTS.md에", "AGENTS.md")]:
        assert latin in tn.normalize_text(token).split(), token


def test_decomposed_hangul_normalizes_like_composed(monkeypatch):
    """NFD filenames (macOS SMB vaults) contain no [가-힣] — without folding at
    the seam they would route to the heuristic while NFC text routes to Kiwi."""
    import unicodedata
    _real_kiwi_provider(monkeypatch)
    monkeypatch.setattr(tn, "_kiwi_text", lambda t: " ".join(t.split()))
    composed = "페르소나 번들"
    decomposed = unicodedata.normalize("NFD", composed)
    assert tn.normalize_text(decomposed) == tn.normalize_text(composed)


def test_a_latin_identifier_wearing_a_postposition_keeps_its_shape(monkeypatch):
    """'node_modules를' must not hand a bare '를' to Kiwi, which turns that lone
    postposition into a spurious token."""
    _real_kiwi_provider(monkeypatch)
    monkeypatch.setattr(tn, "_kiwi_text", lambda t: "<" + t + ">")
    for token, expected in [("recall.py에서", "recall.py"),
                            ("node_modules를", "node_modules"),
                            ("AGENTS.md에", "AGENTS.md")]:
        assert tn.normalize_text(token) == expected


def test_a_genuinely_mixed_word_splits_by_script(monkeypatch):
    _real_kiwi_provider(monkeypatch)
    monkeypatch.setattr(tn, "_kiwi_text", lambda t: t)
    assert set(tn.normalize_text("AI기반").split()) == {"AI", "기반"}


def test_strip_josa_is_provider_independent(monkeypatch):
    """Callers need the bare stem, not a morpheme analysis — even under kiwi."""
    _real_kiwi_provider(monkeypatch)
    assert tn.strip_josa("번들을") == "번들"
    assert tn.strip_josa("ARIMA와") == "ARIMA"
    assert tn.strip_josa("") == ""
