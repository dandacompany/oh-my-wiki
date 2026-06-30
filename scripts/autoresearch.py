"""Autoresearch: stateful 3-round (capped at 5) research loop.

LLM does the open-ended work (decompose query into claims, invoke MCP search,
read sources, judge confidence, detect gaps, draft synthesis).
This script handles deterministic state: session directory, per-round JSON
artifacts, stop criterion, and final file-back to wiki/syntheses/.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from scripts import ingest, query, registry, slugify
from scripts.paths import registry_path

MAX_ROUNDS_HARD_CAP = 5
DEFAULT_MAX_ROUNDS = 3


def _vault_row(db_path: Path, vault_id: int):
    conn = registry.connect(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM vaults WHERE id = ?", (vault_id,)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise registry.VaultError(f"unknown vault_id={vault_id}")
    return row


def init_session(
    db_path: Path,
    *,
    vault_id: int,
    query: str,
    max_rounds: int = DEFAULT_MAX_ROUNDS,
) -> dict:
    """Create .oh-my-wiki/sessions/<ts>-<slug>/ with mission.json.
    Raises registry.VaultError if vault is not wiki-mode.
    Returns {session_id, session_dir, max_rounds}.
    """
    vault = _vault_row(db_path, vault_id)
    if vault["mode"] != "wiki":
        raise registry.VaultError(
            f"autoresearch requires a wiki-mode vault; vault {vault['name']!r} is {vault['mode']!r}"
        )
    capped = min(max(1, max_rounds), MAX_ROUNDS_HARD_CAP)

    ts = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    slug = slugify.slugify(query)[:60] or "untitled"
    session_id = f"{ts}-{slug}"
    sessions_root = Path(vault["path"]) / ".oh-my-wiki" / "sessions"
    session_dir = sessions_root / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    mission = {
        "session_id": session_id,
        "query": query,
        "vault_id": vault_id,
        "vault_name": vault["name"],
        "max_rounds": capped,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    (session_dir / "mission.json").write_text(
        json.dumps(mission, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return {
        "session_id": session_id,
        "session_dir": str(session_dir),
        "max_rounds": capped,
    }


VALID_CONFIDENCE = {"high", "medium", "low"}
SOURCE_FIELDS = ("label", "url", "title", "raw_relpath")


def _normalize_source(source) -> dict:
    """A source is either a legacy string (→ {label}) or an object carrying any of
    label/url/title/raw_relpath. Keeps round JSON backward-compatible."""
    if isinstance(source, str):
        return {"label": source, "url": None, "title": None, "raw_relpath": None}
    if not isinstance(source, dict):
        raise ValueError("source must be a string or object")
    out = {k: source.get(k) for k in SOURCE_FIELDS}
    if not any(out.values()):
        raise ValueError(
            "source object must include at least one of label/url/title/raw_relpath")
    return out


def normalize_claims(claims: list[dict]) -> list[dict]:
    """Validate + normalize round claims: confidence ∈ {high,medium,low}, claim text
    required, sources normalized to the {label,url,title,raw_relpath} shape."""
    normalized = []
    for claim in claims:
        if not isinstance(claim, dict):
            raise ValueError("claim must be an object")
        text = claim.get("claim")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("claim text is required")
        confidence = claim.get("confidence")
        if confidence not in VALID_CONFIDENCE:
            raise ValueError("confidence must be one of high, medium, low")
        sources = claim.get("sources", [])
        if not isinstance(sources, list):
            raise ValueError("sources must be a list")
        normalized.append({
            "claim": text,
            "confidence": confidence,
            "sources": [_normalize_source(s) for s in sources],
        })
    return normalized


def raw_relpaths(session_dir: Path) -> list[str]:
    """Distinct raw/ files collected across all rounds (sorted) — what a
    --no-synthesis run actually filed into the vault."""
    found = set()
    for path in sorted(Path(session_dir).glob("round-*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for claim in data.get("claims", []):
            for source in claim.get("sources", []):
                if isinstance(source, dict) and source.get("raw_relpath"):
                    found.add(source["raw_relpath"])
    return sorted(found)


def record_round(
    session_dir: Path,
    *,
    round_num: int,
    claims: list[dict],
    gaps_remaining: list[str],
    notes: str = "",
) -> Path:
    """Write round-N.json into session_dir. Idempotent (overwrites)."""
    session_dir = Path(session_dir)
    mission_path = session_dir / "mission.json"
    if not mission_path.exists():
        raise FileNotFoundError(f"no mission.json in {session_dir}")
    mission = json.loads(mission_path.read_text(encoding="utf-8"))
    max_rounds = mission["max_rounds"]
    if not (1 <= round_num <= max_rounds):
        raise ValueError(
            f"round_num={round_num} out of bounds (1..{max_rounds})"
        )
    payload = {
        "round_num": round_num,
        "claims": normalize_claims(claims),
        "gaps_remaining": list(gaps_remaining),
        "notes": notes,
        "recorded_at": datetime.now().isoformat(timespec="seconds"),
    }
    target = session_dir / f"round-{round_num}.json"
    target.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return target


def should_stop(session_dir: Path) -> tuple[bool, str]:
    """Return (stop, reason). reason ∈ {max_rounds, no_gaps, in_progress}."""
    session_dir = Path(session_dir)
    mission_path = session_dir / "mission.json"
    if not mission_path.exists():
        raise FileNotFoundError(f"no mission.json in {session_dir}")
    mission = json.loads(mission_path.read_text(encoding="utf-8"))
    max_rounds = mission["max_rounds"]

    round_files = sorted(session_dir.glob("round-*.json"))
    if not round_files:
        return (False, "in_progress")

    last = json.loads(round_files[-1].read_text(encoding="utf-8"))
    if not last["gaps_remaining"]:
        return (True, "no_gaps")
    if len(round_files) >= max_rounds:
        return (True, "max_rounds")
    return (False, "in_progress")


def _derive_summary(body: str, *, cap: int = 240) -> str:
    """First real prose paragraph of the synthesis body (skips headings/blank/markers),
    truncated. Used as frontmatter `summary` so the page ranks in search/recall."""
    for para in (body or "").split("\n\n"):
        line = " ".join(para.split())
        if not line or line.startswith("#") or line.startswith("**Claim"):
            continue
        return line[:cap].rstrip() + ("…" if len(line) > cap else "")
    return ""


def file_back(
    db_path: Path,
    *,
    vault_id: int,
    session_dir: Path,
    title: str,
    body: str,
    citations: list[str],
    tags: list[str],
    date_str: str,
) -> str:
    """Write synthesis page + update index + append log + mark session filed.
    Idempotent: if filed.json already exists, returns the previously-filed relpath
    without doing any further writes.
    """
    session_dir = Path(session_dir)
    filed_path = session_dir / "filed.json"
    if filed_path.exists():
        existing = json.loads(filed_path.read_text(encoding="utf-8"))
        return existing["synthesis_relpath"]

    relpath = query.write_synthesis(
        db_path,
        vault_id=vault_id,
        title=title,
        body=body,
        citations=citations,
        tags=tags,
        date_str=date_str,
        summary=_derive_summary(body),
    )
    slug = relpath.removeprefix("wiki/syntheses/").removesuffix(".md")
    ingest.update_index(
        db_path,
        vault_id=vault_id,
        entries=[("syntheses", slug, title)],
    )
    ingest.append_log(
        db_path,
        vault_id=vault_id,
        op="autoresearch",
        title=title,
        date_str=date_str,
    )
    filed = {
        "synthesis_relpath": relpath,
        "filed_at": datetime.now().isoformat(timespec="seconds"),
    }
    filed_path.write_text(
        json.dumps(filed, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return relpath


def session_status(session_dir: Path) -> dict:
    """For commands/autoresearch.md and debug."""
    session_dir = Path(session_dir)
    mission = json.loads((session_dir / "mission.json").read_text(encoding="utf-8"))
    round_files = sorted(session_dir.glob("round-*.json"))
    last_gaps: list[str] = []
    if round_files:
        last = json.loads(round_files[-1].read_text(encoding="utf-8"))
        last_gaps = list(last["gaps_remaining"])
    filed = (session_dir / "filed.json").exists()
    return {
        "query": mission["query"],
        "rounds_completed": len(round_files),
        "max_rounds": mission["max_rounds"],
        "last_gaps": last_gaps,
        "filed": filed,
        "raw_relpaths": raw_relpaths(session_dir),
    }


def main(argv: list[str] | None = None) -> int:
    import argparse
    import sys as _sys

    p = argparse.ArgumentParser(prog="scripts.autoresearch")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init")
    p_init.add_argument("--db", default=None)
    p_init.add_argument("--vault-id", type=int)
    p_init.add_argument("--query", required=True)
    p_init.add_argument("--max-rounds", type=int, default=DEFAULT_MAX_ROUNDS)

    p_rec = sub.add_parser("record")
    p_rec.add_argument("--session-dir", required=True)
    p_rec.add_argument("--round", dest="round_num", type=int, required=True)
    p_rec.add_argument("--claims-json", default="[]")
    p_rec.add_argument("--gaps-json", default="[]")
    p_rec.add_argument("--notes", default="")

    p_stop = sub.add_parser("should-stop")
    p_stop.add_argument("--session-dir", required=True)

    p_stat = sub.add_parser("status")
    p_stat.add_argument("--session-dir", required=True)

    p_file = sub.add_parser("file-back")
    p_file.add_argument("--db", default=None)
    p_file.add_argument("--vault-id", type=int)
    p_file.add_argument("--session-dir", required=True)
    p_file.add_argument("--title", required=True)
    p_file.add_argument("--body-file", required=True,
                        help="Path to a file containing the synthesis body (UTF-8)")
    p_file.add_argument("--citations-json", default="[]")
    p_file.add_argument("--tags-json", default="[]")
    p_file.add_argument("--date", dest="date_str", required=True)

    args = p.parse_args(argv)

    # db only needed for init / file-back; safe-default otherwise
    db_path = Path(args.db) if getattr(args, "db", None) else registry_path()

    def _resolve_vault_id(default_id: int | None) -> int:
        if default_id is not None:
            return default_id
        active = registry.get_active(db_path)
        if active is None:
            print("no active vault — run vault-use first", file=_sys.stderr)
            raise SystemExit(2)
        return active["id"]

    if args.cmd == "init":
        vid = _resolve_vault_id(args.vault_id)
        info = init_session(
            db_path, vault_id=vid, query=args.query, max_rounds=args.max_rounds
        )
        print(json.dumps(info, ensure_ascii=False))
        return 0

    if args.cmd == "record":
        claims = json.loads(args.claims_json)
        gaps = json.loads(args.gaps_json)
        path = record_round(
            Path(args.session_dir),
            round_num=args.round_num,
            claims=claims,
            gaps_remaining=gaps,
            notes=args.notes,
        )
        print(json.dumps({"round_file": str(path)}, ensure_ascii=False))
        return 0

    if args.cmd == "should-stop":
        stop, reason = should_stop(Path(args.session_dir))
        print(json.dumps({"stop": stop, "reason": reason}))
        return 0

    if args.cmd == "status":
        s = session_status(Path(args.session_dir))
        print(json.dumps(s, ensure_ascii=False))
        return 0

    if args.cmd == "file-back":
        vid = _resolve_vault_id(args.vault_id)
        body = Path(args.body_file).read_text(encoding="utf-8")
        citations = json.loads(args.citations_json)
        tags = json.loads(args.tags_json)
        relpath = file_back(
            db_path,
            vault_id=vid,
            session_dir=Path(args.session_dir),
            title=args.title,
            body=body,
            citations=citations,
            tags=tags,
            date_str=args.date_str,
        )
        print(relpath)
        return 0

    raise SystemExit(f"unknown cmd: {args.cmd}")


if __name__ == "__main__":
    raise SystemExit(main())
