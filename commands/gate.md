# /omw gate — run the maintenance/capture cycle

Triggered when the user accepts the maintenance gate. Steps:

1. Read the pending parts from the latest `<omw-gate>` block.
2. For **capture**: propose ingesting this session's research/synthesis
   (`omw ingest` / autoresearch). Show the proposed pages; apply on confirm.
3. For **reindex**: run `omw reindex` then `omw connections` (read-only) and
   summarize new/changed clusters and bridges.
4. For **upkeep**: run `omw lint` and `omw review audit`; propose fixes /
   supersessions; apply only what the user confirms.
5. For **recall**: surface the recalled-but-stale pages and offer a
   consistency/librarian pass (proposals only).

Foreground does these inline. Background hands the same checklist to
dispatch the persona upkeep subagent (Workstream D), which prepares proposals without applying writes.
If the user says "later" (or declines), take no action — the gate snoozes
itself and will re-surface after the next cooldown period.
Never mutate vault content without explicit user confirmation.
