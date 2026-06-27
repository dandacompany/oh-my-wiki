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
