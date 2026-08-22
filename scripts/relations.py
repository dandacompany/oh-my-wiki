"""One reading of frontmatter `relations:`, shared by every consumer.

Two shapes occur in real vaults:

    relations:                       relations:
      see-also: [a, b]                 - see-also: a
      derived-from: opencove           - derived-from: opencove

The mapping form is canonical (it is what `omw page write --relation` and merge emit),
but the list-of-single-key-mappings form is natural to hand-write and 27 of 84 pages in
a live vault used it. Consumers used to guard with `isinstance(rels, dict)` and skip
everything else, so those relations sat in the file feeding neither the link graph nor
valid_relations checking — a silent failure with no way for the user to notice.

Normalizing on read (rather than migrating the pages) means no vault is rewritten and
the relations start working immediately. Pure; never mutates its argument.
"""
from __future__ import annotations


def normalize(value) -> dict[str, list[str]]:
    """Return {verb: [target, ...]} for any supported shape; {} for anything else.

    A list entry with more than one key is ambiguous about ordering and grouping, so it
    is dropped rather than guessed at.
    """
    if isinstance(value, dict):
        return {k: _as_list(v) for k, v in value.items()}
    if isinstance(value, list):
        out: dict[str, list[str]] = {}
        for entry in value:
            if not isinstance(entry, dict) or len(entry) != 1:
                continue
            (verb, target), = entry.items()
            out.setdefault(verb, []).extend(_as_list(target))
        return out
    return {}


def _as_list(v) -> list:
    if isinstance(v, list):
        return list(v)
    return [] if v is None else [v]
