"""'Oh My Wiki' splash banner — stdlib only, dependency-free.

Wordmark: figlet 'Standard' font for "oh my wiki" (generated offline, embedded).
Spinner: Unicode braille frames, reproducing the look of the MIT-licensed
`unicode-animations` npm package (data only; no runtime dependency).
"""
from __future__ import annotations

import os
import sys
import time

WORDMARK = r"""        _                                  _ _    _
   ___ | |__    _ __ ___  _   _  __      _(_) | _(_)
  / _ \| '_ \  | '_ ` _ \| | | | \ \ /\ / / | |/ / |
 | (_) | | | | | | | | | | |_| |  \ V  V /| |   <| |
  \___/|_| |_| |_| |_| |_|\__, |   \_/\_/ |_|_|\_\_|
                          |___/"""

SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"  # 10-frame braille dots

GITHUB_URL = "https://github.com/dandacompany/oh-my-wiki"
WEB_URL = "https://oh-my-wiki.com"
CONTACT = "dante@dante-labs.com"
MAKER = "Dante Labs · dante-labs.com"

TAGLINE = "a wiki your AI agent builds as you work"

_DIM = "\x1b[2m"
_ACCENT = "\x1b[36m"
_RESET = "\x1b[0m"


def version() -> str:
    """Read the package version from the single source of truth (never hardcoded)."""
    import importlib.metadata as m
    try:
        return m.version("oh-my-wiki")
    except Exception:
        import json
        from pathlib import Path
        pj = Path(__file__).resolve().parents[1] / ".claude-plugin" / "plugin.json"
        try:
            return json.loads(pj.read_text(encoding="utf-8")).get("version", "0.0.0")
        except Exception:
            return "0.0.0"


def should_animate(stream=None) -> bool:
    stream = stream if stream is not None else sys.stdout
    if os.environ.get("OMW_NO_BANNER") or os.environ.get("NO_COLOR") or os.environ.get("CI"):
        return False
    try:
        return bool(stream.isatty())
    except Exception:
        return False


def _footer(color: bool) -> str:
    rows = [("GitHub", GITHUB_URL), ("Web", WEB_URL), ("Contact", CONTACT), ("Made by", MAKER)]
    out = []
    for label, value in rows:
        lab = f"{_DIM}{label:<9}{_RESET}" if color else f"{label:<9}"
        out.append(f"  {lab} {value}")
    return "\n".join(out)


def _tagline(frame: str, color: bool) -> str:
    spin = f"{_ACCENT}{frame}{_RESET}" if color else frame
    return f"  {spin}  {TAGLINE} · v{version()}"


def banner_text(*, color: bool = False) -> str:
    """The full static banner (settled spinner frame). Used for pipes/tests/help."""
    return (
        f"{WORDMARK}\n\n"
        f"{_tagline(SPINNER[0], color)}\n\n"
        f"{_footer(color)}\n"
    )


def render(*, animate=None, stream=None, sleep=time.sleep, color=None) -> None:
    stream = stream if stream is not None else sys.stdout
    if os.environ.get("OMW_NO_BANNER"):
        return  # hard suppression — show nothing on any surface
    try:
        if animate is None:
            animate = should_animate(stream)
        if color is None:
            color = animate  # color only when we're in an animated TTY context

        if not animate:
            stream.write(banner_text(color=color))
            stream.flush()
            return

        # animated: print wordmark, then spin the tagline line in place (~0.6s), then settle.
        stream.write(WORDMARK + "\n\n")
        spins = 18
        for i in range(spins):
            frame = SPINNER[i % len(SPINNER)]
            stream.write("\r" + _tagline(frame, color))
            stream.flush()
            sleep(0.033)
        stream.write("\r" + _tagline(SPINNER[0], color) + "\n\n")
        stream.write(_footer(color) + "\n")
        stream.flush()
    except (BrokenPipeError, ValueError):
        return  # consumer closed the pipe (e.g. `omw --help | head`) — stop quietly
