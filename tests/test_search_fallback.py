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


def test_cli_fallback_reports_provider(monkeypatch, capsys):
    import json
    from scripts import omw_cli
    _patch(monkeypatch, ["brave", "tavily"], {"brave": "error", "tavily": "hits"})
    rc = omw_cli.main(["search", "q"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and out["provider"] == "tavily"


def test_cli_no_fallback_single_provider(monkeypatch, capsys):
    from scripts import omw_cli
    _patch(monkeypatch, ["brave", "tavily"], {"brave": "error", "tavily": "hits"})
    rc = omw_cli.main(["search", "q", "--no-fallback"])
    assert rc == 1  # bare search() raises on the configured provider's error
