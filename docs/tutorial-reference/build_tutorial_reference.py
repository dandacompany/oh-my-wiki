#!/usr/bin/env python3
"""Full-feature static HTML reference for the current oh-my-wiki release.

A sibling of the showcase (docs/tutorial-omw). It REUSES the showcase's design
system via importlib — HEAD (<head>+<style>, incl. the .ref-table style), esc(),
render_block(), render_section() — and defines its OWN SECTIONS / body() / main().

The command appendix is generated from the public operation registry; persona
and frontmatter tables are read from personas/*.md and schemas/base.yml.
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
    f"<title>oh-my-wiki v{_omw.VERSION} — 따라 하는 위키 셋업</title>",
    f"<title>oh-my-wiki v{_omw.VERSION} — 전체 기능 레퍼런스</title>",
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
        lede="두 가지 설치 경로 중 환경에 맞는 하나를 고릅니다. 설치 후 "
        "<code>omw setup</code>이 레지스트리와 첫 vault를 만들고, "
        "<code>omw status</code>·<code>omw doctor</code>가 연결 상태를 검증합니다.",
        commands=[
            {
                "label": "PATH A — PyPI (pipx / pip) · 권장",
                "bar": "bash",
                "text": "pipx install oh-my-wiki   # 또는: pip install oh-my-wiki\n"
                "omw setup agents",
                "callout": "설치 즉시 <code>omw</code> 커맨드를 사용할 수 있습니다.",
            },
            {
                "label": "PATH B — git clone + install script (개발자)",
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
                "label": "PATH C — Skills CLI",
                "bar": "bash",
                "text": "skills add dandacompany/oh-my-wiki@oh-my-wiki -g -y --copy -a claude-code",
                "callout": "스킬만 설치됩니다. <code>omw</code> CLI는 처음 사용 시 설치됩니다 — "
                "에이전트에 <code>omw 셋업 점검해줘</code>라고 하면 CLI 프리플라이트가 설치합니다. "
                "또는 지금 <code>pipx install oh-my-wiki</code>.",
            },
            {
                "label": "설정 마법사 — omw setup",
                "bar": "terminal",
                "text": "omw setup",
                "callout": "섹션을 순서대로 진행하는 대화형 마법사입니다. 섹션 인자를 주면 한 섹션만 "
                "다시 조정합니다: <code>vault</code> · <code>hosts</code> · <code>search</code> · "
                "<code>fetch</code> · <code>serve</code> · <code>personas</code> · <code>import</code> · "
                "<code>viewer</code> · <code>agents</code> · <code>recall</code> · <code>gate</code> · "
                "<code>playwright</code>. "
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
            {
                "label": "전체 명령 둘러보기 — omw help",
                "bar": "output",
                "text": "oh-my-wiki — commands by lifecycle phase\n\n"
                "Usage: omw <command> [options]   ·   omw <command> -h for command details\n\n"
                "Capture — bring sources in\n"
                "  fetch    [CLI]   ...    inbox  [CLI]   ...    ingest [skill] ...\n"
                "Synthesize — combine into new knowledge\n"
                "  context  [CLI]   ...    query  [skill] ...\n"
                "Use — pull knowledge back out\n"
                "  export   [CLI]   ...    list   [CLI]   ...    view   [CLI]   ...",
                "callout": "<code>omw help</code>는 모든 명령을 지식 라이프사이클 단계"
                "(capture→structure→synthesize→retrieve→maintain→use)별로 묶어 보여줍니다. "
                "<code>[CLI]</code>은 바로 실행하는 결정론 명령, <code>[skill]</code>은 세션의 omw 스킬이 "
                "수행하는 자연어 명령입니다. <code>omw -h</code>·<code>omw --help</code>도 같은 화면을 냅니다. "
                "개별 명령 상세는 <code>omw &lt;command&gt; -h</code>로 확인합니다. "
                "지원하는 에이전트(Claude Code·Codex 등)에서는 omw 스킬을 짧은 별칭 "
                "<code>/omw</code>·<code>$omw</code>로도 부를 수 있습니다(설치 시 함께 들어가는 별칭 스킬).",
            },
            {
                "label": "버전 확인 — omw version",
                "bar": "terminal",
                "text": f"omw version        # → omw {_omw.VERSION}\n"
                f"omw -v             # → omw {_omw.VERSION}\n"
                f"omw --version      # → omw {_omw.VERSION}",
            },
            {
                "label": "전체 현황·건강 한눈에 — omw report",
                "bar": "output",
                "text": f"omw report · demand-wiki · 현재 상태    omw {_omw.VERSION}\n\n"
                "VAULTS  (2 registered, active: demand-wiki)\n"
                "  * demand-wiki     wiki/obsidian   71 notes\n"
                "    work-notes      memo/markdown   38 notes\n\n"
                "ACTIVE VAULT  demand-wiki   ~/wiki   wiki/obsidian\n"
                "  Layers     raw 64 · wiki 71 · meta 2\n"
                "  Wiki       entities 41 · concepts 22 · syntheses 8\n"
                "  Graph      71 nodes · 188 edges · 6 dangling · modularity 0.62\n"
                "             4 communities · 3 bridges · 2 hubs\n"
                "  Index      present · 2 pages drifted\n"
                "  Review     due 5 · stale 4 · expired 1\n\n"
                "HEALTH\n"
                "  Install    ok   (yt-dlp ok · chromium missing · search brightdata)\n"
                "  Vault      ⚠ FAIR   (score 76 · stale 4 · expired 1 · dangling 6 · orphans 2 · lint 9)\n\n"
                "NEXT\n"
                "  1. maintain — 9 lint issue(s)          → omw lint\n"
                "  2. review   — 5 page(s) stale/expired   → omw review audit",
                "callout": "<code>omw report</code>는 흩어진 신호를 한 화면으로 모읍니다 — 등록된 모든 볼트 요약, "
                "활성 볼트의 구성(레이어·엔티티/콘셉트/synthesis·그래프·인덱스·리뷰), 그리고 건강 판정"
                "(설치 상태 · 볼트 등급 <code>GOOD</code>/<code>FAIR</code>/<code>NEEDS WORK</code> · 다음 행동). "
                "결정론적 읽기 전용이며 기본은 텍스트, <code>--json</code>으로 구조화 출력을 냅니다. "
                "<code>--vault</code>로 다른 볼트를, <code>--no-reindex</code>로 인덱스 갱신 생략을 선택합니다.",
            },
            {
                "label": "최신으로 업그레이드 — omw update",
                "bar": "terminal",
                "text": "omw update --check    # 현재→최신 비교만 (업그레이드 안 함)\n"
                "omw update            # 확인 후 환경에 맞게 자가 업그레이드\n"
                "omw update --yes      # 확인 없이 (비대화형/cron)",
                "callout": "설치 방식(pipx / pip / PEP668)을 감지해 올바른 업그레이드 명령을 실행하고, "
                "이미 최신이면 그대로 종료합니다. 업그레이드 후 관리형 호스트 블록"
                "(<code>CLAUDE.md</code> 등)을 새 버전 기준으로 다시 주입할지 묻습니다"
                "(<code>--no-refresh</code>로 생략). 설정·지식 볼트는 건드리지 않습니다.",
            },
            {
                "label": "통합 되돌리기 — omw uninstall",
                "bar": "terminal",
                "text": "omw uninstall --dry-run   # 제거 대상 미리보기 (아무것도 안 지움)\n"
                "omw uninstall             # 관리형 블록·훅·스킬 번들 제거 (자동 감지)\n"
                "omw uninstall --purge     # + ~/.omw config·시크릿·registry (볼트 보존)\n"
                "omw uninstall --vaults    # + 볼트 콘텐츠 삭제 ('delete' 타이핑 확인)",
                "callout": "<code>omw setup</code>이 주입한 것을 안전하게 되돌립니다 — 호스트 지침 파일의 "
                "관리형 블록, 네이티브 훅, 스킬 번들을 자동 감지해 제거합니다. 기본은 완전 가역(무손실)이며, "
                "<code>--purge</code>를 줘야 <code>~/.omw</code> 설정·시크릿·registry를, "
                "<code>--vaults</code>를 줘야 볼트 콘텐츠를 지웁니다. <strong>지식 볼트는 <code>--vaults</code> "
                "없이는 절대 삭제하지 않습니다.</strong> 패키지 자체는 마지막에 <code>pip uninstall</code> "
                "명령을 안내만 합니다(자동 실행하지 않음). TTY에서는 단계별 마법사로 묻습니다.",
            },
            {
                "label": "요청·작업 히스토리 — omw history",
                "bar": "terminal",
                "text": "omw history log --type generate --request \"슬라이드 만들어줘\" \\\n"
                "  --summary \"칠판 슬라이드 1장\" --ref wiki/concepts/agents.md\n"
                "omw history log --type edit --request \"더 짧게\" \\\n"
                "  --revises 1 --outcome revised --focus \"길이를 줄여줘\"\n\n"
                "omw history similar \"슬라이드 만들기\"   # 유사 과거 요청 + 결과 (JSON)\n"
                "omw history prefs                       # 반복 수정의 주안점 집계\n"
                "omw history find \"길이\"   ·   omw history list --type edit   ·   omw history show 2",
                "callout": "볼트별 <strong>요청/작업 히스토리</strong>입니다(<code>wiki/log.md</code> 콘텐츠 "
                "로그와 별개). 작업 단위를 끝내면 <code>omw history log</code>로 타입·요청·요약·연관 페이지"
                "(<code>--ref</code>)를 기록하고, 답변을 다시 고쳐달라는 요청은 <code>--revises &lt;id&gt; "
                "--outcome revised --focus \"바뀐 점\"</code>으로 남깁니다. 다음에 비슷한 요청을 받으면 "
                "<code>omw history similar</code>로 과거를, <code>omw history prefs</code>로 사용자가 반복해서 "
                "요구한 주안점을 먼저 참고합니다. 결정론적 JSON, 스킬이 필요할 때 호출.",
            },
            {
                "label": "로컬 임베딩 — omw embed",
                "bar": "terminal",
                "text": "omw embed status     # 현재 임베딩 provider·모델·전략 + 카운트 (JSON)\n"
                "omw embed list       # 알려진/등록된 모델 목록\n"
                "omw embed install    # fastembed 설치 + 활성 모델 예열\n"
                "omw embed use <model>   # 모델 전환(리셋 + 재인덱싱)\n"
                "omw embed reindex    # 활성 모델로 전체 볼트 재임베딩",
                "callout": "검색·recall 품질을 높이는 <strong>로컬 임베딩</strong>(FastEmbed) 관리입니다. "
                "외부 API 없이 로컬에서 임베딩을 생성하며, <code>omw setup recall</code>에서 임베딩/하이브리드 "
                "전략을 고르면 자동으로 설치·임베딩됩니다. 모델을 바꾸면 벡터 테이블을 리셋하고 재인덱싱합니다. "
                "<code>oh-my-wiki[local-embedding]</code> 익스트라가 필요합니다.",
            },
            {
                "label": "프롬프트별 recall — omw setup recall",
                "bar": "terminal",
                "text": "omw setup recall",
                "prose": "<strong>프롬프트별 recall</strong>은 물어보는 순간 AI 에이전트가 활성 위키를 "
                "자동으로 참고하게 만듭니다. <code>omw find</code>를 직접 실행하지 않아도 됩니다. "
                "<code>omw setup</code> 마법사의 한 섹션이기도 합니다.",
                "callout": "모드를 설정하고, 호스트 지침 파일에 안내 블록을 주입하며, 호스트별 네이티브 훅을 연결합니다. "
                "Claude Code·Codex는 <strong>SessionStart · UserPromptSubmit · PreToolUse</strong> 회상과 "
                "<strong>PreCompact · Stop</strong> 세션 임시 캡처를 사용합니다. host-neutral — 엔진 하나를 호스트별로 번역합니다.",
            },
            {
                "kind": "note",
                "text": "<span class='star'>★ 호스트 선택 — 규약 단위</span> — "
                "<code>omw setup recall</code>·<code>omw setup personas</code>의 호스트 선택지는 "
                "<strong>지침 파일(규약) 단위</strong>로 묶입니다: "
                "<code>claude</code>(CLAUDE.md) · <code>codex·opencode</code>(AGENTS.md — 같은 파일이라 한 번만 기록) · "
                "<code>gemini</code>(GEMINI.md) · <code>hermes</code>(프로필 선택 → "
                "<code>~/.hermes/profiles/&lt;프로필&gt;/SOUL.md</code>) · <code>openclaw</code>(워크스페이스 선택 → "
                "<code>&lt;워크스페이스&gt;/AGENTS.md</code>). 프로필/워크스페이스는 <code>--profile</code>·"
                "<code>--workspace</code>로 비대화형 지정합니다. Gemini는 SessionStart·BeforeAgent, "
                "Hermes는 pre_llm_call, OpenCode·OpenClaw는 TypeScript recall 플러그인을 사용합니다. 스킬 설치"
                "(<code>omw setup agents</code>)는 <strong>에이전트 단위</strong>로 6종 모두 각자 디렉토리에 깝니다.",
            },
            {
                "label": "설정 두 축 — recall.mode (언제) · recall.strategy (어떻게)",
                "bar": "config",
                "text": "recall.mode      auto       # 프롬프트마다 검색 → 강한 히트 시 <omw-recall> 블록 주입\n"
                "                 advisory   # 강한 히트 시 동일하게 주입; 히트 없을 때만 omw find 넛지로 폴백\n"
                "                 off\n\n"
                "recall.strategy  fts        # 키워드 + 한국어 조사 정규화 (결정론적, 기본값)\n"
                "                 embedding  # 시맨틱 벡터 검색 via sqlite-vec (provider 필요: omw setup recall --embed-provider openai|fake)\n"
                "                            # provider 미설정 시 키워드(FTS) 결과로 폴백\n"
                "                 hybrid     # fts + embedding RRF 융합; embedding provider 미설정 시 사실상 FTS\n"
                "                 llm        # 에이전트 위임 — 훅이 <omw-recall> 지시 방출, 세션 에이전트가 검색\n"
                "                            # submode: route(키워드vs시맨틱 판단 후 omw find) · generative(후보 읽어 필터)\n"
                "                            # 알 수 없는 전략은 fts로 폴백",
                "callout": "<code>mode</code>는 <strong>언제</strong> 위키를 참고할지, "
                "<code>strategy</code>는 <strong>어떻게</strong> 후보를 찾을지를 정합니다. "
                "<code>auto</code>와 <code>advisory</code> 모두 강한 히트가 있으면 <code>&lt;omw-recall&gt;</code>을 주입합니다. "
                "차이는 히트가 없을 때: <code>auto</code>는 조용히 넘어가고, <code>advisory</code>는 넛지를 남깁니다.",
            },
            {
                "label": "auto 모드에서 프롬프트에 주입되는 블록 예시",
                "bar": "omw-recall",
                "text": "<omw-recall> 활성 omw 위키에 관련 페이지가 있습니다 — 답변의 근거/출처로 활용하세요:\n"
                "- Demand Forecasting — wiki/syntheses/demand-forecasting.md [arima,prophet] (score 1.9)\n"
                "</omw-recall>",
                "callout": "제목·경로·태그·인용 점수가 함께 들어가, 에이전트가 곧바로 출처로 인용할 수 있습니다.",
            },
            {
                "kind": "note",
                "text": "<span class='star'>★ recall 품질의 비결</span> — "
                "recall은 좋은 <strong>title·aliases·tags·summary</strong> frontmatter에서 좋아집니다. "
                "FTS5는 본문도 검색하며, 품질 게이트는 이름·별칭·태그·요약·제한된 본문 근거와 의미 검색의 일치를 함께 확인합니다.",
            },
            {
                "label": "세션 임시 캡처 — 확인·숨김·끄기",
                "bar": "terminal",
                "text": "omw recall sessions\n"
                "omw recall sessions --dismiss <id>\n"
                "omw setup recall --session-capture off",
                "callout": "Claude Code·Codex에서 같은 프로젝트의 마지막 요청·결과·다룬 파일만 로컬 registry에 저장합니다. "
                "일반적인 비밀값 패턴을 가리고, 불러올 때는 이스케이프된 JSON 데이터로 구분합니다. "
                "최대 5개·30일 보관하며 위키로 자동 승격하지 않습니다. "
                "Codex는 <code>/hooks</code>에서 새 사용자 훅 승인이 필요합니다.",
            },
            {
                "label": "호스트 훅 출력 형식 — omw recall --format / --event",
                "bar": "terminal",
                "text": "omw recall prompt --format claude-json --event UserPromptSubmit\n"
                "omw recall pretool --format codex-json --event PreToolUse\n"
                "omw recall capture --host codex --source stop --format codex-json --event Stop\n"
                "omw recall sessions",
                "callout": "<code>omw recall</code>은 다섯 동작(<code>preamble</code> · <code>prompt</code> · "
                "<code>pretool</code> · <code>capture</code> · <code>sessions</code>)과 호스트별 플래그를 제공합니다. "
                "<code>--format</code>은 <code>plain</code>(기본) · "
                "<code>claude-json</code>(→ <code>{\"hookSpecificOutput\": {…}}</code>) · "
                "<code>codex-json</code> · <code>gemini-json</code> · <code>hermes-json</code> 중 하나입니다. "
                "<code>--event &lt;EventName&gt;</code>는 훅 이벤트 이름(<code>UserPromptSubmit</code> 등)을 "
                "봉투에 포함합니다. <code>omw setup recall</code>이 훅 설정 파일에 이 명령을 자동으로 주입하므로 "
                "보통 직접 실행할 필요는 없습니다 — 훅 출력을 디버깅하거나 커스텀 훅을 구성할 때 사용합니다.",
            },
            {
                "label": "설정 미리보기 — omw setup --dry-run",
                "bar": "terminal",
                "text": "omw setup --dry-run",
                "callout": "<code>omw setup --dry-run</code>은 <code>recall</code> · <code>personas</code> · "
                "<code>agents</code> 섹션이 호스트 지침 파일이나 훅에 무엇을 쓸지 미리 보여줍니다 — "
                "실제 파일 수정이나 훅 연결은 전혀 하지 않습니다. "
                "<code>omw setup</code>을 처음 실행하기 전에 확인용으로 유용합니다.",
            },
        ],
    ),
    # ── B. 볼트 · 수집 ────────────────────────────────────────────────────────
    dict(
        num="B",
        title="볼트 · 수집",
        lede="vault는 하나의 지식 저장소입니다. <code>omw vault</code> 서브커맨드로 생성·전환·관리하고, "
        "<code>omw import</code>로 기존 자료를 끌어오며, 세션에서 자연어 "
        "<code>ingest</code>로 새 소스를 흡수합니다.",
        commands=[
            {
                "label": "vault 생성 — omw vault create",
                "bar": "terminal",
                "text": "omw vault create demo --mode wiki",
                "callout": "<code>--mode</code>는 <code>wiki</code> · <code>memo</code> · "
                "<code>personal</code> · <code>book</code> · <code>business</code> · "
                "<code>github-codebase</code> · <code>website</code> 중 하나입니다. "
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
                "label": "목록 · 전환 · 조회",
                "bar": "terminal",
                "text": "omw vault list           # 등록된 vault를 JSON으로 (is_active 포함)\n"
                "omw vault list --all     # 아카이브된 vault까지 포함\n"
                "omw vault use demo       # 활성 vault 전환\n"
                "omw vault current        # 현재 활성 vault\n"
                "omw vault info demo      # 한 vault의 상세를 JSON으로",
            },
            {
                "label": "이름 변경 · 이동 · 설정 — rename · move · set",
                "bar": "terminal",
                "text": "omw vault rename demo research        # 레지스트리 라벨 변경 (인덱스 보존)\n"
                "omw vault move research ~/research-vault  # 폴더를 디스크에서 이동 + 경로 갱신\n"
                "omw vault set research --mode business    # 기존 파일 보존 + 새 모드 골격 추가",
                "callout": "<code>rename</code>은 라벨만, <code>move</code>는 실제 폴더 위치를 바꾸고 "
                "레지스트리 경로를 함께 갱신합니다.",
            },
            {
                "label": "아카이브 · 삭제 — archive · delete · forget",
                "bar": "terminal",
                "text": "omw vault archive research     # 목록에서 숨김 (인덱스 보존) · unarchive로 복원\n"
                "omw vault delete research      # 소프트 삭제 — vault를 휴지통으로 이동\n"
                "omw vault delete research --hard --yes   # 영구 삭제\n"
                "omw vault forget research      # 레지스트리 행만 제거 — 파일은 보존",
                "callout": "<code>delete</code>는 기본이 <strong>소프트</strong>(휴지통)이며 "
                "<code>--hard --yes</code>로만 영구 삭제합니다. <code>forget</code>은 디스크 파일을 "
                "건드리지 않고 레지스트리 행만 지웁니다(같은 경로로 다시 <code>create</code>하면 복구).",
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
                "kind": "note",
                "text": "<span class='star'>★ Notion 데이터베이스 · 스캔 PDF</span> — "
                "<code>--source notion</code>은 하위 페이지(child_page)뿐 아니라 "
                "<strong>데이터베이스(child_database)</strong>도 가져옵니다 — 각 행을 한 페이지로 변환합니다"
                "(페이지네이션·순환 안전). 스캔된 이미지 PDF는 <code>extract_text()</code>가 비면 "
                "<strong>OCR로 폴백</strong>합니다 — <code>pip install \"oh-my-wiki[ocr]\"</code>"
                "(pytesseract + Pillow)로 활성화하며, 미설치 시 원본 PDF만 보존하고 조용히 넘어갑니다.",
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
                "label": "근거 있는 인용 컨텍스트 — omw context",
                "bar": "terminal",
                "text": "omw context \"forecasting model\" --limit 8",
            },
            {
                "label": "결과 — 히트 본문 + 인용 매니페스트 (JSON)",
                "bar": "output",
                "text": "{\n"
                "  \"query\": \"forecasting model\",\n"
                "  \"strategy\": \"fts\",\n"
                "  \"hits\": [\n"
                "    { \"slug\": \"prophet\", \"relpath\": \"wiki/concepts/prophet.md\",\n"
                "      \"title\": \"Prophet\", \"score\": 4.1,\n"
                "      \"body\": \"## Summary\\n\\nProphet is an additive ...\",\n"
                "      \"truncated\": false, \"body_missing\": false }\n"
                "  ],\n"
                "  \"citations\": [ { \"slug\": \"prophet\", \"title\": \"Prophet\",\n"
                "                   \"relpath\": \"wiki/concepts/prophet.md\" } ]\n"
                "}",
                "callout": "설정된 검색 전략으로 후보를 찾고 <strong>각 히트의 본문을 읽어</strong> 인용 "
                "매니페스트와 함께 돌려줍니다. 세션의 <code>query</code> 카드는 이 본문·슬러그로만 답을 "
                "구성하므로 인용 환각이 사라집니다. 본문이 4000자를 넘으면 <code>truncated: true</code>, "
                "인덱스에는 있으나 디스크에서 사라진 페이지는 <code>body_missing: true</code>로 표시됩니다.",
            },
            {
                "label": "패싯 브라우징 — omw list",
                "bar": "terminal",
                "text": "omw list --type concept --tag forecasting\n"
                "omw list --status superseded        # 대체된 페이지만\n"
                "omw list --layer wiki --visibility public",
            },
            {
                "label": "결과 — 필터된 페이지 목록 (JSON, LLM 없음)",
                "bar": "output",
                "text": "[\n"
                "  { \"relpath\": \"wiki/concepts/arima.md\", \"title\": \"ARIMA\",\n"
                "    \"type\": \"concept\", \"status\": \"processed\", \"visibility\": \"private\" },\n"
                "  { \"relpath\": \"wiki/concepts/prophet.md\", \"title\": \"Prophet\",\n"
                "    \"type\": \"concept\", \"status\": \"processed\", \"visibility\": \"private\" }\n"
                "]",
                "callout": "<code>--tag</code>·<code>--type</code>·<code>--status</code>·"
                "<code>--layer</code>·<code>--visibility</code>를 AND로 조합합니다. 순수 SQL이라 "
                "LLM이 필요 없습니다.",
            },
            {
                "label": "자족 슬라이스 내보내기 — omw export",
                "bar": "terminal",
                "text": "omw export --tag forecasting --out ./forecasting-slice\n"
                "omw export --tag forecasting --zip ./forecasting.zip\n"
                "omw export --type concept --out ./concepts --force   # 비어있지 않은 폴더 허용",
                "callout": "선택한 페이지를 <code>wiki/&lt;layer&gt;/</code> 구조 그대로 디렉터리(또는 "
                "<code>--zip</code> 아카이브)로 복사하고 <code>EXPORT_MANIFEST.md</code>(내보낸 목록 + "
                "슬라이스 밖을 가리키는 dangling 링크)를 함께 씁니다. 슬라이스 밖 링크는 본문 그대로 보존됩니다. "
                "비어있지 않은 출력 폴더는 <code>--force</code> 없이는 거부하며, 볼트 루트 안에는 절대 쓰지 않습니다.",
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
        title="유지 — 페르소나",
        lede="위키 유지·검증 추론은 6종 wiki-maintenance persona가 담당합니다. "
        "세션에서 자연어로 호출하면 입력 내용에 따라 스킬이 적절한 persona로 라우팅합니다. "
        "오케스트레이션은 omw가 하지 않습니다 — 다단계 연결은 호스트 AI 에이전트(Claude Code · Codex · Gemini)가 맡습니다.",
        commands=[
            {
                "kind": "note",
                "text": "<span class='star'>★ 공통 모델 — propose → confirm → execute</span> — "
                "모든 persona는 파일을 읽고, 제안 초안을 작성하고, 무엇이 바뀔지 보여준 다음에야 작성합니다. "
                "사람의 확인 없이는 어떤 파일도 변경되지 않습니다."
                "<ul>"
                "<li><strong>input_kinds</strong>는 각 persona가 받는 입력(text · file · vault_page) 종류입니다.</li>"
                "<li><strong>output_kind</strong>는 결과가 어디로 가는지를 나타냅니다 — "
                "<code>stdout</code>(세션 출력) · "
                "<code>sibling_suffix</code>(형제 파일).</li>"
                "</ul>",
            },
            {
                "label": "autoresearch — 세션에서:",
                "bar": "ai session",
                "text": "autoresearch how does the LLM Wiki pattern compare to Zettelkasten?",
                "callout": "다라운드 웹 리서치로 출처를 가중하고, 인라인 인용·confidence 태그가 붙은 "
                "구조화 synthesis 초안을 만들어 저장 전 확인을 요청합니다. → "
                "<code>wiki/syntheses/&lt;slug&gt;.md</code>",
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
                "label": "Auditor / Librarian / Curator — 세션에서:",
                "bar": "ai session",
                "text": "audit my wiki                      # wiki-auditor: 무엇이 문제인지 진단\n"
                "tidy the wiki structure            # wiki-librarian: 고칠 구조 제안\n"
                "curate my wiki                     # curator: index 재정렬 제안",
                "callout": "auditor는 무엇이 아픈지 진단하고, librarian은 어떻게 고칠지 제안하며 "
                "(교차 링크·고립 해소·병합), curator는 <code>wiki/index.md</code>를 재동기화합니다. "
                "Fact-checker는 웹 검색 도구(<code>mcp__brightdata__search_engine</code>)를 사용합니다.",
            },
            {
                "label": "결정론 CLI로 페르소나 실행 — omw persona-run",
                "bar": "terminal",
                "text": "# 자체 수집(self-gathering) 페르소나 — 소스 없이\n"
                "omw persona-run consistency-checker --backend codex\n"
                "omw persona-run curator --backend claude\n\n"
                "# 소스 기반 페르소나 — 입력 지정\n"
                "omw persona-run fact-checker --page wiki/concepts/llm-wiki.md\n"
                "omw persona-run terminology-manager --file docs/glossary-draft.md\n\n"
                "# 제안 파일 적용\n"
                "omw persona-run curator --apply wiki/index.md.proposed.md",
                "callout": "<code>omw persona-run</code>은 페르소나를 격리된 일회성 서브에이전트(one-shot subagent)로 "
                "실행합니다. <code>--backend</code>는 <code>claude</code> · <code>codex</code> · "
                "<code>gemini</code> · <code>opencode</code> 중 하나로, 어떤 호스트에서도 같은 명령어로 씁니다. "
                "페르소나는 <strong>자체 수집</strong>(self-gathering — consistency-checker · curator · "
                "wiki-auditor · wiki-librarian)과 <strong>소스 기반</strong>(source-driven — fact-checker · "
                "terminology-manager)으로 나뉩니다. 자체 수집 역할은 <code>--page</code>·<code>--file</code>·"
                "<code>--text</code>가 불필요하며, 소스 기반 역할은 이 중 하나가 필수입니다. "
                "제안(propose) 권한을 가진 역할은 <code>&lt;target&gt;.proposed.md</code>를 생성하고 "
                "<code>--apply &lt;proposal&gt;</code>로만 실제 파일에 반영합니다.",
            },
            {
                "label": "omw persona-run 결과 예시 (JSON)",
                "bar": "json",
                "text": "{\"role\": \"consistency-checker\", \"backend\": \"codex\", \"filed\": null}",
                "callout": "<code>filed</code>는 <code>null</code>(stdout 출력 전용) 또는 "
                "사이드카 파일 경로(예: <code>wiki/concepts/llm-wiki.factcheck.md</code>)입니다.",
            },
            {
                "kind": "note",
                "text": "<span class='star'>★ access 필드 — 파일링 경계 강제</span> — "
                "각 페르소나의 frontmatter에는 <code>access: read-only | propose | write</code> 필드가 있습니다. "
                "이 값은 결과가 어디로 가는지를 결정하는 파일링 경계(filing boundary)에서 강제됩니다 — "
                "<strong>read-only</strong> 페르소나(fact-checker · consistency-checker · "
                "terminology-manager · wiki-auditor · wiki-librarian)는 볼트 콘텐츠 페이지에 절대 직접 쓰지 않고 "
                "stdout 또는 사이드카 리포트로만 출력합니다. "
                "<strong>propose</strong> 페르소나(curator)는 <code>.proposed.md</code>로 스테이징하고 "
                "<code>--apply</code>로만 적용합니다.",
            },
            {
                "label": "번들 실행 — omw persona-bundle",
                "bar": "terminal",
                "text": "omw persona-bundle list                          # 번들 목록\n"
                "omw persona-bundle show tidy                     # 번들 구성 확인\n"
                "omw persona-bundle run tidy --backend claude\n"
                "omw persona-bundle run tidy --page wiki/concepts/llm-wiki.md --backend codex",
                "callout": "<code>omw persona-bundle</code>은 이름 붙은 페르소나 팀을 순서대로 실행합니다 — "
                "각 페르소나는 격리된 일회성 서브에이전트로 실행됩니다. "
                "기본 제공 번들 <code>tidy</code>는 <code>consistency-checker + curator</code> 순서로 실행합니다. "
                "<code>--page</code>는 소스 기반 역할에만 라우팅됩니다. "
                "번들에 소스 기반 역할이 포함되어 있는데 <code>--page</code>가 없으면 오류가 납니다.",
            },
            {
                "label": "팬아웃 실행 — omw persona-fanout",
                "bar": "terminal",
                "text": "# 페이지를 명시적으로 지정\n"
                "omw persona-fanout fact-checker \\\n"
                "  --pages wiki/concepts/arima.md,wiki/concepts/prophet.md\n\n"
                "# 필터로 페이지 선택\n"
                "omw persona-fanout fact-checker \\\n"
                "  --tag forecasting --type concept --backend codex",
                "callout": "<code>omw persona-fanout</code>은 페이지 목록을 결정하고 각 페이지에 대해 "
                "<code>omw persona-run</code> 명령을 생성합니다 — 호스트 AI 에이전트가 이 명령들을 병렬로 실행합니다. "
                "<code>--pages a,b,c</code>로 직접 지정하거나 "
                "<code>--tag · --type · --status · --layer · --visibility</code> 필터를 AND 조합해 선택합니다. "
                "<strong>소스 기반 역할만 허용됩니다</strong> — "
                "consistency-checker · curator처럼 볼트 전체를 스스로 수집하는 역할은 팬아웃 대상이 아닙니다.",
            },
            {
                "label": "omw persona-fanout 결과 예시 (JSON)",
                "bar": "json",
                "text": "{\n"
                "  \"role\": \"fact-checker\",\n"
                "  \"backend\": \"codex\",\n"
                "  \"page_count\": 2,\n"
                "  \"commands\": [\n"
                "    \"omw persona-run fact-checker --page wiki/concepts/arima.md --backend codex\",\n"
                "    \"omw persona-run fact-checker --page wiki/concepts/prophet.md --backend codex\"\n"
                "  ]\n"
                "}",
                "callout": "<code>commands</code> 배열을 호스트 AI 에이전트가 병렬로 실행합니다. "
                "<code>page_count</code>는 선택된 페이지 수입니다.",
            },
            {
                "after_persona_table": True,
            },
        ],
        after="__PERSONA_TABLE__",
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
                "label": "중복 통합 — omw merge",
                "bar": "terminal",
                "text": "omw merge wiki/concepts/dup.md wiki/concepts/keeper.md\n"
                "# → keeper.md.proposed.md (통합본) + dup.md.proposed.md (tombstone) 스테이징\n"
                "omw merge --apply wiki/concepts/keeper.md.proposed.md   # 검토 후 적용",
                "callout": "두 유사 페이지를 하나로 합칩니다. <code>&lt;source&gt;</code>를 "
                "<code>&lt;target&gt;</code>(생존)으로 통합 — frontmatter union(태그·관계·source_raw·aliases), "
                "본문은 <code>## Merged from [[source]]</code> 아래로 이어붙이고, source-slug을 winner의 "
                "<code>aliases</code>에 등록해 기존 <code>[[source]]</code> 링크가 살아남습니다. source는 "
                "<code>status: merged</code> tombstone이 됩니다. 모든 변경은 <code>.proposed.md</code>로 "
                "스테이징되고 <code>--apply</code> 전까지 실제 페이지는 그대로입니다. 타입이 다르면 "
                "<code>--force</code>가 필요합니다.",
            },
            {
                "kind": "note",
                "text": "<span class='star'>★ supersede vs merge</span> — "
                "<code>supersede</code>는 한 페이지를 다른 페이지로 <strong>대체</strong>(단방향, 본문 보존 안 함)하고, "
                "<code>merge</code>는 두 페이지를 하나로 <strong>통합</strong>(본문 합치고 링크 보존)합니다. "
                "중복 후보는 <code>omw lint</code>의 <code>content_duplicate_candidates</code>가 제안합니다.",
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
        "별도 앱 확장 없이 동작하며, <code>omw setup viewer</code>로 기본 뷰어를 저장하고 "
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
                "두 앱 모두 URI 스킴을 기본으로 지원하므로 별도 확장이 불필요합니다.",
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
                "label": "RSS/Atom 피드 큐잉 — omw inbox add-feed",
                "bar": "terminal",
                "text": "omw inbox add-feed https://example.com/feed.xml\n"
                "omw inbox run    # 큐에 쌓인 피드 항목들을 한 번에 수집",
                "callout": "RSS 2.0/Atom 피드를 파싱해 각 글의 링크를 받은함 큐에 등록합니다(중복 URL 자동 제거). "
                "뉴스레터·블로그·팟캐스트 쇼노트를 한 번에 모읍니다. 갱신은 <code>add-feed</code>를 다시 실행하면 "
                "새 항목만 추가됩니다. 피드는 SSRF 가드 + 5MB 크기 제한으로 안전하게 가져옵니다.",
            },
            {
                "label": "일괄 수집 — omw inbox run",
                "bar": "terminal",
                "text": "omw inbox run",
                "callout": "큐에 있는 URL을 순서대로 가져와 <code>raw/</code> 레이어에 저장합니다. "
                "LLM 추론 없이 원본 그대로 저장하는 결정론 수집입니다. 같은 <code>source_url</code>의 "
                "raw 문서가 이미 있으면 네트워크를 다시 호출하거나 <code>-N.md</code> 복사본을 만들지 않고 "
                "기존 문서를 재사용하며 결과의 <code>deduped</code> 항목에 표시합니다.",
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
    # ── K. 슬래시 커맨드 · 체이닝 ─────────────────────────────────────────────
    dict(
        num="K",
        title="슬래시 커맨드 · 라이프사이클 체이닝",
        lede="모든 스킬 작업과 유지보수 페르소나는 명시적인 슬래시 커맨드로도 제공됩니다. "
        "작업이 끝나면 <code>omw next --after</code>가 현재 vault 상태에 맞는 다음 단계를 계산하지만 "
        "사용자 확인 없이 자동 실행하지는 않습니다.",
        commands=[
            {
                "label": "스킬 작업과 페르소나 바로 부르기",
                "bar": "ai session",
                "text": "/omw-ingest ./source.pdf\n"
                "/omw-summary wiki/concepts/llm-wiki.md\n"
                "/omw-synthesis forecasting\n\n"
                "/omw-auditor\n"
                "/omw-librarian\n"
                "/omw-curator\n"
                "/omw-fact-checker wiki/concepts/llm-wiki.md",
                "callout": "<code>/omw-librarian</code>과 <code>/omw-auditor</code>는 실제 role 이름의 "
                "선두 <code>wiki-</code>를 생략한 짧은 이름입니다. CLI에서는 "
                "<code>omw persona-run wiki-librarian</code>처럼 전체 role 이름을 씁니다.",
            },
            {
                "label": "상태 기반 다음 단계 확인",
                "bar": "terminal",
                "text": "omw next --after ingest --json\n"
                "# search/fetch → ingest → summary → synthesis → lint → review",
                "callout": "클러스터가 없으면 synthesis를, lint 문제가 없으면 lint를 제안에서 제외합니다. "
                "계산은 LLM 없이 같은 입력에 같은 결과를 내며, 안전 기본값은 중단입니다.",
            },
        ],
    ),
    # ── L. 완전 삭제 ─────────────────────────────────────────────────────────
    dict(
        num="L",
        title="완전 삭제",
        lede="호스트 연결, OMW 설정, 등록된 지식 vault, Python 패키지를 순서대로 제거합니다. "
        "<code>--vaults</code>는 등록된 vault 폴더까지 삭제하므로 필요한 문서는 먼저 백업합니다.",
        commands=[
            {
                "label": "1. 삭제 대상 미리보기",
                "bar": "terminal",
                "text": "omw uninstall --purge --vaults --dry-run",
                "callout": "아직 아무것도 지우지 않습니다. 기본 위치뿐 아니라 별도로 등록한 "
                "Obsidian·Markdown 폴더가 포함되는지 경로를 확인합니다.",
            },
            {
                "label": "2. 호스트 연결·설정·vault 삭제",
                "bar": "terminal",
                "text": "omw uninstall --purge --vaults",
                "callout": "<code>--purge</code>는 설정·시크릿·레지스트리를, <code>--vaults</code>는 "
                "등록된 vault 콘텐츠를 제거합니다. 사람이 직접 실행할 때는 확인을 건너뛰는 "
                "<code>--yes</code>를 쓰지 않습니다.",
            },
            {
                "label": "3. 설치 방식에 맞는 Python 패키지 제거",
                "bar": "terminal",
                "text": "pipx uninstall oh-my-wiki\n"
                "# 또는\n"
                "python3 -m pip uninstall oh-my-wiki",
            },
            {
                "label": "4. 제거 확인",
                "bar": "terminal",
                "text": "command -v omw\n"
                "ls -la \"$HOME/.omw\"\n\n"
                "# 정확히 기본 OMW 홈인지 눈으로 확인한 뒤에만\n"
                "rm -rf -- \"$HOME/.omw\"",
                "callout": "<code>OMW_HOME</code>을 바꿨다면 변수 값을 삭제 명령에 바로 넣지 말고, "
                "실제 경로를 먼저 출력해 정확한 대상인지 확인합니다.",
            },
        ],
    ),
    # ── M. 다른 환경에서 안전하게 사용 ───────────────────────────────────────
    dict(
        num="M",
        title="Windows · NAS · Hermes에서 안전하게 사용",
        lede="v2.44는 운영체제와 저장장치 차이 때문에 setup이나 재색인이 멈추지 않도록 경로·문자 인코딩·휴지통 처리를 보강했습니다.",
        commands=[
            {
                "label": "설치와 실제 저장 경로 확인",
                "bar": "terminal",
                "text": "omw doctor\n"
                "omw vault info <vault-name>",
                "callout": "WSL에서는 한글 Windows 사용자 폴더를 안전하게 찾고, CP949·UTF-16 노트도 "
                "재색인할 수 있습니다. 경로 자동 감지가 어려우면 명시적인 <code>/mnt/c/Users/...</code> "
                "절대 경로를 사용합니다.",
            },
            {
                "label": "NAS·SMB vault의 안전한 휴지통",
                "bar": "behavior",
                "text": "vault/.trash 사용 가능  → vault 안에서 소프트 삭제\n"
                "vault/.trash 사용 불가  → OMW_HOME/.trash/<vault>/ 로 자동 대체",
                "callout": "macOS SMB가 <code>.trash</code> 이름을 막아도 vault 등록은 계속됩니다. "
                "<code>omw doctor</code>가 실제로 쓰는 휴지통 경로를 보여줍니다.",
            },
            {
                "label": "Hermes 사용자 지정 홈",
                "bar": "terminal",
                "text": "export HERMES_HOME=/opt/data/hermes\n"
                "omw setup personas --profile <profile>\n"
                "omw setup recall --profile <profile>",
                "callout": "Hermes 프로필과 스킬 경로는 기본 <code>~/.hermes</code>를 가정하지 않고 "
                "<code>HERMES_HOME</code>을 따릅니다.",
            },
        ],
    ),
    # ── N. 데이터 무결성 · 운영 루프 ──────────────────────────────────────────
    dict(
        num="N",
        title="중복 없이 안전하게 운영하기",
        lede="삭제·수집·색인·진단을 한 흐름으로 묶으면 위키가 커져도 중복과 끊어진 링크를 줄일 수 있습니다.",
        commands=[
            {
                "label": "모든 vault 모드에서 안전한 페이지 삭제",
                "bar": "ai session",
                "text": "/omw-delete wiki/concepts/old-page.md",
                "callout": "기본은 소프트 삭제입니다. 들어오는 링크는 표시 텍스트로 바꾸고, 해당 페이지를 "
                "가리키는 관계 필드는 제거해 그래프가 끊어진 상태로 남지 않게 합니다.",
            },
            {
                "label": "권장 유지보수 흐름",
                "bar": "terminal",
                "text": "omw report\n"
                "omw lint\n"
                "omw next\n"
                "# 필요한 persona 실행·수정 후\n"
                "omw reindex --full\n"
                "omw report",
                "callout": "<code>lint</code>는 세션 시작 알림과 같은 그래프 기반 구조 검사를 포함합니다. "
                "<code>reindex --full</code>은 디스크에서 사라진 파일의 색인 행도 정리합니다. "
                "반복 작업은 <code>omw setup gate</code>로 유지보수 알림을 켤 수 있습니다.",
            },
            {
                "label": "임베딩 모델 전환",
                "bar": "terminal",
                "text": "omw embed status\n"
                "omw embed use intfloat/multilingual-e5-small\n"
                "omw embed status",
                "callout": "모델을 바꾸면 OMW가 벡터를 초기화하고 다시 임베딩합니다. E5 계열의 "
                "검색어·문서 접두사는 내부에서 자동 처리하므로 사용자가 <code>query:</code>나 "
                "<code>passage:</code>를 직접 붙일 필요가 없습니다.",
            },
        ],
    ),
    # ── 부록 ─────────────────────────────────────────────────────────────────
    dict(
        num="부록",
        title="레퍼런스 표",
        lede=f"CLI {_omw.CLI_COUNT}개와 스킬 작업 {_omw.SKILL_COUNT}개, frontmatter 필드, "
        "페르소나 6종을 현재 코드에서 자동으로 정리합니다. 상세 플래그는 "
        "<code>omw &lt;command&gt; --help</code>로 확인합니다.",
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


_PHASE_LABELS = {
    "capture": "수집",
    "structure": "구조화",
    "synthesize": "종합",
    "retrieve": "검색",
    "maintain": "유지",
    "use": "활용",
    "meta": "설정",
}


def _command_table() -> str:
    rows = []
    for op in _omw.CLI_OPS:
        rows.append(
            _row(
                [
                    f"<code>omw {esc(op.name)}</code>",
                    esc(_PHASE_LABELS.get(op.phase or "meta", op.phase or "meta")),
                    f"<code>{esc(op.cli_template or ('omw ' + op.name))}</code>",
                    esc(_omw.OP_SUMMARY_KO[op.name]),
                ]
            )
        )
    skill_names = " · ".join(f"<code>{esc(op.name)}</code>" for op in _omw.SKILL_OPS)
    return (
        f'<div class="block-label">CLI {_omw.CLI_COUNT}개 — 공개 작업 레지스트리 자동 생성</div>'
        '<div class="table-scroll"><table class="ref-table">'
        + _header(["명령", "단계", "호출 형태", "설명"])
        + "".join(rows)
        + "</table></div>"
        + '<div class="callout" style="margin-top:18px">'
        + f"세션 스킬 작업 {_omw.SKILL_COUNT}개: {skill_names}. "
        + "생각과 판단이 필요한 작업은 AI 세션이 절차를 수행하고, 정확한 플래그는 "
        + "<code>omw &lt;command&gt; --help</code>로 확인합니다."
        + "</div>"
    )


CLI_TABLE = _command_table()

FRONTMATTER_TABLE = (
    '<div class="block-label">Frontmatter 필드 규약 (schemas/base.yml)</div>'
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
        f'<div class="block-label">페르소나 {len(rows)}종 (personas/*.md frontmatter)</div>'
        '<table class="ref-table">'
        + _header(["persona", "역할", "input_kinds", "output_kind"])
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
            f"omw CLI ({_omw.CLI_COUNT}개)",
            "결정론 작업 — 수집·구조화·검색·유지·활용·설정을 공개 명령으로 실행",
        ),
        (
            "💬",
            "omw 스킬",
            "세션 내 자연어 추론 — ingest · query · find · open · edit · move · delete · "
            f"autoresearch · {_omw.SKILL_COUNT}개 스킬 작업 · 6개 유지보수 페르소나",
        ),
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# body + main
# ─────────────────────────────────────────────────────────────────────────────
def body() -> str:
    persona_table = _persona_table()

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
        rendered.append(html_s)
    sections_html = "\n\n".join(rendered)

    overview_block = render_block({"kind": "design", "design": OVERVIEW_DESIGN})

    return f"""<body>
<header class="hero">
  <div class="hero-inner">
    <span class="hero-badge">oh-my-wiki · v{_omw.VERSION} · 전체 기능 레퍼런스</span>
    <h1>oh-my-wiki 전체 기능<br>레퍼런스</h1>
    <p class="tagline">Claude Code · Codex · Gemini 세션에서 자연어로 위키를 키우고,
    <code>omw</code> CLI {_omw.CLI_COUNT}개와 스킬 작업 {_omw.SKILL_COUNT}개로 지식의 전체 흐름을 다룹니다.
    명령 목록은 v{_omw.VERSION} 공개 작업 레지스트리에서 자동 생성됩니다.</p>
    <dl class="meta-grid">
      <div><dt>표면</dt><dd>omw CLI + omw 스킬</dd></div>
      <div><dt>CLI 서브커맨드</dt><dd>{_omw.CLI_COUNT}개</dd></div>
      <div><dt>스킬 작업</dt><dd>{_omw.SKILL_COUNT}개</dd></div>
      <div><dt>페르소나</dt><dd>6종</dd></div>
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
    공개 플래그는 <code>omw &lt;command&gt; --help</code>로 확인합니다. 명령 목록은
    <code>scripts/ops_registry.py</code>에서 자동 생성하고, 페르소나·frontmatter 표는
    personas/ · schemas/ 에서 직접 읽었습니다.
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
