"""Removing the active vault must hand `active` to a survivor, not leave it empty.

Three paths reach this: `vault forget`, `vault archive`, and `vault delete` (soft and
hard). All of them funnel into registry.forget_vault / set_archived, so succession
lives there rather than in each command. Before this, a create-then-remove round trip —
the exact shape of exploratory use and of following a tutorial — left the registry with
no is_active=1 row and every subsequent command failing with "no active vault", even
though other vaults were still registered.
"""
import pytest

from scripts import registry, vault_ops


def _mk(db, tmp_path, name):
    p = tmp_path / name
    p.mkdir(parents=True, exist_ok=True)
    return registry.add_vault(db, name=name, path=p, type_="markdown", mode="wiki")


@pytest.fixture
def two_vaults(tmp_db, tmp_path):
    registry.init_db(tmp_db)
    _mk(tmp_db, tmp_path, "keeper")
    _mk(tmp_db, tmp_path, "victim")
    registry.set_active(tmp_db, "keeper")
    registry.set_active(tmp_db, "victim")      # victim is active, keeper used earlier
    return tmp_db


def _active(db):
    row = registry.get_active(db)
    return row["name"] if row else None


def test_forget_active_hands_over(two_vaults):
    registry.forget_vault(two_vaults, "victim")
    assert _active(two_vaults) == "keeper"


def test_archive_active_hands_over(two_vaults):
    registry.set_archived(two_vaults, "victim", True)
    assert _active(two_vaults) == "keeper"


def test_delete_active_hands_over(two_vaults, tmp_path):
    vault_ops.delete(two_vaults, "victim", hard=False, yes=True,
                     now_ts="20260822-000000")
    assert _active(two_vaults) == "keeper"


def test_forget_reports_the_successor(two_vaults):
    """The caller must be able to tell the user active moved — silence is the defect."""
    out = registry.forget_vault(two_vaults, "victim")
    assert out["active_moved_to"] == "keeper"


def test_forget_non_active_leaves_active_alone(two_vaults):
    out = registry.forget_vault(two_vaults, "keeper")
    assert _active(two_vaults) == "victim"
    assert out["active_moved_to"] is None


def test_last_vault_leaves_no_active_and_says_so(tmp_db, tmp_path):
    registry.init_db(tmp_db)
    _mk(tmp_db, tmp_path, "only")
    registry.set_active(tmp_db, "only")
    out = registry.forget_vault(tmp_db, "only")
    assert _active(tmp_db) is None
    assert out["active_moved_to"] is None


def test_archived_vaults_are_not_eligible_successors(tmp_db, tmp_path):
    registry.init_db(tmp_db)
    for n in ("shelved", "live", "victim"):
        _mk(tmp_db, tmp_path, n)
    registry.set_archived(tmp_db, "shelved", True)
    registry.set_active(tmp_db, "live")
    registry.set_active(tmp_db, "victim")
    registry.forget_vault(tmp_db, "victim")
    assert _active(tmp_db) == "live"


def test_forget_unknown_vault_still_raises(two_vaults):
    with pytest.raises(registry.VaultError):
        registry.forget_vault(two_vaults, "nope")
