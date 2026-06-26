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


from scripts import vector_index


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
