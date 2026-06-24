from scripts import links


def test_new_relation_verbs_extracted():
    meta = {"relations": {"derived-from": ["b"], "extends": ["c"], "see-also": ["d"]}}
    rels = {(s, r) for s, r, _ in links.extract_relations(meta)}
    assert ("b", "derived-from") in rels
    assert ("c", "extends") in rels
    assert ("d", "see-also") in rels


def test_unknown_relation_ignored():
    meta = {"relations": {"frobnicate": ["x"], "uses": ["y"]}}
    rels = {r for _, r, _ in links.extract_relations(meta)}
    assert "uses" in rels and "frobnicate" not in rels


def test_inline_new_relation_extracted():
    body = "intro\n\nderived-from:: [[b]]\n"
    rels = {(s, r) for s, r, _ in links.extract_inline_relations(body)}
    assert ("b", "derived-from") in rels
