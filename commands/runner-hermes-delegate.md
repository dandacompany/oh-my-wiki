<!-- commands/runner-hermes-delegate.md -->

# runner: hermes-delegate (single persona-run via delegate_task)

**Kind:** procedure. omw cannot call Hermes' `delegate_task` tool itself —
only the Hermes host agent can. So omw prints this card; YOU (the Hermes host)
execute it.

**When:** `omw persona-run <role> --runner hermes-delegate` inside a Hermes session,
for a single lightweight run. This path has **no durable board and no Blocked
review gate** — if you need the user-confirmation gate, use
`--runner hermes-kanban` instead.

## Steps

1. Build the persona spec + deterministic input the same way omw would, by
   reading the persona and gathering its input. The simplest path: run
   `omw persona-run <role> --runner host` would dispatch via omw's own backend;
   for the delegate path instead gather the two pieces and hand them to
   `delegate_task`.
2. Call your `delegate_task` tool:
   - `goal`: the persona's system-prompt body (its role + protocol).
   - `context`: the deterministic input (the page content / lint / drift report)
     plus "stage any change as a `.proposed.md` sidecar; never edit a vault page
     in place; summarize proposals back to me."
   - `toolsets`: restrict to what the role needs (read-only for analysis roles).
   - `model`: optional; omit to inherit this profile's default.
3. When the child returns its summary, relay it to the user. Apply any staged
   `.proposed.md` only on the user's explicit confirmation (`omw … --apply …`).
   Destructive ops (merge/supersede/delete/overwrite) require explicit approval.
