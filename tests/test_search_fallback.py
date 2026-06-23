import pytest
from scripts import search as S
from scripts.search.base import SearchError


class _Stub:
    def __init__(self, behavior):
        self.behavior = behavior  # "hits" | "empty" | "error"

    def search(self, query, *, limit=10):
        if self.behavior == "error":
            raise SearchError("stub 429")
        if self.behavior == "empty":
            return []
        return [{"title": "t", "url": "https://x", "snippet": "s"}]


def _patch(monkeypatch, available, behaviors):
    monkeypatch.setattr(S, "available_providers", lambda: list(available))
    monkeypatch.setattr(S, "resolve_provider", lambda name=None: _Stub(behaviors[name or available[0]]))


def test_first_error_second_answers(monkeypatch):
    _patch(monkeypatch, ["brave", "tavily"], {"brave": "error", "tavily": "hits"})
    out = S.search_with_fallback("q", provider="brave")
    assert out["provider"] == "tavily"
    assert out["results"] and out["tried"] == ["brave", "tavily"]


def test_empty_counts_as_failure(monkeypatch):
    _patch(monkeypatch, ["brave", "tavily"], {"brave": "empty", "tavily": "hits"})
    out = S.search_with_fallback("q", provider="brave")
    assert out["provider"] == "tavily"


def test_all_fail_raises_naming_tried(monkeypatch):
    _patch(monkeypatch, ["brave", "tavily"], {"brave": "error", "tavily": "empty"})
    with pytest.raises(SearchError) as e:
        S.search_with_fallback("q", provider="brave")
    assert "brave" in str(e.value) and "tavily" in str(e.value)
