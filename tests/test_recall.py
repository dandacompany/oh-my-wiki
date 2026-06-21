"""Unit tests for scripts.recall — render_always_on_block + marker-agnostic upsert."""
from scripts import recall


def test_always_on_block_is_wiki_first_and_marked():
    block = recall.render_always_on_block()
    assert "omw-wiki-first:start" in block and "omw-wiki-first:end" in block
    assert "omw find" in block and "raw/" in block
