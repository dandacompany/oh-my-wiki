#!/usr/bin/env python3
"""Full-feature static HTML reference for oh-my-wiki (Korean, v3).

A sibling of the showcase (docs/tutorial-omw). It REUSES the showcase's design
system via importlib — HEAD (<head>+<style>, incl. the .ref-table style), esc(),
render_block(), render_section() — and defines its OWN SECTIONS / body() / main().

All CLI flags are verified live (`python3 -m scripts.omw_cli <sub> --help`); all
command outputs are verified live in an isolated `OMW_HOME=$(mktemp -d)/.omw`
vault, with personal paths masked to ~/.omw. Persona/team/frontmatter tables are
read from personas/*.md, teams/*.md, schemas/base.yml. Docs only — no product code.
"""
import importlib.util
import pathlib

BASE = pathlib.Path(__file__).resolve().parent
OUT = BASE / "tutorial-reference.html"

# ─────────────────────────────────────────────────────────────────────────────
# Reuse the showcase design system via importlib
# ─────────────────────────────────────────────────────────────────────────────
_spec = importlib.util.spec_from_file_location(
    "_omw", BASE.parent / "tutorial-omw" / "build_tutorial_omw.py"
)
_omw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_omw)

# Reuse HEAD verbatim, swapping only the <title> text.
HEAD = _omw.HEAD.replace(
    "<title>oh-my-wiki v3 — 따라 하는 위키 셋업</title>",
    "<title>oh-my-wiki v3 — 전체 기능 레퍼런스</title>",
    1,
)
esc = _omw.esc
render_block = _omw.render_block
render_section = _omw.render_section


# ─────────────────────────────────────────────────────────────────────────────
# SECTIONS — feature-area reference (Korean). Reader-first; subject = the tool.
# ─────────────────────────────────────────────────────────────────────────────
SECTIONS: list[dict] = [
    # ── A. 설치 · 설정 ────────────────────────────────────────────────────────
    dict(
        num="A",
        title="설치 · 설정",
        lede="세 가지 설치 경로 중 환경에 맞는 하나를 고릅니다. 설치 후 "
        "<code>omw setup</code>이 레지스트리와 첫 vault를 만들고, "
        "<code>omw status</code>·<code>omw doctor</code>가 연결 상태를 검증합니다.",
        commands=[
            {
                "label": "PATH A — Skills CLI (Claude Code 권장)",
                "bar": "bash",
                "text": "skills add dandacompany/oh-my-wiki@oh-my-wiki -g -y --copy -a claude-code",
                "callout": "스킬을 <code>~/.claude/skills/</code>에 설치하고 "
                "<code>oh-my-wiki</code>와 단축 별칭 <code>omw</code>를 함께 등록합니다.",
            },
            {
                "label": "PATH B — Claude Code 플러그인 마켓플레이스",
                "bar": "claude code",
                "text": "/plugin marketplace add dandacompany/oh-my-wiki\n"
                "/plugin install oh-my-wiki@oh-my-wiki-marketplace",
                "callout": "이후 업데이트는 "
                "<code>/plugin marketplace update oh-my-wiki-marketplace</code>로 진행합니다.",
            },
            {
                "label": "PATH C — git clone + install script (Codex CLI · 개발자)",
                "bar": "bash",
                "text": "git clone https://github.com/dandacompany/oh-my-wiki\n"
                "cd oh-my-wiki\n"
                "bash bin/install.sh",
                "callout": "인스톨러는 Python 3.10+ 확인, "
                "<code>pip install -e \".\"</code>, "
                "<code>~/.claude/skills/oh-my-wiki</code>·<code>omw</code> symlink 생성(멱등성), "
                "<code>pytest</code> 검증을 수행합니다. "
                "<code>--dev</code>(테스트 의존성), <code>--force</code>(프롬프트 없이 교체), "
                "<code>--no-test</code>, <code>--skills-dir &lt;path&gt;</code> 플래그를 받습니다.",
            },
            {
                "label": "설정 마법사 — omw setup",
                "bar": "terminal",
                "text": "omw setup",
                "callout": "섹션을 순서대로 진행하는 대화형 마법사입니다. 섹션 인자를 주면 한 섹션만 "
                "다시 조정합니다: <code>vault</code> · <code>hosts</code> · <code>search</code> · "
                "<code>serve</code> · <code>personas</code> · <code>tts</code> · <code>import</code>. "
                "<code>--noninteractive</code>는 플래그·기본값만으로 프롬프트 없이 생성합니다.",
            },
            {
                "label": "상태 확인 — omw status (깨끗한 머신)",
                "bar": "json",
                "text": "{\n"
                '  "vault_count": 0,\n'
                '  "active": null,\n'
                '  "needs": "setup",\n'
                '  "vaults": []\n'
                "}",
                "callout": "<code>needs</code>는 <code>setup</code>(첫 vault 필요) · "
                "<code>select</code>(vault 선택 필요) · <code>migrate</code>(레거시 "
                "<code>data/registry.db</code> 감지) · <code>op</code>(준비 완료) 중 하나입니다. "
                "소스 트리에서 실행하면 <code>data/registry.db</code> 때문에 "
                "<code>needs: \"migrate\"</code>가 표시되며 이는 개발 트리에서만 나타납니다.",
            },
            {
                "label": "설치 건강 검사 — omw doctor",
                "bar": "output",
                "text": "omw home:   ~/.omw  ok\n"
                "registry:   ~/.omw/registry.db  ok\n"
                "  * demo (wiki/markdown) ~/.omw/vaults/demo",
                "callout": "<code>doctor</code>는 각 컴포넌트를 찾으면 <code>ok</code>를, 없으면 무엇이 "
                "빠졌는지 보고합니다. <code>omw setup</code> 전이라면 "
                "<code>missing (run: omw setup)</code>으로 표시됩니다.",
            },
            {
                "kind": "note",
                "text": "<span class='star'>★ OMW_HOME</span> — "
                "레지스트리는 <code>$OMW_HOME/registry.db</code>에 저장됩니다(기본값 "
                "<code>~/.omw/registry.db</code>). 설정·토큰은 <code>~/.omw/config.yaml</code>과 "
                "<code>~/.omw/.env</code>(권한 <code>0600</code>)에 저장됩니다."
                "<ul>"
                "<li><code>export OMW_HOME=/path/to/isolated/.omw</code>로 완전히 분리된 wiki 환경을 "
                "운영합니다. 테스트·CI·다중 환경 격리에 유용합니다.</li>"
                "</ul>",
            },
        ],
    ),
    # ── B. 볼트 · 수집 ────────────────────────────────────────────────────────
    dict(
        num="B",
        title="볼트 · 수집",
        lede="vault는 하나의 지식 저장소입니다. <code>omw vault</code> 4개 동작으로 생성·전환하고, "
        "<code>omw import</code>로 기존 자료를 끌어오며, 세션에서 자연어 "
        "<code>ingest</code>로 새 소스를 흡수합니다.",
        commands=[
            {
                "label": "vault 생성 — omw vault create",
                "bar": "terminal",
                "text": "omw vault create demo --mode wiki",
                "callout": "<code>--mode</code>는 <code>memo</code>(가벼운 노트) 또는 "
                "<code>wiki</code>(Karpathy raw/wiki/index/log 패턴). "
                "<code>--type</code>은 <code>markdown</code> 또는 <code>obsidian</code>. "
                "<code>--location</code>은 <code>global</code> · <code>project</code> · "
                "절대 경로를 받습니다.",
            },
            {
                "label": "성공하면 보이는 것",
                "bar": "json",
                "text": "{\n"
                '  "created": "demo",\n'
                '  "path": "~/.omw/vaults/demo",\n'
                '  "mode": "wiki",\n'
                '  "type": "markdown"\n'
                "}",
            },
            {
                "label": "목록 · 전환 · 제거",
                "bar": "terminal",
                "text": "omw vault list           # 등록된 vault를 JSON으로 (is_active 포함)\n"
                "omw vault use demo       # 활성 vault 전환\n"
                "omw vault forget demo    # 레지스트리 행만 제거 — 파일은 보존",
                "callout": "<code>vault forget</code>은 디스크 파일을 절대 건드리지 않고 "
                "레지스트리 행만 지웁니다. 같은 경로로 다시 <code>create</code>하면 복구됩니다.",
            },
            {
                "label": "기존 자료 가져오기 — omw import",
                "bar": "terminal",
                "text": "omw import --source folder   --src-dir ./notes\n"
                "omw import --source obsidian --src-dir ~/Obsidian/MyVault\n"
                "omw import --source notion   --notion-id <export-id>",
                "callout": "<code>--source</code>는 <code>folder</code> · <code>obsidian</code> · "
                "<code>notion</code>. <code>--layer</code>는 가져온 파일을 "
                "<code>raw</code>(스냅샷) 또는 <code>wiki</code> 레이어 중 어디에 둘지 정합니다. "
                "<code>--vault</code>로 대상 vault를 지정합니다(기본값: 활성 vault).",
            },
            {
                "label": "세션에서 새 소스 흡수 — ingest (자연어)",
                "bar": "ai session",
                "text": "ingest this\n\n"
                "<붙여넣은 기사·링크·문서 본문>",
                "callout": "스킬이 제목·slug·태그·저장 위치를 제안하고, 확인하면 저장합니다. "
                "소스 하나당 <strong>raw 스냅샷 1개 + 요약 1개 + 엔티티·개념 페이지 10~15개 터치</strong>가 "
                "정상입니다.",
            },
            {
                "kind": "design",
                "label": "4-레이어 저장 모델",
                "design": {
                    "goal": "한 소스가 네 레이어로 펼쳐진다.",
                    "components": [
                        ("📥", "raw", "원본을 그대로 보존한 스냅샷. 가공 전 진실원천."),
                        ("📚", "wiki", "요약·개념·엔티티 페이지. 인용 가능한 구조화 지식."),
                        ("🗂️", "memo", "가벼운 노트(memo 모드). 빠른 캡처용."),
                        ("🏷️", "meta", "index·log 등 운영 메타 페이지. 필수 필드 면제."),
                    ],
                },
            },
        ],
    ),
    # ── C. 질의 · 검색 ────────────────────────────────────────────────────────
    dict(
        num="C",
        title="질의 · 검색",
        lede="vault 내부 검색은 SQLite FTS5(BM25)로 동작합니다. 웹 검색은 별개로 "
        "외부 provider를 통합니다. 세 가지 경로 — 세션 내 자연어, 로컬 HTTP API, 외부 웹 검색 — 를 "
        "용도에 맞게 구분합니다.",
        commands=[
            {
                "label": "vault 인덱싱 방식",
                "bar": "fts5",
                "text": "title + summary + tags + body  →  SQLite FTS5 (BM25)\n"
                "FTS5 미지원 시  →  토큰 스코어 기반 자동 폴백",
                "callout": "세션에서 \"내 위키에서 X에 대해 뭐라고 해?\"라고 물으면 스킬이 FTS5로 후보를 "
                "찾고 LLM이 결과를 재순위 매깁니다(임베딩 없음). 추론은 세션에서, 검색은 결정론으로.",
            },
            {
                "label": "세션 내 자연어 질의 — query (자연어)",
                "bar": "ai session",
                "text": "내 위키에서 compounding knowledge에 대해 뭐라고 해?",
                "callout": "<code>commands/query.md</code>의 절차로 FTS5 후보를 가져온 뒤 LLM이 "
                "재순위 매기고 출처를 인용해 답합니다.",
            },
            {
                "label": "외부 웹 검색 — omw search",
                "bar": "terminal",
                "text": "omw search \"LLM wiki pattern\" --provider brave --limit 5",
                "callout": "<code>omw search</code>는 외부 provider"
                "(brave · tavily · exa · firecrawl · brightdata)를 통한 <strong>웹 검색</strong>이며 "
                "vault 내부를 검색하지 않습니다. provider 미설정 시 다음을 출력합니다 — "
                "<code>error: no search provider configured — run `omw setup search`</code>.",
            },
            {
                "label": "provider 설정 — omw setup search",
                "bar": "terminal",
                "text": "omw setup search",
            },
            {
                "kind": "note",
                "text": "<span class='star'>★ autoresearch</span> — "
                "세션에서 <code>autoresearch &lt;질문&gt;</code>이라고 말하면 질문을 주장 단위로 분해하고, "
                "주장별 최대 3라운드 웹 검색 후 confidence 태그를 부여하며, synthesis 초안을 작성해 "
                "저장 전 확인을 요청합니다. → <code>wiki/syntheses/&lt;slug&gt;.md</code>",
            },
        ],
    ),
    # ── D. 작성 (페르소나 · 팀) ──────────────────────────────────────────────
    dict(
        num="D",
        title="작성 — 페르소나 · 팀",
        lede="작성·검증·유지 추론은 16종 writing persona가 담당합니다. "
        "세션에서 자연어로 호출하면 입력 내용에 따라 스킬이 적절한 persona로 라우팅합니다. "
        "여러 persona를 묶은 9종 팀 템플릿으로 파이프라인을 한 번에 돌립니다.",
        commands=[
            {
                "kind": "note",
                "text": "<span class='star'>★ 공통 모델 — propose → confirm → execute</span> — "
                "모든 persona는 파일을 읽고, 제안 초안을 작성하고, 무엇이 바뀔지 보여준 다음에야 작성합니다. "
                "사람의 확인 없이는 어떤 파일도 변경되지 않습니다."
                "<ul>"
                "<li><strong>input_kinds</strong>는 각 persona가 받는 입력(text · file · vault_page) 종류입니다.</li>"
                "<li><strong>output_kind</strong>는 결과가 어디로 가는지를 나타냅니다 — "
                "<code>stdout</code>(세션 출력) · <code>new_page</code>(새 페이지) · "
                "<code>sibling_file</code>·<code>sibling_suffix</code>(형제 파일) · "
                "<code>inplace</code>(제자리 편집).</li>"
                "</ul>",
            },
            {
                "label": "Researcher — 세션에서:",
                "bar": "ai session",
                "text": "autoresearch how does the LLM Wiki pattern compare to Zettelkasten?",
                "callout": "다라운드 웹 리서치로 출처를 가중하고, 인라인 인용·confidence 태그가 붙은 "
                "구조화 페이지 초안을 만듭니다. → <code>new_page</code>",
            },
            {
                "label": "Fact-checker — 세션에서:",
                "bar": "ai session",
                "text": "fact-check wiki/concepts/llm-wiki.md",
                "callout": "초안을 원자 단위 주장으로 분해해 웹 검색으로 검증하고, 판정 표"
                "(supported · contradicted · partial · unverifiable)를 "
                "<code>&lt;page&gt;.factcheck.md</code>에 작성합니다. → <code>sibling_suffix</code>",
            },
            {
                "label": "Polisher / Translator / Summarizer — 세션에서:",
                "bar": "ai session",
                "text": "polish this            # 번역투 제거·문체 정리 (제자리, .trash 백업)\n"
                "translate this to Korean   # frontmatter·코드블록 보존, 형제 파일 생성\n"
                "summarize this         # 한 줄 / 한 단락 / 상세 3단 JSON",
                "callout": "Polisher는 <code>--lang ko</code>에서 korean-prose-polish 규칙을 따릅니다. "
                "Translator·Fact-checker는 웹 검색 도구(<code>mcp__brightdata__search_engine</code>)를 사용합니다.",
            },
            {
                "label": "Wiki-auditor / Wiki-librarian / Curator — 세션에서:",
                "bar": "ai session",
                "text": "check my wiki for contradictions   # auditor: 건강 진단\n"
                "build a glossary for my vault      # terminology-manager\n"
                "curate my wiki                     # index 재정렬 제안",
                "callout": "auditor는 무엇이 아픈지 진단하고, librarian은 어떻게 고칠지 제안하며"
                "(교차 링크·고립 해소·병합), curator는 <code>wiki/index.md</code>를 재동기화합니다.",
            },
            {
                "after_persona_table": True,
            },
        ],
        after="__PERSONA_TABLE__\n__TEAM_TABLE__",
    ),
    # ── E. 유지 (규약 · 신뢰도 · 링크) ───────────────────────────────────────
    dict(
        num="E",
        title="유지 — 규약 · 신뢰도 · 링크",
        lede="vault 건강은 결정론 명령으로 유지합니다. 스키마가 페이지 규약을 정의하고, "
        "<code>supersede</code>·<code>review</code>가 신뢰도와 수명을, "
        "<code>links</code>·<code>fields</code>가 그래프를, <code>lint</code>가 전체 health를 관리합니다.",
        commands=[
            {
                "label": "페이지 규약 조회 — omw schema list / show",
                "bar": "terminal",
                "text": "omw schema list                    # 13개 타입 + 각 타입 요구사항\n"
                "omw schema show entity             # 한 타입의 유효 스키마\n"
                "omw schema show entity --vault demo   # vault 오버라이드 적용",
                "callout": "13개 타입: article · book · comparison · concept · doc · entity · link · "
                "meta · note · paper · summary · synthesis · video. "
                "<code>entity</code>만 본문에 <code>## Summary</code> 섹션을 요구하고, "
                "<code>meta</code>는 필수 필드를 면제받습니다.",
            },
            {
                "label": "vault별 스키마 오버라이드",
                "bar": "tree",
                "text": "~/.omw/vaults/demo/\n"
                "└── schemas/\n"
                "    └── entity.yml   ← 이 vault에서만 내장 entity 스키마를 오버라이드",
                "callout": "<code>&lt;vault&gt;/schemas/</code>의 파일이 패키지 루트 <code>schemas/</code>의 "
                "내장 기본값보다 우선합니다. 공유 기본값을 건드리지 않고 특정 프로젝트에 커스텀 타입을 "
                "추가하거나 필드 규칙을 강화합니다.",
            },
            {
                "label": "신뢰도 대체 — omw supersede",
                "bar": "terminal",
                "text": "omw supersede wiki/concepts/old-method.md --by llm-wiki",
                "callout": "페이지를 삭제하지 않고 frontmatter에 <code>status: superseded</code> + "
                "<code>superseded_by: &lt;slug&gt;</code>를 써서 감사 추적을 보존합니다. 반환 JSON은 "
                "<code>{relpath, status, superseded_by}</code>.",
            },
            {
                "label": "리뷰 주기 — omw review done / due",
                "bar": "terminal",
                "text": "omw review done wiki/concepts/llm-wiki.md --grade pass --today 2026-06-01\n"
                "omw review due --today 2026-09-01 --scheduled-only",
                "callout": "<code>--grade</code>는 <code>pass</code> 또는 <code>needs-work</code>. "
                "간격은 confidence를 따릅니다 — high → 90일, medium → 30일, low → 7일. "
                "<code>due</code>는 <code>{relpath, due, interval_days, confidence}</code> 목록을 반환하며, "
                "<code>review:</code> 블록이 없는 페이지는 <code>due: null</code>로 가장 앞에 정렬됩니다. "
                "<code>--scheduled-only</code>는 미검토 페이지를 제외합니다.",
            },
            {
                "label": "엔티티 자동 링크 — omw links suggest / link",
                "bar": "terminal",
                "text": "omw links suggest                                    # 링크 없는 언급 목록\n"
                "omw links suggest wiki/concepts/llm-wiki.md          # 한 페이지로 한정\n"
                "omw links link wiki/concepts/llm-wiki.md --to andrej-karpathy",
                "callout": "<code>suggest</code>는 <code>{src_relpath, target_slug, target_relpath, "
                "mention, position}</code> 목록을, <code>link</code>는 첫 언급을 "
                "<code>[[andrej-karpathy|Andrej Karpathy]]</code>로 제자리에서 재작성합니다. "
                "페이지는 <code>aliases:</code> frontmatter 목록으로 매칭 대상을 늘립니다.",
            },
            {
                "kind": "note",
                "text": "<span class='star'>★ 한국어 조사 매칭</span> — "
                "본문에 <strong>안드레이 카르파시가 이 방법을 제안했다.</strong>처럼 조사 "
                "<code>가</code>가 붙어 있어도, <code>suggest</code>가 이름을 slug와 매칭하고 "
                "<code>link</code>는 <code>[[…|안드레이 카르파시]]가 이 방법을 제안했다.</code>로 삽입합니다. "
                "조사는 wikilink 괄호 밖에 남고 표시 텍스트는 조사 없는 표준 이름입니다.",
            },
            {
                "label": "인라인 필드 — omw fields",
                "bar": "terminal",
                "text": "omw fields wiki/concepts/llm-wiki.md",
                "callout": "본문에 Dataview 문법 <code>key:: value</code>를 넣으면 frontmatter와 함께 "
                "파싱·인덱싱됩니다. 반환 JSON은 <code>{relpath, frontmatter, inline}</code>. 관계 키"
                "(<code>uses</code> · <code>contradicts</code> · <code>supersedes:: [[B]]</code>)는 "
                "frontmatter <code>relations:</code>와 동일하게 타입드 엣지 그래프에 반영됩니다.",
            },
            {
                "label": "전체 health 검사 — omw lint",
                "bar": "json",
                "text": "{\n"
                '  "vault_id": 1,\n'
                '  "vault_path": "~/.omw/vaults/demo",\n'
                '  "frontmatter_issues": [],\n'
                '  "drift": { "missing_files": [], "mtime_drift": [] },\n'
                '  "links": {\n'
                '    "broken": [], "orphans": [],\n'
                '    "index_drift": { "missing_from_index": [], "dangling_in_index": [] },\n'
                '    "contradictions": [], "supersedes": [],\n'
                '    "superseded_unmarked": [], "link_suggestions": []\n'
                "  },\n"
                '  "auto_fix_hints": []\n'
                "}",
                "callout": "<code>frontmatter_issues</code>는 필수 필드 검사, <code>drift</code>는 "
                "디스크↔인덱스 불일치, <code>links</code>의 7개 키는 구조 건강(broken · orphans · "
                "index_drift · contradictions · supersedes · superseded_unmarked · link_suggestions), "
                "<code>auto_fix_hints</code>는 실행 가능한 해결책을 담습니다. "
                "<code>--vault</code>로 대상 vault를 지정합니다.",
            },
            {
                "after_frontmatter_table": True,
            },
        ],
        after="__FRONTMATTER_TABLE__",
    ),
    # ── F. 운영 ──────────────────────────────────────────────────────────────
    dict(
        num="F",
        title="운영",
        lede="<code>omw serve</code>가 메신저 봇을 위한 로컬 읽기 전용 쿼리 API를 띄웁니다. "
        "host export로 어떤 AI 호스트에서도 같은 스킬을 쓰고, "
        "<code>OMW_HOME</code> 디렉토리 복사만으로 백업·이전이 끝납니다.",
        commands=[
            {
                "label": "인증 토큰 생성 — omw setup serve",
                "bar": "terminal",
                "text": "omw setup serve --generate-token",
                "callout": "토큰을 <code>~/.omw/.env</code>에 <code>OMW_SERVE_TOKEN</code>으로 "
                "권한 <code>0600</code>으로 저장합니다.",
            },
            {
                "label": "서버 시작 — omw serve",
                "bar": "terminal",
                "text": "omw serve                                        # http://127.0.0.1:8765 (localhost 전용)\n"
                "omw serve --host 0.0.0.0 --port 9000 --vault demo --limit 5",
                "callout": "기본 바인딩은 localhost입니다. 공개·TLS 노출은 리버스 프록시(예: Caddy)로 "
                "앞단을 구성합니다 — 서버 자체는 TLS를 종료하지 않습니다. "
                "<code>--limit</code>은 응답당 최대 hit 수 상한입니다.",
            },
            {
                "label": "메신저 API — curl",
                "bar": "bash",
                "text": "TOKEN=$(grep OMW_SERVE_TOKEN ~/.omw/.env | cut -d= -f2)\n\n"
                "# health (인증 불필요)\n"
                "curl -s http://127.0.0.1:8765/health\n"
                '# {"status":"ok"}\n\n'
                "# query (POST + bearer token)\n"
                "curl -s -X POST http://127.0.0.1:8765/query \\\n"
                '  -H "Authorization: Bearer $TOKEN" \\\n'
                '  -H "Content-Type: application/json" \\\n'
                '  -d \'{"text":"what is attention?","limit":3}\'',
                "callout": "<code>POST /query</code>는 인증 필요, <code>GET /health</code>는 인증 불필요, "
                "<code>GET /query</code>는 405를 반환합니다. 본문 필드 — <code>text</code>(필수) · "
                "<code>user</code> · <code>channel</code>(로그 패스스루) · <code>vault</code> · "
                "<code>limit</code>.",
            },
            {
                "label": "응답 형식 (200) — 재순위 hit 목록 (LLM 없음)",
                "bar": "json",
                "text": "{\n"
                '  "query": "what is attention?",\n'
                '  "vault": "ai-research",\n'
                '  "count": 1,\n'
                '  "hits": [\n'
                "    {\n"
                '      "relpath": "wiki/concepts/attention.md",\n'
                '      "title": "Attention",\n'
                '      "summary": "...",\n'
                '      "tags": ["nlp"],\n'
                '      "score": 12.3\n'
                "    }\n"
                "  ]\n"
                "}",
                "callout": "서버는 답을 합성하지 않고 랭커 결과를 그대로 돌려줍니다. 메신저"
                "(Slack · Telegram · Discord) 어댑터는 이 hit을 메시지로 포매팅하는 얇은 webhook입니다. "
                "에러는 모두 JSON — 401(토큰) · 400(본문) · 404(vault) · 409(활성 vault 없음) · "
                "405(메서드) · 500(내부). 전체 형식은 "
                "<code>references/messenger-api.md</code>에 있습니다.",
            },
            {
                "label": "host export — 어떤 AI 호스트에서도 동일",
                "bar": "terminal",
                "text": "omw setup hosts --host claude,codex,gemini",
                "callout": "<code>CLAUDE.md</code> · <code>AGENTS.md</code>(Codex) · "
                "<code>GEMINI.md</code>에 동일한 트리거 문구를 export합니다. "
                "<code>--base-dir</code>로 instruction 파일 위치를 지정합니다. host-universal — "
                "한 SKILL.md가 모든 호스트에서 같은 방식으로 동작합니다.",
            },
            {
                "kind": "note",
                "text": "<span class='star'>★ 백업 · 이전</span> — "
                "모든 상태가 <code>$OMW_HOME</code>(기본 <code>~/.omw</code>) 한 곳에 모입니다 — "
                "<code>registry.db</code> · <code>config.yaml</code> · <code>.env</code> · "
                "<code>vaults/</code>."
                "<ul>"
                "<li>이 디렉토리를 복사하면 백업이, 새 머신에서 같은 위치에 두고 "
                "<code>OMW_HOME</code>을 가리키면 이전이 끝납니다.</li>"
                "<li>SMB 마운트 vault(<code>/Volumes/…</code>)는 <code>cp -a</code> 대신 "
                "<code>rsync -rlpt</code>를 사용합니다.</li>"
                "</ul>",
            },
        ],
    ),
    # ── G. 뷰어 연동 (view · setup viewer) ───────────────────────────────────
    dict(
        num="G",
        title="뷰어 연동 — Obsidian · Logseq",
        lede="활성 vault·페이지·검색 결과를 Obsidian 또는 Logseq에서 URI 스킴으로 직접 엽니다. "
        "플러그인 설치 없이 동작하며, <code>omw setup viewer</code>로 기본 뷰어를 저장하고 "
        "설정 스캐폴드를 생성합니다.",
        commands=[
            {
                "label": "기본 뷰어 설정 — omw setup viewer",
                "bar": "terminal",
                "text": "omw setup viewer",
                "callout": "기본 뷰어(obsidian 또는 logseq)를 <code>~/.omw/config.yaml</code>에 저장하고, "
                "<code>.obsidian/</code> 또는 <code>logseq/</code> 설정 스캐폴드를 생성합니다.",
            },
            {
                "label": "페이지 열기 — omw view",
                "bar": "terminal",
                "text": "omw view                                          # 활성 vault를 뷰어로\n"
                "omw view wiki/concepts/llm-wiki.md               # 특정 페이지를 뷰어로\n"
                "omw view --search \"compounding knowledge\"         # 검색 결과를 뷰어로\n"
                "omw view --viewer logseq                          # 뷰어 일회성 지정\n"
                "omw view wiki/concepts/llm-wiki.md --print        # URI만 출력 (열지 않음)",
                "callout": "<code>--viewer</code>를 생략하면 <code>omw setup viewer</code>에서 저장한 기본값을 사용합니다. "
                "<code>--print</code>는 앱을 실행하지 않고 URI만 stdout에 출력해 자동화에 활용합니다.",
            },
            {
                "kind": "note",
                "text": "<span class='star'>★ URI 스킴</span> — "
                "Obsidian은 <code>obsidian://open?vault=…&file=…</code>, "
                "Logseq는 <code>logseq://graph/…?page=…</code> 형식을 사용합니다. "
                "두 앱 모두 URI 스킴을 지원하므로 별도 플러그인이 불필요합니다.",
            },
        ],
    ),
    # ── H. 공개 여부 (visibility) ─────────────────────────────────────────────
    dict(
        num="H",
        title="공개 여부 — visibility",
        lede="페이지별로 공개(public)·비공개(private) 여부를 설정합니다. "
        "기본값은 private이며, <code>omw serve</code>는 public 페이지만 노출합니다(secure-by-default).",
        commands=[
            {
                "label": "공개 여부 조회 — omw visibility get",
                "bar": "terminal",
                "text": "omw visibility get wiki/concepts/llm-wiki.md",
                "callout": "해당 페이지의 현재 공개 여부를 출력합니다.",
            },
            {
                "label": "공개 여부 설정 — omw visibility set",
                "bar": "terminal",
                "text": "omw visibility set wiki/concepts/llm-wiki.md public\n"
                "omw visibility set wiki/concepts/old-method.md wiki/concepts/draft.md private",
                "callout": "여러 <code>relpath</code>를 동시에 지정할 수 있습니다. "
                "마지막 인수가 <code>public</code> 또는 <code>private</code>입니다. "
                "<code>omw serve</code>는 <code>public</code>으로 설정된 페이지만 <code>POST /query</code>로 노출합니다.",
            },
            {
                "kind": "note",
                "text": "<span class='star'>★ secure-by-default</span> — "
                "새 페이지의 기본값은 <strong>private</strong>입니다. "
                "공개 API나 메신저 봇에 노출하려면 <code>omw visibility set &lt;relpath&gt; public</code>으로 "
                "명시적으로 설정해야 합니다.",
            },
        ],
    ),
    # ── I. 받은함 (inbox) ─────────────────────────────────────────────────────
    dict(
        num="I",
        title="받은함 — inbox",
        lede="URL을 큐에 모아 일괄 수집합니다. 브라우저를 읽다 흥미로운 링크를 발견하면 "
        "<code>add</code>로 쌓아 두고, 나중에 <code>run</code>으로 한 번에 raw/로 가져옵니다.",
        commands=[
            {
                "label": "URL 큐에 추가 — omw inbox add",
                "bar": "terminal",
                "text": "omw inbox add https://example.com/article\n"
                "omw inbox add https://youtu.be/dQw4w9WgXcQ",
                "callout": "URL을 받은함 큐에 등록합니다. 즉시 수집하지 않습니다.",
            },
            {
                "label": "큐 조회 — omw inbox list",
                "bar": "terminal",
                "text": "omw inbox list           # 대기 중인 URL 목록\n"
                "omw inbox list --done    # 처리된 항목 포함",
            },
            {
                "label": "항목 제거 — omw inbox remove",
                "bar": "terminal",
                "text": "omw inbox remove https://example.com/article",
            },
            {
                "label": "일괄 수집 — omw inbox run",
                "bar": "terminal",
                "text": "omw inbox run",
                "callout": "큐에 있는 URL을 순서대로 가져와 <code>raw/</code> 레이어에 저장합니다. "
                "LLM 추론 없이 원본 그대로 저장하는 결정론 수집입니다.",
            },
            {
                "kind": "note",
                "text": "<span class='star'>★ LLM 없음</span> — "
                "<code>omw inbox run</code>은 <strong>LLM 없이</strong> 원본을 그대로 raw/에 저장합니다. "
                "이후 세션에서 <code>ingest</code>를 사용하면 LLM이 요약·페이지 생성까지 처리합니다.",
            },
        ],
    ),
    # ── J. 개별 URL 수집 (fetch) ──────────────────────────────────────────────
    dict(
        num="J",
        title="개별 URL 수집 — fetch",
        lede="URL 하나(웹페이지 또는 유튜브 자막)를 즉시 raw/로 가져옵니다. "
        "urllib → chromium(SPA) → cloud(Firecrawl/Bright Data) 순서로 자동 캐스케이드하며 "
        "SSRF 가드가 내부 주소를 차단합니다.",
        commands=[
            {
                "label": "웹페이지 가져오기 — omw fetch",
                "bar": "terminal",
                "text": "omw fetch https://example.com/article\n"
                "omw fetch https://youtu.be/VIDEO_ID\n"
                "omw fetch https://example.com/spa --backend chromium\n"
                "omw fetch https://example.com/article --today 2026-06-01",
                "callout": "<code>--backend</code>는 <code>auto</code>(기본) · <code>urllib</code> · "
                "<code>chromium</code> · <code>cloud</code> 중 하나입니다. "
                "<code>auto</code>는 urllib → chromium → cloud 순으로 시도합니다. "
                "<code>--today</code>로 수집 날짜를 명시합니다.",
            },
            {
                "kind": "note",
                "text": "<span class='star'>★ 백엔드 캐스케이드</span> — "
                "urllib(기본 HTTP)로 먼저 시도하고, SPA처럼 JS 렌더링이 필요하면 chromium으로, "
                "그래도 실패하면 Firecrawl·Bright Data 클라우드 백엔드로 자동 전환합니다. "
                "YouTube URL은 자막(자동 생성 포함)을 추출합니다. "
                "내부 IP·loopback 주소는 SSRF 가드로 차단됩니다.",
            },
        ],
    ),
    # ── 부록 ─────────────────────────────────────────────────────────────────
    dict(
        num="부록",
        title="레퍼런스 표",
        lede="CLI 17개 서브커맨드·플래그, frontmatter 필드, 페르소나 16종, 팀 9종을 표로 정리합니다. "
        "모든 플래그는 <code>--help</code>로, 출력은 격리 vault에서 실측했습니다.",
        commands=[{"after_cli_table": True}],
        after="__CLI_TABLE__",
    ),
]


# ─────────────────────────────────────────────────────────────────────────────
# Appendix tables (.ref-table — reusing the showcase HEAD style)
# ─────────────────────────────────────────────────────────────────────────────
def _row(cells: list[str]) -> str:
    return "<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>"


def _header(cells: list[str]) -> str:
    return "<tr>" + "".join(f"<th>{esc(c)}</th>" for c in cells) + "</tr>"


CLI_TABLE = (
    '<div class="block-label">CLI 17개 서브커맨드 · 플래그 (--help 실측)</div>'
    '<table class="ref-table">'
    + _header(["서브커맨드", "동작 / 서브-서브커맨드", "주요 플래그"])
    + _row(["<code>omw status</code>", "레지스트리 상태를 JSON으로", "—"])
    + _row(
        [
            "<code>omw vault</code>",
            "<code>create</code> · <code>list</code> · <code>use</code> · <code>forget</code>",
            "<code>--mode {memo,wiki}</code> · <code>--type {markdown,obsidian}</code> · <code>--location</code>",
        ]
    )
    + _row(["<code>omw lint</code>", "결정론 vault health 검사", "<code>--vault</code>"])
    + _row(
        [
            "<code>omw fields</code>",
            "frontmatter + 인라인 <code>key:: value</code> 표시",
            "<code>relpath</code> · <code>--vault</code>",
        ]
    )
    + _row(
        [
            "<code>omw links</code>",
            "<code>suggest [relpath]</code> · <code>link</code>",
            "<code>--to &lt;slug&gt;</code> · <code>--vault</code>",
        ]
    )
    + _row(
        [
            "<code>omw review</code>",
            "<code>due</code> · <code>done</code>",
            "<code>--grade {pass,needs-work}</code> · <code>--today</code> · <code>--scheduled-only</code> · <code>--vault</code>",
        ]
    )
    + _row(
        [
            "<code>omw supersede</code>",
            "페이지를 superseded로 표시",
            "<code>relpath</code> · <code>--by &lt;slug&gt;</code> · <code>--vault</code>",
        ]
    )
    + _row(
        [
            "<code>omw schema</code>",
            "<code>list</code> · <code>show &lt;type&gt;</code>",
            "<code>--vault</code> (오버라이드 적용)",
        ]
    )
    + _row(
        [
            "<code>omw search</code>",
            "외부 provider 웹 검색",
            "<code>query</code> · <code>--provider</code> · <code>--limit</code>",
        ]
    )
    + _row(
        [
            "<code>omw serve</code>",
            "로컬 읽기 전용 쿼리 API (포트 8765)",
            "<code>--host</code> · <code>--port</code> · <code>--vault</code> · <code>--limit</code>",
        ]
    )
    + _row(
        [
            "<code>omw setup</code>",
            "<code>vault·hosts·search·serve·personas·tts·import</code>",
            "<code>--noninteractive</code> · <code>--generate-token</code> · <code>--enable</code> · <code>--main</code> · <code>--host</code> · …",
        ]
    )
    + _row(
        [
            "<code>omw import</code>",
            "폴더 / Obsidian / Notion 가져오기",
            "<code>--source {folder,obsidian,notion}</code> · <code>--src-dir</code> · <code>--notion-id</code> · <code>--layer {raw,wiki}</code> · <code>--vault</code>",
        ]
    )
    + _row(["<code>omw doctor</code>", "omw 설정 + 설치 건강 검증", "—"])
    + _row(
        [
            "<code>omw view</code>",
            "활성 vault·페이지·검색을 Obsidian/Logseq URI 스킴으로 열기",
            "<code>[relpath]</code> · <code>--search Q</code> · <code>--viewer {obsidian,logseq}</code> · <code>--print</code>",
        ]
    )
    + _row(
        [
            "<code>omw visibility</code>",
            "<code>get &lt;relpath&gt;</code> · <code>set &lt;relpath…&gt; {public,private}</code>",
            "<code>relpath</code> (다중 가능) · <code>public|private</code>",
        ]
    )
    + _row(
        [
            "<code>omw inbox</code>",
            "<code>add</code> · <code>list</code> · <code>remove</code> · <code>run</code>",
            "<code>url</code> · <code>--done</code>(list)",
        ]
    )
    + _row(
        [
            "<code>omw fetch</code>",
            "URL 하나(웹페이지·유튜브 자막)를 raw/로 즉시 수집",
            "<code>url</code> · <code>--backend {auto,urllib,chromium,cloud}</code> · <code>--today YYYY-MM-DD</code>",
        ]
    )
    + "</table>"
    + '<div class="callout" style="margin-top:18px">'
    "추론 작업(<code>ingest</code> · <code>query</code> · <code>find</code> · <code>open</code> · "
    "<code>edit</code> · <code>move</code> · <code>delete</code> · <code>autoresearch</code> · "
    "<code>persona-*</code> · <code>dispatch</code> · <code>team</code> · <code>team-run</code> · "
    "<code>swarm-monitor</code>)은 <strong>Claude / Codex / Gemini 세션</strong>에서 자연어로 "
    "사용합니다 — CLI에서 호출하면 \"needs a Claude session\" 안내가 출력됩니다."
    "</div>"
)

FRONTMATTER_TABLE = (
    '<div class="block-label">Frontmatter 필드 규약 (schemas/base.yml + v3 필드)</div>'
    '<table class="ref-table">'
    + _header(["필드", "타입 / 허용값", "설명"])
    + _row(["<code>title</code>", "str (필수)", "페이지 제목"])
    + _row(["<code>date</code>", "str (필수)", "작성·갱신 날짜 (YYYY-MM-DD)"])
    + _row(
        [
            "<code>type</code>",
            "str (필수)",
            "13개 스키마 타입 중 하나 (concept · entity · …). <code>meta</code> 타입은 필수 필드 면제",
        ]
    )
    + _row(["<code>tags</code>", "list (필수)", "주제 태그 목록"])
    + _row(
        [
            "<code>confidence</code>",
            "<code>high</code> · <code>medium</code> · <code>low</code>",
            "근거의 충분함. review 간격을 결정 (90 / 30 / 7일)",
        ]
    )
    + _row(
        [
            "<code>status</code>",
            "<code>draft</code> · <code>inbox</code> · <code>processed</code> · <code>raw</code> · <code>superseded</code> · <code>meta</code>",
            "페이지 수명 단계",
        ]
    )
    + _row(
        [
            "<code>superseded_by</code>",
            "str (slug)",
            "<code>status: superseded</code>일 때 대체 페이지 slug",
        ]
    )
    + _row(
        [
            "<code>review</code>",
            "dict — <code>{last, due, interval_days}</code>",
            "다음 재평가 일정. <code>omw review</code>가 관리",
        ]
    )
    + _row(["<code>aliases</code>", "list", "엔티티 자동 링크 매칭에 쓰이는 별칭 목록"])
    + _row(
        [
            "<code>relations</code>",
            "dict — <code>{uses, contradicts, supersedes}</code>",
            "타입드 엣지 그래프. 본문 인라인 <code>key:: [[B]]</code>와 동등",
        ]
    )
    + _row(
        [
            "인라인 <code>key:: value</code>",
            "Dataview 라인 문법 (본문)",
            "frontmatter와 함께 파싱·인덱싱. <code>omw fields</code>로 조회",
        ]
    )
    + "</table>"
)


def _persona_table() -> str:
    import re

    rows = []

    def _scalar(fm: str, key: str) -> str:
        # match `key: value` or `key: >` folded scalars on the next lines
        m = re.search(rf"(?m)^{key}:\s*(.+)$", fm)
        if not m:
            return ""
        val = m.group(1).strip()
        if val in (">", "|", ">-", "|-"):
            # folded/literal block — gather following indented lines
            lines = []
            after = fm[m.end():].splitlines()
            for ln in after:
                if ln.startswith("  ") or ln.strip() == "":
                    lines.append(ln.strip())
                else:
                    break
            return " ".join(x for x in lines if x).strip()
        return val

    def _list(fm: str, key: str) -> str:
        m = re.search(rf"(?m)^{key}:\s*(.*)$", fm)
        if not m:
            return ""
        inline = m.group(1).strip()
        if inline.startswith("[") and inline.endswith("]"):
            return ", ".join(x.strip() for x in inline[1:-1].split(",") if x.strip())
        # block list — following `  - item` lines
        items = []
        for ln in fm[m.end():].splitlines():
            s = ln.strip()
            if ln.startswith("  - ") or s.startswith("- "):
                items.append(s.lstrip("- ").strip())
            elif s == "":
                continue
            else:
                break
        return ", ".join(items)

    persona_dir = BASE.parent.parent / "personas"
    for f in sorted(persona_dir.glob("*.md")):
        text = f.read_text(encoding="utf-8")
        parts = text.split("---")
        fm = parts[1] if len(parts) >= 3 else ""
        name = _scalar(fm, "name") or f.stem
        desc = _scalar(fm, "description")
        # trim description to first sentence-ish for the table
        desc_short = re.split(r"(?<=[.。])\s", desc.strip())[0] if desc else ""
        if len(desc_short) > 120:
            desc_short = desc_short[:117] + "…"
        inp = _list(fm, "input_kinds")
        out = _scalar(fm, "output_kind")
        rows.append(
            _row(
                [
                    f"<code>{esc(name)}</code>",
                    esc(desc_short),
                    f"<code>{esc(inp)}</code>" if inp else "—",
                    f"<code>{esc(out)}</code>" if out else "—",
                ]
            )
        )

    return (
        '<div class="block-label">페르소나 16종 (personas/*.md frontmatter)</div>'
        '<table class="ref-table">'
        + _header(["persona", "역할", "input_kinds", "output_kind"])
        + "".join(rows)
        + "</table>"
    )


def _team_table() -> str:
    import re

    rows = []
    team_dir = BASE.parent.parent / "teams"
    for f in sorted(team_dir.glob("*.md")):
        text = f.read_text(encoding="utf-8")
        parts = text.split("---")
        fm = parts[1] if len(parts) >= 3 else ""
        name_m = re.search(r"(?m)^name:\s*(.+)$", fm)
        name = name_m.group(1).strip() if name_m else f.stem
        mode_m = re.search(r"(?m)^mode:\s*(.+)$", fm)
        mode = mode_m.group(1).strip() if mode_m else "—"
        # description: may be folded with `>` — gather indented continuation
        dm = re.search(r"(?m)^description:\s*(.*)$", fm)
        desc = ""
        if dm:
            first = dm.group(1).strip()
            if first in (">", "|", ">-", "|-"):
                lines = []
                for ln in fm[dm.end():].splitlines():
                    if ln.startswith("  ") or ln.strip() == "":
                        lines.append(ln.strip())
                    else:
                        break
                desc = " ".join(x for x in lines if x).strip()
            else:
                desc = first
        desc_short = re.split(r"(?<=[.。])\s", desc.strip())[0] if desc else ""
        if len(desc_short) > 130:
            desc_short = desc_short[:127] + "…"
        rows.append(
            _row(
                [
                    f"<code>{esc(name)}</code>",
                    esc(desc_short),
                    f"<code>{esc(mode)}</code>" if mode != "—" else "—",
                ]
            )
        )
    return (
        '<div class="block-label" style="margin-top:30px">팀 템플릿 9종 (teams/*.md frontmatter)</div>'
        '<table class="ref-table">'
        + _header(["team", "목적", "mode"])
        + "".join(rows)
        + "</table>"
    )


# ─────────────────────────────────────────────────────────────────────────────
# OVERVIEW design block — the two-surface model
# ─────────────────────────────────────────────────────────────────────────────
OVERVIEW_DESIGN = {
    "goal": "omw를 두 표면으로 쓴다 — 결정론 CLI와 세션 내 스킬.",
    "principles": [
        "페르소나는 제안, 결정론 명령이 실행 (propose → confirm → execute).",
        "어떤 AI 호스트(Claude Code · Codex · Gemini)에서도 동일한 SKILL.md, 동일한 트리거 문구.",
        "모든 파일 변경은 감사 가능 — 추론은 투명하게, 출력은 결정론으로.",
    ],
    "components": [
        (
            "⌨️",
            "omw CLI (17개)",
            "결정론 ops — status · vault · lint · fields · links · review · supersede · "
            "schema · search · serve · setup · import · doctor · view · visibility · inbox · fetch",
        ),
        (
            "💬",
            "omw 스킬",
            "세션 내 자연어 추론 — ingest · query · find · edit · autoresearch · "
            "16 페르소나 · 9 팀",
        ),
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# body + main
# ─────────────────────────────────────────────────────────────────────────────
def body() -> str:
    persona_table = _persona_table()
    team_table = _team_table()

    toc_links = "\n".join(
        f'<a href="#step-{s["num"]}"><span class="tag">{esc(s["num"])}</span>{esc(s["title"])}</a>'
        for s in SECTIONS
    )

    rendered = []
    for s in SECTIONS:
        html_s = render_section(s)
        html_s = html_s.replace("__CLI_TABLE__", CLI_TABLE)
        html_s = html_s.replace("__FRONTMATTER_TABLE__", FRONTMATTER_TABLE)
        html_s = html_s.replace("__PERSONA_TABLE__", persona_table)
        html_s = html_s.replace("__TEAM_TABLE__", team_table)
        rendered.append(html_s)
    sections_html = "\n\n".join(rendered)

    overview_block = render_block({"kind": "design", "design": OVERVIEW_DESIGN})

    return f"""<body>
<header class="hero">
  <div class="hero-inner">
    <span class="hero-badge">oh-my-wiki · v3 · 전체 기능 레퍼런스</span>
    <h1>oh-my-wiki 전체 기능<br>레퍼런스</h1>
    <p class="tagline">Claude Code · Codex · Gemini 세션에서 자연어로 위키를 키우고,
    <code>omw</code> CLI 17개 서브커맨드로 결정론 작업을 실행합니다. 기능 영역 10개 + 부록 표 4종.
    모든 플래그는 <code>--help</code>로, 출력은 격리 vault에서 실측했습니다.</p>
    <dl class="meta-grid">
      <div><dt>표면</dt><dd>omw CLI + omw 스킬</dd></div>
      <div><dt>CLI 서브커맨드</dt><dd>17개</dd></div>
      <div><dt>페르소나 · 팀</dt><dd>16 · 9</dd></div>
      <div><dt>페이지 타입</dt><dd>13개 스키마</dd></div>
    </dl>
  </div>
</header>

<nav class="toc"><div class="toc-inner">
{toc_links}
</div></nav>

<main>
<section id="overview">
  <div class="container">
    <div class="section-num">OVERVIEW</div>
    <h2>개요 — 두 표면 모델</h2>
    <p class="lede">oh-my-wiki는 Andrej Karpathy의 "LLM Wiki" 워크플로를 구현합니다.
    모든 소스는 raw 스냅샷, 요약 페이지, 10–15개의 엔티티·개념 페이지 터치로 이어지고,
    쿼리는 구조화된 위키에서 출처를 인용해 답합니다. host-universal — 하나의 SKILL.md가
    Claude Code · Codex · Gemini에서 동일하게 동작합니다. 인터페이스는 정확히 두 개입니다.</p>
    {overview_block}
  </div>
</section>

{sections_html}
</main>

<footer>
  <div class="container">
    oh-my-wiki — host-universal LLM 위키 · MIT License<br>
    CLI 플래그는 <code>python3 -m scripts.omw_cli &lt;sub&gt; --help</code>로, 출력은
    격리 <code>OMW_HOME</code> vault에서 실측했습니다. 페르소나·팀·frontmatter 표는
    personas/ · teams/ · schemas/ 에서 직접 읽었습니다.
    <div class="links">
      <a href="../../TUTORIAL.ko.md">TUTORIAL.ko.md</a>
      <a href="../../TUTORIAL.md">TUTORIAL.md (EN)</a>
      <a href="../tutorial-omw/tutorial-omw.html">튜토리얼 쇼케이스</a>
      <a href="https://github.com/dandacompany/oh-my-wiki">github.com/dandacompany/oh-my-wiki</a>
    </div>
  </div>
</footer>
</body>
</html>
"""


def main():
    OUT.write_text(HEAD + body(), encoding="utf-8")
    print(f"Wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
