"""Unit tests for scripts.recall — render_always_on_block + marker-agnostic upsert."""
from scripts import recall, text_normalize


def test_always_on_block_is_wiki_first_and_marked():
    block = recall.render_always_on_block()
    assert "omw-wiki-first:start" in block and "omw-wiki-first:end" in block
    assert "omw find" in block and "raw/" in block


def test_normalize_query_delegates_and_preserves_behavior():
    assert recall.normalize_query("학교에서 ARIMA와") == "학교 ARIMA"
    assert recall.normalize_query("학교에서") == text_normalize.normalize_text("학교에서")


def test_strip_josa_still_callable():
    assert recall._strip_josa("평가지표를") == "평가지표"
