import types

import pytest

from scripts import embed


def test_get_embedder_fastembed_returns_fastembed_embedder():
    e = embed.get_embedder({"provider": "fastembed",
                            "model": "intfloat/multilingual-e5-small", "dim": 384})
    assert isinstance(e, embed.FastEmbedEmbedder)
    assert e.dim == 384
    assert e.model == "intfloat/multilingual-e5-small"


def test_get_embedder_fastembed_defaults():
    e = embed.get_embedder({"provider": "fastembed"})
    assert e.model == embed.DEFAULT_LOCAL_MODEL
    assert e.dim == 384


def test_fastembed_embed_lazy_imports_and_maps(monkeypatch):
    # Fake the fastembed module so no real model downloads.
    calls = {}

    class _FakeTE:
        def __init__(self, model_name=None):
            calls["model_name"] = model_name

        def embed(self, texts):
            for _ in texts:
                yield [0.1, 0.2, 0.3]

    fake_mod = types.SimpleNamespace(TextEmbedding=_FakeTE)
    monkeypatch.setitem(__import__("sys").modules, "fastembed", fake_mod)
    e = embed.FastEmbedEmbedder(model="m", dim=3)
    out = e.embed(["a", "b"])
    assert out == [[0.1, 0.2, 0.3], [0.1, 0.2, 0.3]]
    assert calls["model_name"] == "m"


from scripts import embed_install


def test_ensure_fastembed_noop_when_present(monkeypatch):
    monkeypatch.setattr(embed_install, "fastembed_available", lambda: True)
    called = {"pip": False}
    monkeypatch.setattr(embed_install.subprocess, "run",
                        lambda *a, **k: called.__setitem__("pip", True))
    assert embed_install.ensure_fastembed(assume_yes=True) is True
    assert called["pip"] is False


def test_ensure_fastembed_installs_when_absent(monkeypatch):
    states = iter([False, True])  # absent, then present after install
    monkeypatch.setattr(embed_install, "fastembed_available", lambda: next(states))
    ran = {}
    monkeypatch.setattr(embed_install.subprocess, "run",
                        lambda argv, **k: ran.setdefault("argv", argv))
    assert embed_install.ensure_fastembed(assume_yes=True) is True
    assert "fastembed" in " ".join(ran["argv"])


from scripts import vector_index


from scripts import embed_admin, config as _config


def _fake_env(tmp_path, monkeypatch):
    monkeypatch.setenv("OMW_HOME", str(tmp_path))
    from scripts import registry
    from scripts.paths import registry_path
    db = registry_path()
    registry.init_db(db)
    registry.add_vault(db, name="v1", path=tmp_path / "v1", type_="markdown", mode="wiki")
    return db


def test_switch_model_writes_config_resets_and_reindexes(tmp_path, monkeypatch):
    db = _fake_env(tmp_path, monkeypatch)
    monkeypatch.setattr(embed_admin.embed_install, "ensure_fastembed", lambda **k: True)
    monkeypatch.setattr(embed_admin, "resolve_dim", lambda d, m: 384)
    reset_called = {"n": 0}
    monkeypatch.setattr(embed_admin.vector_index, "reset", lambda d: reset_called.__setitem__("n", reset_called["n"] + 1))
    reidx = {"vaults": 0}
    monkeypatch.setattr(embed_admin.reindex, "refresh_embeddings",
                        lambda d, *, vault_id, relpaths=None: reidx.__setitem__("vaults", reidx["vaults"] + 1) or 1)
    out = embed_admin.switch_model(db, "intfloat/multilingual-e5-small", assume_yes=True)
    assert out["ok"] is True and out["dim"] == 384
    emb = _config.load_config()["recall"]["embedding"]
    assert emb["provider"] == "fastembed" and emb["model"] == "intfloat/multilingual-e5-small" and emb["dim"] == 384
    assert reset_called["n"] == 1 and reidx["vaults"] == 1


def test_switch_model_aborts_on_install_failure_no_config_change(tmp_path, monkeypatch):
    db = _fake_env(tmp_path, monkeypatch)
    monkeypatch.setattr(embed_admin.embed_install, "ensure_fastembed", lambda **k: False)
    out = embed_admin.switch_model(db, "some/model", assume_yes=True)
    assert out["ok"] is False
    assert (_config.load_config().get("recall") or {}).get("embedding") in (None, {})


def test_add_model_registers_known(tmp_path, monkeypatch):
    db = _fake_env(tmp_path, monkeypatch)
    monkeypatch.setattr(embed_admin.embed_install, "ensure_fastembed", lambda **k: True)
    monkeypatch.setattr(embed_admin, "resolve_dim", lambda d, m: 512)
    out = embed_admin.add_model(db, "custom/model", assume_yes=True)
    assert out["ok"] is True and out["dim"] == 512
    known = embed_admin.list_models(db)["known"]
    assert "custom/model" in known


def test_status_shape(tmp_path, monkeypatch):
    db = _fake_env(tmp_path, monkeypatch)
    st = embed_admin.status(db)
    for key in ("provider", "model", "dim", "strategy", "fastembed_available", "vector_index_available", "vaults"):
        assert key in st


def test_vector_index_reset_allows_new_dim(tmp_path, monkeypatch):
    if not vector_index.available():
        pytest.skip("sqlite-vec not installed")
    from scripts import registry
    db = tmp_path / "registry.db"
    registry.init_db(db)
    v = registry.add_vault(db, name="v1", path=tmp_path / "v1",
                           type_="markdown", mode="wiki")
    e8 = embed.FakeEmbedder(dim=8)
    assert vector_index.upsert(db, vault_id=v["id"], embedder=e8,
                               rows=[("wiki/a.md", "hello")]) == 1
    # switching to a different dim requires a reset first
    vector_index.reset(db)
    e16 = embed.FakeEmbedder(dim=16)
    assert vector_index.upsert(db, vault_id=v["id"], embedder=e16,
                               rows=[("wiki/a.md", "hello")]) == 1
