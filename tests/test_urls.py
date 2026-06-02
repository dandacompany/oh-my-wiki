# tests/test_urls.py
from scripts import urls


def test_normalize_lowercases_scheme_host_and_strips_fragment_and_utm():
    u = urls.normalize_url("HTTPS://Example.COM/Path?utm_source=x&a=1#frag")
    assert u == "https://example.com/Path?a=1"


def test_normalize_youtube_canonicalizes_to_watch_url():
    a = urls.normalize_url("https://youtu.be/dQw4w9WgXcQ?t=5")
    b = urls.normalize_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=RD")
    assert a == b == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def test_is_youtube_and_youtube_id():
    assert urls.is_youtube("https://youtu.be/dQw4w9WgXcQ")
    assert urls.is_youtube("https://www.youtube.com/watch?v=abc123DEF45")
    assert not urls.is_youtube("https://example.com/watch?v=x")
    assert urls.youtube_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"


def test_is_blocked_url_ssrf():
    assert urls.is_blocked_url("file:///etc/passwd")
    assert urls.is_blocked_url("http://localhost/x")
    assert urls.is_blocked_url("http://127.0.0.1/x")
    assert urls.is_blocked_url("http://169.254.169.254/latest/meta-data")
    assert urls.is_blocked_url("http://10.0.0.5/x")
    assert urls.is_blocked_url("http://192.168.1.1/x")
    assert not urls.is_blocked_url("https://example.com/x")
    assert urls.is_blocked_url("ftp://example.com/x")  # non-http(s) scheme


def test_ssrf_blocks_obfuscated_ipv4():
    assert urls.is_blocked_url("http://2130706433/")    # decimal 127.0.0.1
    assert urls.is_blocked_url("http://0x7f000001/")     # hex 127.0.0.1
    assert urls.is_blocked_url("http://127.1/")          # abbreviated loopback
    assert not urls.is_blocked_url("http://example.com/")  # real hostname still allowed


def test_youtube_host_match_is_not_substring():
    assert urls.youtube_id("https://notyoutube.com/watch?v=dQw4w9WgXcQ") is None
    assert urls.youtube_id("https://youtube.com.evil.com/watch?v=dQw4w9WgXcQ") is None
    assert not urls.is_youtube("https://evilyoutu.be/dQw4w9WgXcQ")
    # legit forms still work
    assert urls.youtube_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert urls.youtube_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
