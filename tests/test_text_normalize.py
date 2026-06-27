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
    assert isinstance(tn.ANALYZER_VERSION, str) and tn.ANALYZER_VERSION
    assert tn._provider() in tn.ANALYZER_VERSION  # version encodes the provider id


def test_provider_defaults_to_heuristic():
    tn._reset_provider_cache()
    assert tn._provider() == "heuristic"
