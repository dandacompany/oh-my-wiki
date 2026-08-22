# `distill` — write a new distilled page from this session

**Mode:** wiki (active vault must be wiki-mode)
**Underlying ops:** `omw find` · `omw page write` · `omw links suggest` · `omw reindex` · `omw lint`

Counterpart of `ingest`. Use `ingest` when there is an **external source to capture**
(a file, a URL, pasted long-form text) — it saves the original to `raw/` first. Use
`distill` when the material is **what happened in this session** (a design discussion,
a debugging conclusion, an execution record you already filed) and the page you are
about to write is the distillation, not the source.

Never write a wiki file with the host's file tools instead of this procedure — doing so
skips provenance, the new-vs-update choice, link suggestions, and reindexing.

## Preconditions

Call `omw status` first. Refuse if `active.mode != "wiki"`; suggest `omw vault use <wiki-vault>`.

If `confirm_target` is `true` (2+ vaults registered), confirm the destination vault before
writing — unless it was already confirmed in this session (see SKILL.md Multi-vault write guard).

## Flow

1. **Check for an existing page first.** Run `omw find "<key nouns>"`. If a page already
   covers this material, this is an `edit`, not a `distill` — surface the `new-vs-update`
   structured choice (safe default: **Propose as new**) and follow the user's pick.

2. **Decide the layer.** `concepts` for an idea or technique, `entities` for a person /
   org / product / paper, `summaries` for a condensation of one source. When the layer is
   ambiguous, ask with the `page-type` decision class (safe default: `note`).

3. **Find the provenance.** If a `raw/` file records the session this page comes from
   (an execution record, a captured transcript, a fetched source), that relpath is the
   page's `source_raw`. Run `omw find` over `raw/` to locate it. If genuinely nothing was
   captured, say so explicitly in the proposal rather than leaving the field empty
   silently — a distilled page with no traceable origin is a known wiki-structure defect.

4. **Draft the body.** Standalone prose grounded in the session's actual material. Do NOT
   invent facts. Prefer the precise relation verbs in `relations:` — `derived-from`,
   `extends`, `illustrates`, `applies-to`, `instances-of`, `see-also`.

5. **Propose, then confirm** (never write silently). Show the title, layer, tags,
   `source_raw`, and the draft body. Ask: "Write this page? [Yes / No]".

6. **On Yes, write it:**

   ```bash
   omw page write --layer <concepts|entities|summaries> --title "<title>" \
     --body-file <body.md> --tags <t1>,<t2> --date <YYYY-MM-DD> \
     --source-raw <raw-relpath> --index "<oneliner>" --log-op distill
   ```

   `omw page write` updates the index section, appends the log entry, and reindexes.

7. **Propose entity links.** Run `omw links suggest` and show the `[[slug]]` insertions for
   the page just written and any prior page that now mentions it. On confirmation apply the
   set with `omw links link --from-suggestions` (one reindex at the end). Never insert
   silently. Skipping this is what leaves a new page orphaned.

8. **Report** the relpath, the `source_raw` it points at, and the links applied.

## After

Run `omw next --after distill --json` and offer the next lifecycle step via the host's
native ask tool — safe default: stop. A freshly written page is the most common source of
orphan / index-drift / one-way-link findings, so `lint` is the expected successor when the
vault has issues.

## Error handling

- Active vault is memo-mode → refuse, suggest `omw vault use <wiki-vault>`.
- `omw find` shows an existing page on the same topic → do not write a second page; take
  the `new-vs-update` fork.
- Layer directory has no index section → `omw page write` creates it; mention this in the report.

## Ask (omw-ask)

This op's user forks are decision classes `new-vs-update` (step 1) and `page-type` (step 2).
Surface each as a **structured choice** per the omw-ask convention with the safe default
offered first; honor the session-sticky and non-interactive degrade rules.
