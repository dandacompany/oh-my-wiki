# Vault modes

A vault uses one of seven modes, chosen by `omw setup vault` or
`omw vault create --mode` and stored in `vaults.mode`.

| Aspect           | memo-mode                            | wiki-mode                                                                                                                          |
| ---------------- | ------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------- |
| Directory layout | Topic folders + `inbox/` + `.trash/` | `raw/` + `wiki/` (+ `summaries`, `entities`, `concepts`, `comparisons`, `syntheses`) + `wiki/index.md` + `wiki/log.md` + `.trash/` |
| Ingest concept   | Each note is self-contained          | New source goes to `raw/`, then LLM updates 10–15 wiki pages                                                                       |
| Query            | Search returns notes                 | Search reads pages and may file the answer back as a new synthesis                                                                 |
| Lint             | None (Plan A/B)                      | Contradictions, stale claims, orphans, missing concepts, empty data                                                                |
| Best for         | Casual note-taking                   | Research, deep knowledge bases                                                                                                     |

Extended modes add a purpose-specific top-level scaffold:

| Mode              | Directories                                                          |
| ----------------- | -------------------------------------------------------------------- |
| `personal`        | `journal/`, `goals/`, `people/`, `health/`                           |
| `book`            | `chapters/`, `characters/`, `worldbuilding/`, `outlines/`, `drafts/` |
| `business`        | `meetings/`, `decisions/`, `clients/`, `vendors/`, `processes/`      |
| `github-codebase` | `modules/`, `apis/`, `decisions/`, `runbooks/`, `glossary/`          |
| `website`         | `pages/`, `posts/`, `assets/`, `seo/`, `outlines/`                   |

`omw vault set <name> --mode <mode>` preserves existing files and adds the new
mode's missing scaffold before updating the registry. It never removes folders
from the previous mode.
