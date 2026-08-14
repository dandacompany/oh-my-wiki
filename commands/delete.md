# `delete` — remove a page

Deletion always uses the `delete-page` structured choice. Default to Cancel.
After explicit approval, soft-delete by moving the exact page into the vault's
configured trash, rewrite confirmed backlinks as plain display text, and run
`omw reindex --full`. Hard delete requires a second explicit confirmation and
must never be selected automatically.
