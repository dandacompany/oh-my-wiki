from scripts import ops_registry as reg


def test_every_op_is_triggered_or_allowlisted():
    for op in reg.OPS:
        triggered = bool(op.triggers)
        allowed = op.name in reg._NO_TRIGGER_OK
        assert triggered != allowed, (
            f"{op.name}: must have triggers XOR be in _NO_TRIGGER_OK (got triggers={triggered}, allow={allowed})")


def test_allowlist_names_are_real_ops():
    known = set(reg.names())
    assert reg._NO_TRIGGER_OK <= known


def test_no_keyword_maps_to_two_ops():
    seen: dict[str, str] = {}
    for op in reg.OPS:
        for kw in op.triggers:
            k = kw.lower()
            assert k not in seen or seen[k] == op.name, (
                f"keyword {kw!r} maps to both {seen.get(k)} and {op.name}")
            seen[k] = op.name


def test_resolve_representative_keywords():
    assert reg.resolve("이 작업 기록 좀 봐줘") == "history"
    assert reg.resolve("현황 보여줘") == "report"
    assert reg.resolve("omw 제거해줘") == "uninstall"
    assert reg.resolve("리서치 해줘") == "autoresearch"
    assert reg.resolve("팩트체크해줘") == "persona-factcheck"
    assert reg.resolve("이거 내보내기 해줘") == "export"
    assert reg.resolve("아무 관련 없는 잡담") is None
    assert reg.resolve("") is None
    assert reg.resolve(None) is None


def test_resolve_longest_keyword_wins():
    # "vault 목록" (vault) must beat "목록" (list) when both appear
    assert reg.resolve("vault 목록 보여줘") == "vault"
    assert reg.resolve("그냥 목록 보여줘") == "list"


def test_triggers_for():
    assert "현황" in reg.triggers_for("report")
    assert reg.triggers_for("status") == ()        # allowlisted → no triggers
    assert reg.triggers_for("nonexistent") == ()
