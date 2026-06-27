---
name: omw-kanban-worker
description: Run an omw persona as a Hermes kanban worker — read the card body as your persona spec, do read-only or proposal work via the omw CLI, stage proposals as sidecars, and terminate the run with kanban_complete or a review-required kanban_block.
---

# omw kanban worker

You were spawned by the Hermes kanban dispatcher to execute ONE omw persona card.
The card `body` is your instruction. Follow this contract exactly.

## 1. Read your assignment

The card body has two parts:

- **Persona spec** — treat it as your system prompt (your role, protocol, output kind).
- **Deterministic input** — the data omw already gathered (lint/drift report, or a page's content). If the input says to fetch fresh data, run the named `omw` command.

## 2. Do the work through the omw CLI

- Use `omw <op>` for everything (`omw find`, `omw context`, `omw lint`, `omw fields`, …).
- You are operating on the active omw vault. **Never edit a vault page in place.**

## 3. Stage changes as proposals (omw invariant: propose → confirm → execute)

- Any change you want to make is written as a `.proposed.md` sidecar next to its
  target — never onto the target itself. (omw's persona ops + `--apply` already
  follow this; do the same.)
- Put every audit-relevant field (which pages, proposal paths, your reasoning,
  decisions) into a `kanban_comment` FIRST — `kanban_block` only carries a short reason.

## 4. Terminate the run with exactly one tool call

- **`kanban_complete(summary=…, metadata=…)`** — for terminal read-only outputs
  (a report, a glossary write to omw's own db, a research writeup) where nothing
  in the vault needs a human's yes.
- **`kanban_block(reason="review-required: <what to review>")`** — whenever you
  staged a `.proposed.md` (or anything needs the user's judgment). The user reviews
  on the board and `kanban_unblock`s to approve.

## 5. On respawn after unblock

- Read the comment thread. If the user approved, apply the staged proposal with the
  matching omw command (e.g. `omw <op> --apply <proposal>` / `omw merge --apply …`)
  and then `kanban_complete`. If not approved, `kanban_block` again with what's missing.

## 6. Destructive ops are ALWAYS review-gated

Operations that consolidate or remove knowledge — **merge**, **supersede**,
**delete**, or overwriting an existing page — must ALWAYS `kanban_block` with
`review-required` and must NEVER be auto-applied, even under a session "auto" mode.
The non-destructive branch is the default; the user must explicitly approve.
