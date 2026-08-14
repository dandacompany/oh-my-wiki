# `create` — capture a new memo

Run `omw status` and require a memo-mode vault. Propose title, folder, tags,
type, and today's ISO date. After confirmation, write a UTF-8 Markdown file
under the active vault with valid frontmatter, then run `omw reindex` and report
the final relpath. Resolve filename collisions with `-2`, `-3`, and so on.
