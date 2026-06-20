# omw menu — interactive entry point

When the user opens omw without a specific verb (e.g. says "omw", "위키 열어줘",
"오마이위키 뭐 할까"), present a menu with the AskUserQuestion tool instead of guessing.

Use a single AskUserQuestion question, header "omw", options:

- **지식 추가 (ingest)** — follow commands/ingest.md
- **질문 (query)** — follow commands/query.md
- **건강검진 (lint)** — follow commands/lint.md
- **노후 정리 (review audit)** — run `omw review audit`, then offer the stale list as a
  multiSelect AskUserQuestion so the user picks pages to refresh/supersede

After the maintenance preamble shows a `유지보수:` nudge, proactively offer the
"노후 정리" path. For the stale-list selection, set `multiSelect: true` and map each
selected page to `omw review done <relpath> --grade ...` or `omw supersede`.
