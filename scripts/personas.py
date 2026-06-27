"""Writing-agent persona framework.

Personas live at personas/<role>.md with YAML frontmatter that declares
the persona's name, description, capabilities, required tools, model hint,
input kinds, and output kind. The body is the prompt template the LLM
follows when invoked.

This module never calls an LLM. It loads + validates persona definitions
and provides deterministic I/O (resolve input, resolve output path, write
output). The LLM does the cognitive work via commands/persona-<role>.md.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from scripts import frontmatter, paths, registry
from scripts.paths import registry_path

PERSONAS_ROOT = paths.bundled_dir("personas")

VALID_OUTPUT_KINDS = {"sibling_file", "sibling_suffix", "inplace", "new_page", "stdout"}
VALID_MODEL_HINTS = {"fast", "standard", "most_capable"}
REQUIRED_FRONTMATTER_KEYS = (
    "name", "description", "capabilities", "tools",
    "model_hint", "input_kinds", "output_kind",
)


class PersonaError(Exception):
    """Raised for unknown persona, invalid frontmatter, missing input, etc."""


def _parse_persona_text(text: str) -> dict:
    """Internal: parse a persona markdown file's text into a spec dict."""
    try:
        meta, body = frontmatter.parse(text)
    except frontmatter.FrontmatterError as exc:
        raise PersonaError(f"malformed frontmatter: {exc}") from exc
    for key in REQUIRED_FRONTMATTER_KEYS:
        if key not in meta:
            raise PersonaError(f"missing required key in frontmatter: {key!r}")
    if meta["output_kind"] not in VALID_OUTPUT_KINDS:
        raise PersonaError(
            f"invalid output_kind: {meta['output_kind']!r} "
            f"(valid: {sorted(VALID_OUTPUT_KINDS)})"
        )
    if meta["model_hint"] not in VALID_MODEL_HINTS:
        raise PersonaError(
            f"invalid model_hint: {meta['model_hint']!r} "
            f"(valid: {sorted(VALID_MODEL_HINTS)})"
        )
    if not isinstance(meta["capabilities"], list):
        raise PersonaError("capabilities must be a list")
    if not isinstance(meta["tools"], list):
        raise PersonaError("tools must be a list")
    if not isinstance(meta["input_kinds"], list) or not meta["input_kinds"]:
        raise PersonaError("input_kinds must be a non-empty list")
    spec = dict(meta)
    spec["body"] = body
    return spec


def list_personas() -> list[dict]:
    """Return [{name, description, capabilities, tools, model_hint,
    input_kinds, output_kind}, ...] for every persona under personas/."""
    out = []
    if not PERSONAS_ROOT.is_dir():
        return out
    for md in sorted(PERSONAS_ROOT.glob("*.md")):
        try:
            spec = _parse_persona_text(md.read_text(encoding="utf-8"))
        except PersonaError:
            continue
        entry = {k: spec[k] for k in REQUIRED_FRONTMATTER_KEYS}
        # optional routing keywords (used by persona_export's dispatch table)
        triggers = spec.get("triggers")
        entry["triggers"] = list(triggers) if isinstance(triggers, list) else []
        out.append(entry)
    return out


def load_persona(name: str) -> dict:
    """Return the full persona spec (frontmatter dict + 'body' key)."""
    target = PERSONAS_ROOT / f"{name}.md"
    if not target.exists():
        raise PersonaError(f"unknown persona: {name!r}")
    return _parse_persona_text(target.read_text(encoding="utf-8"))


def resolve_input(
    *,
    text: str | None = None,
    file_path: Path | None = None,
    vault_relpath: str | None = None,
    db_path: Path | None = None,
    vault_id: int | None = None,
) -> tuple[str, dict]:
    """Resolve exactly one input source into (content, source_meta).
    source_meta = {kind, origin} where kind ∈ {text, file, vault_page}.
    """
    provided = sum(
        x is not None for x in (text, file_path, vault_relpath)
    )
    if provided == 0:
        raise PersonaError("no input provided (need text, file_path, or vault_relpath)")
    if provided > 1:
        raise PersonaError("exactly one of text, file_path, vault_relpath required")

    if text is not None:
        return text, {"kind": "text", "origin": None}

    if file_path is not None:
        fp = Path(file_path)
        if not fp.exists():
            raise PersonaError(f"file not found: {fp}")
        return fp.read_text(encoding="utf-8"), {"kind": "file", "origin": fp}

    # vault_relpath
    if db_path is None or vault_id is None:
        raise PersonaError("vault_relpath requires db_path and vault_id")
    try:
        vault_root = registry.get_vault_root(db_path, vault_id)
    except registry.VaultError as e:
        raise PersonaError(f"unknown vault_id={vault_id}") from e
    abs_path = vault_root / vault_relpath
    if not abs_path.exists():
        raise PersonaError(f"vault page not found: {vault_relpath}")
    return (
        abs_path.read_text(encoding="utf-8"),
        {"kind": "vault_page", "origin": abs_path},
    )


def resolve_output_path(
    *,
    persona: dict,
    source_meta: dict,
    db_path: Path | None = None,
    vault_id: int | None = None,
    lang: str | None = None,
    title: str | None = None,
    suffix: str | None = None,
) -> Path | None:
    """Compute where this persona's output should be filed.
    Returns None for stdout kind."""
    from scripts import slugify as _slugify
    kind = persona["output_kind"]

    if kind == "stdout":
        return None

    if kind == "sibling_file":
        if not lang:
            raise PersonaError("sibling_file output requires lang= argument")
        origin = source_meta.get("origin")
        if origin is None:
            raise PersonaError("sibling_file output requires source with origin path")
        origin = Path(origin)
        stem = origin.stem
        return origin.with_name(f"{stem}.{lang}{origin.suffix}")

    if kind == "sibling_suffix":
        if not suffix:
            raise PersonaError("sibling_suffix output requires suffix= argument")
        origin = source_meta.get("origin")
        if origin is None:
            raise PersonaError("sibling_suffix output requires source with origin path")
        origin = Path(origin)
        stem = origin.stem
        return origin.with_name(f"{stem}.{suffix}{origin.suffix}")

    if kind == "inplace":
        origin = source_meta.get("origin")
        if origin is None:
            raise PersonaError("inplace output requires source with origin path")
        return Path(origin)

    if kind == "new_page":
        if not title:
            raise PersonaError("new_page output requires title= argument")
        if db_path is None or vault_id is None:
            raise PersonaError("new_page output requires db_path and vault_id")
        slug = _slugify.slugify(title)
        try:
            vault_root = registry.get_vault_root(db_path, vault_id)
        except registry.VaultError as e:
            raise PersonaError(f"unknown vault_id={vault_id}") from e
        return vault_root / "wiki" / "syntheses" / f"{slug}.md"

    raise PersonaError(f"unsupported output_kind: {kind!r}")


def write_output(
    *,
    persona: dict,
    target_path: Path | None,
    content: str,
    source_meta: dict,
    backup_dir: Path | None = None,
) -> Path | None:
    """File the LLM-produced content per persona's output contract.
    Returns the actual path written, or None for stdout kind."""
    kind = persona["output_kind"]

    if kind == "stdout":
        return None

    if target_path is None:
        raise PersonaError(f"output_kind={kind!r} requires a target_path")

    target = Path(target_path)

    if kind == "inplace" and backup_dir is not None and target.exists():
        backup_dir = Path(backup_dir)
        backup_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        backup_name = f"{ts}-{target.name}"
        backup_path = backup_dir / backup_name
        backup_path.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json as _json
    import sys as _sys

    p = argparse.ArgumentParser(prog="scripts.personas")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="List all personas (JSON)")

    p_show = sub.add_parser("show", help="Show one persona's full spec (JSON)")
    p_show.add_argument("name")

    p_run = sub.add_parser("run", help="File pre-written LLM output per persona contract")
    p_run.add_argument("name")
    p_run.add_argument("--db", default=None)
    p_run.add_argument("--vault-id", type=int)
    grp_in = p_run.add_mutually_exclusive_group(required=True)
    grp_in.add_argument("--text")
    grp_in.add_argument("--file", dest="file_path")
    grp_in.add_argument("--vault-relpath")
    p_run.add_argument("--lang", help="target language for sibling_file (e.g. ko)")
    p_run.add_argument("--suffix",
                       help="suffix for sibling_suffix output kind (e.g. factcheck)")
    p_run.add_argument("--title", help="title for new_page output kind")
    p_run.add_argument("--output-file", required=True,
                       help="path to file containing the LLM-produced output")
    p_run.add_argument("--backup-dir",
                       help="for inplace output: directory to back up original")

    args = p.parse_args(argv)

    if args.cmd == "list":
        print(_json.dumps(list_personas(), ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "show":
        try:
            spec = load_persona(args.name)
        except PersonaError as exc:
            print(str(exc), file=_sys.stderr)
            return 2
        print(_json.dumps(spec, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "run":
        try:
            persona = load_persona(args.name)
        except PersonaError as exc:
            print(str(exc), file=_sys.stderr)
            return 2

        db_path = Path(args.db) if args.db else registry_path()
        try:
            _, source_meta = resolve_input(
                text=args.text,
                file_path=Path(args.file_path) if args.file_path else None,
                vault_relpath=args.vault_relpath,
                db_path=db_path if args.vault_relpath else None,
                vault_id=args.vault_id if args.vault_relpath else None,
            )
        except PersonaError as exc:
            print(str(exc), file=_sys.stderr)
            return 2

        output_content = Path(args.output_file).read_text(encoding="utf-8")

        if persona["output_kind"] == "stdout":
            print(output_content)
            return 0

        try:
            target_path = resolve_output_path(
                persona=persona,
                source_meta=source_meta,
                db_path=db_path,
                vault_id=args.vault_id,
                lang=args.lang,
                title=args.title,
                suffix=args.suffix,
            )
        except PersonaError as exc:
            print(str(exc), file=_sys.stderr)
            return 2

        backup_dir = Path(args.backup_dir) if args.backup_dir else None
        result = write_output(
            persona=persona,
            target_path=target_path,
            content=output_content,
            source_meta=source_meta,
            backup_dir=backup_dir,
        )
        if result is not None:
            print(str(result))
        return 0

    raise SystemExit(f"unknown cmd: {args.cmd}")


if __name__ == "__main__":
    raise SystemExit(main())
