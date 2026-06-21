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
