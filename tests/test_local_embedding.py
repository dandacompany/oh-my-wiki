import json as _json
import types

import pytest

from scripts import config as _config
from scripts import embed, embed_admin, embed_install, omw_cli, setup_wizard, vector_index


def test_get_embedder_fastembed_returns_fastembed_embedder():
    e = embed.get_embedder({"provider": "fastembed",
                            "model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
                            "dim": 384})
    assert isinstance(e, embed.FastEmbedEmbedder)
    assert e.dim == 384
    assert e.model == "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


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


def test_ensure_fastembed_no_consent_no_pip(monkeypatch):
    """When consent is withheld (assume_yes=False, non-interactive), ensure_fastembed
    must return False without ever calling pip (subprocess.run)."""
    monkeypatch.setattr(embed_install, "fastembed_available", lambda: False)
    pip_called = {"n": 0}
    monkeypatch.setattr(embed_install.subprocess, "run",
                        lambda *a, **k: pip_called.__setitem__("n", pip_called["n"] + 1))
    result = embed_install.ensure_fastembed(assume_yes=False, interactive=False)
    assert result is False
    assert pip_called["n"] == 0, "pip must NOT be called when consent is not given"


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
    # stub count: return 0 (no wiki notes) so vault counts as ok (no wiki pages)
    monkeypatch.setattr(embed_admin.vector_index, "count", lambda d, *, vault_id: 0)
    model = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    out = embed_admin.switch_model(db, model, assume_yes=True)
    assert out["ok"] is True and out["dim"] == 384
    emb = _config.load_config()["recall"]["embedding"]
    assert emb["provider"] == "fastembed" and emb["model"] == model and emb["dim"] == 384
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


def test_cli_embed_status_json(tmp_path, monkeypatch, capsys):
    db = _fake_env(tmp_path, monkeypatch)
    assert omw_cli.main(["embed", "status"]) == 0
    out = _json.loads(capsys.readouterr().out)
    assert out["strategy"] == "fts" and "vaults" in out


def test_cli_embed_use_invokes_switch(tmp_path, monkeypatch, capsys):
    db = _fake_env(tmp_path, monkeypatch)
    called = {}
    model = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    monkeypatch.setattr(embed_admin, "switch_model",
                        lambda d, m, **k: called.update(model=m) or {"ok": True, "model": m, "dim": 384, "vaults_reindexed": 1, "detail": None})
    assert omw_cli.main(["embed", "use", model]) == 0
    assert called["model"] == model


def test_cli_embed_use_failure_returns_1(tmp_path, monkeypatch, capsys):
    db = _fake_env(tmp_path, monkeypatch)
    monkeypatch.setattr(embed_admin, "switch_model",
                        lambda d, m, **k: {"ok": False, "model": m, "dim": None, "vaults_reindexed": 0, "detail": "boom"})
    assert omw_cli.main(["embed", "use", "x/y"]) == 1


def test_embed_op_in_registry_and_help():
    from scripts import ops_registry
    op = next(o for o in ops_registry.OPS if o.name == "embed")
    for sub in ["status", "list", "use", "add", "install", "reindex"]:
        assert sub in op.cli_template


def test_setup_recall_embedding_triggers_switch_model(tmp_path, monkeypatch):
    db = _fake_env(tmp_path, monkeypatch)
    captured = {}
    monkeypatch.setattr(
        setup_wizard, "_embed_admin_switch",
        lambda *a, **k: captured.update(args=a, kw=k) or {
            "ok": True, "model": embed.DEFAULT_LOCAL_MODEL, "dim": 384,
            "vaults_reindexed": 1, "detail": None,
        },
        raising=False,
    )
    rc = setup_wizard.setup_recall(mode="auto", strategy="embedding", noninteractive=True)
    assert rc == 0
    assert captured, "embedding strategy must invoke _embed_admin_switch"


def test_setup_recall_fts_does_not_trigger_switch_model(tmp_path, monkeypatch):
    _fake_env(tmp_path, monkeypatch)
    captured = {}
    monkeypatch.setattr(
        setup_wizard, "_embed_admin_switch",
        lambda *a, **k: captured.update(args=a, kw=k) or {"ok": True},
        raising=False,
    )
    rc = setup_wizard.setup_recall(mode="auto", strategy="fts", noninteractive=True)
    assert rc == 0
    assert not captured, "fts strategy must NOT invoke _embed_admin_switch"


def test_setup_recall_llm_does_not_trigger_switch_model(tmp_path, monkeypatch):
    _fake_env(tmp_path, monkeypatch)
    captured = {}
    monkeypatch.setattr(
        setup_wizard, "_embed_admin_switch",
        lambda *a, **k: captured.update(args=a, kw=k) or {"ok": True},
        raising=False,
    )
    rc = setup_wizard.setup_recall(mode="auto", strategy="llm", noninteractive=True)
    assert rc == 0
    assert not captured, "llm strategy must NOT invoke _embed_admin_switch"


# ---------------------------------------------------------------------------
# FIX 2: vec_meta fail-closed tests
# ---------------------------------------------------------------------------

def test_vector_index_query_fails_closed_on_dim_mismatch(tmp_path, monkeypatch):
    """upsert with dim=8, then query with dim=16 → [] (fail-closed)."""
    if not vector_index.available():
        pytest.skip("sqlite-vec not installed")
    from scripts import registry as _reg
    db = tmp_path / "registry.db"
    _reg.init_db(db)
    v = _reg.add_vault(db, name="v1", path=tmp_path / "v1", type_="markdown", mode="wiki")
    e8 = embed.FakeEmbedder(dim=8)
    vector_index.upsert(db, vault_id=v["id"], embedder=e8, rows=[("wiki/a.md", "hello")])
    e16 = embed.FakeEmbedder(dim=16)
    results = vector_index.query(db, vault_id=v["id"], embedder=e16, text="hello")
    assert results == [], "should return [] when dims differ (fail-closed)"


def test_vector_index_query_works_when_model_is_none(tmp_path, monkeypatch):
    """upsert with FakeEmbedder (no model attr, dim=8) then query with FakeEmbedder
    (no model, dim=8) should succeed — model=None means no mismatch."""
    if not vector_index.available():
        pytest.skip("sqlite-vec not installed")
    from scripts import registry as _reg
    db = tmp_path / "registry.db"
    _reg.init_db(db)
    v = _reg.add_vault(db, name="v1", path=tmp_path / "v1", type_="markdown", mode="wiki")
    e = embed.FakeEmbedder(dim=8)
    # FakeEmbedder has no .model attribute — getattr returns None
    assert not hasattr(e, "model")
    vector_index.upsert(db, vault_id=v["id"], embedder=e, rows=[("wiki/a.md", "hello")])
    results = vector_index.query(db, vault_id=v["id"], embedder=embed.FakeEmbedder(dim=8),
                                 text="hello")
    assert isinstance(results, list)
    # Should return results (not fail-closed) since both models are None


def test_vector_index_count_returns_stored_count(tmp_path, monkeypatch):
    """count() returns the number of rows stored for a given vault."""
    if not vector_index.available():
        pytest.skip("sqlite-vec not installed")
    from scripts import registry as _reg
    db = tmp_path / "registry.db"
    _reg.init_db(db)
    v = _reg.add_vault(db, name="v1", path=tmp_path / "v1", type_="markdown", mode="wiki")
    e = embed.FakeEmbedder(dim=8)
    assert vector_index.count(db, vault_id=v["id"]) == 0
    vector_index.upsert(db, vault_id=v["id"], embedder=e, rows=[
        ("wiki/a.md", "hello"),
        ("wiki/b.md", "world"),
    ])
    assert vector_index.count(db, vault_id=v["id"]) == 2


def test_vector_index_meta_is_none_after_reset(tmp_path, monkeypatch):
    """After reset(), meta() returns None."""
    if not vector_index.available():
        pytest.skip("sqlite-vec not installed")
    from scripts import registry as _reg
    db = tmp_path / "registry.db"
    _reg.init_db(db)
    v = _reg.add_vault(db, name="v1", path=tmp_path / "v1", type_="markdown", mode="wiki")
    e = embed.FakeEmbedder(dim=8)
    vector_index.upsert(db, vault_id=v["id"], embedder=e, rows=[("wiki/a.md", "hello")])
    assert vector_index.meta(db) is not None
    vector_index.reset(db)
    assert vector_index.meta(db) is None


# ---------------------------------------------------------------------------
# FIX 3: switch_model zero-embed detection
# ---------------------------------------------------------------------------

def test_switch_model_fails_when_no_vectors_produced_for_wiki_vault(tmp_path, monkeypatch):
    """switch_model returns ok=False when wiki notes exist but no vectors were stored."""
    from scripts import registry as _reg
    db = _fake_env(tmp_path, monkeypatch)
    monkeypatch.setattr(embed_admin.embed_install, "ensure_fastembed", lambda **k: True)
    monkeypatch.setattr(embed_admin, "resolve_dim", lambda d, m: 384)
    monkeypatch.setattr(embed_admin.vector_index, "reset", lambda d: None)
    monkeypatch.setattr(embed_admin.reindex, "refresh_embeddings",
                        lambda d, *, vault_id, relpaths=None: None)
    # Simulate: vault has 3 wiki notes but 0 vectors (model unsupported)
    monkeypatch.setattr(embed_admin.vector_index, "count", lambda d, *, vault_id: 0)

    # We need the vault's notes table to report wiki notes.
    # Patch registry.connect to return a fake conn for the notes count query.
    real_connect = _reg.connect
    class _FakeConn:
        def execute(self, sql, params=()):
            if "FROM notes" in sql:
                class _Row:
                    def __getitem__(self, k): return 3
                class _Cursor:
                    def fetchone(self): return _Row()
                return _Cursor()
            # delegate everything else
            return real_connect(db).execute(sql, params)
        def close(self): pass

    monkeypatch.setattr(embed_admin.registry, "connect", lambda p: _FakeConn())
    monkeypatch.setattr(embed_admin.registry, "list_vaults",
                        lambda d: [{"id": 1, "name": "v1"}])

    out = embed_admin.switch_model(db, "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
                                   assume_yes=True)
    assert out["ok"] is False
    assert "no vectors" in out["detail"]
