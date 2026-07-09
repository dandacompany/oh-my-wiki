"""GitHub star nudge — non-intrusive, opt-out, never blocks or hits the network.

Two once-each moments (A: right after `omw update`; B: once, 3 days after first use)
plus the explicit `omw star` command. All output is a single stdout line, TTY-gated,
and silenced by any of: `dismissed` state, `OMW_NO_STAR=1`, or config `star.nudge=false`.
State lives in ~/.omw/star-state.json (gate-state.json pattern); the vault is never
touched. Never raises to the caller.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta

from scripts.paths import omw_home

REPO_URL = "https://github.com/dandacompany/oh-my-wiki"
REPO_SLUG = "dandacompany/oh-my-wiki"
GRACE_DAYS = 3

_DEFAULT_STATE = {"first_seen": None, "install_nudge_shown": False, "dismissed": False}


def state_path():
    return omw_home() / "star-state.json"


def load_state() -> dict:
    try:
        data = json.loads(state_path().read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("not an object")
    except (OSError, ValueError):
        return dict(_DEFAULT_STATE)
    for k, v in _DEFAULT_STATE.items():
        data.setdefault(k, v)
    return data


def save_state(state: dict) -> None:
    try:
        p = state_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass  # best-effort; a nudge is never worth failing a command


def _config_nudge_enabled() -> bool:
    try:
        from scripts import config
        star = (config.load_config() or {}).get("star") or {}
        return star.get("nudge", True) is not False
    except Exception:
        return True


def suppressed(state: dict | None = None) -> bool:
    """True if no nudge should ever show right now (dismissed / env / config)."""
    if os.environ.get("OMW_NO_STAR") == "1":
        return True
    if not _config_nudge_enabled():
        return True
    st = state if state is not None else load_state()
    return bool(st.get("dismissed"))


def nudge_line() -> str:
    return ("★ Enjoying oh-my-wiki? A GitHub star helps others find it: "
            f"{REPO_URL}  (run `omw star --dismiss` to hide)")


def maybe_update_nudge(*, now: datetime, is_tty: bool) -> str | None:
    """Nudge A — shown once per successful `omw update` (unless suppressed / non-TTY)."""
    if not is_tty or suppressed():
        return None
    return nudge_line()


def maybe_install_nudge(*, now: datetime, is_tty: bool) -> str | None:
    """Nudge B — once, GRACE_DAYS after first use. Sets first_seen on the first call."""
    if not is_tty:
        return None
    state = load_state()
    if suppressed(state):
        return None
    if state.get("install_nudge_shown"):
        return None
    first = state.get("first_seen")
    if not first:
        state["first_seen"] = now.isoformat()
        save_state(state)
        return None  # grace period just started
    try:
        first_dt = datetime.fromisoformat(first)
    except (TypeError, ValueError):
        state["first_seen"] = now.isoformat()
        save_state(state)
        return None
    if now < first_dt + timedelta(days=GRACE_DAYS):
        return None
    state["install_nudge_shown"] = True
    save_state(state)
    return nudge_line()


def dismiss() -> None:
    state = load_state()
    state["dismissed"] = True
    save_state(state)


def status() -> dict:
    st = load_state()
    return {"first_seen": st.get("first_seen"),
            "install_nudge_shown": bool(st.get("install_nudge_shown")),
            "dismissed": bool(st.get("dismissed")),
            "suppressed": suppressed(st),
            "repo": REPO_URL}


def open_repo() -> bool:
    """Open the repo in a browser. Returns success; never raises."""
    try:
        import webbrowser
        return webbrowser.open(REPO_URL)
    except Exception:
        return False


# ── one-click star via the user's own GitHub CLI auth ────────────────────────
# omw never handles a token: it delegates to `gh`, which stars AS the logged-in
# user. A star can only be registered by the account that owns it, so this is the
# only "actually register it" path short of the user clicking the web page.
def gh_ready() -> bool:
    """True if `gh` is installed AND authenticated."""
    import shutil
    import subprocess
    if not shutil.which("gh"):
        return False
    try:
        return subprocess.run(["gh", "auth", "status"], capture_output=True,
                              timeout=10).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def star_via_gh() -> bool:
    """Star the repo as the user's gh account (PUT /user/starred/<slug>). Success?"""
    import subprocess
    try:
        r = subprocess.run(["gh", "api", "--method", "PUT",
                            f"/user/starred/{REPO_SLUG}"],
                           capture_output=True, timeout=20)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False
