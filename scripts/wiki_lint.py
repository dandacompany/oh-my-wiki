"""Wiki-mode structural lint: orphan/missing/empty/dangling checks."""
from __future__ import annotations

import difflib
import re
import time
from collections import Counter, defaultdict
from pathlib import Path

from scripts import links, registry

ORPHAN_GRACE_DAYS = 7

# Matches [[target]] or [[target|alias]] — captures the target slug
_WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:\|[^\]]+)?\]\]")

# v2.0 candidate detection
STALE_CLAIM_AGE_DAYS = 180
STALE_CLAIM_PHRASES = ("currently", "as of", "the latest")
CONTRADICTION_PAIRS = [
    ("is faster", "is not faster"),
    ("supports", "contradicts"),
    ("is", "is not"),
    ("can", "cannot"),
]
# Matches [text](./path.md) — captures relpath (without ./ prefix)
_MDLINK_RE = re.compile(r"\[[^\]]+\]\(\./([^)]+\.md)\)")

# v2.0 bidir / drift constants
LINK_BIDIR_LAYERS = {"entities", "concepts"}
TERMINOLOGY_DRIFT_THRESHOLD = 0.85

# v2.0 content-duplicate detection constants
CONTENT_DUPLICATE_THRESHOLD = 0.55
CONTENT_DUPLICATE_MIN_TOKENS = 40
_WORD_RE = re.compile(r"\w+", re.UNICODE)


def check(db_path: Path, *, vault_id: int) -> dict:
    """Return wiki structural lint report. Read-only."""
    root = registry.get_vault_root(db_path, vault_id)

    pages = _scan_pages(root)
    return {
        "vault_id": vault_id,
        "vault_path": str(root),
        # Reuse the indexed graph as the single definition shared by `omw lint`
        # and maintenance personas.  Re-deriving these from selected folders was
        # the source of cross-layer false positives.
        "orphan_pages":     links.orphans(db_path, vault_id),
        "missing_concepts": _missing_concepts_from_index(db_path, vault_id),
        "empty_data":       _empty_data(pages),
        "dangling_links":   _dangling_links(pages, root),
        # v2.0 additions:
        "contradiction_candidates": _contradiction_candidates(pages),
        "stale_claim_candidates":   _stale_claim_candidates(pages),
        "link_bidirectionality_gaps":   _link_bidirectionality_gaps(pages, root),
        "terminology_drift_candidates": _terminology_drift_candidates(pages, root),
        "content_duplicate_candidates": _content_duplicate_candidates(pages),
    }


def _scan_pages(root: Path) -> list[tuple[str, str, float]]:
    """Return [(relpath, body, mtime), ...] for wiki/* notes (excluding index/log)."""
    out = []
    wiki_dir = root / "wiki"
    if not wiki_dir.is_dir():
        return out
    for p in sorted(wiki_dir.rglob("*.md")):
        if ".trash" in p.parts:
            continue
        if p.name.endswith(".proposed.md"):
            continue
        rel = str(p.relative_to(root)).replace("\\", "/")
        if rel in {"wiki/index.md", "wiki/log.md"}:
            continue
        text = p.read_text(encoding="utf-8")
        out.append((rel, text, p.stat().st_mtime))
    return out


def _slug_from_relpath(relpath: str) -> str:
    """wiki/entities/karpathy.md -> karpathy"""
    name = relpath.rsplit("/", 1)[-1]
    return name[:-3] if name.endswith(".md") else name


def _inbound_link_counts(pages: list[tuple[str, str, float]]) -> Counter:
    counter: Counter[str] = Counter()
    for _rel, body, _mt in pages:
        for m in _WIKILINK_RE.finditer(body):
            counter[m.group(1).strip()] += 1
        for m in _MDLINK_RE.finditer(body):
            target = m.group(1)
            counter[_slug_from_relpath(target)] += 1
    return counter


def _orphan_pages(pages: list[tuple[str, str, float]]) -> list[dict]:
    inbound = _inbound_link_counts(pages)
    now = time.time()
    out = []
    for rel, _body, mt in pages:
        slug = _slug_from_relpath(rel)
        if inbound.get(slug, 0) > 0:
            continue
        age_days = int((now - mt) / 86400)
        if age_days < ORPHAN_GRACE_DAYS:
            continue
        out.append({"relpath": rel, "age_days": age_days})
    return out


def _existing_slugs(root: Path) -> set[str]:
    """Slugs that have a page in any wiki content layer."""
    out: set[str] = set()
    wiki = root / "wiki"
    if not wiki.is_dir():
        return out
    for p in wiki.rglob("*.md"):
        if ".trash" not in p.parts and not p.name.endswith(".proposed.md"):
            out.add(p.stem.lower())
    return out


def _missing_concepts_from_index(
    db_path: Path, vault_id: int, threshold: int = 2,
) -> list[dict]:
    """Unresolved wikilink targets referenced from at least `threshold` pages.

    `links.resolve` already understands every wiki layer and aliases, so this
    cannot disagree with the graph-backed `omw lint` broken-link result.
    """
    referenced_by: dict[str, set[str]] = defaultdict(set)
    for row in links.broken_links(db_path, vault_id):
        if row["link_type"] == "wikilink":
            referenced_by[row["dst_slug"]].add(row["src_relpath"])
    return [
        {"title": title, "referenced_by": sorted(refs)}
        for title, refs in sorted(referenced_by.items())
        if len(refs) >= threshold
    ]


def _missing_concepts(
    pages: list[tuple[str, str, float]],
    root: Path,
    threshold: int = 2,
) -> list[dict]:
    existing = _existing_slugs(root)
    referenced_by: dict[str, list[str]] = defaultdict(list)
    for rel, body, _mt in pages:
        seen_in_this_page: set[str] = set()
        for m in _WIKILINK_RE.finditer(body):
            tgt = m.group(1).strip()
            if tgt in seen_in_this_page:
                continue
            seen_in_this_page.add(tgt)
            if tgt not in existing:
                referenced_by[tgt].append(rel)
    out = []
    for title, refs in sorted(referenced_by.items()):
        if len(refs) >= threshold:
            out.append({"title": title, "referenced_by": refs})
    return out


EMPTY_BODY_THRESHOLD = 50  # chars after stripping frontmatter and whitespace
PLACEHOLDER_TOKENS = ("TBD", "TODO")


def _strip_frontmatter(text: str) -> str:
    """Return body after `---\\n…\\n---\\n` if present."""
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end >= 0:
            return text[end + 5:]
    return text


def _empty_data(pages: list[tuple[str, str, float]]) -> list[dict]:
    out = []
    for rel, text, _mt in pages:
        body = _strip_frontmatter(text).strip()
        if len(body) < EMPTY_BODY_THRESHOLD:
            out.append({"relpath": rel, "reason": f"body<{EMPTY_BODY_THRESHOLD}chars"})
            continue
        non_blank_lines = [ln for ln in body.split("\n") if ln.strip()]
        if not non_blank_lines:
            out.append({"relpath": rel, "reason": "no_non_blank_lines"})
            continue
        placeholder_lines = sum(
            1 for ln in non_blank_lines
            if any(tok in ln for tok in PLACEHOLDER_TOKENS)
        )
        if placeholder_lines / len(non_blank_lines) > 0.5:
            out.append({"relpath": rel, "reason": "majority_placeholders"})
    return out


def _dangling_links(
    pages: list[tuple[str, str, float]],
    root: Path,
) -> list[dict]:
    """Detect [text](./relpath.md) links whose target file doesn't exist (under wiki/)."""
    out = []
    wiki_dir = root / "wiki"
    for rel, body, _mt in pages:
        for m in _MDLINK_RE.finditer(body):
            target_rel = m.group(1)
            target_path = wiki_dir / target_rel
            if not target_path.exists():
                out.append({"source": rel, "target": target_rel})
    return out


def _contradiction_candidates(
    pages: list[tuple[str, str, float]],
) -> list[dict]:
    """For every pair of pages that share at least one wikilink target,
    flag them as a candidate if their bodies contain opposing-verb pairs.
    Final verdict is LLM-judged in commands/lint.md."""
    targets_by_page: dict[str, set[str]] = {}
    bodies_by_page: dict[str, str] = {}
    for rel, body, _mt in pages:
        targets_by_page[rel] = {m.group(1).strip() for m in _WIKILINK_RE.finditer(body)}
        bodies_by_page[rel] = body.lower()

    out: list[dict] = []
    relpaths = sorted(targets_by_page.keys())
    for i, a in enumerate(relpaths):
        for b in relpaths[i + 1:]:
            shared = targets_by_page[a] & targets_by_page[b]
            if not shared:
                continue
            body_a = bodies_by_page[a]
            body_b = bodies_by_page[b]
            for pos, neg in CONTRADICTION_PAIRS:
                if (pos in body_a and neg in body_b) or (neg in body_a and pos in body_b):
                    for entity in sorted(shared):
                        out.append({
                            "page_a": a,
                            "page_b": b,
                            "shared_entity": entity,
                            "lexicon_pair": [pos, neg],
                            "verdict": "candidate",
                        })
                    break
    return out


def _stale_claim_candidates(
    pages: list[tuple[str, str, float]],
) -> list[dict]:
    now = time.time()
    out: list[dict] = []
    for rel, body, mt in pages:
        age_days = int((now - mt) / 86400)
        if age_days < STALE_CLAIM_AGE_DAYS:
            continue
        body_lc = body.lower()
        for phrase in STALE_CLAIM_PHRASES:
            if phrase in body_lc:
                out.append({
                    "relpath": rel,
                    "claim_phrase": phrase,
                    "age_days": age_days,
                    "verdict": "candidate",
                })
                break
    return out


def _layer_of(relpath: str) -> str:
    """Returns 'summaries', 'entities', 'concepts', etc. or '' for top-level files."""
    parts = relpath.split("/")
    if len(parts) >= 3 and parts[0] == "wiki":
        return parts[1]
    return ""


def _link_bidirectionality_gaps(
    pages: list[tuple[str, str, float]],
    root: Path,
) -> list[dict]:
    """For every link A → B where A and B are both wiki pages,
    flag if B does NOT link back to A.
    Same-layer constraint: only flag when both pages are in
    LINK_BIDIR_LAYERS (entities or concepts). Cross-layer
    (summary → entity, etc.) is normal and never flagged.
    """
    slug_to_rel: dict[str, str] = {}
    for rel, _body, _mt in pages:
        slug_to_rel[_slug_from_relpath(rel)] = rel

    outgoing: dict[str, set[str]] = {rel: set() for rel, _b, _m in pages}
    for rel, body, _mt in pages:
        for m in _WIKILINK_RE.finditer(body):
            tgt = m.group(1).strip()
            if tgt in slug_to_rel:
                outgoing[rel].add(slug_to_rel[tgt])
        for m in _MDLINK_RE.finditer(body):
            tgt_slug = _slug_from_relpath(m.group(1))
            if tgt_slug in slug_to_rel:
                outgoing[rel].add(slug_to_rel[tgt_slug])

    out: list[dict] = []
    for src, targets in outgoing.items():
        src_layer = _layer_of(src)
        for tgt in targets:
            tgt_layer = _layer_of(tgt)
            same_layer = src_layer == tgt_layer
            both_in_bidir_layers = (
                src_layer in LINK_BIDIR_LAYERS and tgt_layer in LINK_BIDIR_LAYERS
            )
            if not (same_layer and both_in_bidir_layers):
                continue
            if src not in outgoing.get(tgt, set()):
                out.append({
                    "source": src,
                    "target": tgt,
                    "same_layer": True,
                })
    return out


def _word_shingles(text: str, k: int = 3) -> set[tuple[str, ...]]:
    """k-word shingles (lowercased) of the body text."""
    toks = [t.lower() for t in _WORD_RE.findall(text)]
    if len(toks) < k:
        return set()
    return {tuple(toks[i:i + k]) for i in range(len(toks) - k + 1)}


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    union = len(a | b)
    return len(a & b) / union if union else 0.0


def _content_duplicate_candidates(pages: list[tuple[str, str, float]]) -> list[dict]:
    """Pairs of pages whose BODY (frontmatter stripped) overlaps by word-trigram
    Jaccard >= CONTENT_DUPLICATE_THRESHOLD. Stubs (< CONTENT_DUPLICATE_MIN_TOKENS
    word tokens) are skipped. Orthogonal to slug similarity."""
    enriched: list[tuple[str, set]] = []
    for rel, text, _mt in pages:
        body = _strip_frontmatter(text)
        if len(_WORD_RE.findall(body)) < CONTENT_DUPLICATE_MIN_TOKENS:
            continue
        sh = _word_shingles(body)
        if sh:
            enriched.append((rel, sh))
    out: list[dict] = []
    for i in range(len(enriched)):
        rel_a, sh_a = enriched[i]
        for j in range(i + 1, len(enriched)):
            rel_b, sh_b = enriched[j]
            sim = _jaccard(sh_a, sh_b)
            if sim < CONTENT_DUPLICATE_THRESHOLD:
                continue
            slug_a = _slug_from_relpath(rel_a)
            slug_b = _slug_from_relpath(rel_b)
            out.append({
                "slug_a": slug_a,
                "slug_b": slug_b,
                "similarity": round(sim, 3),
                "suggested": f"omw merge {slug_a} {slug_b}",
            })
    return out


def _slug_similarity(a: str, b: str) -> float:
    """Return the higher of raw SequenceMatcher ratio and token-set ratio.

    Token-set ratio sorts the hyphen-delimited tokens before comparing, which
    catches "andrej-karpathy" vs "karpathy-andrej" style drift where the same
    words appear in a different order.
    """
    raw = difflib.SequenceMatcher(None, a, b).ratio()
    a_sorted = "-".join(sorted(a.split("-")))
    b_sorted = "-".join(sorted(b.split("-")))
    token_set = difflib.SequenceMatcher(None, a_sorted, b_sorted).ratio()
    return max(raw, token_set)


def _terminology_drift_candidates(
    pages: list[tuple[str, str, float]],
    root: Path,
) -> list[dict]:
    """Find pairs of existing slugs whose names are highly similar AND that
    are referenced from the same source page.

    Similarity is the max of the raw SequenceMatcher ratio and a token-set
    ratio (tokens sorted before comparison) so that word-reorder variants like
    "andrej-karpathy" / "karpathy-andrej" are also detected.
    """
    slugs: list[str] = sorted({_slug_from_relpath(rel) for rel, _b, _m in pages})

    co_ref: dict[str, set[str]] = {}
    for rel, body, _mt in pages:
        refs: set[str] = set()
        for m in _WIKILINK_RE.finditer(body):
            refs.add(m.group(1).strip())
        for m in _MDLINK_RE.finditer(body):
            refs.add(_slug_from_relpath(m.group(1)))
        co_ref[rel] = refs

    out: list[dict] = []
    seen_pairs: set[tuple[str, str]] = set()
    for i, a in enumerate(slugs):
        for b in slugs[i + 1:]:
            if (a, b) in seen_pairs:
                continue
            ratio = _slug_similarity(a, b)
            if ratio < TERMINOLOGY_DRIFT_THRESHOLD:
                continue
            co_ref_pages = sorted(
                rel for rel, refs in co_ref.items() if a in refs and b in refs
            )
            if not co_ref_pages:
                continue
            seen_pairs.add((a, b))
            out.append({
                "slug_a": a,
                "slug_b": b,
                "similarity": round(ratio, 3),
                "co_referenced_in": co_ref_pages,
            })
    return out
