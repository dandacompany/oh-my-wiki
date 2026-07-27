from scripts import embed


def test_none_provider_returns_no_embedder():
    assert embed.get_embedder({"provider": "none"}) is None
    assert embed.get_embedder({}) is None


def test_fake_embedder_is_deterministic_and_dim_stable():
    e = embed.FakeEmbedder(dim=8)
    a = e.embed(["ARIMA 정상성", "ARIMA 정상성"])
    b = e.embed(["ARIMA 정상성"])
    assert len(a) == 2 and len(a[0]) == 8
    assert a[0] == a[1] == b[0]          # deterministic
    assert e.embed(["다른 문장"])[0] != a[0]


def test_e5_uses_asymmetric_query_and_passage_prefixes():
    e = embed.FastEmbedEmbedder("intfloat/multilingual-e5-large", 1024)
    assert embed.prefix_scheme(e) == embed.E5_PREFIX_SCHEME
    assert embed.passage_texts(e, ["문서"]) == ["passage: 문서"]
    assert embed.query_text(e, "질문") == "query: 질문"


def test_non_instruction_model_keeps_text_unchanged():
    e = embed.FastEmbedEmbedder(embed.DEFAULT_LOCAL_MODEL, 384)
    assert embed.prefix_scheme(e) == "none"
    assert embed.passage_texts(e, ["문서"]) == ["문서"]
    assert embed.query_text(e, "질문") == "질문"
