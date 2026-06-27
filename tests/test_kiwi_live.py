import pytest

pytest.importorskip("kiwipiepy")

from scripts import text_normalize as tn  # noqa: E402


def test_kiwi_lemmatizes_real_text():
    out = tn._kiwi_text("학교에서 먹었다")
    toks = out.split()
    assert "학교" in toks          # noun kept
    assert "먹다" in toks          # verb → dictionary form
    assert "에서" not in toks      # josa dropped
    assert "었다" not in out       # ending dropped


def test_kiwi_adjective_dictionary_form():
    out = tn._kiwi_text("아파서 약을 먹었다")
    toks = out.split()
    assert "아프다" in toks        # adjective → dictionary form
    assert "약" in toks
    assert "먹다" in toks


def test_kiwi_irregular_predicates_kept():
    out = tn._kiwi_text("더운 날씨에 걸어서 집을 지었다")
    toks = out.split()
    assert "덥다" in toks    # ㅂ-irregular adjective (VA-I)
    assert "걷다" in toks    # ㄷ-irregular verb (VV-I)
    assert "짓다" in toks    # ㅅ-irregular verb (VV-I)
