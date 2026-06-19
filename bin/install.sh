#!/usr/bin/env bash
# oh-my-wiki — installer
#
# Installs the skill into ~/.claude/skills/ (both canonical name oh-my-wiki and
# the short alias omw), pip-installs the Python package in editable mode, and
# runs the test suite to verify everything works on this machine.
#
# Idempotent: safe to re-run. Existing symlinks are kept if they already point
# to this repo; otherwise replaced (with a confirmation prompt unless --force).
#
# Usage:
#   bash bin/install.sh              # default: production deps only
#   bash bin/install.sh --dev        # install with [dev] extras (pytest, ruff)
#   bash bin/install.sh --force      # replace existing symlinks without prompt
#   bash bin/install.sh --no-test    # skip the pytest verification step
#   bash bin/install.sh --skills-dir <path>   # override ~/.claude/skills/

set -euo pipefail

# ---------- Argument parsing ----------
EXTRAS=""
FORCE=0
RUN_TEST=1
SKILLS_DIR="${HOME}/.claude/skills"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dev)         EXTRAS=".[dev]" ; shift ;;
    --force)       FORCE=1 ; shift ;;
    --no-test)     RUN_TEST=0 ; shift ;;
    --skills-dir)  SKILLS_DIR="$2" ; shift 2 ;;
    -h|--help)
      sed -n '2,16p' "$0" | sed 's/^# \?//'
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      echo "Run 'bash bin/install.sh --help' for usage." >&2
      exit 2
      ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PKG_TARGET="${EXTRAS:-.}"

# ---------- Banner ----------
if [ -t 1 ] && [ -z "${OMW_NO_BANNER:-}" ] && [ -z "${NO_COLOR:-}" ] && [ -z "${CI:-}" ]; then
  cat <<'OMWBANNER'
        _                                  _ _    _
   ___ | |__    _ __ ___  _   _  __      _(_) | _(_)
  / _ \| '_ \  | '_ ` _ \| | | | \ \ /\ / / | |/ / |
 | (_) | | | | | | | | | | |_| |  \ V  V /| |   <| |
  \___/|_| |_| |_| |_| |_|\__, |   \_/\_/ |_|_|\_\_|
                          |___/

  a wiki your AI agent builds as you work

  GitHub    https://github.com/dandacompany/oh-my-wiki
  Web       https://oh-my-wiki.com
  Contact   dante@dante-labs.com
  Made by   Dante Labs · dante-labs.com

OMWBANNER
fi

# ---------- 1. Python version check ----------
echo "==> [1/5] Python version check"
if ! command -v python3 >/dev/null 2>&1; then
  echo "    ❌ python3 not found on PATH. Install Python 3.10 or newer first." >&2
  exit 1
fi
PY_VER="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
PY_MAJOR="$(echo "$PY_VER" | cut -d. -f1)"
PY_MINOR="$(echo "$PY_VER" | cut -d. -f2)"
if [[ "$PY_MAJOR" -lt 3 || ("$PY_MAJOR" -eq 3 && "$PY_MINOR" -lt 10) ]]; then
  echo "    ❌ Python ${PY_VER} found, but oh-my-wiki requires 3.10+." >&2
  exit 1
fi
echo "    ✅ Python ${PY_VER}"

# ---------- 2. pip install ----------
echo "==> [2/5] pip install -e \"${PKG_TARGET}\""
if ! ( cd "$REPO_ROOT" && python3 -m pip install -e "$PKG_TARGET" --quiet ); then
  echo "    pip install hit an externally-managed environment (PEP 668); retrying with --break-system-packages" >&2
  ( cd "$REPO_ROOT" && python3 -m pip install --break-system-packages -e "$PKG_TARGET" --quiet )
fi
echo "    ✅ package installed (editable)"

# ---------- 3. Skill symlinks ----------
mkdir -p "$SKILLS_DIR"

link_one() {
  local name="$1"     # e.g. "oh-my-wiki" or "omw"
  local target="$2"   # absolute path the symlink should point to
  local link="${SKILLS_DIR}/${name}"

  if [[ -L "$link" ]]; then
    local current
    current="$(readlink "$link")"
    if [[ "$current" == "$target" ]]; then
      echo "    ✅ ${name} symlink already correct"
      return 0
    fi
    if [[ "$FORCE" -eq 0 ]]; then
      printf "    ⚠️  %s exists and points to %s. Replace with %s? [y/N] " \
        "$link" "$current" "$target"
      read -r ans
      [[ "$ans" =~ ^[Yy]$ ]] || { echo "    skipped"; return 0; }
    fi
    rm "$link"
  elif [[ -e "$link" ]]; then
    echo "    ❌ ${link} exists but is not a symlink. Remove it manually first." >&2
    exit 1
  fi

  ln -s "$target" "$link"
  echo "    ✅ linked ${name} → ${target}"
}

echo "==> [3/5] Skill symlinks (under ${SKILLS_DIR})"
link_one "oh-my-wiki" "$REPO_ROOT"
link_one "omw"        "${REPO_ROOT}/omw"


# ---------- 4. Pytest verification (optional) ----------
if [[ "$RUN_TEST" -eq 1 ]]; then
  echo "==> [4/5] pytest verification"
  if command -v pytest >/dev/null 2>&1; then
    ( cd "$REPO_ROOT" && pytest -q 2>&1 | tail -3 )
    echo "    ✅ tests green"
  else
    echo "    ⚠️  pytest not on PATH — skipping verification"
    echo "       (install with: bash bin/install.sh --dev)"
  fi
else
  echo "==> [4/5] pytest verification skipped (--no-test)"
fi

# ---------- 5. Next steps ----------
echo "==> [5/5] Done"
cat <<EOF

   oh-my-wiki is installed.

   In a fresh Claude Code (or Codex CLI) session, try any of these:
     - "open my wiki"
     - "omw"
     - "위키 열어줘"
     - "이거 정리해줘" (after pasting long content)

   Useful commands:
     - pytest -v                                  # full test suite (91+ tests)
     - omw status                                 # inspect registry/vault state
     - python3 -m scripts.lint --vault-id N       # health check a vault
     - bash bin/uninstall.sh                      # remove symlinks + uninstall pkg

   Optional fetch backends (for \`omw inbox\` / \`omw fetch\`):
     - yt-dlp (YouTube transcripts):   pip install yt-dlp   (or: brew install yt-dlp)
     - Playwright chromium (SPA pages): pip install playwright && playwright install chromium
     - or configure a cloud scraper:    omw setup search   (firecrawl / brightdata)

   Docs:
     - README.md        — overview
     - TUTORIAL.md      — English walkthrough
     - TUTORIAL.ko.md   — 한국어 가이드
     - https://github.com/dandacompany/oh-my-wiki

EOF
