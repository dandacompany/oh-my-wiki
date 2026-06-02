# tests/test_fetch_youtube.py
import pytest

from scripts import fetch_youtube
from scripts.fetch_errors import NeedsYtDlp


def test_parse_vtt_strips_timestamps_and_dedupes():
    vtt = (
        "WEBVTT\n\n"
        "00:00:00.000 --> 00:00:02.000\n<c>Hello</c> world\n\n"
        "00:00:02.000 --> 00:00:04.000\nHello world\n\n"
        "00:00:04.000 --> 00:00:06.000\nsecond line\n"
    )
    text = fetch_youtube.parse_vtt(vtt)
    assert text == "Hello world\nsecond line"


def test_fetch_transcript_raises_needs_ytdlp_when_absent(monkeypatch):
    monkeypatch.setattr(fetch_youtube.shutil, "which", lambda _: None)
    with pytest.raises(NeedsYtDlp):
        fetch_youtube.fetch_transcript("https://www.youtube.com/watch?v=dQw4w9WgXcQ")


def test_fetch_transcript_rejects_non_youtube_url():
    import pytest
    from scripts.fetch_errors import FetchError
    with pytest.raises(FetchError):
        fetch_youtube.fetch_transcript("-X arbitrary")  # not a youtube URL → rejected pre-subprocess
    with pytest.raises(FetchError):
        fetch_youtube.fetch_transcript("https://example.com/page")


def test_fetch_transcript_passes_url_after_double_dash(monkeypatch, tmp_path):
    # Capture the argv handed to subprocess and assert `--` precedes the url.
    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        # simulate yt-dlp writing one vtt + info.json into the -o tmpdir
        o_idx = args.index("-o")
        out_tmpl = args[o_idx + 1]
        d = __import__("pathlib").Path(out_tmpl).parent
        (d / "vid.en.vtt").write_text("WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nhi\n")
        (d / "vid.info.json").write_text('{"title": "T"}')

        class R:
            returncode = 0
            stderr = ""

        return R()

    monkeypatch.setattr(fetch_youtube.shutil, "which", lambda _: "/usr/bin/yt-dlp")
    monkeypatch.setattr(fetch_youtube.subprocess, "run", fake_run)
    title, text = fetch_youtube.fetch_transcript("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    args = captured["args"]
    assert "--" in args and args.index("--") == len(args) - 2  # `--` is second-to-last, url last
    assert args[-1] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert title == "T" and "hi" in text
