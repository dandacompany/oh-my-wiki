# scripts/community.py
"""Deterministic community detection over the wiki link graph (zero deps, zero tokens).

Greedy modularity (Clauset–Newman–Moore) on the undirected, weighted graph built from
`links.graph()` resolved edges. Used by `omw connections` to surface communities,
bridges (cross-community edges = "surprising connections"), and hubs. Pure stdlib;
fully deterministic (sorted iteration + id renumbering by smallest member)."""
from __future__ import annotations

from scripts import links

_META = set(links.META_RELPATHS)


def _build_graph(edges):
    """(adj, deg) from links.graph() rows. Undirected, weighted, no self-loops, no META."""
    adj: dict[str, dict[str, int]] = {}
    for e in edges or []:
        if not e.get("resolved"):
            continue
        u, v = e.get("src_relpath"), e.get("dst_relpath")
        if not u or not v or u == v or u in _META or v in _META:
            continue
        adj.setdefault(u, {})
        adj.setdefault(v, {})
        adj[u][v] = adj[u].get(v, 0) + 1
        adj[v][u] = adj[v].get(u, 0) + 1
    deg = {u: sum(nbrs.values()) for u, nbrs in adj.items()}
    return adj, deg


def _renumber(labels: dict[str, int]) -> dict[str, int]:
    """Renumber community ids 0..k-1 by each community's smallest member (sorted),
    so labels are stable regardless of internal merge order."""
    members: dict[int, list[str]] = {}
    for node, cid in labels.items():
        members.setdefault(cid, []).append(node)
    order = sorted(members, key=lambda c: min(members[c]))
    remap = {old: new for new, old in enumerate(order)}
    return {node: remap[cid] for node, cid in labels.items()}


def _modularity(adj, deg, labels, two_m: int) -> float:
    """Standard weighted modularity Q for the given partition (all-pairs O(n²) sum)."""
    if two_m == 0:
        return 0.0
    nodes = list(adj)
    q = 0.0
    for u in nodes:
        for v in nodes:
            if labels[u] == labels[v]:
                w = adj[u].get(v, 0)
                q += w - deg[u] * deg[v] / two_m
    return q / two_m


def detect(edges):
    """Greedy-modularity partition. Returns (labels {relpath: community_id}, modularity).
    Deterministic: candidate merges are scanned in sorted order, ΔQ ties broken by the
    lexicographically smallest community key; ids renumbered by smallest member."""
    adj, deg = _build_graph(edges)
    if not adj:
        return {}, 0.0
    two_m = sum(deg.values())  # = 2 * total edge weight

    # community state: cid -> set(nodes); per-community total degree; inter-community weights
    comm: dict[int, set[str]] = {}
    cdeg: dict[int, int] = {}
    node_comm: dict[str, int] = {}
    for i, node in enumerate(sorted(adj)):
        comm[i] = {node}
        cdeg[i] = deg[node]
        node_comm[node] = i

    def between(ci: int, cj: int) -> int:
        a, b = comm[ci], comm[cj]
        small, big = (a, b) if len(a) <= len(b) else (b, a)
        tot = 0
        for u in small:
            for v, w in adj[u].items():
                if v in big:
                    tot += w
        return tot

    while True:
        # adjacency between communities (sorted candidate pairs for determinism)
        pairs = set()
        for u in adj:
            cu = node_comm[u]
            for v in adj[u]:
                cv = node_comm[v]
                if cu != cv:
                    pairs.add((min(cu, cv), max(cu, cv)))
        best = None  # (dQ, ci, cj)
        for ci, cj in sorted(pairs):
            e_ij = 2 * between(ci, cj) / two_m        # undirected edge fraction: between() counts once, *2 normalises
            a_i, a_j = cdeg[ci] / two_m, cdeg[cj] / two_m
            dQ = e_ij - 2 * a_i * a_j                 # standard CNM ΔQ
            if best is None or dQ > best[0] + 1e-12:
                best = (dQ, ci, cj)
        if best is None or best[0] <= 0:
            break
        _, ci, cj = best
        # merge cj into ci
        for n in comm[cj]:
            node_comm[n] = ci
        comm[ci] |= comm[cj]
        cdeg[ci] += cdeg[cj]
        del comm[cj]
        del cdeg[cj]

    labels = _renumber(dict(node_comm))
    return labels, round(_modularity(adj, deg, labels, two_m), 4)


def analyze(db_path, *, vault_id: int, min_bridge_score: int = 0) -> dict:
    """Communities + bridges (cross-community edges) + hubs (nodes adjacent to ≥2
    communities) over the vault's resolved link graph. Read-only; never raises.

    Only wiki-layer pages are considered: edges where either endpoint does not start
    with 'wiki/' or is a META page (index, log) are dropped before graph construction."""
    rows = links.graph(db_path, vault_id)
    edges = [r for r in (rows or [])
             if str(r.get("src_relpath", "")).startswith("wiki/")
             and str(r.get("dst_relpath", "")).startswith("wiki/")
             and r.get("src_relpath") not in _META
             and r.get("dst_relpath") not in _META]
    adj, deg = _build_graph(edges)
    labels, modularity = detect(edges)
    if not adj:
        return {"modularity": 0.0, "communities": [], "bridges": [], "hubs": []}

    members: dict[int, list[str]] = {}
    for node, cid in labels.items():
        members.setdefault(cid, []).append(node)
    communities = sorted(
        ({"id": cid, "size": len(ms), "members": sorted(ms)} for cid, ms in members.items()),
        key=lambda c: (-c["size"], c["id"]),
    )

    bridges = []
    seen = set()
    for u in sorted(adj):
        for v in sorted(adj[u]):
            if labels[u] == labels[v]:
                continue
            key = tuple(sorted((u, v)))
            if key in seen:
                continue
            seen.add(key)
            src, dst = key
            score = deg[src] * deg[dst]
            if score < min_bridge_score:
                continue
            bridges.append({"src": src, "dst": dst,
                            "src_community": labels[src], "dst_community": labels[dst],
                            "weight": adj[u][v], "score": score})
    bridges.sort(key=lambda b: (-b["score"], b["src"], b["dst"]))

    hubs = []
    for u in sorted(adj):
        nbr_comms = sorted({labels[v] for v in adj[u]})
        if len(nbr_comms) >= 2:
            hubs.append({"relpath": u, "communities": nbr_comms, "degree": deg[u]})
    hubs.sort(key=lambda h: (-len(h["communities"]), -h["degree"], h["relpath"]))

    return {"modularity": modularity, "communities": communities,
            "bridges": bridges, "hubs": hubs}
