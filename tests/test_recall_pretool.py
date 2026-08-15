import pytest

from scripts import recall


def _has_active(monkeypatch, yes=True):
    class _DB:
        def exists(self):
            return True
    monkeypatch.setattr("scripts.paths.registry_path", lambda: _DB())
    monkeypatch.setattr(recall, "_active",
                        lambda db: {"id": 1, "name": "v"} if yes else None)


def test_pretool_nudges_on_raw_grep(monkeypatch):
    _has_active(monkeypatch, True)
    out = recall.pretool({"tool_name": "Grep",
                          "tool_input": {"pattern": "ARIMA", "path": "raw/"}})
    assert "omw find" in out and recall.MARKER in out
    assert not any("가" <= char <= "힣" for char in out)


def test_pretool_silent_without_wiki(monkeypatch):
    _has_active(monkeypatch, False)
    out = recall.pretool({"tool_name": "Read",
                          "tool_input": {"file_path": "raw/x.md"}})
    assert out == ""


def test_pretool_silent_on_unrelated_tool(monkeypatch):
    _has_active(monkeypatch, True)
    out = recall.pretool({"tool_name": "Bash",
                          "tool_input": {"command": "ls"}})
    assert out == ""


def test_pretool_supports_codex_exec_command(monkeypatch):
    _has_active(monkeypatch, True)
    monkeypatch.setattr(recall, "_pretool_path_hits", lambda payload: [{
        "relpath": "wiki/recall-hooks.md", "title": "Recall hooks", "score": 8.0}])
    out = recall.pretool({
        "tool_name": "exec_command",
        "tool_input": {"cmd": "sed -n '1,80p' scripts/recall.py"},
    })
    assert "Related wiki pages" in out and "wiki/recall-hooks.md" in out


def test_pretool_codex_command_detects_raw(monkeypatch):
    _has_active(monkeypatch, True)
    monkeypatch.setattr(recall, "_pretool_path_hits", lambda payload: [])
    out = recall.pretool({
        "tool_name": "exec_command",
        "tool_input": {"cmd": "rg hook raw/claude-code.md"},
    })
    assert "omw find" in out


# --- shell-noise gate -------------------------------------------------------
# A shell command carrying no file-path argument must never reach the index:
# `ls`/`date`/`git status` are host bookkeeping, not a topic to recall on.

SHELL_NOISE = [
    "ls -la",
    "date",
    "git status --short --branch",
    "echo hello world",
    "pwd",
    "sed -n '1,260p'",
]


@pytest.mark.parametrize("command", SHELL_NOISE)
def test_shell_noise_yields_no_query(command):
    assert recall._pretool_path_query(
        {"tool_name": "bash", "tool_input": {"command": command}}) == ""


@pytest.mark.parametrize("command", SHELL_NOISE)
def test_shell_noise_never_hits_the_index(monkeypatch, command):
    # An active vault is stubbed in so a regression provably *reaches* the
    # recorder; without it the lookup would bail on "no vault" and pass
    # vacuously (and touch the real registry on a dev machine).
    _has_active(monkeypatch, True)
    # _pretool_path_hits swallows every exception, so a raising stub would pass
    # vacuously — record the calls instead.
    calls = []
    monkeypatch.setattr("scripts.search_index.query",
                        lambda *a, **k: calls.append(k) or [])
    assert recall._pretool_path_hits(
        {"tool_name": "bash", "tool_input": {"command": command}}) == []
    assert calls == []


@pytest.mark.parametrize("command,expected", [
    # 'wiki', 'concepts' and 'docs' name vault structure, not a subject
    ("cat wiki/concepts/kiwi.md", {"kiwi"}),
    ("sed -n '1,120p' docs/BACKLOG.md", {"BACKLOG"}),
    ("git diff -- packages/db/key-rotation.ts | sed -n 1,260p",
     {"packages", "db", "key-rotation"}),
    ("rg hook raw/claude-code.md", {"claude-code"}),
])
def test_path_arguments_survive_as_the_query(command, expected):
    """Only path-shaped arguments become search terms; flags and utility names go."""
    got = set(recall._pretool_path_query(
        {"tool_name": "bash", "tool_input": {"command": command}}).split())
    assert got == expected


def test_every_vault_layer_is_a_stopword():
    """Anti-drift: a new layer in ingest.WIKI_LAYERS must be added here too,
    or its directory name starts being treated as a topic again."""
    from scripts import ingest
    assert set(ingest.WIKI_LAYERS) <= recall._PRETOOL_STOPWORDS


def test_non_shell_tools_keep_their_pattern():
    """Grep's pattern is a human-chosen search term — it must not be filtered out."""
    q = recall._pretool_path_query(
        {"tool_name": "Grep", "tool_input": {"pattern": "ARIMA", "path": "raw/"}})
    assert "ARIMA" in q.split()


# --- relevance gate ---------------------------------------------------------
# FTS scores do not rank relevance here: measured on a real vault, the apt query
# '페르소나 번들' tops out at 5.7 while the junk query 'packages db key-rotation'
# reaches 11.5 — a common word matching often in long documents outscores a real
# topical match. So a hit qualifies by *naming* a search term, not by scoring.

def _stub_index(monkeypatch, rows):
    _has_active(monkeypatch, True)
    monkeypatch.setattr("scripts.search_index.query", lambda *a, **k: [
        {"relpath": r, "title": t, "score": s} for r, t, s in rows])
    monkeypatch.setattr(recall, "normalize_query", lambda t: t)


def _hits_for(command):
    return recall._pretool_path_hits(
        {"tool_name": "bash", "tool_input": {"command": command}})


def test_hit_naming_a_search_term_survives(monkeypatch):
    _stub_index(monkeypatch, [
        ("wiki/concepts/key-rotation.md", "Key rotation", 4.0),
        ("raw/2026-07-08-hermes-plugins.md", "Hermes plugins", 11.5),
    ])
    assert [h["relpath"] for h in _hits_for("cat packages/db/key-rotation.ts")] == [
        "wiki/concepts/key-rotation.md"]


def test_high_scoring_hits_that_name_nothing_are_dropped(monkeypatch):
    """A junk query outscoring a real one must still inject nothing."""
    _stub_index(monkeypatch, [
        ("raw/2026-07-08-hermes-plugins.md", "Hermes plugins", 11.5),
        ("raw/2026-06-29-hermes-config.md", "Hermes configuration", 10.6),
    ])
    assert _hits_for("cat packages/db/key-rotation.ts") == []


def test_a_term_matching_only_the_title_counts(monkeypatch):
    _stub_index(monkeypatch, [("wiki/notes/n1.md", "Kiwi tokenizer notes", 3.0)])
    assert len(_hits_for("cat docs/kiwi.md")) == 1


def test_layer_directory_names_cannot_qualify_a_hit(monkeypatch):
    """'concepts' names a vault layer, not a topic — it must not match on its own."""
    _stub_index(monkeypatch, [("wiki/concepts/unrelated.md", "Unrelated", 2.4)])
    assert _hits_for("cat wiki/concepts/kiwi.md") == []


def test_a_hyphenated_term_matches_a_spaced_title(monkeypatch):
    """The index splits 'key-rotation' into two words, so the gate must too."""
    _stub_index(monkeypatch, [("wiki/concepts/n1.md", "Key rotation", 4.0)])
    assert len(_hits_for("cat packages/db/key-rotation.ts")) == 1


def test_only_part_of_a_compound_term_is_not_enough(monkeypatch):
    """'Key management' shares 'key' but is not the page about key-rotation."""
    _stub_index(monkeypatch, [("wiki/concepts/n1.md", "Key management", 4.0)])
    assert _hits_for("cat packages/db/key-rotation.ts") == []


def test_short_ascii_terms_cannot_qualify_a_hit(monkeypatch):
    """'db' would substring-match dbt, mariadb, sandbox — too weak to inject on."""
    _stub_index(monkeypatch, [("wiki/concepts/dbt-modeling.md", "dbt modeling", 9.0)])
    assert _hits_for("cat src/db/schema.sql") == []


def test_ascii_terms_match_on_word_boundaries(monkeypatch):
    _stub_index(monkeypatch, [("wiki/concepts/sandbox.md", "Sandbox", 9.0)])
    assert _hits_for("cat src/box/run.py") == []


def test_two_syllable_hangul_terms_still_qualify(monkeypatch):
    """Hangul has no word boundaries, and 2 syllables is already specific."""
    _stub_index(monkeypatch, [("wiki/concepts/번들-구성.md", "", 5.7)])
    assert len(_hits_for("cat wiki/concepts/번들.md")) == 1


def test_date_shaped_path_segments_are_not_search_terms():
    """Dates name this vault's filename convention, not a subject."""
    for command in ("cat notes/2026-07-08/x.md", "cat docs/2026-07-08.md"):
        terms = recall._pretool_path_query(
            {"tool_name": "bash", "tool_input": {"command": command}}).split()
        assert "2026-07-08" not in terms


def test_a_qualifying_hit_below_the_top_three_is_still_found(monkeypatch):
    """Score does not rank relevance, so the gate must see a wide candidate set."""
    rows = [(f"wiki/notes/other{i}.md", "", 20.0 - i) for i in range(6)]
    rows.append(("wiki/concepts/hybrid-search.md", "Hybrid search", 3.0))
    _stub_index(monkeypatch, rows)
    assert [h["relpath"] for h in _hits_for("cat wiki/concepts/hybrid-search.md")] == [
        "wiki/concepts/hybrid-search.md"]


def test_at_most_three_pages_are_injected(monkeypatch):
    _stub_index(monkeypatch, [(f"wiki/notes/kiwi-{i}.md", "", 9.0) for i in range(6)])
    assert len(_hits_for("cat wiki/concepts/kiwi.md")) == 3


def test_no_index_call_when_no_term_can_qualify(monkeypatch):
    _has_active(monkeypatch, True)
    calls = []
    monkeypatch.setattr("scripts.search_index.query",
                        lambda *a, **k: calls.append(k) or [])
    assert _hits_for("cat src/db/x.md") == []
    assert calls == []


def test_repeated_paths_do_not_crowd_out_the_term_budget():
    q = recall._pretool_path_query({"tool_name": "bash", "tool_input": {
        "command": "cat a/kiwi.md a/kiwi.md a/kiwi.md a/kiwi.md b/hybrid-search.md"}})
    assert "hybrid-search" in q.split() and q.split().count("kiwi") == 1


def test_hangul_terms_match_across_unicode_normalization(monkeypatch):
    """NFD filenames (macOS SMB vaults) must still match an NFC query term."""
    import unicodedata
    relpath = unicodedata.normalize("NFD", "wiki/concepts/페르소나.md")
    _stub_index(monkeypatch, [(relpath, "", 5.7)])
    assert len(_hits_for("cat wiki/concepts/페르소나.md")) == 1
