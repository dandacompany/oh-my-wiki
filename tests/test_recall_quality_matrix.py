"""Behavioural retrieval benchmark for the hook-side quality gate.

The cases intentionally mix Korean/English, identifiers, paraphrases, long
prompts, and unrelated everyday/coding requests.  They are small and fully
deterministic so quality regressions fail in CI instead of being noticed only
after a host hook injects irrelevant context.
"""

import pytest

from scripts import search_index


POSITIVE_CASES = [
    (
        "exact-korean-title",
        "ZimaBoard2 2.5GbE NIC가 1GbE로 협상되는 문제",
        "ZimaBoard2의 2.5GbE NIC이 1GbE로 협상되고 있다",
    ),
    (
        "korean-josa-and-long-prompt",
        "Claude Code에서 SessionStart 훅 JSON 출력이 깨질 때 복구한 내용을 찾아줘",
        "Claude Code SessionStart 훅 JSON 출력 계약 복구",
    ),
    (
        "mixed-language-config",
        "Hostinger Docker에서 Hermes의 HERMES_HOME 경로가 달라지는 이유",
        "OMW Hostinger Docker Hermes HERMES_HOME 경로 수정",
    ),
    (
        "domain-identifier",
        "ArtifactEnvelope와 ApprovalRecord 주문 승인 게이트 설계",
        "ArtifactEnvelope ApprovalRecord 기반 주문 승인 게이트",
    ),
    (
        "remote-shell-error",
        "Codex remote SSH에서 sh is not recognized 오류가 발생한다",
        "Codex remote SSH POSIX shell compatibility",
    ),
    (
        "course-number",
        "국민대 7287401-01 AI에이전트실무 분반 정보",
        "국민대학교 AI에이전트실무 7287401-01 분반",
    ),
    (
        "versioned-cli",
        "npm 전역 설치 뒤에도 활성 Codex CLI 0.147.0이 바뀌지 않는다",
        "Codex CLI 0.147.0 활성 NVM 설치 경로",
    ),
    (
        "semantic-paraphrase",
        "도커 안에서 에이전트 홈 폴더가 엉뚱한 위치로 잡히는 현상",
        "Hostinger Docker Hermes HERMES_HOME 경로 수정",
    ),
]


NEGATIVE_CASES = [
    ("translation", "이 문장을 영어로 번역해줘 오늘 회의는 세 시에 시작합니다"),
    ("typescript", "TypeScript 배열을 숫자 오름차순으로 정렬하는 코드를 작성해줘"),
    ("dinner", "오늘 저녁 메뉴 세 가지 추천해줘"),
    ("fibonacci", "피보나치 수열을 재귀 함수로 구현해줘"),
    ("weather", "서울의 이번 주말 날씨를 알려줘"),
    ("email-regex", "정규표현식으로 이메일 형식을 검사하는 방법"),
    ("rewrite", "이 문장을 더 자연스럽게 다듬어줘 확인 후 회신 부탁드립니다"),
    ("thanks-email", "간단한 감사 인사 이메일을 작성해줘"),
    ("generic-comparison", "검색 품질 테스트를 다양하게 설정해서 mem0와 비교해봐"),
    ("generic-resume", "이전 작업을 이어서 진행하고 남은 항목을 마무리해줘"),
]


def _rank(query, title, *, target_vec=0.84, noise_vec=0.62):
    target = {
        "relpath": "wiki/target.md", "title": title,
        "summary": "검증된 프로젝트 문서", "tags": [], "score": 5.0,
    }
    noise = {
        "relpath": "wiki/noise.md", "title": "서브에이전트 플랫폼 비교",
        "summary": "일반적인 도구 비교와 테스트", "tags": ["comparison"], "score": 4.0,
    }
    return search_index._quality_rank(
        None, vault_id=1, q=query, fts_hits=[target, noise],
        emb_hits=[
            {"relpath": target["relpath"], "score": target_vec},
            {"relpath": noise["relpath"], "score": noise_vec},
        ],
        limit=3,
    )


@pytest.mark.parametrize("case_id,query,title", POSITIVE_CASES, ids=[c[0] for c in POSITIVE_CASES])
def test_positive_recall_matrix(case_id, query, title):
    # The semantic-paraphrase case intentionally has almost no lexical overlap;
    # its distinctive vector score must rescue it.
    out = _rank(query, title)
    assert out and out[0]["relpath"] == "wiki/target.md", case_id


@pytest.mark.parametrize("case_id,query", NEGATIVE_CASES, ids=[c[0] for c in NEGATIVE_CASES])
def test_negative_recall_matrix_is_silent(case_id, query):
    # Simulate the common failure mode: a generic word puts an irrelevant page in
    # both candidate lists, but its semantic score is mediocre and non-distinctive.
    out = search_index._quality_rank(
        None, vault_id=1, q=query,
        fts_hits=[{
            "relpath": "wiki/noise.md", "title": "서브에이전트 플랫폼 비교",
            "summary": "일반적인 테스트와 작업 방법", "tags": ["comparison"], "score": 4.0,
        }],
        emb_hits=[
            {"relpath": "wiki/noise.md", "score": 0.62},
            {"relpath": "raw/other.md", "score": 0.60},
        ],
        limit=3,
    )
    assert out == [], case_id
