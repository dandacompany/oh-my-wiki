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
