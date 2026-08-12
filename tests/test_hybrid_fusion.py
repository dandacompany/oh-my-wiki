from scripts.search_index import rrf_fuse, search_strategy
import scripts.search_index as search_index


def test_rrf_merges_and_ranks():
    """Items appearing in multiple lists score higher via RRF."""
    r1 = ["a", "b", "c"]
    r2 = ["c", "a", "d"]
    result = rrf_fuse([r1, r2])
    ranked = [item for item, _ in result]
    # 'a' and 'c' appear in both lists → should outrank 'b' and 'd'
    assert ranked.index("a") < ranked.index("b")
    assert ranked.index("a") < ranked.index("d")
    assert ranked.index("c") < ranked.index("b")
    assert ranked.index("c") < ranked.index("d")
    assert ranked[0] in {"a", "c"}


def test_search_strategy_fts_matches_query():
    """strategy='fts' delegates to the existing query() function."""
    fake_hit = {"relpath": "wiki/foo.md", "title": "Foo", "score": 1.0}

    original_query = search_index.query

    def mock_query(db_path, *, vault_id, query, limit, visibility=None):
        return [fake_hit]

    search_index.query = mock_query
    try:
        result = search_strategy(None, vault_id=1, q="q", limit=3, strategy="fts")
        assert result == [fake_hit]
    finally:
        search_index.query = original_query


def test_search_strategy_uses_fts_query_for_lexical_leg(monkeypatch):
    seen = {}
    def fake_query(db, *, vault_id, query, limit, visibility=None):
        seen["q"] = query
        return [{"relpath": "wiki/x.md", "score": 1.0}]
    monkeypatch.setattr(search_index, "query", fake_query)
    search_index.search_strategy(None, vault_id=1, q="ARIMA와", limit=3,
                                 strategy="fts", fts_query="ARIMA")
    assert seen["q"] == "ARIMA"   # the normalized fts_query reached the FTS leg


class _FakeEmb:
    dim = 8

    def embed(self, texts):
        return [[0.0] * self.dim for _ in texts]


def test_recall_quality_expands_candidates_and_promotes_exact_title(monkeypatch):
    """Recall retrieval must not fuse only the final top_k candidates.

    The exact structured page is deliberately below a raw page in both legs.  A
    larger candidate pool plus lexical evidence should still make it the first
    result, while weak distractors are omitted rather than injected.
    """
    seen = {}

    def fake_fts(db, *, vault_id, query, limit, visibility=None, include_match_text=False):
        seen["fts_limit"] = limit
        assert include_match_text is True
        return [
            {"relpath": "raw/zima-hardware.md", "title": "ZimaBoard2 hardware network notes",
             "summary": "NIC measurements", "tags": [], "score": 9.0},
            {"relpath": "wiki/summaries/zima-nic.md",
             "title": "ZimaBoard2의 2.5GbE NIC이 1GbE로 협상되고 있다",
             "summary": "링크 협상 원인", "tags": ["network"], "score": 8.0},
            {"relpath": "wiki/noise.md", "title": "Agent platform comparison",
             "summary": "unrelated", "tags": [], "score": 7.0},
        ]

    def fake_vec(db, *, vault_id, embedder, text, limit):
        seen["vec_limit"] = limit
        return [
            {"relpath": "raw/zima-hardware.md", "score": 0.88},
            {"relpath": "wiki/summaries/zima-nic.md", "score": 0.86},
            {"relpath": "wiki/noise.md", "score": 0.58},
        ]

    monkeypatch.setattr(search_index, "query", fake_fts)
    import scripts.vector_index as vector_index
    monkeypatch.setattr(vector_index, "query", fake_vec)

    out = search_strategy(
        None, vault_id=1,
        q="ZimaBoard2 2.5GbE NIC가 1GbE로 협상되는 문제",
        limit=3, strategy="hybrid", embedder=_FakeEmb(), quality_gate=True,
    )

    assert seen == {"fts_limit": 24, "vec_limit": 24}
    assert out[0]["relpath"] == "wiki/summaries/zima-nic.md"
    assert "wiki/noise.md" not in {h["relpath"] for h in out}
    assert 0.0 <= out[0]["score"] <= 1.0


def test_recall_quality_stays_silent_for_one_word_overlap(monkeypatch):
    """A shared generic word such as 'comparison' is not recall evidence."""
    monkeypatch.setattr(search_index, "query", lambda *a, **k: [
        {"relpath": "wiki/subagents.md", "title": "서브에이전트 플랫폼 비교",
         "summary": "호스트별 위임 구조", "tags": ["comparison"], "score": 5.0},
    ])
    import scripts.vector_index as vector_index
    monkeypatch.setattr(vector_index, "query", lambda *a, **k: [
        {"relpath": "wiki/subagents.md", "score": 0.58},
    ])

    out = search_strategy(
        None, vault_id=1,
        q="검색 품질 테스트를 다양하게 설정해서 mem0와 비교해봐",
        limit=3, strategy="hybrid", embedder=_FakeEmb(), quality_gate=True,
    )
    assert out == []


def test_recall_quality_keeps_supported_paraphrase(monkeypatch):
    """Two-leg agreement plus a strong semantic score rescues a paraphrase."""
    target = {
        "relpath": "wiki/hermes-home.md",
        "title": "Hostinger Docker Hermes HERMES_HOME 경로 수정",
        "summary": "컨테이너별 홈 경로 탐색", "tags": ["hermes", "docker"],
        "score": 4.0,
    }
    monkeypatch.setattr(search_index, "query", lambda *a, **k: [target])
    import scripts.vector_index as vector_index
    monkeypatch.setattr(vector_index, "query", lambda *a, **k: [
        {"relpath": target["relpath"], "score": 0.83},
        {"relpath": "wiki/noise.md", "score": 0.62},
    ])

    out = search_strategy(
        None, vault_id=1,
        q="도커 안에서 헤르메스 홈 폴더가 다른 경로로 잡히는 문제",
        limit=3, strategy="hybrid", embedder=_FakeEmb(), quality_gate=True,
    )
    assert [h["relpath"] for h in out] == [target["relpath"]]


def test_recall_quality_prefers_multi_fact_page_over_single_token_entity(monkeypatch):
    """A relation question needs a page covering several facts, not just an entity name."""
    fts_hits = [
        {"relpath": "wiki/entities/bluekiwi.md", "title": "BlueKiwi",
         "summary": "AI workflow service", "tags": ["software"], "score": 9.0},
        {"relpath": "wiki/section-6-3.md", "title": "Hermes 인프런 6.3 실측 우선",
         "summary": "Section 6에서 BlueKiwi 워크플로를 검증한다",
         "tags": ["hermes", "bluekiwi", "course-production"], "score": 8.0},
    ]
    emb_hits = [
        {"relpath": "wiki/entities/bluekiwi.md", "score": 0.76},
        {"relpath": "wiki/section-6-3.md", "score": 0.75},
    ]
    monkeypatch.setattr(search_index, "query", lambda *a, **k: fts_hits)
    import scripts.vector_index as vector_index
    monkeypatch.setattr(vector_index, "query", lambda *a, **k: emb_hits)

    out = search_strategy(
        None, vault_id=1, q="현재 인프런 Section 6의 BlueKiwi 순서",
        limit=3, strategy="hybrid", embedder=_FakeEmb(), quality_gate=True,
    )
    assert out[0]["relpath"] == "wiki/section-6-3.md"


def test_recall_quality_exact_multiword_tag_is_not_diluted(monkeypatch):
    """One exact multiword tag remains strong even when the page has many tags."""
    target = {
        "relpath": "wiki/vibe.md", "title": "Hermes-native 투자 자동화 결정",
        "summary": "주문 승인 구조", "tags": [
            "hermes", "quant-investing", "trading-agent", "vibe-trading",
            "hermes-council", "architecture-decision",
        ], "score": 8.0,
    }
    monkeypatch.setattr(search_index, "query", lambda *a, **k: [target])
    import scripts.vector_index as vector_index
    monkeypatch.setattr(vector_index, "query", lambda *a, **k: [])

    out = search_strategy(
        None, vault_id=1, q="Vibe Trading 주문 승인 게이트 ArtifactEnvelope",
        limit=3, strategy="hybrid", embedder=_FakeEmb(), quality_gate=True,
    )
    assert [h["relpath"] for h in out] == ["wiki/vibe.md"]


def test_embedding_only_quality_gate_rejects_weak_neighbours(monkeypatch):
    monkeypatch.setattr(search_index, "query", lambda *a, **k: [])
    import scripts.vector_index as vector_index
    monkeypatch.setattr(vector_index, "query", lambda *a, **k: [
        {"relpath": "wiki/noise.md", "score": 0.63},
        {"relpath": "wiki/other.md", "score": 0.61},
    ])
    monkeypatch.setattr(search_index, "hydrate", lambda *a, **k: [
        {"relpath": "wiki/noise.md", "title": "Unrelated platform comparison",
         "summary": "", "tags": [], "score": 0.63},
        {"relpath": "wiki/other.md", "title": "Other notes",
         "summary": "", "tags": [], "score": 0.61},
    ])

    out = search_strategy(
        None, vault_id=1, q="TypeScript 배열 정렬 코드 작성",
        limit=3, strategy="embedding", embedder=_FakeEmb(), quality_gate=True,
    )
    assert out == []


def test_hybrid_quality_gate_filters_fts_fallback_without_embedder(monkeypatch):
    monkeypatch.setattr(search_index, "query", lambda *a, **k: [
        {"relpath": "wiki/noise.md", "title": "플랫폼 비교",
         "summary": "일반 테스트", "tags": [], "score": 4.0},
    ])
    out = search_strategy(
        None, vault_id=1, q="검색 품질 테스트를 mem0와 비교해봐",
        limit=3, strategy="hybrid", embedder=None, quality_gate=True,
    )
    assert out == []


def test_recall_quality_tolerates_ascii_identifier_typo_and_abbreviation(monkeypatch):
    target = {
        "relpath": "wiki/zima.md",
        "title": "ZimaBoard2 2.5GbE NIC 1GbE 링크 협상",
        "summary": "네트워크 협상 기록", "tags": [], "score": 5.0,
    }
    monkeypatch.setattr(search_index, "query", lambda *a, **k: [target])
    import scripts.vector_index as vector_index
    monkeypatch.setattr(vector_index, "query", lambda *a, **k: [
        {"relpath": target["relpath"], "score": 0.72},
    ])
    out = search_strategy(
        None, vault_id=1, q="ZimaBord2 2.5G NIC가 왜 1G로 링크되는지",
        limit=3, strategy="hybrid", embedder=_FakeEmb(), quality_gate=True,
    )
    assert [h["relpath"] for h in out] == [target["relpath"]]


def test_recall_quality_uses_bounded_fts_body_match_evidence(monkeypatch):
    raw = {
        "relpath": "raw/hostinger.md", "title": None, "summary": None,
        "tags": [], "score": 8.0,
        "_match_text": "도커 컨테이너 에이전트 홈 경로가 예상과 다르게 잡힌 원인",
    }
    monkeypatch.setattr(search_index, "query", lambda *a, **k: [raw])
    import scripts.vector_index as vector_index
    monkeypatch.setattr(vector_index, "query", lambda *a, **k: [
        {"relpath": raw["relpath"], "score": 0.71},
        {"relpath": "wiki/noise.md", "score": 0.70},
    ])
    monkeypatch.setattr(search_index, "hydrate", lambda *a, **k: [
        {"relpath": raw["relpath"], "title": None, "summary": None,
         "tags": [], "score": 8.0},
        {"relpath": "wiki/noise.md", "title": "OpenCove", "summary": "",
         "tags": [], "score": 0.70},
    ])
    out = search_strategy(
        None, vault_id=1,
        q="도커 컨테이너에서 에이전트 홈 경로가 예상과 다르게 잡힌 문제",
        limit=3, strategy="hybrid", embedder=_FakeEmb(), quality_gate=True,
    )
    assert out[0]["relpath"] == raw["relpath"]


def test_recall_quality_accepts_strong_fts_body_evidence_without_vector(monkeypatch):
    raw = {
        "relpath": "raw/hostinger.md", "title": None, "summary": None,
        "tags": [], "score": 8.0,
        "_match_text": "도커 컨테이너 에이전트 홈 경로 예상 다르게 잡히다",
    }
    monkeypatch.setattr(search_index, "query", lambda *a, **k: [raw])
    import scripts.vector_index as vector_index
    monkeypatch.setattr(vector_index, "query", lambda *a, **k: [])
    monkeypatch.setattr(search_index, "hydrate", lambda *a, **k: [{
        "relpath": raw["relpath"], "title": None, "summary": None,
        "tags": [], "score": 8.0,
    }])
    out = search_strategy(
        None, vault_id=1,
        q="도커 컨테이너에서 에이전트 홈 경로가 예상과 다르게 잡힌 문제",
        limit=3, strategy="hybrid", embedder=_FakeEmb(), quality_gate=True,
    )
    assert [h["relpath"] for h in out] == [raw["relpath"]]


def test_recall_quality_prunes_candidates_far_below_best(monkeypatch):
    fts_hits = [
        {"relpath": "wiki/best.md", "title": "Claude Code 훅 JSON 복구",
         "summary": "SessionStart 오류", "tags": [], "score": 9.0},
        {"relpath": "wiki/near.md", "title": "Claude Code 훅 공식 문서",
         "summary": "훅 reference", "tags": [], "score": 8.0},
        {"relpath": "wiki/far.md", "title": "Hermes Codex 플러그인",
         "summary": "일반 플러그인", "tags": [], "score": 7.0},
    ]
    emb_hits = [
        {"relpath": "wiki/best.md", "score": 0.82},
        {"relpath": "wiki/near.md", "score": 0.78},
        {"relpath": "wiki/far.md", "score": 0.64},
    ]
    monkeypatch.setattr(search_index, "query", lambda *a, **k: fts_hits)
    import scripts.vector_index as vector_index
    monkeypatch.setattr(vector_index, "query", lambda *a, **k: emb_hits)
    out = search_strategy(
        None, vault_id=1, q="Claude Code SessionStart 훅 JSON 오류 복구",
        limit=3, strategy="hybrid", embedder=_FakeEmb(), quality_gate=True,
    )
    relpaths = [h["relpath"] for h in out]
    assert relpaths[0] == "wiki/best.md"
    assert "wiki/far.md" not in relpaths


def test_relative_quality_prune_uses_best_score_floor():
    ranked = [
        (0.80, {"relpath": "best"}),
        (0.65, {"relpath": "near"}),
        (0.63, {"relpath": "far"}),
    ]
    assert [h["relpath"] for h in search_index._relative_prune(ranked, limit=3)] == [
        "best", "near",
    ]
