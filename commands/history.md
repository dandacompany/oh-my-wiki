# omw history — when to log and when to consult

`omw history` is the request/interaction history (per vault). It is **skill-driven**:
the CLI writes/reads deterministically; you decide when to call it.

## Log after a unit of work

When you finish a substantive request (a research pull, a generated artifact, a
multi-step edit/fix), record it:

    omw history log --type <research|query|generate|edit|fix|ingest|other> \
      --request "<one-line: what the user asked>" \
      --summary "<one-line: what you did>" \
      --ref <wiki/entities/...> --ref <wiki/concepts/...> --tag <tag>

`--ref` links the related entity/concept/synthesis pages. Skip trivial
conversational turns — log work, not chatter.

## Log a revision (this powers `prefs`)

If the user asks to revise or regenerate a prior answer, log a new row that points
back at the original and names what they wanted changed:

    omw history log --type edit --request "<the revise ask>" \
      --outcome revised --revises <id-of-original> \
      --focus "<exactly what the user asked to change — tone, length, citations…>"

Use `--outcome regenerated` if they asked for a full redo. The `--focus` text is
what `omw history prefs` aggregates into the user's recurring preferences.

## Consult before handling a substantive or repeat-style request

- `omw history similar "<the request>"` — surface similar past requests + their
  outcomes/refs, to reuse prior groundwork.
- `omw history prefs` — the user's recurring revision focus; apply it pre-emptively
  so the first draft already matches their known preferences.

Cite history as grounding when you use it; it is not auto-injected.
