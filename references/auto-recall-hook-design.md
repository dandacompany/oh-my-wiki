# 설계 제안: omw 자동 위키 recall 훅 (auto-recall)

> 상태: **구현 완료** (엔진 + Tier1 + Tier2 호스트 네이티브 훅 배선 + 매니페스트). 2026-06-18.
> 구현: `scripts/recall.py`(`omw recall preamble|prompt`, stdin JSON 프롬프트 추출, `wire_host`), `omw setup recall`(Tier1 가이드 주입 + `recall.mode` + Tier2 훅 배선), `hooks/hooks.json`의 `user_prompt_submit`.
> **세 호스트 모두 동일한 훅 스키마**(`{"hooks": {<Event>: [{"hooks":[{"type":"command","command":...}]}]}}`)를 씀:
>
> - Claude Code → `~/.claude/settings.json`
> - Codex → `~/.codex/hooks.json`
> - Gemini CLI → `~/.gemini/settings.json`
>   `wire_host`가 `SessionStart`(→`omw recall preamble`)+`UserPromptSubmit`(→`omw recall prompt`)를 멱등 병합(기존 보존, `.omw-bak` 백업). UserPromptSubmit는 stdin JSON에서 프롬프트 필드를 추출한다.
>   교차호스트 검증 결과: 기존 `hooks/hooks.json`은 어느 호스트에도 자동 배선돼 있지 않았다(plugin.json hooks 필드 없음) — 즉 "Claude 전용"이 아니라 "미배선". recall은 호스트 중립 엔진 + 호스트별 번역으로 설계.
>   목표: 에이전트(Claude Code / Codex)가 **스스로 omw 위키를 검색·활용**하도록 만든다.
>   트리거 의도: (a) 새/모르는 세션 시작, (b) 사용자가 과거 맥락을 요청, (c) 에이전트가 "정보가 부족하다"고 자가 판단할 때.

---

## 1. 배경 — 지금 있는 것과 없는 것

**이미 있음 (활용):**

- `hooks/hooks.json` → `session_start`/`session_stop` 훅이 `scripts.hot_cache`를 호출.
  - `session_start`: `wiki/hot.md`(최근 페이지+직전 세션 요약)를 preamble로 주입.
  - `session_stop`: 레지스트리 + 세션 요약으로 `wiki/hot.md` 갱신.
    → **세션 단위 부트스트랩**은 mem0의 SessionStart 패턴과 동형으로 이미 존재.

**없음 (이번 설계 대상):**

1. **프롬프트 단위 recall** — 사용자가 질문할 때마다 위키를 참조할지 결정/주입하는 단계 (mem0의 `UserPromptSubmit` 훅에 해당).
2. **자가 판단 트리거** — "내가 이 도메인/프로젝트 사실을 모른다" → 위키 먼저 검색.

## 2. mem0 레퍼런스 (이 세션에서 실제 관측한 패턴)

- **SessionStart 훅**: "무엇이든 하기 전에 `search_memories`로 관련 맥락을 먼저 로드하라"는 *지시문*을 주입.
- **UserPromptSubmit 훅**: 매 프롬프트에 *결정 가이드*를 주입 —
  - `Search WHEN`(과거 작업 언급 / "어떻게 하지" 질문 / 에러·디버깅 / 스택·툴 관련 / 알려진 프로젝트의 비자명 작업)
  - `Skip WHEN`(단순 확인·연속 / 사용자가 새 정보를 _진술_ / 일반지식 질문 / 이미 검색함)
  - 쿼리 작성 팁(명사구, 2~4개 병렬, 필터 형태).
- 핵심 철학: **훅은 검색을 강제하지 않고, "언제·어떻게 검색할지" 판단을 에이전트에게 위임**. (단, mem0는 검색을 에이전트가 직접 실행)

omw는 결정적 FTS(`scripts.search_index.query`)와 `omw serve`(retrieve-only HTTP)를 이미 갖고 있어, **훅이 직접 검색해 결과를 주입**하는 더 강한 옵션도 가능하다.

## 3. 제안 — 2-tier recall

### Tier 1 — Advisory(지시 주입, mem0식)

프롬프트 단위로 **결정 가이드 텍스트**만 주입. 에이전트가 필요시 `omw find`/FTS를 직접 실행.

- 장점: 노이즈 0, 토큰 적음, 오탐 없음.
- 단점: 에이전트가 게으르면 안 부를 수 있음.

### Tier 2 — Auto-retrieve(결정적 주입, RAG식)

훅이 **직접 `omw find`(FTS)** 를 프롬프트에 대해 실행하고, 상위 히트가 임계 이상이면
`<omw-recall>` 블록으로 **제목·경로·스니펫·confidence**를 주입.

- 장점: 에이전트가 안 불러도 근거가 들어옴, 자가판단 불필요.
- 단점: 무관한 프롬프트에 노이즈 → **게이트 필수**.

### 권고: 하이브리드 (기본 `auto`, 보수적 게이트 + Tier1 가이드 병행)

- Tier2를 보수적 임계로 켜고, 임계 미달이면 Tier1 가이드만 남긴다.

## 4. 게이트 휴리스틱 (Tier2 오탐 방지)

주입 조건(모두 충족 시):

1. 프롬프트 길이 ≥ 12자 & 단순 확인("ok","고마워","계속")이 아님.
2. 활성 볼트 존재 & wiki/memo 노트 ≥ 1.
3. FTS 상위 점수 ≥ `recall.min_score`(기본 2.0).
4. 주입은 top‑`recall.top_k`(기본 3), 스니펫 ≤ 280자, **세션 내 동일 페이지 재주입 금지**(de-dup).

## 5. 구현 스케치

### 새 스크립트 `scripts/recall.py`

```
omw recall preamble                # SessionStart: hot.md + 볼트 토픽 인덱스 요약
omw recall prompt [--text T]       # UserPromptSubmit: stdin/T로 받은 프롬프트에 대해
                                   #   Tier2 히트 → <omw-recall> 주입 / 없으면 Tier1 가이드
                                   #   stdout = 주입할 컨텍스트(없으면 빈 출력=조용히 패스)
```

- 출력은 **호스트 훅 규약**에 맞춘다(아래 6절). 실패/무볼트/저점수는 **조용히 빈 출력**(절대 블로킹 X).

### config (`~/.omw/config.yaml`)

```yaml
recall:
  mode: auto # off | advisory | auto
  min_score: 2.0
  top_k: 3
  snippet_chars: 280
```

## 6. 호스트 배선(wiring)

| 호스트        | 세션 부트스트랩                           | 프롬프트 단위                                                                             | 비고                                 |
| ------------- | ----------------------------------------- | ----------------------------------------------------------------------------------------- | ------------------------------------ |
| Claude Code   | plugin `hooks.json` `session_start`(기존) | `.claude/settings.json` 의 `UserPromptSubmit` 훅 → `omw recall prompt`                    | 가장 강한 Tier2 가능                 |
| Codex         | 작업폴더 codex가 AGENTS.md 읽음           | **AGENTS.md 관리 블록**(persona처럼) 에 Tier1 가이드 주입 + 선택적 `omw recall prompt` 훅 | codex의 per-prompt 훅 표면 확인 필요 |
| Gemini/Hermes | 동일 패턴                                 | 동일                                                                                      | —                                    |

> codex는 per-prompt 훅이 제한적일 수 있으므로, **Tier1을 AGENTS.md 관리 블록으로** 넣는 게 1차(= `omw setup personas`가 AGENTS.md를 쓰는 것과 동일 메커니즘 재사용). Claude Code는 settings.json `UserPromptSubmit`로 Tier2까지.

### "정보 부족 자가판단" 처리

훅이 탐지 불가 → **Tier1 가이드로 위임**. omw용 WHEN/SKIP 표(예시):

- Search WHEN: 프로젝트/도메인 사실 질문, "예전에 정리한", "위키에 있던", 비자명한 의사결정.
- Skip WHEN: 일반 문법/상식, 단순 확인, 사용자가 새 사실을 진술(=오히려 `ingest` 후보).

## 7. mem0와의 차이/시너지

- mem0 = **개인/세션 기억**(휘발적 맥락), omw = **출처·confidence 박힌 지식자산**(영구·감사가능).
- 둘은 경쟁 아님: recall 훅이 **둘 다** 조회하도록 가이드 가능(mem0=내가 한 일, omw=검증된 지식).

## 8. 열린 질문 (승인 시 결정)

1. 기본 모드: `auto`(Tier2 보수적) vs `advisory`(Tier1만)?
2. Tier2 주입을 Claude Code에만? codex는 Tier1(AGENTS.md)만으로 시작?
3. `omw recall prompt`가 mem0처럼 **여러 각도 병렬 쿼리**까지 생성할지, 단일 FTS로 시작할지.
4. de-dup 상태 저장 위치(세션 파일 vs hot.md 메타).

## 9. 다음 액션(승인 후)

- [ ] `scripts/recall.py`(preamble/prompt) + 게이트 + config + 테스트(빈볼트/저점수/주입/ dedup).
- [ ] `hooks/hooks.json`에 `user_prompt_submit` 엔트리 추가(있는 호스트).
- [ ] `omw setup recall` 섹션(모드 선택) + `omw setup agents`가 AGENTS.md에 recall 가이드 블록 주입.
- [ ] 문서: SKILL.md / README에 recall 동작 설명.

---

## 10. 설정 가능한 검색 전략 (계획 — 2026-06-18 합의, 미구현)

> 동기: josa 같은 손코딩은 "LLM 없이 결정론으로 검색"하기 때문에 필요하다. 품질을
> 올리는 길은 regex를 더 늘리는 게 아니라 **임베딩** 또는 **LLM**이다. 단, 무엇이
> 옳은지 확신이 없으므로 **모두 구현해 사용자가 모드를 고르게** 한다. 아래는 그
> 설정 구조의 합의안(네이밍 확정). 엔진 구현은 후속.

### 두 개의 독립 축

혼동을 줄이기 위해 **언제 개입(trigger)** 과 **어떻게 검색(strategy)** 을 분리한다.

**축 1 — `mode` (trigger, 기존):** `off` | `advisory`(훅은 넛지, 인루프 LLM이 검색) | `auto`(훅이 미리 긁어 주입)

**축 2 — `strategy` (검색 방법, 신규):**

| 값          | 종류   | 설명                                                                    |
| ----------- | ------ | ----------------------------------------------------------------------- |
| `fts`       | 결정론 | 키워드 가중 랭커(현행) + josa 정규화. 싸고 오프라인. **현재 구현됨**    |
| `embedding` | 결정론 | 의미 벡터 검색. josa/복합어/동의어를 규칙 없이 처리. (인덱서+벡터 필요) |
| `hybrid`    | 결정론 | `fts` + `embedding` 랭크 융합                                           |
| `llm`       | LLM    | LLM 주도. 하위 모드 `llm.submode`로 분기                                |

**`llm.submode` (strategy=llm일 때만):**

- `route` — **LLM이 상황을 보고 `fts`/`embedding`/`hybrid` 중 무엇을 적용할지 판단**해 그 결정론 백엔드를 호출(라우터).
- `generative` — **LLM이 생성형으로 직접 후보를 읽고 관련성을 판단·처리**(가장 강력, 가장 비쌈).

### 설정 스키마 (backward compatible — 기존 `mode` 유지, `strategy` 추가)

```yaml
recall:
  mode: auto # off | advisory | auto        (언제)
  strategy: fts # fts | embedding | hybrid | llm (어떻게)
  llm:
    submode: route # route | generative           (strategy=llm일 때만)
  min_score: 1.0 # fts/embedding 임계
  top_k: 3
```

### 두 축의 상호작용 (비용 가드)

`strategy=llm` × `mode=auto` = **프롬프트마다 별도 LLM 호출**(비쌈/느림). 반대로
`mode=advisory`면 이미 도는 에이전트가 곧 그 LLM이라 **추가 비용 0**. 권장 짝:

| mode       | 권장 strategy                  | 이유                                    |
| ---------- | ------------------------------ | --------------------------------------- |
| `auto`     | `fts` / `embedding` / `hybrid` | 결정론, 매 프롬프트 호출해도 쌈         |
| `advisory` | `llm`(route/generative)        | 인루프 에이전트가 수행 → 추가 비용 없음 |

→ `omw setup recall`에서 두 축을 고르게 하고, **비싼 조합(auto+llm) 선택 시 경고**만 띄운다(차단하지 않음 — 사용자 자유).

### 구현 로드맵 (확정 후)

- [x] config 2축 분리: `recall.strategy`(+`llm.submode`) 추가, 기본 `fts`(현행 동작 보존), 미구현 전략은 `fts`로 graceful fallback + "planned" 안내.
- [x] `embedding` 백엔드: 임베딩 인덱서(볼트 내부 저장) + 벡터 검색. 모델 의존성 선택형.
- [x] `hybrid` 랭크 융합(RRF 등).
- [ ] `llm.route`(분류 1콜) / `llm.generative`(후보 read+판정). ← 미래 작업 (future work)
- [x] `omw setup recall`에 strategy/submode 선택 + 비용 가드 경고. (`configure_recall()` 프로그래매틱 진입점 구현 완료)
- [ ] josa 정규화는 `fts` 전략 내부 옵션으로 흡수(`embedding`/`llm`은 불필요).
