# oh-my-wiki — 현재 릴리스 시나리오 튜토리얼

> **영어 버전**: [TUTORIAL.md](./TUTORIAL.md)

이 튜토리얼은 실제 wiki vault를 구축하고 유지하는 과정을 단계별로 안내합니다.
명령과 플래그는 현재 공개 CLI를 기준으로 검증합니다. 설치된 정확한 버전은 `omw version`으로 확인하세요.
자연어 작업(ingest, query, autoresearch, persona)은 Claude Code / Codex / Gemini 세션에서
입력하는 프롬프트 형태로 표시됩니다. CLI 출력이 아닙니다.

---

## Part 1 — 무엇이며, 왜 쓰는가

**oh-my-wiki**는 AI 코딩 에이전트로 구동하는 wiki 규약 및 유지 관리 프레임워크입니다.
Andrej Karpathy가 "LLM Wiki" Gist에서 설명한 워크플로를 구현합니다. 모든 소스는
raw 스냅샷, 요약 페이지, 그리고 10–15개의 엔티티 및 개념 페이지 터치로 이어집니다.
쿼리는 평문 파일 덤프가 아닌 이 구조화된 wiki에서 가져오므로, 답변이 특정 페이지를
출처로 인용할 수 있습니다.

### Host-universal

oh-my-wiki는 **특정 AI 호스트에 종속되지 않습니다**. 다음 환경에서 동일하게 작동합니다:

- **Claude Code** — SKILL.md가 자동으로 감지되며, 트리거 문구로 스킬이 실행됩니다.
- **Codex CLI** — 동일한 SKILL.md, 동일한 트리거 문구.
- **OpenCode** — Codex와 같은 `AGENTS.md` 규약을 읽습니다.
- **Gemini CLI** — 동일한 SKILL.md, 동일한 트리거 문구.
- **Hermes** — 프로필별(`~/.hermes/profiles/<프로필>/`)로 격리되어 동작합니다.
- **OpenClaw** — 워크스페이스별로 격리되어 동작합니다.

어떤 호스트도 특별 대우를 받지 않습니다. 지금 사용 중인 에이전트라면 무엇이든 작동합니다.

### Two-surface model

oh-my-wiki는 정확히 두 가지 인터페이스를 제공합니다:

| 인터페이스      | 설명                                 | 예시                                                                                                                                                 |
| --------------- | ------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| **`omw` CLI**   | 결정론적 작업 — LLM 없이도 실행 가능 | `omw status`, `omw vault create`, `omw lint`, `omw schema list`, `omw supersede`, `omw review`, `omw links`, `omw fields`, `omw setup`, `omw doctor` |
| **`omw` skill** | 세션 내 자연어 추론                  | ingest, query, autoresearch, summary, synthesis, personas, find, edit, move, delete — 각각 `/omw-<op>` 슬래시 커맨드로도 제공                        |

모델의 흐름은 이렇습니다. **persona가 제안 → 사용자가 확인 → 결정론적 작업이 실행**.
Writing persona는 콘텐츠를 분석해 변경 사항을 제안하고, `omw` CLI가 결정론적 출력(링크 삽입,
supersede 처리, lint 수정)을 실행합니다. 이 구조 덕분에 추론 과정은 투명하고 파일 변경은
감사할 수 있습니다.

---

## Part 2 — 설치

환경에 맞는 방법을 선택하세요. PyPI 또는 git 경로를 선택한 경우 설치 후 `omw doctor`를
실행해 모든 것이 올바르게 연결되었는지 확인하세요. Skills CLI 경로를 선택한 경우 CLI는
처음 사용 시 설치됩니다(이후 `omw doctor` 실행).

### Path A — PyPI (`pip` / `pipx`) — 권장

레포를 클론하지 않고 [PyPI](https://pypi.org/project/oh-my-wiki/)에서 `omw` CLI를
설치합니다:

```bash
pipx install oh-my-wiki        # 격리된 CLI (권장)
# 또는
pip install oh-my-wiki         # 현재 환경에 설치
```

배포되는 wheel은 self-contained입니다 — schemas, personas, backends, 그리고 전체
스킬을 함께 담고 있어 바로 동작하는 `omw`를 얻습니다. 설치 후 번들된 스킬을 에이전트에
등록하려면 `omw setup agents`를 실행하세요. GitHub에서 직접 설치하는 것도 동일하게
동작합니다: `pipx install git+https://github.com/dandacompany/oh-my-wiki`.

### Path B — git clone + install script (개발자, Codex CLI 사용자)

```bash
git clone https://github.com/dandacompany/oh-my-wiki
cd oh-my-wiki
bash bin/install.sh
```

인스톨러가 수행하는 작업:

1. Python 3.10+ 확인.
2. `pip install -e "."` 실행 (개발용은 `--dev`를 추가해 pytest/ruff 포함).
3. `~/.claude/skills/oh-my-wiki`와 `~/.claude/skills/omw` symlink 생성 (멱등성 보장).
4. 설치 검증을 위해 `pytest -q` 실행 (`--no-test`로 건너뛸 수 있음).
5. 다음 단계와 트리거 문구를 출력.

재실행해도 안전합니다. `--force`를 사용하면 프롬프트 없이 기존 symlink를 교체합니다.
전체 플래그는 `bash bin/install.sh --help`로 확인하세요.

### Path C — Skills CLI (Claude Code 사용자)

```bash
skills add dandacompany/oh-my-wiki@oh-my-wiki -g -y --copy -a claude-code
```

이 명령은 스킬을 `~/.claude/skills/`에 설치하고 `oh-my-wiki`와 `omw` 단축 별칭 스킬
이름을 모두 등록합니다. 스킬만 설치됩니다. `omw` CLI는 처음 사용 시 설치됩니다 — 에이전트를
열고 **`omw 셋업 점검해줘`**(또는 `set up omw`)라고 말하면 스킬이 CLI 사전 확인을 실행하고
확인 후 CLI를 설치합니다. 지금 바로 설치하려면: `pipx install oh-my-wiki`.

### 설치 확인

```
omw doctor
```

vault가 존재하는 경우 출력 예시 (경로는 각자의 머신에 따라 다름):

```
omw home:   /Users/you/.omw  ok
registry:   /Users/you/.omw/registry.db  ok
  * demo (wiki/markdown) /Users/you/.omw/vaults/demo
```

**새 머신**에서 `omw setup`을 실행하기 전에는 다음과 같이 표시됩니다:

```
omw home:   /Users/you/.omw  missing (run: omw setup)
registry:   /Users/you/.omw/registry.db  missing
  no vaults registered — run: omw setup
```

`doctor`는 각 컴포넌트를 찾으면 `ok`를 보고하고, 없으면 무엇이 빠졌는지 설명합니다.

---

## Part 3 — 5분 빠른 시작

### Step 1 — 설정 마법사 실행

```
omw setup
```

`omw setup`은 첫 번째 vault, 검색 provider, serve API, persona, import, viewer, agents,
프롬프트별 recall 설정을 구성하는 대화형 마법사입니다.
프롬프트에 따라 진행하세요. 빠른 시작을 원하면 기본값을 그대로 받아들이면 됩니다. 나중에
`omw setup vault`나 `omw setup personas`를 다시 실행해 개별 섹션을 조정할 수 있습니다.

### Step 2 — 상태 확인

설정 직후 새 설치는 다음과 같이 표시됩니다:

```
omw status
```

```json
{
  "vault_count": 0,
  "active": null,
  "needs": "setup",
  "vaults": []
}
```

`needs: "setup"`은 깨끗한 머신에서 실제 사용자가 보는 화면입니다. (소스 트리에서 실행 중인 경우
`data/registry.db`가 저장소에 존재하므로 `needs`가 `"migrate"`로 표시됩니다. 이는 개발 트리에서만
나타나는 정상적인 동작입니다.)

### Step 3 — 첫 번째 vault 만들기

```
omw vault create demo --mode wiki
```

```json
{
  "created": "demo",
  "path": "~/.omw/vaults/demo",
  "mode": "wiki",
  "type": "markdown"
}
```

활성화 상태를 확인합니다:

```
omw vault list
```

```json
[
  {
    "name": "demo",
    "path": "~/.omw/vaults/demo",
    "mode": "wiki",
    "type": "markdown",
    "is_active": true
  }
]
```

### Step 4 — 노트 추가 (AI 세션에서)

Claude Code(또는 Codex / Gemini)를 열고 다음과 같이 말하세요:

```
ingest this

Andrej Karpathy calls the LLM Wiki a "compounding knowledge artifact". Every
source gets saved verbatim to raw/, a summary lands at wiki/summaries/, and
the entities and concepts that appeared get their own pages. 10–15 page touches
per ingest is normal.
```

스킬이 제목, slug, 태그, 저장 위치를 제안합니다. 확인하면 저장됩니다.

### Step 5 — lint 검사 실행

```
omw lint
```

문제가 없는 깨끗한 vault에서는:

```json
{
  "vault_id": 1,
  "vault_path": "~/.omw/vaults/demo",
  "frontmatter_issues": [],
  "drift": { "missing_files": [], "mtime_drift": [] },
  "links": {
    "broken": [],
    "orphans": [],
    "index_drift": { "missing_from_index": [], "dangling_in_index": [] },
    "contradictions": [],
    "supersedes": [],
    "superseded_unmarked": [],
    "link_suggestions": []
  },
  "auto_fix_hints": []
}
```

`frontmatter_issues: []`는 모든 페이지가 필수 필드 검사를 통과했음을 의미합니다.
`links` 키들(`broken`, `orphans`, `index_drift`, `contradictions`,
`supersedes`, `superseded_unmarked`, `link_suggestions`)은 vault의
전체적인 구조 건강 상태를 알려줍니다. `drift`는 디스크에 있지만 인덱스에 없는 파일을
보고하고, `auto_fix_hints`는 문제가 발견되면 실행할 수 있는 해결 방법을 제시합니다.

---

## Part 4 — 시나리오: 실제 wiki 성장시키기

이 섹션은 단일 연속 예제로 진행됩니다. 세 개의 페이지가 있는 `demo` vault를 사용합니다:

- `wiki/entities/andrej-karpathy.md` — Andrej Karpathy의 엔티티 페이지
- `wiki/concepts/llm-wiki.md` — LLM Wiki 방법론의 개념 페이지
- `wiki/concepts/old-method.md` — 나중에 폐기할 오래된 페이지

vault는 Part 3에서 생성했습니다. 페이지는 아래에서 세션 내 프롬프트 형태로 보여주는
ingest 워크플로로 추가됩니다.

### 4.1 스키마 — 각 페이지 타입에 필요한 필드는?

oh-my-wiki는 13개의 내장 페이지 타입을 제공합니다. 목록 확인:

```
omw schema list
```

13개 타입은 다음과 같습니다:
`article, book, comparison, concept, doc, entity, link, meta, note, paper, summary, synthesis, video`

목록의 각 항목은 `type`, `required_fields`, `required_sections`, `field_types`,
`allowed_values`를 가진 스키마 객체입니다. entity 타입을 자세히 살펴봅니다:

```
omw schema show entity
```

```json
{
  "type": "entity",
  "required_fields": ["title", "date", "type", "tags"],
  "required_sections": ["## Summary"],
  "field_types": {
    "tags": "list",
    "title": "str",
    "date": "str",
    "review": "dict",
    "aliases": "list"
  },
  "allowed_values": {
    "confidence": ["high", "medium", "low"],
    "status": ["draft", "inbox", "processed", "raw", "superseded", "meta"]
  }
}
```

모든 entity 페이지는 본문에 `## Summary` 섹션이 있어야 합니다. `confidence` 필드는
`high`, `medium`, `low`를 허용합니다. `status` 필드는 `allowed_values`에 나열된
값들을 허용합니다.

#### vault별 스키마 오버라이드

vault 디렉토리 안에 `schemas/` 폴더를 만들어 특정 vault의 스키마를 오버라이드하거나
확장할 수 있습니다. `<vault>/schemas/`의 파일이 패키지 루트의 내장 `schemas/`보다 우선합니다.
이렇게 하면 공유 기본값을 건드리지 않고 특정 프로젝트에 커스텀 타입을 추가하거나
필드 규칙을 강화할 수 있습니다.

```
~/.omw/vaults/demo/
└── schemas/
    └── entity.yml   ← overrides the built-in entity schema for this vault only
```

`demo` vault가 활성화된 상태에서 `omw schema show entity`는 오버라이드를 반영합니다.

### 4.2 데모 페이지 ingest

Claude Code(또는 Codex / Gemini) 세션에서 다음과 같이 말하세요:

```
ingest this

Andrej Karpathy is a researcher and educator known for karpathy.ai and the
LLM Wiki Gist. He describes wikis as compounding knowledge artifacts where
every source feeds the graph.
```

제안된 메타데이터를 확인합니다. 스킬이 `wiki/entities/andrej-karpathy.md`를 작성합니다.

그 다음:

```
ingest this

The LLM Wiki method is a structured approach to personal knowledge management.
Raw sources go to raw/, processed pages go to wiki/. Andrej Karpathy popularized
this pattern. The owner field tracks who maintains the page.
owner:: dante
status:: draft
```

이로써 `wiki/concepts/llm-wiki.md`가 작성됩니다. `owner:: dante`와 `status:: draft` 줄에
주목하세요. 이것은 인라인 `key:: value` 필드(Dataview 문법)입니다. oh-my-wiki는 이를
frontmatter 필드와 함께 보존하고 인덱싱합니다.

그런 다음 나중에 폐기할 페이지를 추가합니다:

```
ingest this

The old flat-notes method stores everything in a single folder with no
structure. It is quick to start but does not scale.
```

이로써 `wiki/concepts/old-method.md`가 작성됩니다.

### 4.3 Confidence와 supersession

페이지에는 해당 페이지의 근거가 얼마나 충분한지를 나타내는 `confidence` 필드(`high`,
`medium`, `low`)가 있습니다. 페이지가 더 나은 것으로 대체될 때, 삭제하는 대신
`superseded`로 표시합니다. 이렇게 하면 감사 추적이 보존됩니다.

`old-method.md`를 `llm-wiki`로 supersede 처리합니다:

```
omw supersede wiki/concepts/old-method.md --by llm-wiki
```

```json
{
  "relpath": "wiki/concepts/old-method.md",
  "status": "superseded",
  "superseded_by": "llm-wiki"
}
```

oh-my-wiki는 `old-method.md`에 다음 두 개의 frontmatter 필드를 작성합니다:

```yaml
status: superseded
superseded_by: llm-wiki
```

`omw lint`는 본문에서 "outdated" 또는 "replaced"로 비공식적으로 설명되어 있지만
이 필드가 없는 페이지를 `superseded_unmarked` 키 아래에 표시합니다.

### 4.4 Review 주기 — wiki 페이지의 간격 반복

모든 페이지는 frontmatter의 `review:` 블록으로 다음 재평가 일정을 지정할 수 있습니다.
간격은 confidence에 따라 달라집니다:

- `confidence: high` → 90일 간격
- `confidence: medium` → 30일 간격
- `confidence: low` → 7일 간격

`llm-wiki.md`(high-confidence 페이지)의 review를 완료 처리합니다:

```
omw review done wiki/concepts/llm-wiki.md --grade pass --today 2026-06-01
```

```json
{
  "relpath": "wiki/concepts/llm-wiki.md",
  "review": { "last": "2026-06-01", "due": "2026-08-30", "interval_days": 90 }
}
```

`high` confidence → 90일 간격 → 만료일 `2026-08-30`.

review 대상 목록을 조회합니다 (미래 날짜 시뮬레이션):

```
omw review due --today 2026-09-01
```

`{relpath, due, interval_days, confidence}` 항목의 목록이 반환됩니다. `review:` 블록이 없는
페이지는 `due: null`로 표시되며 가장 앞에 정렬됩니다. 한 번도 검토되지 않았으므로 주의가
필요합니다.

### 4.5 웹 검색, vault FTS5, 그리고 로컬 쿼리 API

#### `omw search` — 외부 웹 검색

`omw search "<query>"`는 외부 검색 provider(brave / tavily / exa / firecrawl /
brightdata)를 통한 **웹 검색**을 수행합니다. 오픈 웹에서 결과를 가져오며,
vault 내부를 검색하는 것은 **아닙니다**.

먼저 provider를 설정하세요:

```
omw setup search
```

provider가 설정되지 않은 경우 CLI는 다음을 출력합니다:

```
error: no search provider configured — run `omw setup search`
```

#### vault 검색 — FTS5 + 세션 내 쿼리

vault는 **SQLite FTS5**(title + summary + tags + body에 대한 BM25)로 인덱싱되며,
FTS5를 사용할 수 없을 때는 토큰 스코어 기반으로 자동 폴백됩니다. 검색 방법:

- **Claude / Codex / Gemini 세션에서**: "내 위키에서 X에 대해 뭐라고 해?"라고 말하면
  스킬이 FTS5로 검색하고 LLM이 결과를 재순위 매깁니다.
- **로컬 HTTP API** (`omw serve`)를 통해: 쿼리를 POST하면 순위가 매겨진 결과를 JSON으로
  반환합니다(서버에 LLM 없음 — 검색만).

#### `omw serve` — 로컬 읽기 전용 HTTP API

먼저 인증 토큰을 생성합니다(`~/.omw/.env`에 `OMW_SERVE_TOKEN`으로 저장됩니다):

```
omw setup serve --generate-token
```

그런 다음 서버를 시작합니다:

```
omw serve
```

서버는 **`http://127.0.0.1:8765`**(localhost 전용)에서 실행됩니다.
`POST /query`(인증 필요)로 vault를 쿼리하거나, `GET /health`(인증 불필요)로 활성
상태를 확인할 수 있습니다. `GET /query`는 405를 반환합니다.

```bash
# health (no auth)
curl -s http://127.0.0.1:8765/health

# query (POST + bearer token)
curl -s -X POST http://127.0.0.1:8765/query \
  -H "Authorization: Bearer $OMW_SERVE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"text": "compounding knowledge", "limit": 5}'
```

전체 요청/응답 JSON 형식과 Slack, Telegram, Discord 어댑터 스케치는
`references/messenger-api.md`를 참고하세요.

### 4.6 엔티티 자동 링크

wiki가 성장하면서 개념 페이지에 엔티티를 언급하지만 링크를 걸지 않는 경우가 생깁니다.
oh-my-wiki는 이런 링크 없는 언급을 감지하고 자동으로 링크를 삽입할 수 있습니다.

`llm-wiki.md` 페이지("Andrej Karpathy"를 언급)를 추가한 후 다음을 실행합니다:

```
omw links suggest
```

```json
[
  {
    "src_relpath": "wiki/concepts/llm-wiki.md",
    "target_slug": "andrej-karpathy",
    "target_relpath": "wiki/entities/andrej-karpathy.md",
    "mention": "Andrej Karpathy",
    "position": 145
  },
  {
    "src_relpath": "wiki/entities/andrej-karpathy.md",
    "target_slug": "llm-wiki",
    "target_relpath": "wiki/concepts/llm-wiki.md",
    "mention": "LLM Wiki",
    "position": 88
  }
]
```

출력은 모든 페이지에서 발견된 링크 없는 언급을 나열합니다. `llm-wiki.md`의 문자 위치 145에서
"Andrej Karpathy"가 wikilink 없이 언급되고, `andrej-karpathy.md`의 위치 88에서 "LLM Wiki"가
wikilink 없이 언급됩니다. 두 경우 모두 vault에 일치하는 페이지가 존재합니다.

링크를 삽입합니다:

```
omw links link wiki/concepts/llm-wiki.md --to andrej-karpathy
```

전체 제안 목록을 검토한 뒤 승인했다면 한 프로세스에서 일괄 적용할 수 있습니다.
재색인은 마지막에 한 번만 실행됩니다.

```bash
omw links link --from-suggestions
omw links link --from-suggestions --dry-run
```

```json
{
  "relpath": "wiki/concepts/llm-wiki.md",
  "target_slug": "andrej-karpathy",
  "mention": "Andrej Karpathy",
  "inserted": "[[andrej-karpathy|Andrej Karpathy]]"
}
```

oh-my-wiki는 해당 언급을 `[[andrej-karpathy|Andrej Karpathy]]`로 제자리에서 재작성합니다.

#### 한국어 엔티티 매칭

oh-my-wiki는 한국어 형태소를 올바르게 처리합니다. 페이지에 다음과 같이 쓰여 있다면:

```
안드레이 카르파시가 이 방법을 제안했다.
```

조사 `가`가 엔티티 이름에 붙어 있습니다. `omw links suggest`는 `안드레이 카르파시가`가
`안드레이 카르파시`의 엔티티 페이지 slug와 일치한다는 것을 감지하고,
`omw links link`는 다음과 같이 삽입합니다:

```
[[…|안드레이 카르파시]]가 이 방법을 제안했다.
```

조사는 wikilink 괄호 밖에 남습니다. 링크 표시 텍스트는 조사 없는 표준 이름입니다.

#### Aliases

엔티티 페이지는 frontmatter에 `aliases:` 목록을 선언할 수 있습니다:

```yaml
aliases:
  - Karpathy
  - AK
```

`omw links suggest`는 모든 alias를 링크 없는 언급과 매칭하므로, 전체 이름뿐 아니라
약칭 참조도 잡아낼 수 있습니다.

### 4.7 인라인 `key:: value` 필드

페이지 본문에 Dataview 스타일의 인라인 필드를 포함할 수 있습니다:

```
owner:: dante
status:: draft
uses:: [[llm-wiki]]
```

이는 파싱되어 frontmatter와 함께 저장됩니다. 페이지의 전체 필드 집합을 확인합니다:

```
omw fields wiki/concepts/llm-wiki.md
```

```json
{
  "relpath": "wiki/concepts/llm-wiki.md",
  "frontmatter": {
    "title": "LLM Wiki",
    "date": "2026-06-01",
    "type": "concept",
    "tags": ["method"]
  },
  "inline": { "owner": ["dante"], "status": ["draft"] }
}
```

wikilink(`[[other-page]]`)를 참조하는 관계 키(`uses`, `contradicts`, `supersedes`)는
frontmatter `relations:`와 동일한 방식으로 타입드 엣지 그래프에 반영됩니다.

### 4.8 wiki 유지 관리 persona (세션 내, 자연어)

oh-my-wiki는 Claude Code / Codex / Gemini 세션에서 자연어로 호출하는 여섯 가지 wiki
유지 관리 persona를 제공합니다. 별도 커맨드가 필요 없습니다. 스킬이 입력한 내용에 따라
적절한 persona로 라우팅합니다. 목록은 wiki-auditor / wiki-librarian / curator / fact-checker /
consistency-checker / terminology-manager입니다(Part 5 표 참고).

**Wiki-auditor** — lint·유지 상태·그래프를 모아 무엇이 문제인지 우선순위로 진단합니다.

```
audit my wiki
```

**Wiki-librarian** — 고립 페이지·교차 링크·병합 후보 등 구조를 어떻게 고칠지 제안합니다.

```
tidy the wiki structure
```

**Curator** — `wiki/index.md`의 누락과 순서를 검토하고 새 구성을 제안합니다.

```
curate my index
```

**Fact-checker** — 초안을 원자 단위 주장으로 분해하고, 웹 검색으로 각각을 검증한 후,
판정 표(supported / contradicted / partial / unverifiable)가 담긴 형제 리포트를
`<your-page>.factcheck.md`에 작성합니다. Claude 세션에서 다음과 같이 말하세요:

```
fact-check wiki/concepts/llm-wiki.md
```

**Consistency-checker** — 전체 일관성 검사를 실행합니다. 모순, 용어 표류, 오래된 주장을 점검합니다.
Claude 세션에서 다음과 같이 말하세요:

```
check my wiki for contradictions
```

**Terminology-manager** — vault의 용어집을 구축하고 유지 관리합니다. Claude 세션에서
다음과 같이 말하세요:

```
build a glossary for my vault
```

출처가 필요한 리서치는 `autoresearch` wiki 작업(FAQ 참고)을 사용하세요. 질문을 주장 단위로
분해하고, 주장별로 최대 3라운드의 Bright Data MCP 검색을 실행하며, confidence 태그를 부여한
다음, `wiki/syntheses/`에 synthesis 페이지 초안을 작성하고 저장 전에 확인을 요청합니다.

모든 persona는 **제안 → 확인 → 실행** 모델을 따릅니다. 파일을 읽고, 제안 초안을 작성하고,
무엇이 변경될지 보여준 다음 작성합니다.

### 4.9 프롬프트별 recall — 필요한 순간 위키가 알아서 따라옵니다

위키는 _쓰여야_ 값을 합니다. `recall`은 질문하는 순간 AI 에이전트가 활성 위키를
자동으로 참고하게 만듭니다. `omw find`를 직접 떠올려 칠 필요가 없습니다.

활성화(전체 `omw setup`의 한 단계이기도 하고, 단독 실행도 가능):

```
omw setup recall
```

이 명령은 모드를 설정하고, 호스트 지침 파일에 짧은 가이드 블록을 넣고, 네이티브 훅을
배선합니다. Claude Code와 Codex에서는 `SessionStart`·`UserPromptSubmit`·`PreToolUse`로
회상하고, `PreCompact`·`Stop`에서 다음 세션에 필요한 최소 맥락을 임시 저장합니다.
여기서 omw는 호스트 중립적입니다. 하나의 엔진을 각 호스트의 훅 포맷으로 번역할 뿐입니다.

임시 세션 캡처는 위키 페이지가 아닙니다. 마지막 요청·결과·다룬 파일만 비밀값을 가린 뒤
같은 프로젝트 범위에 최대 5개, 30일 동안 로컬 레지스트리에 보관합니다. 새 세션을 시작하거나
"이어서 진행해"처럼 재개를 요청하면 이 맥락을 함께 보여 줍니다. 지식 후보 승격은 기본값이
`off`이며, 권장 `staged` 모드도 승인 전에는 볼트 파일을 바꾸지 않습니다.

```
omw recall sessions                         # 임시 캡처 확인
omw recall sessions --dismiss <id>          # 사용한 캡처 숨기기
omw setup recall --session-capture off      # 임시 캡처 끄기
omw setup recall --knowledge-candidates staged
omw candidates status                       # 모드·범위·보존 기간·처리 이유
omw candidates list                         # 후보 묶음 목록
omw candidates show <batch-id>              # 분류·신뢰도·판단 이유
omw candidates approve <batch-id>           # 승인한 항목만 private raw/로 승격
omw candidates dismiss <batch-id>           # 파일 변경 없이 버리기
```

후보 추출은 결정론적으로 동작합니다(같은 입력이면 같은 결과이며, 매 턴 모델을 호출하지
않습니다). `Stop`은 캡처만 하고, `PreCompact` 또는 다음 세션 경계에서 묶어서 분석합니다.
활성 볼트를 현재 회상 검색 방식으로 확인한 뒤 `new`·`update`·`duplicate`·`conflict`로
표시합니다. 승인하지 않은 후보 묶음은 30일 뒤 만료됩니다. `omw candidates config`로
프로젝트·호스트·볼트별 모드를 따로 끌 수 있습니다. 별도 선택인 `auto-raw`는 신뢰도가 높은
새 항목만 비공개 `raw/`에 저장하며, 위키 페이지 수정·병합·공개·덮어쓰기는 계속 확인을 받습니다.

AgentMemory는 선택 사항입니다. 문서화된 `GET /agentmemory/export`로 JSON을 내보낸 뒤
`omw candidates run --agentmemory-json <export.json>`을 실행합니다. OMW는 AgentMemory의
내부 데이터베이스를 직접 읽지 않습니다.

Codex는 새 사용자 훅을 처음 설치하거나 명령이 바뀌면 신뢰 확인을 요구합니다. 설정 후 Codex에서
`/hooks`를 열어 OMW의 새 훅을 검토·승인해야 실제로 실행됩니다.

`PreToolUse`는 에이전트가 파일을 읽기 직전에 파일명과 관련된 위키 페이지를 찾아 줍니다.
특히 `raw/`를 바로 읽으려 할 때는 이미 정리된 `wiki/`가 있는지 먼저 확인하도록 안내합니다.

호스트 선택지는 **지침 파일(규약) 단위**로 묶입니다 — `claude`(CLAUDE.md) · `codex·opencode`(AGENTS.md, 한 번만 기록) · `gemini`(GEMINI.md) · `hermes`(프로필 **여러 개 선택** → `~/.hermes/profiles/<프로필>/SOUL.md`) · `openclaw`(워크스페이스 **여러 개 선택** → `<워크스페이스>/AGENTS.md`). 프로필/워크스페이스 선택은 **멀티 셀렉트(체크박스)** 입니다 — 원하는 만큼 체크하면(활성 프로필·기본 워크스페이스는 기본 체크) 선택한 **모든** 대상에 가이드 블록과 네이티브 훅이 기록됩니다. 비대화형으로는 `--profile` / `--workspace`에 **콤마로 여러 개**를 줄 수 있습니다(예: `--profile iris,mark`). 호스트가 제공하는 훅 종류에 따라 실제 배선 범위는 달라지며, Claude Code와 Codex가 위의 전체 회상·임시 캡처 흐름을 사용합니다.

| 호스트              | 네이티브 회상 범위                                 | 세션 임시 캡처                                              |
| ------------------- | -------------------------------------------------- | ----------------------------------------------------------- |
| Claude Code         | `SessionStart` · `UserPromptSubmit` · `PreToolUse` | `PreCompact` · `Stop`                                       |
| Codex               | `SessionStart` · `UserPromptSubmit` · `PreToolUse` | `PreCompact` · `Stop` — `/hooks` 승인 필요                  |
| Gemini CLI          | `SessionStart` · `BeforeAgent`                     | 사용하지 않음                                               |
| Hermes              | 선택한 프로필별 `pre_llm_call`                     | `post_llm_call`; 이전 세션은 다음 `pre_llm_call`에서 후보화 |
| OpenCode · OpenClaw | 호스트별 TypeScript recall 플러그인                | 사용하지 않음                                               |

세션 캡처는 `recall.mode`와 독립적이며 기본값은 켜짐입니다. recall을 꺼도 이전 캡처가
자동 삭제되지는 않습니다. 위의 확인·숨김 명령으로 관리하세요.

FTS와 의미 검색은 점수 범위가 다릅니다. `recall.min_score`는 FTS 기준으로 유지되고,
임베딩·하이브리드의 0~1 기준은 `recall.min_scores.embedding`과
`recall.min_scores.hybrid`로 따로 설정합니다. `omw embed status`에서 실제 기준값,
설정 경고, 영구 모델 캐시 위치, 볼트별 색인 비율을 확인할 수 있습니다.

설정 가능한 두 축:

- `recall.mode` — _언제_ 작동하나:
  - `auto` — 매 프롬프트마다 활성 볼트를 검색해, 관련 페이지가 있으면 `<omw-recall>`
    블록(제목·경로·태그·출처)을 주입해 에이전트가 그 근거로 답하게 합니다.
  - `advisory` — 훅은 강한 히트가 있을 때 여전히 검색하여 `<omw-recall>` 블록을 주입합니다;
    임계값을 만족하는 강한 히트가 없을 때만 `omw find`를 권유하는 한 줄 넛지로 폴백합니다.
    (auto vs advisory의 차이는 강한 히트가 없을 때: auto는 조용히 넘어가고, advisory는 넛지를 남깁니다.)
  - `off` — 비활성.
- `recall.strategy` — _어떻게_ 검색하나:
  - `fts` — 키워드 + 한국어 조사 정규화 (결정론적, 기본값).
  - `embedding` — sqlite-vec를 통한 시맨틱 벡터 검색. `omw setup recall
--embed-provider openai` (또는 `fake`)로 provider를 설정해야 동작. provider 미설정 시
    키워드(FTS) 결과로 폴백합니다.
  - `hybrid` — fts + embedding의 RRF 융합. 임베딩 provider 미설정 시 사실상 FTS로 동작합니다.
  - `llm` — 에이전트 위임: recall 훅이 `<omw-recall>` 지시를 내보내고, 세션 내 에이전트가
    직접 검색합니다. `recall.llm.submode`로 서브모드 선택 가능: `route`(에이전트가 키워드
    vs 시맨틱을 판단 후 `omw find` 실행) · `generative`(에이전트가 후보를 읽어 진짜 관련
    항목만 남김). 알 수 없는 전략은 `fts`로 폴백합니다.

예시 — 위키에 있는 주제를 물으면(예: "수요 예측에서 ARIMA와 Prophet 비교") 에이전트는
다음을 받습니다:

```
<omw-recall> 활성 omw 위키에 관련 페이지가 있습니다 — 답변의 근거/출처로 활용하세요:
- Demand Forecasting — `wiki/syntheses/demand-forecasting.md` [arima,prophet] (score 1.9)
</omw-recall>
```

그래서 추측 대신 단테님이 검증·출처를 단 페이지를 인용해 답합니다.

> recall 품질은 좋은 `title` / `aliases` / `tags` / `summary` frontmatter에서 좋아집니다.
> FTS5는 페이지 본문도 검색합니다. 하이브리드·임베딩 recall은 결과를 주입하기 전에 정확한
> 이름, 별칭, 태그, 요약, 제한된 본문 근거, 의미 검색의 일치 정도를 함께 확인합니다.

---

## Part 5 — 레퍼런스

### 주요 CLI 서브커맨드

아래 표는 자주 쓰는 명령을 추린 것입니다. 전체 정본은 작업 단계별로 자동 생성되는
`omw help`에서 확인하세요.

| 서브커맨드        | 인터페이스 | 한 줄 설명                                                                                                                                                                                                                                                                                     |
| ----------------- | ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `omw status`      | CLI        | 레지스트리 상태 표시: vault 수, 활성 vault, `needs` 코드                                                                                                                                                                                                                                       |
| `omw vault`       | CLI        | Vault 관리: `create` · `list [--all]` · `use` · `current` · `info` · `rename` · `move` · `set` · `archive`/`unarchive` · `delete`(소프트 기본, `--hard --yes`) · `forget`                                                                                                                      |
| `omw lint`        | CLI        | 결정론적 vault 건강 검사 (frontmatter + links + drift)                                                                                                                                                                                                                                         |
| `omw search`      | CLI        | 설정된 외부 provider를 통한 웹 검색 (brave/tavily/exa/…)                                                                                                                                                                                                                                       |
| `omw serve`       | CLI        | 로컬 읽기 전용 HTTP 쿼리 API 시작 (포트 8765)                                                                                                                                                                                                                                                  |
| `omw schema`      | CLI        | 페이지 타입 스키마 표시: `list`, `show <type>`                                                                                                                                                                                                                                                 |
| `omw supersede`   | CLI        | 페이지를 `status: superseded` + `superseded_by: <slug>`로 표시                                                                                                                                                                                                                                 |
| `omw review`      | CLI        | 간격 반복 대기열: `due`, `done`                                                                                                                                                                                                                                                                |
| `omw links`       | CLI        | 엔티티 자동 링크: `suggest`, `link`                                                                                                                                                                                                                                                            |
| `omw fields`      | CLI        | 페이지의 frontmatter + 인라인 `key:: value` 필드 표시                                                                                                                                                                                                                                          |
| `omw import`      | CLI        | 폴더 / Obsidian / Notion(페이지 + DB 행) 가져오기 · 스캔 이미지 PDF는 OCR 폴백(`oh-my-wiki[ocr]` 익스트라)                                                                                                                                                                                     |
| `omw setup`       | CLI        | 대화형 마법사: vault, 검색, serve, persona, import, viewer, agents, recall                                                                                                                                                                                                                     |
| `omw doctor`      | CLI        | omw 설정 + 설치 건강 상태 검증                                                                                                                                                                                                                                                                 |
| `omw connections` | CLI        | 위키 링크 그래프에 대한 커뮤니티 감지; 커뮤니티·브리지(크로스 커뮤니티 링크)·허브(≥2 커뮤니티 연결 페이지)를 표시합니다. 읽기 전용 JSON.                                                                                                                                                       |
| `omw maint`       | CLI        | 지식 관리 상태: `omw maint status [--vault] [--exit-code]`으로 만료/오래된 페이지 + lint 이슈를 집계하고 한 줄 넛지를 출력합니다. `--exit-code`는 작업이 필요하면 1을 반환합니다(cron 친화적).                                                                                                 |
| `omw report`      | CLI        | 한 화면 상태 + 건강 대시보드: 전체 볼트 요약 + 활성 볼트 구성(레이어/엔티티/콘셉트/synthesis/그래프/태그/인덱스/받은함/리뷰) + 건강 판정(설치 + 볼트 등급 + 다음 행동). 기본 텍스트, `--json`은 구조화 dict; 읽기 전용.                                                                        |
| `omw history`     | CLI        | 볼트별 요청/작업 히스토리(`wiki/log.md`와 별개): `log`은 작업 단위 기록(타입 + 요청 + 요약 + `--ref` 페이지), `similar`는 유사 과거 요청 랭킹, `prefs`는 반복 수정 주안점 집계, `find`/`list`/`show`. 스킬 주도, 결정론적 JSON.                                                                |
| `omw help`        | CLI        | 모든 명령을 라이프사이클 단계별로 정리해 표시 (`omw -h` / `--help` 동일)                                                                                                                                                                                                                       |
| `omw version`     | CLI        | 설치된 omw 버전 출력 (`omw -v` / `--version` 동일)                                                                                                                                                                                                                                             |
| `omw update`      | CLI        | 환경 감지 자가 업그레이드 (`--check` 점검만 / `--yes` 비대화형 / `--no-refresh`); 설정·볼트 미변경                                                                                                                                                                                             |
| `omw uninstall`   | CLI        | omw 호스트 통합 되돌리기: 관리형 블록 제거 · omw 훅 제거 · 스킬 번들 삭제(자동 감지). `--purge`는 ~/.omw config + 시크릿 + registry까지, `--vaults`는 볼트 콘텐츠 삭제(타이핑 확인), `--dry-run`은 미리보기. `--vaults` 없이는 볼트를 절대 삭제하지 않으며, `pip uninstall` 명령을 안내합니다. |
| `omw inbox`       | CLI        | URL 받은함 큐: `add` / `add-feed`(RSS/Atom 피드의 글 링크 일괄 큐잉) / `list` / `remove` / `run`(일괄 수집)                                                                                                                                                                                    |
| `omw context`     | CLI        | 인용 컨텍스트 검색 — 설정된 전략으로 후보를 찾고 각 히트 본문 + citations를 JSON으로 반환 (인용 환각 방지)                                                                                                                                                                                     |
| `omw list`        | CLI        | 패싯 페이지 목록(JSON): `--tag` / `--type` / `--status` / `--layer` / `--visibility` (LLM 없음)                                                                                                                                                                                                |
| `omw export`      | CLI        | vault 슬라이스를 자족 Markdown 폴더(또는 `--zip`) + `EXPORT_MANIFEST.md`로 내보내기; 볼트 밖에만 기록                                                                                                                                                                                          |
| `omw merge`       | CLI        | 두 유사 페이지를 하나로 통합 (frontmatter union + `## Merged from` 본문 + winner `aliases` + source tombstone); `.proposed.md` 스테이징 → `--apply`                                                                                                                                            |
| `omw next`        | CLI        | 다음 라이프사이클 액션 추천; `--after <op>`는 파이프라인 op 완료 후 상태가 승인한 다음 op을 반환(결정론적; 안전 기본값=중단)                                                                                                                                                                   |
| `omw recall`      | CLI        | 에이전트 훅 회상: `preamble` · `prompt` · `pretool` · `capture` · `sessions`; `sessions --dismiss <id>`는 임시 맥락을 숨기고 `omw setup recall --session-capture on/off`는 이후 캡처를 제어                                                                                                    |
| `omw candidates`  | CLI        | 완료 세션의 지식 제안 검토: `status` · `config` · `list` · `show` · `run` · `approve` · `dismiss`; staged 모드는 명시적 승인 전까지 파일을 쓰지 않음                                                                                                                                           |

추론 작업(`ingest`, `query`, `summary`, `synthesis`, `find`, `edit`, `autoresearch`,
persona)은 Claude / Codex / Gemini 세션이 필요합니다. 자연어로 말하거나, `/omw <op>`,
또는 아래의 명시적 `/omw-<op>` 슬래시 커맨드로 실행하세요. 파이프라인 op 완료 후 omw는
상태가 승인한 다음 단계를 **제안**하고(`omw next --after <op>`, 결정론적; 안전 기본값=중단)
진행 여부를 물어봅니다 — **자동 실행하지 않습니다.** 그 한 번의 제안을 넘어서는 멀티 스텝
오케스트레이션은 호스트 AI 에이전트(Claude Code / Codex / Gemini)가 담당합니다.

### 슬래시 커맨드

모든 procedure op과 모든 persona는 명시적 슬래시 커맨드로도 제공됩니다. 설치 시점에
op 레지스트리 + persona 로스터에서 자동 생성돼(새 op/persona가 생기면 자동 획득, 드리프트
0), `/omw <op>` 별칭도 그대로 유효합니다 — "어떤 op?" 단계를 건너뛰는 추가 바로가기입니다.

| Op 커맨드           | Persona 커맨드                             |
| ------------------- | ------------------------------------------ |
| `/omw-ingest`       | `/omw-librarian` (wiki-librarian)          |
| `/omw-query`        | `/omw-auditor` (wiki-auditor)              |
| `/omw-open`         | `/omw-curator`                             |
| `/omw-edit`         | `/omw-fact-checker`                        |
| `/omw-move`         | `/omw-consistency-checker`                 |
| `/omw-delete`       | `/omw-terminology-manager`                 |
| `/omw-autoresearch` | _(각각 `omw persona-run <role>` 디스패치)_ |
| `/omw-summary`      |                                            |
| `/omw-synthesis`    |                                            |

persona 슬래시 이름은 중복되는 선두 `wiki-`를 뗍니다(`/omw-librarian`, `/omw-auditor`);
persona role 이름(`wiki-librarian`)은 `omw persona-run`에서 그대로 씁니다.

**라이프사이클 체이닝.** 파이프라인 op 완료 후 스킬이 `omw next --after <op>`를 실행해
체인의 다음 단계를 제안합니다 — `search`/`fetch` → `ingest` → `summary` → `synthesis` →
`lint` → `review`, 그리고 `autoresearch` → `synthesis`. 다음 op은 결정론적으로 계산되며
(정적 successor를 볼트 상태로 걸러 불필요 단계 자동 제거 — 예: `synthesis`는 clusters가 있을
때만, `lint`는 lint 이슈가 있을 때만), 스킬은 호스트 도구로 **안전 기본값=중단**으로 물어보고
다음 op을 스스로 실행하지 않습니다.

### Frontmatter 규약

**필수 필드** (`meta`를 제외한 모든 페이지 타입):

```yaml
title: "Page Title"
date: "2026-06-01"
type: concept # one of the 13 schema types
tags: [method, wiki]
```

**선택적 필드**:

```yaml
confidence: high # high | medium | low (drives review interval)
status: draft # draft | inbox | processed | raw | superseded | meta
superseded_by: llm-wiki # slug of the replacement page (when status: superseded)
review:
  last: "2026-06-01"
  due: "2026-08-30"
  interval_days: 90
aliases:
  - Karpathy LLM Wiki
  - LLM wiki method
```

**인라인 필드** (본문에서, Dataview 문법):

```
owner:: dante
status:: draft
uses:: [[llm-wiki]]
contradicts:: [[old-method]]
```

### Persona 목록

| Persona                 | 슬래시 커맨드              | 호출 문구                     | 출력                           |
| ----------------------- | -------------------------- | ----------------------------- | ------------------------------ |
| **Wiki-librarian**      | `/omw-librarian`           | "open my wiki", "ingest this" | ingest / 정리 요청 라우팅      |
| **Wiki-auditor**        | `/omw-auditor`             | "위키 점검", "뭐가 문제"      | "무엇이 아픈지" 진단 (세션 내) |
| **Curator**             | `/omw-curator`             | "curate my wiki"              | 유지 관리 제안 (세션 내)       |
| **Fact-checker**        | `/omw-fact-checker`        | "fact-check this"             | `<page>.factcheck.md`          |
| **Consistency-checker** | `/omw-consistency-checker` | "check for contradictions"    | JSON 리포트 (세션 내)          |
| **Terminology-manager** | `/omw-terminology-manager` | "build a glossary"            | `glossary.db`                  |

각 슬래시 커맨드는 `omw persona-run <role>`을 디스패치합니다(role 이름은 전체 형태 —
예: `wiki-librarian`; 슬래시에서만 중복 `wiki-`를 뗌).

### 스키마 위치

- **내장 스키마**: 패키지 루트의 `schemas/<type>.yml` — 13개 타입.
- **vault별 오버라이드**: `<vault>/schemas/<type>.yml` — 해당 vault에서 내장 스키마보다 우선.

`omw schema show <type>`은 활성 오버라이드가 있으면 항상 이를 반영합니다.

### `OMW_HOME`

oh-my-wiki는 레지스트리를 `$OMW_HOME/registry.db`에 저장합니다 (기본값:
`~/.omw/registry.db`). 환경 변수로 오버라이드할 수 있습니다:

```bash
export OMW_HOME=/path/to/isolated/.omw
omw status
```

테스트, CI, 또는 메인 레지스트리에 영향을 주지 않고 완전히 분리된 wiki 환경을 운영할 때
유용합니다.

---

## Part 6 — FAQ와 문제 해결

### Q. `omw doctor`가 레지스트리가 없다고 합니다

새로 설치한 직후 `omw setup`을 실행하기 전에는 정상입니다. 다음을 실행하세요:

```
omw setup
```

마법사가 레지스트리와 첫 번째 vault를 생성합니다. 그 후 `omw doctor`는 `ok`를 보고합니다.

### Q. `omw status`가 `needs: "setup"` 대신 `needs: "migrate"`를 표시합니다

`needs: "migrate"`는 `omw status`가 스킬 디렉토리(또는 `<cwd>/data/registry.db`)에서
레거시 `data/registry.db` 파일을 감지했을 때 나타납니다. `data/registry.db`가
디스크에 존재하는 **소스 트리 체크아웃**에서 발생합니다.

Skills CLI, 마켓플레이스, PyPI(`pip`/`pipx`), 또는 `bin/install.sh`로 설치한 실제
사용자는 새 머신에서 `needs: "setup"`을 봅니다. `data/`는 .gitignore 처리되어 배포
패키지에 포함되지 않기 때문입니다.

> **참고:** `OMW_HOME` 오버라이드(예: `export OMW_HOME=$(mktemp -d)/.omw`)는 소스 트리에서
> 실행할 때 깨끗한 사용자 환경을 시뮬레이션하지 **않습니다**. 레거시 감지는 `OMW_HOME`과
> 독립적으로 `<skill_dir>/data/registry.db`를 스캔하므로, 소스 트리에서는 mktemp 방법으로도
> `needs: "migrate"`가 반환됩니다.

두 경우 모두 해결 방법은 `omw setup`입니다. 마법사가 레지스트리를 마이그레이션하거나
초기화합니다.

### Q. oh-my-wiki가 세션에서 자동으로 트리거되지 않습니다

명시적 트리거 문구를 사용하세요:

- 영어: "open my wiki", "ingest this", "what does my wiki say about X", "omw", "/omw"
- 한국어: "위키 열어줘", "이거 정리해줘", "위키에 물어봐", "오엠더블유"

또는 다음과 같이 말하세요: `use the oh-my-wiki skill`.

### Q. `omw search`에서 오류가 발생하거나 provider가 설정되지 않았습니다

`omw search`는 **웹 검색** 커맨드로, 외부 검색 provider(brave, tavily, exa, firecrawl,
또는 brightdata)를 쿼리합니다. vault를 검색하는 것이 아닙니다. provider가 설정되지
않은 경우 다음과 같이 표시됩니다:

```
error: no search provider configured — run `omw setup search`
```

`omw setup search`를 실행하고 provider 자격 증명을 입력하면 해결됩니다.

### Q. vault FTS5를 사용할 수 없거나 세션 내 쿼리 결과가 없습니다

vault 인덱스는 내부적으로 SQLite FTS5(BM25)를 사용합니다. FTS5를 사용할 수 없을 때
oh-my-wiki는 토큰 스코어 기반으로 자동 폴백합니다. 대부분의 최신 Python sqlite3 빌드는
FTS5를 포함합니다. 확인 방법:

```bash
python3 -c "import sqlite3; c = sqlite3.connect(':memory:'); c.execute('CREATE VIRTUAL TABLE t USING fts5(body)'); print('FTS5 ok')"
```

오류가 발생하면 sqlite3 빌드에 FTS5가 없는 것입니다. 완전한 기능의 빌드를 설치하세요:

```bash
# macOS with Homebrew
brew install sqlite
```

폴백 토큰 스코어도 여전히 작동합니다. 결과를 잃지 않고 BM25 순위 정밀도만 낮아집니다.

### Q. 두 개의 분리된 wiki를 운영하려면 어떻게 하나요?

각 환경이 자체 레지스트리를 가리키도록 `OMW_HOME`을 사용하세요:

```bash
export OMW_HOME=~/work/.omw   omw vault create work-notes --mode wiki
export OMW_HOME=~/personal/.omw   omw vault create journal --mode wiki
```

각 `OMW_HOME`은 자체 `registry.db`와 `vaults/`를 가집니다. vault 자체는 어디에든 있을 수
있으며, 레지스트리는 경로만 기록합니다.

### Q. 어떤 vault 모드가 있나요?

`omw setup vault`(및 `omw vault create --mode`)에서 다음을 선택할 수 있습니다:

- **memo** — 빠른 캡처를 위한 평탄한 `inbox/`
- **wiki** — Karpathy 3계층 (`raw/` + `wiki/{summaries,entities,concepts,comparisons,syntheses}/`)
- **personal** — `journal/ goals/ people/ health/`
- **book** — `chapters/ characters/ worldbuilding/ outlines/ drafts/`
- **business** — `meetings/ decisions/ clients/ vendors/ processes/`
- **github-codebase** — `modules/ apis/ decisions/ runbooks/ glossary/`
- **website** — `pages/ posts/ assets/ seo/ outlines/`

모든 모드에는 소프트 삭제를 위한 `.trash/`와 `index.md`(wiki 모드에는 `wiki/log.md`도)가
함께 생성됩니다.

### Q. Windows·NAS·Hermes에서는 무엇을 확인해야 하나요?

- WSL에서 Windows 쪽 vault를 쓸 때는 필요하면 `/mnt/c/Users/...` 절대 경로를 지정합니다.
- CP949·UTF-16로 저장된 기존 Markdown도 재색인할 수 있습니다.
- macOS SMB가 `.trash`를 막으면 `OMW_HOME/.trash/<vault>/`를 자동으로 사용합니다.
- Hermes 홈을 바꿨다면 `HERMES_HOME`을 먼저 설정한 뒤 `omw setup personas/recall`을 실행합니다.
- 실제 설치·vault·휴지통 경로는 `omw doctor`와 `omw vault info <name>`으로 확인합니다.

### Q. 위키를 중복 없이 안전하게 유지하는 순서는 무엇인가요?

`omw report` → `omw lint` → `omw next`로 필요한 일을 고르고, 수정 후
`omw reindex --full` → `omw report`로 다시 확인합니다. `inbox run`은 같은
`source_url`의 raw 문서를 재사용하며, E5 임베딩 모델의 `query:`·`passage:` 형식은
OMW가 내부에서 자동 처리합니다.

### Q. Codex CLI에서의 oh-my-wiki는 Claude Code와 어떻게 다른가요?

동일합니다. SKILL.md는 호스트에 무관합니다. 동일한 트리거 문구, 동일한 라우팅 로직,
동일한 커맨드가 스킬을 발견하는 모든 AI 코딩 에이전트에서 작동합니다. Codex는 때때로
자동 트리거가 더 보수적입니다. 트리거 문구로 스킬이 실행되지 않으면
"use the oh-my-wiki skill"이라고 명시적으로 말해 호출하세요.

### Q. autoresearch는 어떻게 작동하나요?

`autoresearch <질문>`은 최대 3라운드(설정 가능; 하드 상한 5)를 실행합니다: 질문을 주장
단위로 분해하고, `omw search`로 검색(Bright Data MCP는 선택적 폴백)한 뒤, 유용한 출처를
`omw fetch`로 `raw/`에 모으고, confidence와 공백을 기록한 다음 **결과를 raw에 둘지
synthesis로 만들지** 묻습니다(`wiki/syntheses/<slug>.md`).

`--no-synthesis`를 붙이면 자료를 `raw/`에 모으는 데서 멈춥니다. 종합 페이지는 만들지
않습니다. 그래프와 연결점을 본 뒤 나중에 synthesis를 만들고 싶을 때 이 모드를 씁니다.
어느 쪽이든 전체 세션 — 라운드별 주장, 정규화된 출처(각 `raw_relpath` 포함), 공백 — 은
감사 및 재실행을 위해 `<vault>/.oh-my-wiki/sessions/<ts>-<slug>/` 아래에 보존됩니다.

### Q. vault import를 되돌리려면 어떻게 하나요?

`omw import`(및 이전의 `vault-import-memo` 흐름)는 항상 작성 전에 사전 이미지를
`.trash/<ts>-pre-import-*.md`에 백업합니다. 단일 파일 복원:

```bash
cp ~/.omw/vaults/legacy/.trash/20260601-pre-import-meeting-notes.md \
   ~/.omw/vaults/legacy/meeting-notes.md
```

전체 배치를 되돌리려면 동일한 타임스탬프 접두사를 가진 모든 백업 파일을 한꺼번에
복원하세요.

### Q. 세션 임시 맥락은 어떻게 이어지나요?

Claude Code와 Codex에서는 `PreCompact`와 `Stop`이 마지막 요청·결과·다룬 파일을 로컬
`~/.omw/registry.db`에 임시 저장합니다. 이후 `SessionStart` 또는 명시적인 재개 요청에서
같은 프로젝트의 최신 대기 캡처 하나만 불러옵니다.

- 저장 전에 일반적인 비밀값 패턴을 가립니다.
- 불러온 문장은 실행할 지시가 아닌, 이스케이프된 신뢰할 수 없는 JSON 데이터로 구분합니다.
- 텍스트와 transcript 읽기 크기를 제한하고 프로젝트당 최대 5개를 30일 보관합니다.
- 캡처는 위키 페이지로 자동 승격되지 않습니다.
- `omw recall sessions`로 확인하고, `--dismiss <id>`로 다음 회상에서 숨기며,
  `omw setup recall --session-capture off`로 이후 캡처를 끕니다.
- 지식 후보 승격은 별도 설정이며 기본값은 `off`입니다. `--knowledge-candidates staged`로
  켠 뒤 `omw candidates list/show`로 검토하고 `approve` 또는 `dismiss`를 명시적으로
  실행합니다. 대기 후보는 30일 뒤 만료되며, `omw candidates status`는 원문을 드러내지
  않고 유지·폐기 이유의 개수만 보여 줍니다.

예전 `hot.md` 유틸리티는 현재 네이티브 세션 연속성 경로가 아니며 `omw setup recall`이
자동 배선하지 않습니다.

---

## 더 알아보기

- **커맨드 레퍼런스**: `commands/*.md`는 모든 작업을 다룹니다.
- **명령 인터페이스**: `omw help`와 `omw <command> --help`를 사용하세요. `scripts/*.py`는 내부 구현이며 사용자 인터페이스가 아닙니다.
- **설계 문서**: `docs/superpowers/specs/` (로컬 전용, 미공개 — 기여자용).
- **테스트**: `pytest -v`로 전체 테스트 스위트를 실행합니다.

이슈 트래커: https://github.com/dandacompany/oh-my-wiki/issues
