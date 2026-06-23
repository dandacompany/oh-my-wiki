import json
import pytest
from scripts import omw_cli


@pytest.fixture
def seeded(tmp_path, monkeypatch):
    """A registry + one vault with two indexed pages (reuse the project's vault helpers)."""
    from tests.conftest import make_vault_with_pages  # see note below
    db, vault_id = make_vault_with_pages(tmp_path, monkeypatch, pages={
        "concepts/athleisure.md": "# Athleisure\n\nRunning and outdoor shift in menswear.",
        "entities/musinsa.md": "# Musinsa\n\nVertical fashion platform for menswear.",
    })
    return db


def test_find_returns_ranked_hits(seeded, capsys):
    rc = omw_cli.main(["find", "menswear"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "musinsa" in out.lower() or "athleisure" in out.lower()


def test_find_json(seeded, capsys):
    rc = omw_cli.main(["find", "platform", "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    data = json.loads(out)
    assert isinstance(data, list)
    assert all("relpath" in h and "score" in h for h in data)


def test_find_limit(seeded, capsys):
    rc = omw_cli.main(["find", "menswear", "--limit", "1", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert len(data) <= 1


def test_find_empty_query_is_usage_not_stub(capsys):
    with pytest.raises(SystemExit) as e:   # argparse: missing required positional
        omw_cli.main(["find"])
    assert e.value.code == 2
