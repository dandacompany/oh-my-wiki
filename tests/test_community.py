# tests/test_community.py
from scripts import community


def _edges(pairs):
    """Build links.graph()-shaped rows from (src, dst) pairs (all resolved wikilinks)."""
    return [{"src_relpath": s, "dst_relpath": d, "dst_slug": d, "link_type": "wikilink",
             "resolved": 1} for s, d in pairs]


def test_build_graph_undirected_weighted_drops_selfloops_and_meta():
    edges = _edges([("a", "b"), ("b", "a"), ("a", "a"),
                    ("a", "wiki/index.md"), ("c", "d")])
    adj, deg = community._build_graph(edges)
    assert adj["a"]["b"] == 2 and adj["b"]["a"] == 2      # parallel + reverse collapse
    assert "a" not in adj.get("a", {})                    # no self-loop
    assert "wiki/index.md" not in adj                     # META excluded
    assert deg["a"] == 2 and deg["c"] == 1


def test_detect_barbell_two_communities_deterministic():
    # two K3 cliques joined by one bridge edge (c3-d1)
    clique1 = [("a1", "a2"), ("a2", "a3"), ("a1", "a3")]
    clique2 = [("b1", "b2"), ("b2", "b3"), ("b1", "b3")]
    bridge = [("a3", "b1")]
    labels, q = community.detect(_edges(clique1 + clique2 + bridge))
    # exactly two communities
    assert len(set(labels.values())) == 2
    # each clique is internally co-assigned
    assert labels["a1"] == labels["a2"] == labels["a3"]
    assert labels["b1"] == labels["b2"] == labels["b3"]
    assert labels["a1"] != labels["b1"]
    assert 0.0 < q <= 1.0
    # deterministic across input-order shuffles
    labels2, q2 = community.detect(_edges(bridge + clique2 + clique1))
    assert labels2 == labels and abs(q2 - q) < 1e-9


def test_detect_single_clique_one_community():
    labels, q = community.detect(_edges([("a", "b"), ("b", "c"), ("a", "c")]))
    assert len(set(labels.values())) == 1


def test_detect_empty_graph():
    assert community.detect([]) == ({}, 0.0)
    # rows that are all unresolved → still empty
    assert community.detect([{"src_relpath": "a", "dst_relpath": "b", "dst_slug": "b",
                              "link_type": "wikilink", "resolved": 0}]) == ({}, 0.0)
