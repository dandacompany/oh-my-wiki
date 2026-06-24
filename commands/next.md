# next

After completing a unit of work (collected sources, built entities/concepts, drafted
a synthesis, ran lint, etc.), propose the most fitting next action instead of stopping
at a summary.

## Procedure

1. Run `omw next` (read-only; it ranks the next steps from the vault's lifecycle
   state — raw vs structured vs synthesized counts, lint/stale debt, research markers,
   graph clusters).
2. Propose the top suggestion to the user, offering **now (foreground)**,
   **background**, or **later**. Show the suggested `omw` command(s).
3. On accept, run the suggested op(s). Every content change stays a proposal the user
   confirms — never write silently. For "structure"/"synthesize" use the omw skill
   procedure; for "maintain"/"review" run `omw lint` / `omw review audit`; for
   "collect" scout with `omw search` then `omw fetch`; for "recall" run `omw find`.
4. If the user declines, stop — do not nag (the `omw gate` turn-end backstop handles
   maintenance reminders separately).

## When to invoke

- after any `ingest` / `autoresearch` / synthesis / structuring task
- when the user asks "what's next?", "다음은?", "이제 뭐 하지?"
