from scripts import fetch_rss

RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>Feed</title>
<item><title>One</title><link>https://ex.com/1</link></item>
<item><title>Two</title><link>https://ex.com/2</link></item>
</channel></rss>"""

ATOM = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>Feed</title>
<entry><title>A</title><link rel="alternate" href="https://ex.com/a"/></entry>
<entry><title>B</title><link href="https://ex.com/b"/></entry>
</feed>"""


def test_parse_rss():
    out = fetch_rss.parse_feed(RSS)
    assert [e["link"] for e in out] == ["https://ex.com/1", "https://ex.com/2"]
    assert out[0]["title"] == "One"


def test_parse_atom():
    out = fetch_rss.parse_feed(ATOM)
    assert [e["link"] for e in out] == ["https://ex.com/a", "https://ex.com/b"]


def test_parse_malformed_returns_empty():
    assert fetch_rss.parse_feed("<not xml") == []
    # entry with no link is skipped
    assert fetch_rss.parse_feed(
        '<rss version="2.0"><channel><item><title>x</title></item></channel></rss>') == []


def test_parse_rejects_doctype_entity_bomb():
    # billion-laughs style: a DOCTYPE with entity defs must be refused before parse.
    bomb = ('<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">'
            '<!ENTITY lol2 "&lol;&lol;&lol;">]>'
            '<rss version="2.0"><channel><item><link>&lol2;</link></item></channel></rss>')
    assert fetch_rss.parse_feed(bomb) == []


def test_add_feed_enqueues(tmp_path, monkeypatch):
    from tests.conftest import make_vault_with_pages
    from scripts import inbox
    db, vid = make_vault_with_pages(tmp_path, monkeypatch, pages={
        "wiki/index.md": "# Index\n",
    })
    monkeypatch.setattr(fetch_rss, "fetch_feed", lambda url: [
        {"title": "One", "link": "https://ex.com/1"},
        {"title": "Two", "link": "https://ex.com/2"},
    ])
    res = inbox.add_feed(db, vault_id=vid, feed_url="https://ex.com/feed")
    assert res["count"] == 2 and len(res["added"]) == 2
    assert len(inbox.list_items(db, vault_id=vid, status="queued")) == 2
    # second call dedups
    res2 = inbox.add_feed(db, vault_id=vid, feed_url="https://ex.com/feed")
    assert len(res2["added"]) == 0 and len(res2["deduped"]) == 2
