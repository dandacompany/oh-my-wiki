"""`relations:` exists in two shapes in real vaults; both must reach the graph.

27 of 84 pages in a live vault wrote relations as a list of single-key mappings
(`[{'derived-from': 'opencove'}]`) rather than a mapping (`{'see-also': [...]}`).
Every consumer guarded with `isinstance(rels, dict)` and silently skipped the rest, so
those relations existed in the file but reached neither the link graph nor
valid_relations checking. The root cause was upstream: no doc showed the shape and
`omw page write` had no flag to set it, so agents guessed.

One normalizer, used by every consumer, is what keeps the guess from mattering.
"""
import pytest

from scripts import links, relations


def test_mapping_shape_passes_through():
    assert relations.normalize({"see-also": ["a", "b"]}) == {"see-also": ["a", "b"]}


def test_scalar_value_becomes_a_list():
    assert relations.normalize({"derived-from": "opencove"}) == {"derived-from": ["opencove"]}


def test_list_of_single_key_mappings():
    assert relations.normalize([{"derived-from": "opencove"}]) == {"derived-from": ["opencove"]}


def test_list_shape_merges_repeated_verbs():
    """A list can repeat a key where a mapping cannot — merge instead of dropping."""
    got = relations.normalize([{"see-also": "a"}, {"see-also": "b"}, {"uses": "c"}])
    assert got == {"see-also": ["a", "b"], "uses": ["c"]}


def test_list_entry_with_a_list_value():
    assert relations.normalize([{"see-also": ["a", "b"]}]) == {"see-also": ["a", "b"]}


@pytest.mark.parametrize("bad", [None, "", "just-a-string", 42, [], {}, ["not-a-mapping"],
                                 [{"a": 1, "b": 2}]])
def test_unusable_shapes_normalize_to_empty(bad):
    """Multi-key list entries are ambiguous, so they are not guessed at."""
    assert relations.normalize(bad) == {}


def test_normalize_does_not_mutate_its_input():
    src = {"see-also": ["a"]}
    relations.normalize(src)["see-also"].append("b")
    assert src == {"see-also": ["a"]}


# ── consumer parity: the reason the normalizer exists ────────────────────────

def test_link_graph_sees_list_shaped_relations():
    """This is the defect: 27 pages' relations never became graph edges."""
    as_map = links.extract_relations({"relations": {"see-also": ["target-page"]}})
    as_list = links.extract_relations({"relations": [{"see-also": "target-page"}]})
    assert as_list == as_map != []


def test_every_consumer_agrees_on_the_same_input():
    """links / page_ops / schema must not disagree — divergence is how the silent
    skip happened in the first place."""
    from scripts import page_ops, schema
    # `synthesis` is used because it declares valid_relations; `base` does not, so a
    # concept page never reaches the relation check at all.
    meta = {"type": "synthesis", "title": "T", "date": "2026-01-01", "tags": ["t"],
            "synthesizes": ["a"], "relations": [{"unexpected-verb": "x"}]}
    schemas = schema.load_schemas()
    issues = schema.validate(meta, "body", schemas=schemas)
    assert any(i["issue"] == "unexpected_relation:unexpected-verb" for i in issues), issues
    assert page_ops.relation_targets(meta) == {"unexpected-verb": ["x"]}
