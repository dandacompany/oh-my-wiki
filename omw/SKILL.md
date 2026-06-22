---
name: omw
description: Short alias for the oh-my-wiki skill (Karpathy-style LLM Wiki with multi-vault sqlite registry). Invoking omw is equivalent to invoking oh-my-wiki — same dispatcher, same vault state, same ops. Use when typing the long name is inconvenient. Trigger phrases — English "omw", "use omw", "/omw", "open omw"; Korean "오엠더블유", "오엠더블유 켜줘", "/omw 실행". The canonical skill is oh-my-wiki; this stub delegates immediately.
---

# omw — alias for oh-my-wiki

This skill is a **thin alias** for [`oh-my-wiki`](../SKILL.md). It exists so that the user can invoke the wiki workflow with three letters instead of the full eleven-character name.

## What to do when invoked

**Always delegate to the canonical oh-my-wiki skill immediately.**

1. Load `../SKILL.md` (the canonical oh-my-wiki dispatcher) and follow its Step 1 — Read registry state procedure.
2. From that point on, behave exactly as if `oh-my-wiki` had been invoked. The user sees no difference.

The canonical skill provides:

- Multi-vault sqlite registry (`scripts/wizard.py`, `scripts/registry.py`)
- memo-mode and wiki-mode dual ops
- 11 user-facing ops (vault-setup / vault-use / vault-list / vault-forget / vault-import-memo / create / find / open / edit / move / delete / ingest / query / lint)
- v2 in progress (plugin install, hot cache, autoresearch, writing-agent personas, multi-agent runtime, swarm protocol)

## Why this stub exists

Claude Code discovers skills by reading `SKILL.md` frontmatter from each directory under `~/.claude/skills/`. To make `omw` register as its own skill name in the discovery list (and as a separate trigger keyword set), it must own a directory with its own `SKILL.md`. This file is the smallest legal version of that.

## Maintenance

If you change the canonical `oh-my-wiki/SKILL.md`, you usually do not need to change this file. The frontmatter description here intentionally repeats only the public surface (name + trigger phrases) so it stays stable.

Update this file only when:

- Trigger keywords for `omw` change
- The relative path `../SKILL.md` to the canonical skill changes
- The alias is deprecated or removed
