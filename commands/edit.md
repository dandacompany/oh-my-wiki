# `edit` — modify an existing page

1. Run `omw status`, then locate the page with `omw find "<query>"` if needed.
2. For an interactive edit, open it with `omw view <relpath>`.
3. For an agent edit, read and update the resolved file using the host's normal
   file tools while preserving valid frontmatter and schema sections.
4. Run `omw reindex` and report the changed field or body.

Use the `new-vs-update` structured choice before replacing an existing page.
