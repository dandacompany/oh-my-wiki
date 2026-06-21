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


def test_barbell_exact_modularity():
    """Barbell (two K3 cliques + one bridge a3-b1) should yield Q ≈ 0.3571.

    Exact value derivation: 7 edges total (two_m=14).
    Each clique contributes 3 internal edges; bridge contributes 1 cross edge.
    Q = (1/14) * sum_{u,v in same community} [A_uv - d_u*d_v/14]
    The expected value rounds to 0.3571 (to 4 decimal places).
    """
    clique1 = [("a1", "a2"), ("a2", "a3"), ("a1", "a3")]
    clique2 = [("b1", "b2"), ("b2", "b3"), ("b1", "b3")]
    bridge = [("a3", "b1")]
    _, q = community.detect(_edges(clique1 + clique2 + bridge))
    assert abs(q - 0.3571) < 0.001, f"Expected Q ≈ 0.3571, got {q}"


def test_dq_factor_sparse_clustering():
    """Regression guard for the corrected ΔQ formula (e_ij - 2*a_i*a_j).

    Graph: path a1-a2-a3 and path b1-b2-b3, joined by bridge edge a3-b1 (5 edges,
    two_m=10).

    With the BUGGY formula (2*e_ij - 2*a_i*a_j, doubling e_ij), the bridge-spanning
    merge dQ is artificially inflated, causing the algorithm to absorb a3 and b1 into
    the same cluster and yield just 2 communities: {a1,a2,a3,b1} and {b2,b3}.

    The CORRECT formula (e_ij - 2*a_i*a_j) makes the greedy CNM stop earlier and
    produce 3 communities: {a1,a2}, {a3,b1}, {b2,b3}.  This is a known limitation of
    greedy CNM on sparse paths — the global optimum (Q=0.30 for {a1,a2,a3}/{b1,b2,b3},
    verified via _modularity brute-force) is not always reachable by the greedy merge
    sequence; the algorithm halts at the locally consistent 3-community partition
    (Q=0.26 by _modularity).

    Discrimination confirmed: the buggy 2*e_ij formula yields 2 communities;
    the corrected formula yields exactly 3.
    """
    edges = [
        ("a1", "a2"), ("a2", "a3"),          # path A
        ("b1", "b2"), ("b2", "b3"),          # path B
        ("a3", "b1"),                         # bridge
    ]
    labels, q = community.detect(_edges(edges))
    communities = set(labels.values())
    assert len(communities) == 3, (
        f"Expected exactly 3 communities on two-path-bridge graph, got {len(communities)}: {labels}"
    )
    # endpoints pair with their direct neighbour only
    assert labels["a1"] == labels["a2"]
    assert labels["b2"] == labels["b3"]
    # bridge nodes a3 and b1 are co-assigned (merged in step 3 of greedy CNM)
    assert labels["a3"] == labels["b1"]
    # the three clusters are distinct
    assert labels["a1"] != labels["a3"]
    assert labels["b2"] != labels["a3"]


def test_detect_sparse_path_splits_not_overmerged():
    # path 0-1, 1-2 plus pendant 0-3. _modularity says {0,3}/{1,2} (Q=0.1667)
    # beats one community (Q=0.0); the detector must not over-merge into one.
    labels, q = community.detect(_edges([("0", "1"), ("1", "2"), ("0", "3")]))
    assert len(set(labels.values())) == 2
    assert abs(q - 0.1667) < 0.001
    # the reported Q must equal the best partition's modularity, never a worse one
    assert q > 0.0


def test_analyze_barbell_reports_bridge(monkeypatch):
    clique1 = [("wiki/a1.md", "wiki/a2.md"), ("wiki/a2.md", "wiki/a3.md"), ("wiki/a1.md", "wiki/a3.md")]
    clique2 = [("wiki/b1.md", "wiki/b2.md"), ("wiki/b2.md", "wiki/b3.md"), ("wiki/b1.md", "wiki/b3.md")]
    bridge = [("wiki/a3.md", "wiki/b1.md")]
    monkeypatch.setattr(community.links, "graph",
                        lambda db, vid: _edges(clique1 + clique2 + bridge))
    rep = community.analyze(None, vault_id=1)
    assert len(rep["communities"]) == 2
    assert rep["modularity"] > 0
    # the single inter-community edge is reported as a bridge (order-normalized)
    assert len(rep["bridges"]) == 1
    b = rep["bridges"][0]
    assert {b["src"], b["dst"]} == {"wiki/a3.md", "wiki/b1.md"}
    assert b["src_community"] != b["dst_community"]
    assert b["score"] == 9  # deg(wiki/a3.md)=3 * deg(wiki/b1.md)=3


def test_analyze_hub_spans_three_communities(monkeypatch):
    # three separate K3 cliques, plus hub H linked to one node in each
    c1 = [("wiki/a1.md", "wiki/a2.md"), ("wiki/a2.md", "wiki/a3.md"), ("wiki/a1.md", "wiki/a3.md")]
    c2 = [("wiki/b1.md", "wiki/b2.md"), ("wiki/b2.md", "wiki/b3.md"), ("wiki/b1.md", "wiki/b3.md")]
    c3 = [("wiki/c1.md", "wiki/c2.md"), ("wiki/c2.md", "wiki/c3.md"), ("wiki/c1.md", "wiki/c3.md")]
    hub = [("wiki/H.md", "wiki/a1.md"), ("wiki/H.md", "wiki/b1.md"), ("wiki/H.md", "wiki/c1.md")]
    monkeypatch.setattr(community.links, "graph", lambda db, vid: _edges(c1 + c2 + c3 + hub))
    rep = community.analyze(None, vault_id=1)
    assert rep["hubs"], "expected at least one hub"
    top = rep["hubs"][0]
    assert top["relpath"] == "wiki/H.md" and len(top["communities"]) == 3


def test_analyze_min_bridge_score_filters(monkeypatch):
    clique1 = [("wiki/a1.md", "wiki/a2.md"), ("wiki/a2.md", "wiki/a3.md"), ("wiki/a1.md", "wiki/a3.md")]
    clique2 = [("wiki/b1.md", "wiki/b2.md"), ("wiki/b2.md", "wiki/b3.md"), ("wiki/b1.md", "wiki/b3.md")]
    bridge = [("wiki/a3.md", "wiki/b1.md")]  # score 9
    monkeypatch.setattr(community.links, "graph",
                        lambda db, vid: _edges(clique1 + clique2 + bridge))
    assert community.analyze(None, vault_id=1, min_bridge_score=10)["bridges"] == []


def test_analyze_empty_graph_is_safe(monkeypatch):
    monkeypatch.setattr(community.links, "graph", lambda db, vid: [])
    rep = community.analyze(None, vault_id=1)
    assert rep == {"modularity": 0.0, "communities": [], "bridges": [], "hubs": []}


def test_analyze_excludes_non_wiki_layer(monkeypatch):
    rows = _edges([("raw/source.md", "wiki/a.md"),  # cross-layer link must be dropped
                   ("wiki/a.md", "wiki/b.md"), ("wiki/b.md", "wiki/c.md"),
                   ("wiki/a.md", "wiki/c.md")])
    monkeypatch.setattr(community.links, "graph", lambda db, vid: rows)
    rep = community.analyze(None, vault_id=1)
    allnodes = {m for c in rep["communities"] for m in c["members"]}
    allnodes |= {b["src"] for b in rep["bridges"]} | {b["dst"] for b in rep["bridges"]}
    allnodes |= {h["relpath"] for h in rep["hubs"]}
    assert all(n.startswith("wiki/") for n in allnodes)
    assert "raw/source.md" not in allnodes
