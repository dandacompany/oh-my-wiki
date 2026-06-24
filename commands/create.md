# `create` — capture a new memo

**Mode:** memo (active vault must be memo-mode)
**Underlying script:** `scripts.memo_ops.write`

## Preconditions

Call `python3 -m scripts.wizard status` first. Refuse if `active.mode != "memo"`. If wiki-mode is active, suggest the user run `vault-use <memo-vault-name>` or `vault-setup` to create a memo vault.

## Flow

### Branch 1 — Pasted body (length > 200 chars)

The user has already pasted long-form content. Propose `{title, slug, folder, tags}` from the body:

- **title**: take the first meaningful line, strip markdown syntax, max 80 chars.
- **slug**: derived from title — let `memo_ops.write` compute via `slugify.slugify`.
- **folder**: default `inbox/`. If body mentions a clear topic ("about X", "X journal"), suggest a topic folder.
- **tags**: 2–4 nouns derived from body content.
- **type**: default `note` unless the body is clearly an `article` (linked URL), `link` (just a URL + comment), `paper`, `video`, `book`, or `doc`.
- **date**: today (ISO YYYY-MM-DD).

Present the proposal in a single AskUserQuestion with options to **Accept**, **Edit field**, or **Cancel**. On Accept, call:

```bash
python3 -m scripts.memo_ops write \
  --vault-id <id> --title "<title>" --folder inbox \
  --tags <tag1>,<tag2> --type note --date 2026-05-24 \
  --body-file /tmp/memo-body-<rand>.md
```

(See "Script invocation" below for the actual CLI shape. If a CLI doesn't exist yet, use `python3 -c "from scripts import memo_ops, registry; ..."`.)

### Branch 2 — Prompt-driven (no paste, or body < 200 chars)

1. Ask the user for a `title` (single line).
2. Show available folders (read `vault.path`, list immediate subdirs excluding `.trash`). Ask which folder (default `inbox/`).
3. Ask for the body content. Allow multi-line via heredoc or temp file.
4. Suggest 2–3 tags from title alone.
5. Single AskUserQuestion to confirm.

## Script invocation

The Python entrypoint takes the body via stdin (long content is unsafe on CLI):

```bash
echo "<body>" | python3 -c "
import sys
from scripts.paths import registry_path
from scripts import memo_ops, registry
db = registry_path()
vault = registry.get_active(db)
relpath = memo_ops.write(
    db,
    vault_id=vault['id'],
    title='<title>',
    body=sys.stdin.read(),
    folder='inbox',
    tags=['<t1>','<t2>'],
    type_='note',
    date_str='2026-05-24',
)
print(relpath)
"
```

## Post-conditions

- New file at `<vault.path>/<relpath>` with valid YAML frontmatter.
- `notes` table contains a row for `relpath`.
- Report back to the user: relpath, full path, and a one-line confirmation.

## Frontmatter conventions

For synthesis or comparison pages, record provenance and follow relation contracts:
synthesis ⇒ `synthesizes: [slugs]` + `## Sources` section; comparison ⇒ `compared_items: [...]`;
use precise relation verbs (`derived-from`/`extends`/`illustrates`/`applies-to`/`instances-of`/`see-also`/`synthesizes`).

## Error handling

- Active vault is wiki-mode → refuse, suggest `vault-use`.
- Slug collision → handled internally; just report the final relpath.
- Folder does not exist → `memo_ops.write` creates it; mention this in the confirmation.
