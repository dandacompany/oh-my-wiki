"""YouTube transcript extraction via the `yt-dlp` CLI (install-time optional)."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from scripts.fetch_errors import FetchError, NeedsYtDlp

_TAG_RE = re.compile(r"<[^>]+>")


def parse_vtt(vtt: str) -> str:
    """Reduce a WebVTT subtitle file to plain de-duplicated lines."""
    out: list[str] = []
    seen_last = None
    for raw in vtt.splitlines():
        line = raw.strip()
        if not line or line == "WEBVTT" or "-->" in line:
            continue
        if line.isdigit():  # cue number
            continue
        line = _TAG_RE.sub("", line).strip()  # strip <c>, <00:00:00.000> inline tags
        if not line or line == seen_last:
            continue
        out.append(line)
        seen_last = line
    return "\n".join(out)


def fetch_transcript(url: str) -> tuple[str, str]:
    """Return (title, transcript_text) for a YouTube URL using yt-dlp.
    Raises NeedsYtDlp if the CLI is missing, FetchError on extraction failure."""
    exe = shutil.which("yt-dlp")
    if not exe:
        raise NeedsYtDlp("yt-dlp is not installed")
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        proc = subprocess.run(
            [exe, "--skip-download", "--write-auto-subs", "--write-subs",
             "--sub-langs", "ko,en", "--sub-format", "vtt",
             "--write-info-json", "-o", str(tmpdir / "%(id)s.%(ext)s"), url],
            capture_output=True, text=True, timeout=120,
        )
        if proc.returncode != 0:
            raise FetchError(f"yt-dlp failed: {proc.stderr.strip()[:200]}")
        info_files = list(tmpdir.glob("*.info.json"))
        title = url
        if info_files:
            try:
                title = json.loads(info_files[0].read_text()).get("title") or url
            except (ValueError, OSError):
                pass
        vtts = sorted(tmpdir.glob("*.vtt"))
        if not vtts:
            raise FetchError("yt-dlp produced no subtitles (none available?)")
        text = parse_vtt(vtts[0].read_text(encoding="utf-8", errors="replace"))
        return title, text
