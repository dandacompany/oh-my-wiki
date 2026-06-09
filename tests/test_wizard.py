import json
import subprocess
import sys
from pathlib import Path

from scripts import registry, wizard


def test_status_zero_vaults(tmp_db):
    registry.init_db(tmp_db)
    out = wizard.status(tmp_db)
    assert out["vault_count"] == 0
    assert out["active"] is None
    assert out["needs"] == "setup"
    assert out["confirm_target"] is False


def test_status_confirm_target_false_with_one_vault(tmp_db, tmp_path):
    registry.init_db(tmp_db)
    p = tmp_path / "v"; p.mkdir()
    registry.add_vault(tmp_db, name="v", path=p, type_="markdown", mode="wiki")
    registry.set_active(tmp_db, "v")
    out = wizard.status(tmp_db)
    assert out["confirm_target"] is False


def test_status_confirm_target_true_with_two_vaults(tmp_db, tmp_path):
    registry.init_db(tmp_db)
    for n in ("a", "b"):
        p = tmp_path / n; p.mkdir()
        registry.add_vault(tmp_db, name=n, path=p, type_="markdown", mode="wiki")
    registry.set_active(tmp_db, "a")
    out = wizard.status(tmp_db)
    assert out["confirm_target"] is True


def test_status_confirm_target_false_when_no_db(tmp_path):
    out = wizard.status(tmp_path / "missing.db")
    assert out["confirm_target"] is False


def test_status_one_active(tmp_db, tmp_path):
    registry.init_db(tmp_db)
    p = tmp_path / "v"; p.mkdir()
    registry.add_vault(tmp_db, name="v", path=p, type_="markdown", mode="memo")
    registry.set_active(tmp_db, "v")
    out = wizard.status(tmp_db)
    assert out["vault_count"] == 1
    assert out["active"]["name"] == "v"
    assert out["active"]["mode"] == "memo"
    assert out["needs"] == "op"


def test_status_multi_no_active(tmp_db, tmp_path):
    registry.init_db(tmp_db)
    for n in ("a", "b"):
        p = tmp_path / n; p.mkdir()
        registry.add_vault(tmp_db, name=n, path=p, type_="markdown", mode="memo")
    out = wizard.status(tmp_db)
    assert out["vault_count"] == 2
    assert out["active"] is None
    assert out["needs"] == "select"


def test_cli_status_emits_json(tmp_db):
    registry.init_db(tmp_db)
    res = subprocess.run(
        [sys.executable, "-m", "scripts.wizard", "status", "--db", str(tmp_db)],
        capture_output=True, text=True, check=True,
        cwd=Path(__file__).resolve().parents[1],
    )
    payload = json.loads(res.stdout)
    assert payload["vault_count"] == 0
