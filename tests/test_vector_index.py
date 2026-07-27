# tests/test_vector_index.py
import pytest
from scripts import vector_index, embed


@pytest.mark.skipif(not vector_index.available(), reason="sqlite-vec not installed")
def test_upsert_then_query_ranks_semantic_neighbour(tmp_path):
    from scripts import registry
    db = tmp_path / "reg.db"
    registry.connect(db).close()           # ensure schema/db exists
    e = embed.FakeEmbedder(dim=64)
    n = vector_index.upsert(db, vault_id=1, embedder=e, rows=[
        ("wiki/arima.md", "ARIMA 정상성 차분 시계열"),
        ("wiki/cooking.md", "김치찌개 레시피 돼지고기"),
    ])
    assert n == 2
    hits = vector_index.query(db, vault_id=1, embedder=e,
                              text="ARIMA 정상성 차분 시계열", limit=1)
    assert hits and hits[0]["relpath"] == "wiki/arima.md"


def test_query_empty_when_unavailable(monkeypatch, tmp_path):
    monkeypatch.setattr(vector_index, "available", lambda: False)
    out = vector_index.query(tmp_path / "x.db", vault_id=1,
                             embedder=embed.FakeEmbedder(), text="q", limit=3)
    assert out == []


def test_query_surfaces_unexpected_error(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(vector_index, "available", lambda: True)

    def boom(*a, **k):
        raise RuntimeError("corrupt store")

    monkeypatch.setattr(vector_index, "_connect", boom)

    class _Emb:
        dim = 384
        model = "m"

        def embed(self, texts):
            return [[0.0] * 384 for _ in texts]

    out = vector_index.query(tmp_path / "db.sqlite", vault_id=1, embedder=_Emb(), text="hi")
    assert out == []  # contract preserved: still falls back
    assert "vector query failed" in capsys.readouterr().err  # no longer silent


@pytest.mark.skipif(not vector_index.available(), reason="sqlite-vec not installed")
def test_e5_prefix_scheme_is_stored_and_roles_are_applied(tmp_path):
    from scripts import registry

    db = tmp_path / "reg.db"
    registry.init_db(db)
    vault = registry.add_vault(
        db, name="v", path=tmp_path / "v", type_="markdown", mode="wiki"
    )

    class Recorder:
        model = "intfloat/multilingual-e5-large"
        dim = 4

        def __init__(self):
            self.calls = []

        def embed(self, texts):
            self.calls.append(list(texts))
            return [[1.0, 0.0, 0.0, 0.0] for _ in texts]

    recorder = Recorder()
    vector_index.upsert(
        db, vault_id=vault["id"], embedder=recorder,
        rows=[("wiki/a.md", "문서")],
    )
    vector_index.query(
        db, vault_id=vault["id"], embedder=recorder, text="질문", limit=1
    )

    assert recorder.calls == [["passage: 문서"], ["query: 질문"]]
    assert vector_index.meta(db)["prefix_scheme"] == embed.E5_PREFIX_SCHEME
