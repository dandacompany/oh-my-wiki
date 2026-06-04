# Frontmatter schema

Every note in a oh-my-wiki vault starts with YAML frontmatter. Missing or malformed frontmatter causes the file to be indexed with `parse_error = 1` and excluded from search.

## Common fields (all layers)

| Field        | Type                | Required    | Notes                                                                                                                                                                                           |
| ------------ | ------------------- | ----------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `title`      | string              | yes         | Used as primary search signal.                                                                                                                                                                  |
| `date`       | string (YYYY-MM-DD) | yes         | Creation date.                                                                                                                                                                                  |
| `type`       | enum                | yes         | `article` \| `link` \| `note` \| `paper` \| `video` \| `book` \| `doc`                                                                                                                          |
| `tags`       | YAML list           | yes         | Must be `[a, b, c]`, never a string.                                                                                                                                                            |
| `summary`    | string              | recommended | One-sentence summary.                                                                                                                                                                           |
| `status`     | enum                | optional    | `inbox` \| `processed` \| `archived` (memo) / `raw` \| `meta` (wiki layers)                                                                                                                     |
| `visibility` | enum                | optional    | `public` \| `private`. Default `private`. Only affects `omw serve`: the local retrieve-only API exposes **only** `visibility: public` pages. In-session `query`/`find` ignore it (full access). |
| `source`     | string (URL)        | optional    | Used at ingest time.                                                                                                                                                                            |

## wiki-mode layer-specific fields

- `raw/` notes carry `status: raw` and ideally `source:` URL.
- `wiki/` notes carry `status: processed` or `status: meta` (for `index.md`/`log.md`).

## Editing rules

- Always edit a single key in-place (`frontmatter.edit_field`). Do not rewrite the whole block.
- `tags` must remain a YAML list. If you need to add a tag, read-modify-write the list, not the YAML text.
- Field order is preserved on dump (sort_keys=False).
