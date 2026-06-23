import json
from scripts import ops_registry as reg
from scripts import cards


def test_autoresearch_card_shape():
    spec = reg.get("autoresearch")
    out = cards.render_card(spec, {"topic": "국내 중년 남성 패션", "rounds": 4})
    assert "procedure: autoresearch" in out
    assert "needs omw skill" in out
    assert "topic: 국내 중년 남성 패션" in out
    assert "rounds: 4" in out
    assert "uses: search → fetch → reindex" in out
    assert "steps: commands/autoresearch.md" in out
    assert "do NOT expect a deterministic result" in out


def test_card_json_roundtrips():
    spec = reg.get("autoresearch")
    data = json.loads(cards.render_card_json(spec, {"topic": "x", "rounds": 2}))
    assert data["procedure"] == "autoresearch"
    assert data["args"]["topic"] == "x"
    assert data["args"]["rounds"] == 2
    assert data["steps"] == "commands/autoresearch.md"
    assert data["uses"] == ["search", "fetch", "reindex"]
