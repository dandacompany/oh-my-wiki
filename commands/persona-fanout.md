# persona-fanout

Run one persona over many pages by fanning out parallel `omw persona-run`
dispatches. The deterministic resolver picks the pages and prints the exact
commands; you (the host) run them in parallel and collect the results.

## When to invoke

User says: "fact-check every entity page", "run X on all draft pages",
"여러 페이지에 페르소나 돌려줘", "배치로 팩트체크".

## Procedure

1. Resolve the page list + commands (deterministic, no side effects):

   ```bash
   omw persona-fanout <role> --pages a.md,b.md        # explicit
   omw persona-fanout <role> --type entity            # or a facet
   omw persona-fanout <role> --tag draft --backend codex
   ```

   It prints `{role, backend, count, pages, commands}`. `count: 0` means nothing
   matched — stop and tell the user.

2. Dispatch every string in `commands` **in parallel** (each is an isolated
   one-shot `omw persona-run`). Only source-driven roles are accepted; vault-wide
   roles (consistency-checker, curator) are rejected by the resolver.

3. Collect each page's outcome — filed report (read-only roles) or staged
   `.proposed.md` (propose roles) — into one summary ordered by page. Apply
   nothing automatically; `propose` outputs stay staged until the user runs
   `omw persona-run <role> --apply <proposal>`.
