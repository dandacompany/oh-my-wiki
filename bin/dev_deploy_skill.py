#!/usr/bin/env python3
"""Dev-mode local deploy of the OMW skill bundle.

Copies the skill straight from THIS repo into the local agent skill dirs, with
**absolute** targets — no cwd sensitivity, and it never shells the marketplace
`skills` CLI (whose reconcile/prune step is what kept deleting the install).

Idempotent and safe to run from git hooks and a SessionStart hook. Prints one
line per target. Never raises (returns non-zero only if every target failed).

Usage:
    python3 bin/dev_deploy_skill.py           # deploy to all targets
    python3 bin/dev_deploy_skill.py --if-missing   # only (re)deploy when absent
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts import agent_skills  # noqa: E402

# Absolute, explicit targets — the two dirs Claude Code / the shared catalog read.
TARGETS = [
    Path.home() / ".claude" / "skills",
    Path.home() / ".agents" / "skills",
]


def deploy(*, if_missing: bool = False) -> int:
    any_ok = False
    for skills_dir in TARGETS:
        dest = skills_dir / "oh-my-wiki"
        if if_missing and (dest / "SKILL.md").exists():
            print(f"omw dev-deploy → {dest}  [present, skipped]")
            any_ok = True
            continue
        skills_dir.mkdir(parents=True, exist_ok=True)
        res = agent_skills.install_into_dir(skills_dir, repo_root=REPO)
        if res.get("ok"):
            any_ok = True
            print(f"omw dev-deploy → {dest}  [ok]")
        else:
            print(f"omw dev-deploy → {dest}  [FAIL: {res.get('detail')}]", file=sys.stderr)
    return 0 if any_ok else 1


if __name__ == "__main__":
    sys.exit(deploy(if_missing="--if-missing" in sys.argv[1:]))
