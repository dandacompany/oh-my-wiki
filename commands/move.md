# `move` — relocate a page

1. Resolve the exact page with `omw find "<query>"` and read the active vault
   path from `omw status`.
2. Ask the `move-backlinks` structured choice; default to rewriting backlinks.
3. Move the file with the host's filesystem tool, update confirmed backlinks,
   then run `omw reindex --full`.
4. Verify the old relpath is absent and report the new relpath.
