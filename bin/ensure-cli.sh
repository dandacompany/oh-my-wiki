#!/usr/bin/env bash
# Ensure the `omw` CLI is installed. Bundled in the skill so a skills-only
# install can self-bootstrap the CLI on first use. NEVER installs silently.
#
#   - omw already on PATH        -> print OMW_BIN=<path>, exit 0
#   - interactive                -> prompt y/N before installing
#   - non-interactive            -> install only if OMW_BOOTSTRAP_YES=1
#                                   else print the manual one-liner, exit 3
set -u

MANUAL='pipx install oh-my-wiki   # or: python3 -m pip install --user oh-my-wiki'

if command -v omw >/dev/null 2>&1; then
  echo "OMW_BIN=$(command -v omw)"
  exit 0
fi

confirm() {
  if [ "${OMW_BOOTSTRAP_YES:-0}" = "1" ]; then return 0; fi
  if [ ! -t 0 ]; then return 1; fi          # non-interactive, not pre-approved
  printf 'omw CLI not found. Install it now (pipx/pip)? [y/N] ' >&2
  read -r ans
  case "$ans" in [yY]*) return 0 ;; *) return 1 ;; esac
}

if ! confirm; then
  echo "omw CLI not installed. To install it yourself, run:" >&2
  echo "  $MANUAL" >&2
  exit 3
fi

if command -v pipx >/dev/null 2>&1; then
  pipx install oh-my-wiki || { echo "pipx install failed. Try: $MANUAL" >&2; exit 3; }
  pipx ensurepath >/dev/null 2>&1 || true
elif command -v python3 >/dev/null 2>&1; then
  python3 -m pip install --user --upgrade oh-my-wiki \
    || python3 -m pip install --user --break-system-packages --upgrade oh-my-wiki
else
  echo "need python3 (and ideally pipx) to install. Run: $MANUAL" >&2
  exit 3
fi

# Resolve the freshly installed binary (PATH of THIS process may not see it yet).
omw_path="$(command -v omw 2>/dev/null || true)"
for cand in ${omw_path:+"$omw_path"} "$HOME/.local/bin/omw"; do
  if [ -n "$cand" ] && [ -x "$cand" ]; then
    echo "OMW_BIN=$cand"
    exit 0
  fi
done
echo "installed, but could not resolve the omw binary. Add your user bin dir to PATH, then run: omw setup" >&2
exit 3
