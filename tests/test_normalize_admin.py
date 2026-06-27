from scripts import normalize_admin


def test_switch_to_heuristic_writes_config_and_reindexes(tmp_path, monkeypatch):
    from scripts import config, registry, reindex
    monkeypatch.setattr(config, "set_config", lambda *a, **k: None)
    monkeypatch.setattr(registry, "list_vaults", lambda db: [{"id": 1}, {"id": 2}])
    monkeypatch.setattr(reindex, "full", lambda db, *, vault_id: 3)
    res = normalize_admin.switch_provider(tmp_path / "r.db", "heuristic")
    assert res["ok"] is True
    assert res["provider"] == "heuristic"
    assert res["vaults_reindexed"] == 2


def test_switch_to_kiwi_aborts_when_install_declined(tmp_path, monkeypatch):
    from scripts import config, kiwi_install
    monkeypatch.setattr(kiwi_install, "ensure_kiwi", lambda **k: False)
    wrote = {"called": False}
    monkeypatch.setattr(config, "set_config", lambda *a, **k: wrote.__setitem__("called", True))
    res = normalize_admin.switch_provider(tmp_path / "r.db", "kiwi")
    assert res["ok"] is False
    assert "kiwipiepy" in (res["detail"] or "")
    assert wrote["called"] is False  # config unchanged on abort


def test_switch_rejects_unknown_provider(tmp_path):
    res = normalize_admin.switch_provider(tmp_path / "r.db", "spacy")
    assert res["ok"] is False
    assert res["vaults_reindexed"] == 0


def test_switch_to_kiwi_succeeds_when_installed(tmp_path, monkeypatch):
    from scripts import config, kiwi_install, registry, reindex
    monkeypatch.setattr(kiwi_install, "ensure_kiwi", lambda **k: True)
    monkeypatch.setattr(config, "set_config", lambda *a, **k: None)
    monkeypatch.setattr(registry, "list_vaults", lambda db: [{"id": 1}])
    monkeypatch.setattr(reindex, "full", lambda db, *, vault_id: 5)
    res = normalize_admin.switch_provider(tmp_path / "r.db", "kiwi")
    assert res["ok"] is True
    assert res["provider"] == "kiwi"
    assert res["vaults_reindexed"] == 1
