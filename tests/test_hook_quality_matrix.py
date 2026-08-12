"""Fifty deterministic hook-trigger cases used alongside the live mem0 comparison."""
import pytest

from scripts import recall, session_capture


@pytest.mark.parametrize("text, expected", [
    ("지난 작업 어디까지 했는지 알려줘", True),
    ("이어서 구현해줘", True),
    ("하던 작업을 마저 진행해", True),
    ("where did we leave off on the hook work", True),
    ("pick up where we left off", True),
    ("resume from where the tests failed", True),
    ("continue from last session", True),
    ("what were we working on yesterday", True),
    ("새 기능을 설계해줘", False),
    ("파이썬 정렬을 설명해줘", False),
    ("continue", False),
    ("테스트 결과를 비교해줘", False),
    ("이 결정을 기억해", False),
    ("새 문서를 작성해", False),
], ids=lambda v: str(v)[:32])
def test_resume_trigger_matrix(text, expected):
    assert recall._is_resume_prompt(text) is expected


@pytest.mark.parametrize("text, tokens", [
    ("auth/session.py raised ConnectionError", ("auth", "session", "ConnectionError")),
    ("Traceback in scripts/recall.py", ("Traceback", "recall")),
    ("TypeError from src/index.ts", ("TypeError", "index")),
    ("fatal while loading config.toml", ("fatal", "config")),
    ("DatabaseException at db/store.go", ("DatabaseException", "store")),
    ("panic in worker.rs", ("panic", "worker")),
], ids=lambda v: str(v)[:32])
def test_error_file_signal_matrix(text, tokens):
    out = " ".join(recall._signal_queries(text))
    assert all(token in out for token in tokens)


@pytest.mark.parametrize("tool_input, expected", [
    ({"file_path": "raw/source.md"}, True),
    ({"path": "/vault/raw/source.md"}, True),
    ({"pattern": "raw/**/*.md"}, True),
    ({"glob": "raw/*"}, True),
    ({"query": "search raw/hooks"}, True),
    ({"file_path": "wiki/page.md"}, False),
    ({"path": "scripts/recall.py"}, False),
    ({"pattern": "README.md"}, False),
], ids=lambda v: str(v)[:32])
def test_raw_target_matrix(tool_input, expected):
    assert recall._targets_raw(tool_input) is expected


@pytest.mark.parametrize("path, tokens", [
    ("scripts/recall.py", ("recall",)),
    ("src/session-capture.ts", ("session-capture",)),
    ("raw/claude-code-hook-contract.md", ("claude-code-hook-contract",)),
    ("tests/test_vector_index.py", ("vector_index",)),
    ("docs/OMW-search-quality.md", ("OMW-search-quality",)),
    ("config/hooks.json", ("config", "hooks")),
], ids=lambda v: str(v)[:32])
def test_pretool_path_query_matrix(path, tokens):
    query = recall._pretool_path_query({"tool_input": {"file_path": path}})
    assert all(token in query for token in tokens)


@pytest.mark.parametrize("text, forbidden", [
    ("OPENAI_API_KEY=sk-abcdefghijklmnop", "abcdefghijklmnop"),
    ("MEM0_TOKEN=m0-abcdefghijklmnop", "abcdefghijklmnop"),
    ("Authorization: Bearer abcdefghijklmnop", "abcdefghijklmnop"),
    ("GITHUB_TOKEN=github_pat-abcdefghijklmnop", "abcdefghijklmnop"),
    ("PASSWORD=hunter2-secret", "hunter2-secret"),
    ("API_SECRET: very-secret-value", "very-secret-value"),
    ("token Bearer a.b.c.defghijklmnop", "a.b.c"),
    ("SERVICE_API_KEY = value-with-dashes", "value-with-dashes"),
], ids=lambda v: str(v)[:32])
def test_capture_redaction_matrix(text, forbidden):
    out = session_capture.sanitize_text(text, limit=200)
    assert forbidden not in out and "[REDACTED]" in out


@pytest.mark.parametrize("text", [
    "ok", "네", "응", "continue", "thanks", "좋아", "yes", "고마워",
])
def test_negative_control_matrix(text):
    assert recall.is_trivial(text) is True
