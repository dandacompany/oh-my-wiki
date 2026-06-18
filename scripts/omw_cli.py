"""User-facing omw CLI: deterministic ops + the setup wizard entrypoint.

The human-facing tool (install + setup + deterministic vault management).
Natural-language work (ingest/query/research/personas) happens inside a Claude
session via the omw skill; the skill may call these deterministic subcommands.
"""
from __future__ import annotations

import argparse
import json
import sys

from scripts import adapters, lint, registry, reindex, wizard
from scripts.paths import ensure_home, registry_path, resolve_vault_root

AGENTIC_OPS = [
    "ingest", "query", "find", "open", "edit", "move", "delete",
    "autoresearch", "persona-translate", "persona-polish", "persona-summarize",
    "persona-scaffold", "persona-factcheck", "persona-consistency",
    "persona-terminology", "dispatch", "team", "team-run", "swarm-monitor",
]


def _cmd_status(args) -> int:
    ensure_home()
    db = registry_path()
    # Compute status BEFORE any init so a pending legacy migration stays visible;
    # only auto-init on the fresh-setup path (mirrors wizard.main()).
    result = wizard.status(db)
    if result["needs"] != "migrate" and not db.exists():
        registry.init_db(db)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _cmd_vault_list(args) -> int:
    db = registry_path()
    if not db.exists():
        print("[]")
        return 0
    out = [
        {
            "name": v["name"],
            "path": v["path"],
            "mode": v["mode"],
            "type": v["type"],
            "is_active": bool(v["is_active"]),
        }
        for v in registry.list_vaults(db)
    ]
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def _cmd_vault_create(args) -> int:
    ensure_home()
    db = registry_path()
    registry.init_db(db)
    root = resolve_vault_root(args.name, args.location)
    root.mkdir(parents=True, exist_ok=True)
    adapters.get_adapter(args.type, vault_name=args.name).init_vault(root, args.mode)
    try:
        vault = registry.add_vault(
            db, name=args.name, path=root, type_=args.type, mode=args.mode
        )
    except registry.VaultError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    registry.set_active(db, args.name)
    reindex.full(db, vault_id=vault["id"])
    print(json.dumps(
        {"created": args.name, "path": str(root), "mode": args.mode, "type": args.type},
        ensure_ascii=False,
    ))
    return 0


def _cmd_vault_use(args) -> int:
    db = registry_path()
    if not db.exists():
        print("error: no registry; run `omw status` first", file=sys.stderr)
        return 1
    try:
        registry.set_active(db, args.name)
    except registry.VaultError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"active vault: {args.name}")
    return 0


def _cmd_vault_forget(args) -> int:
    db = registry_path()
    if not db.exists():
        print("error: no registry; run `omw status` first", file=sys.stderr)
        return 1
    try:
        registry.forget_vault(db, args.name)
    except registry.VaultError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"forgot vault: {args.name} (files untouched)")
    return 0


def _cmd_lint(args) -> int:
    db = registry_path()
    if not db.exists():
        print("error: no registry; run `omw status` to set up", file=sys.stderr)
        return 1
    if args.vault:
        match = [v for v in registry.list_vaults(db) if v["name"] == args.vault]
        if not match:
            print(f"error: vault {args.vault!r} not found", file=sys.stderr)
            return 1
        vault_id = match[0]["id"]
    else:
        active = registry.get_active(db)
        if active is None:
            print("error: no active vault; pass --vault <name>", file=sys.stderr)
            return 1
        vault_id = active["id"]
    print(json.dumps(lint.check(db, vault_id=vault_id), ensure_ascii=False, indent=2))
    return 0


def _cmd_fields(args) -> int:
    from pathlib import Path
    from scripts import frontmatter, inline_fields
    db = registry_path()
    if not db.exists():
        print("error: no registry; run `omw status` to set up", file=sys.stderr)
        return 1
    if args.vault:
        row = next((v for v in registry.list_vaults(db) if v["name"] == args.vault), None)
        if row is None:
            print(f"error: vault {args.vault!r} not found", file=sys.stderr)
            return 1
    else:
        row = registry.get_active(db)
        if row is None:
            print("error: no active vault; pass --vault <name>", file=sys.stderr)
            return 1
    abs_path = Path(row["path"]) / args.relpath
    if not abs_path.exists():
        print(f"error: page not found: {args.relpath}", file=sys.stderr)
        return 1
    text = abs_path.read_text(encoding="utf-8")
    try:
        meta, body = frontmatter.parse(text)
    except frontmatter.FrontmatterError:
        meta, body = {}, text
    print(json.dumps({
        "relpath": args.relpath,
        "frontmatter": meta,
        "inline": inline_fields.extract_inline_fields(body),
    }, ensure_ascii=False, indent=2, default=str))  # default=str: YAML date/datetime → ISO
    return 0


def _cmd_links(args) -> int:
    from scripts import entity_link
    db = registry_path()
    if not db.exists():
        print("error: no registry; run `omw status` to set up", file=sys.stderr)
        return 1
    if args.vault:
        match = [v for v in registry.list_vaults(db) if v["name"] == args.vault]
        if not match:
            print(f"error: vault {args.vault!r} not found", file=sys.stderr)
            return 1
        vault_id = match[0]["id"]
    else:
        active = registry.get_active(db)
        if active is None:
            print("error: no active vault; pass --vault <name>", file=sys.stderr)
            return 1
        vault_id = active["id"]
    if args.links_cmd == "suggest":
        rows = entity_link.suggest_links(db, vault_id=vault_id, relpath=args.relpath)
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    try:
        out = entity_link.apply_link(db, vault_id=vault_id, relpath=args.relpath,
                                     target_slug=args.to)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def _cmd_review(args) -> int:
    from datetime import date
    from scripts import review
    db = registry_path()
    if not db.exists():
        print("error: no registry; run `omw status` to set up", file=sys.stderr)
        return 1
    if args.vault:
        match = [v for v in registry.list_vaults(db) if v["name"] == args.vault]
        if not match:
            print(f"error: vault {args.vault!r} not found", file=sys.stderr)
            return 1
        vault_id = match[0]["id"]
    else:
        active = registry.get_active(db)
        if active is None:
            print("error: no active vault; pass --vault <name>", file=sys.stderr)
            return 1
        vault_id = active["id"]
    today = args.today or date.today().isoformat()
    if args.review_cmd == "due":
        rows = review.due_pages(db, vault_id=vault_id, today=today,
                                include_unscheduled=not args.scheduled_only)
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    try:
        out = review.reschedule(db, vault_id=vault_id, relpath=args.relpath,
                                grade=args.grade, today=today)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def _cmd_visibility(args) -> int:
    from pathlib import Path
    from scripts import frontmatter, reindex
    db = registry_path()
    if not db.exists():
        print("error: no registry; run `omw status` to set up", file=sys.stderr)
        return 1
    if args.vault:
        match = [v for v in registry.list_vaults(db) if v["name"] == args.vault]
        if not match:
            print(f"error: vault {args.vault!r} not found", file=sys.stderr)
            return 1
        vault = match[0]
    else:
        vault = registry.get_active(db)
        if vault is None:
            print("error: no active vault; pass --vault <name>", file=sys.stderr)
            return 1
    root = Path(vault["path"])

    if args.visibility_cmd == "get":
        abs_path = root / args.relpath
        if not abs_path.exists():
            print(f"error: page not found: {args.relpath}", file=sys.stderr)
            return 1
        try:
            meta, _ = frontmatter.parse(abs_path.read_text(encoding="utf-8"))
        except frontmatter.FrontmatterError:
            meta = {}
        print(json.dumps({"relpath": args.relpath,
                          "visibility": meta.get("visibility") or "private"},
                         ensure_ascii=False, indent=2))
        return 0

    # set: args.targets is [relpath..., value]
    *relpaths, value = args.targets
    if value not in ("public", "private"):
        print("error: last argument must be 'public' or 'private'", file=sys.stderr)
        return 1
    if not relpaths:
        print("error: provide at least one relpath before the value", file=sys.stderr)
        return 1
    updated, missing, failed = [], [], []
    for rel in relpaths:
        abs_path = root / rel
        if not abs_path.exists():
            missing.append(rel)
            continue
        text = abs_path.read_text(encoding="utf-8")
        try:
            new_text = frontmatter.edit_field(text, "visibility", value)
        except frontmatter.FrontmatterError:
            failed.append(rel)   # malformed frontmatter — skip, don't crash
            continue
        abs_path.write_text(new_text, encoding="utf-8")
        updated.append(rel)
    if updated:
        reindex.incremental(db, vault_id=vault["id"])
    print(json.dumps({"set": value, "updated": updated, "missing": missing, "failed": failed},
                     ensure_ascii=False, indent=2))
    # any non-updated target (missing or malformed) → nonzero exit so `&&` chains notice
    return 1 if (missing or failed) else 0


def _cmd_supersede(args) -> int:
    from scripts import supersede
    db = registry_path()
    if not db.exists():
        print("error: no registry; run `omw status` to set up", file=sys.stderr)
        return 1
    if args.vault:
        match = [v for v in registry.list_vaults(db) if v["name"] == args.vault]
        if not match:
            print(f"error: vault {args.vault!r} not found", file=sys.stderr)
            return 1
        vault_id = match[0]["id"]
    else:
        active = registry.get_active(db)
        if active is None:
            print("error: no active vault; pass --vault <name>", file=sys.stderr)
            return 1
        vault_id = active["id"]
    try:
        out = supersede.mark_superseded(db, vault_id=vault_id, relpath=args.relpath,
                                        by_slug=args.by)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def _resolve_vault_path(db, name):
    """Return a vault's content path by name (or active). None if unresolved."""
    if not db.exists():
        return None
    if name:
        row = next((v for v in registry.list_vaults(db) if v["name"] == name), None)
    else:
        row = registry.get_active(db)
    return row["path"] if row else None


def _resolve_vault_row(db, name):
    if name:
        match = [v for v in registry.list_vaults(db) if v["name"] == name]
        return match[0] if match else None
    return registry.get_active(db)


def _cmd_inbox(args) -> int:
    from datetime import date
    from scripts import inbox
    db = registry_path()
    if not db.exists():
        print("error: no registry; run `omw status` to set up", file=sys.stderr)
        return 1
    vault = _resolve_vault_row(db, args.vault)
    if vault is None:
        print("error: no active vault; pass --vault <name>", file=sys.stderr)
        return 1
    vid = vault["id"]
    if args.inbox_cmd == "add":
        row = inbox.add(db, vault_id=vid, url=args.url)
        print(json.dumps({"queued": row["url"], "normalized": row["normalized_url"],
                          "deduped": row["deduped"]}, ensure_ascii=False, indent=2))
        return 0
    if args.inbox_cmd == "list":
        print(json.dumps(inbox.list_items(db, vault_id=vid), ensure_ascii=False, indent=2))
        return 0
    if args.inbox_cmd == "remove":
        n = inbox.remove(db, vault_id=vid, url=args.url)
        print(json.dumps({"removed": n}, ensure_ascii=False))
        return 0 if n else 1
    if args.inbox_cmd == "run":
        today = args.today or date.today().isoformat()
        result = inbox.run(db, vault_id=vid, today=today, html_backend=args.backend)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result["failed"] else 0
    return 1


def _cmd_fetch(args) -> int:
    import sqlite3
    from datetime import date
    from scripts import fetch, ingest, reindex, search
    from scripts.fetch_errors import FetchError
    db = registry_path()
    if not db.exists():
        print("error: no registry; run `omw status` to set up", file=sys.stderr)
        return 1
    vault = _resolve_vault_row(db, args.vault)
    if vault is None:
        print("error: no active vault; pass --vault <name>", file=sys.stderr)
        return 1
    try:
        res = fetch.fetch_url(args.url, html_backend=args.backend)
    except (FetchError, search.SearchError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    try:
        relpath = ingest.save_raw(db, vault_id=vault["id"], content=res["text"], ext="md",
                                  title=res["title"] or args.url,
                                  date_str=args.today or date.today().isoformat())
        reindex.incremental(db, vault_id=vault["id"])
    except (OSError, sqlite3.Error) as exc:
        print(f"error: saving fetched content failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"raw_relpath": relpath, "title": res["title"],
                      "backend": res["backend"], "source_url": res["source_url"]},
                     ensure_ascii=False, indent=2))
    return 0


def _cmd_schema(args) -> int:
    from scripts import schema
    db = registry_path()
    vault_path = None
    if args.vault:
        vault_path = _resolve_vault_path(db, args.vault)
        if vault_path is None:
            print(f"error: vault {args.vault!r} not found", file=sys.stderr)
            return 1
    schemas = schema.load_schemas(vault_path=vault_path)

    def _public(name):
        s = schemas[name]
        return {
            "type": name,
            "required_fields": s.get("required_fields", []),
            "required_sections": s.get("required_sections", []),
            "field_types": s.get("field_types", {}),
            "allowed_values": s.get("allowed_values", {}),
        }

    if args.schema_cmd == "list":
        rows = [_public(t) for t in sorted(schema.valid_types(schemas))]
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    # show
    if args.type not in schema.valid_types(schemas):
        valid = ", ".join(sorted(schema.valid_types(schemas)))
        print(f"error: unknown type {args.type!r}; valid types: {valid}", file=sys.stderr)
        return 1
    print(json.dumps(_public(args.type), ensure_ascii=False, indent=2))
    return 0


def _cmd_import(args) -> int:
    from scripts import config, paths, registry, import_source
    db = paths.registry_path()
    # Check notion token early (before vault lookup) so the error is clear even without a vault.
    if args.source == "notion":
        token = config.read_secret("NOTION_API_KEY")
        if not token:
            print("error: no NOTION_API_KEY — run `omw setup import` first.", file=sys.stderr)
            return 1
        if not args.notion_id:
            print("error: --notion-id required for notion import", file=sys.stderr)
            return 1
    if not db.exists():
        print("error: no vault (pass --vault or set an active vault)", file=sys.stderr)
        return 1
    if args.vault:
        row = next((v for v in registry.list_vaults(db) if v["name"] == args.vault), None)
    else:
        row = registry.get_active(db)
    if row is None:
        print("error: no vault (pass --vault or set an active vault)", file=sys.stderr)
        return 1
    vid = row["id"]
    if args.source in ("folder", "obsidian"):
        if not args.src_dir:
            print("error: --src-dir required for folder/obsidian import", file=sys.stderr)
            return 1
        out = import_source.import_folder(db, vault_id=vid, src_dir=args.src_dir,
                                          layer=args.layer, source=args.source)
    elif args.source == "notion":
        out = import_source.import_notion(db, vault_id=vid, token=token,
                                         root_id=args.notion_id, layer=args.layer)
    else:
        print(f"error: unknown source {args.source!r}", file=sys.stderr)
        return 1
    print(json.dumps({"imported": out["imported"], "skipped": out["skipped"],
                      "source": out["source"]}, ensure_ascii=False, indent=2))
    return 0


def _cmd_search(args) -> int:
    from scripts import search as _search
    try:
        results = _search.search(args.query, provider=args.provider, limit=args.limit)
    except _search.SearchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


def _cmd_view(args) -> int:
    from scripts import view
    return view.run(args)


def _cmd_recall(args) -> int:
    from scripts import recall
    out = recall.preamble() if args.action == "preamble" else recall.prompt(args.text)
    if out:
        print(out)
    return 0


def _cmd_serve(args) -> int:
    from scripts import config, paths, server
    token = config.read_secret("OMW_SERVE_TOKEN")
    if not token:
        print(
            "error: no OMW_SERVE_TOKEN configured.\n"
            "Run `omw setup serve --generate-token` (or set OMW_SERVE_TOKEN) first.",
            file=sys.stderr,
        )
        return 1
    try:
        server.serve(
            host=args.host, port=args.port, token=token,
            db_path=paths.registry_path(), default_vault=args.vault,
            max_limit=args.limit,
        )
    except KeyboardInterrupt:
        return 0
    return 0


def _cmd_setup(args) -> int:
    from scripts import setup_wizard
    if args.section is None:
        interactive = (not args.noninteractive) and sys.stdin.isatty()
        if interactive:
            return setup_wizard.run_all(noninteractive=False, base_dir=args.base_dir)
        return setup_wizard.run(
            section=None, noninteractive=args.noninteractive,
            name=args.name, mode=args.mode, type_=args.type, location=args.location,
        )
    if args.section == "serve":
        return setup_wizard.setup_serve(
            token=args.token, generate_token=args.generate_token,
            noninteractive=args.noninteractive,
        )
    if args.section == "personas":
        enabled = [s.strip() for s in args.enable.split(",") if s.strip()] if args.enable else None
        hosts = [s.strip() for s in args.host.split(",") if s.strip()] if args.host else None
        return setup_wizard.setup_personas(
            enabled=enabled, main=args.main, hosts=hosts,
            base_dir=args.base_dir, noninteractive=args.noninteractive,
        )
    if args.section == "tts":
        return setup_wizard.setup_tts(
            provider=args.provider, voice_id=args.voice_id,
            api_key=args.api_key, noninteractive=args.noninteractive,
        )
    if args.section == "search":
        return setup_wizard.setup_search(
            noninteractive=args.noninteractive,
            provider=args.provider,
            api_key=args.api_key,
            zone=args.zone,
        )
    if args.section == "import":
        return setup_wizard.setup_import(
            token=args.token, src_dir=args.src_dir, noninteractive=args.noninteractive)
    if args.section == "viewer":
        return setup_wizard.setup_viewer(viewer=args.viewer, noninteractive=args.noninteractive)
    if args.section == "agents":
        agents = [s.strip() for s in args.agents.split(",") if s.strip()] if args.agents else None
        return setup_wizard.setup_agents(agents=agents, noninteractive=args.noninteractive)
    if args.section == "recall":
        hosts = [s.strip() for s in args.host.split(",") if s.strip()] if args.host else None
        return setup_wizard.setup_recall(
            mode=args.provider, strategy=args.strategy, submode=args.submode,
            hosts=hosts, base_dir=args.base_dir, noninteractive=args.noninteractive,
        )
    return setup_wizard.run(
        section=args.section,
        noninteractive=args.noninteractive,
        name=args.name,
        mode=args.mode,
        type_=args.type,
        location=args.location,
    )


def _cmd_doctor(args) -> int:
    from scripts import setup_wizard
    return setup_wizard.doctor()


def _cmd_agentic(args) -> int:
    op = args.op
    print(
        f"'{op}' needs natural-language reasoning — it is not a deterministic CLI "
        f"command.\nOpen Claude Code and use the omw skill (e.g. say '{op} ...'); "
        f"the skill runs the commands/{op}.md procedure."
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="omw",
        description=(
            "oh-my-wiki user CLI — install/setup + deterministic vault ops. "
            "Natural-language work happens in a Claude session via the omw skill."
        ),
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="Show registry state as JSON.").set_defaults(
        func=_cmd_status
    )

    pv = sub.add_parser("vault", help="Deterministic vault management.")
    vsub = pv.add_subparsers(dest="vault_cmd", required=True)
    vsub.add_parser("list", help="List vaults as JSON.").set_defaults(func=_cmd_vault_list)

    pc = vsub.add_parser("create", help="Create + register a vault.")
    pc.add_argument("name")
    pc.add_argument("--mode", choices=["memo", "wiki"], default="wiki")
    pc.add_argument("--type", choices=["markdown", "obsidian"], default="markdown")
    pc.add_argument(
        "--location", default="global", help="global | project | <absolute path>"
    )
    pc.set_defaults(func=_cmd_vault_create)

    pu = vsub.add_parser("use", help="Set the active vault.")
    pu.add_argument("name")
    pu.set_defaults(func=_cmd_vault_use)

    pf = vsub.add_parser("forget", help="Remove a vault's registry row (files kept).")
    pf.add_argument("name")
    pf.set_defaults(func=_cmd_vault_forget)

    pl = sub.add_parser("lint", help="Run deterministic lint over a vault.")
    pl.add_argument("--vault", default=None, help="vault name (default: active)")
    pl.set_defaults(func=_cmd_lint)

    pfl = sub.add_parser("fields", help="Show a page's frontmatter + inline key:: value fields.")
    pfl.add_argument("relpath")
    pfl.add_argument("--vault", default=None, help="vault name (default: active)")
    pfl.set_defaults(func=_cmd_fields)

    pln = sub.add_parser("links", help="Entity-link suggestions + insertion.")
    lsub = pln.add_subparsers(dest="links_cmd", required=True)
    pls = lsub.add_parser("suggest", help="List unlinked mentions of existing pages.")
    pls.add_argument("relpath", nargs="?", default=None, help="limit to one page")
    pls.add_argument("--vault", default=None, help="vault name (default: active)")
    pls.set_defaults(func=_cmd_links)
    pll = lsub.add_parser("link", help="Insert [[slug]] at the first unlinked mention.")
    pll.add_argument("relpath")
    pll.add_argument("--to", required=True, help="target page slug")
    pll.add_argument("--vault", default=None, help="vault name (default: active)")
    pll.set_defaults(func=_cmd_links)

    prv = sub.add_parser("review", help="Spaced-repetition review queue.")
    rsub = prv.add_subparsers(dest="review_cmd", required=True)
    prd = rsub.add_parser("due", help="List pages due for review.")
    prd.add_argument("--vault", default=None, help="vault name (default: active)")
    prd.add_argument("--today", default=None, help="YYYY-MM-DD (default: today)")
    prd.add_argument("--scheduled-only", dest="scheduled_only", action="store_true",
                     help="exclude never-reviewed pages")
    prd.set_defaults(func=_cmd_review)
    prn = rsub.add_parser("done", help="Record a review verdict + reschedule.")
    prn.add_argument("relpath")
    prn.add_argument("--grade", required=True, choices=["pass", "needs-work"])
    prn.add_argument("--vault", default=None, help="vault name (default: active)")
    prn.add_argument("--today", default=None, help="YYYY-MM-DD (default: today)")
    prn.set_defaults(func=_cmd_review)

    psup = sub.add_parser("supersede", help="Mark a page superseded (status + superseded_by).")
    psup.add_argument("relpath")
    psup.add_argument("--by", required=True, help="slug of the superseding page")
    psup.add_argument("--vault", default=None, help="vault name (default: active)")
    psup.set_defaults(func=_cmd_supersede)

    pvis = sub.add_parser("visibility", help="Get/set a page's serve visibility (public|private).")
    vissub = pvis.add_subparsers(dest="visibility_cmd", required=True)
    pvg = vissub.add_parser("get", help="Print a page's visibility.")
    pvg.add_argument("relpath")
    pvg.add_argument("--vault", default=None, help="vault name (default: active)")
    pvg.set_defaults(func=_cmd_visibility)
    pvs = vissub.add_parser("set", help="Set visibility: omw visibility set <relpath...> <public|private>")
    pvs.add_argument("targets", nargs="+", metavar="RELPATH",
                     help="one or more page relpaths, then the value: public|private (value LAST)")
    pvs.add_argument("--vault", default=None, help="vault name (default: active)")
    pvs.set_defaults(func=_cmd_visibility)

    pib = sub.add_parser("inbox", help="URL inbox queue (add/list/run/remove).")
    ibsub = pib.add_subparsers(dest="inbox_cmd", required=True)
    iba = ibsub.add_parser("add", help="Queue a URL.")
    iba.add_argument("url")
    iba.add_argument("--vault", default=None)
    iba.set_defaults(func=_cmd_inbox)
    ibl = ibsub.add_parser("list", help="List queued/processed items.")
    ibl.add_argument("--vault", default=None)
    ibl.set_defaults(func=_cmd_inbox)
    ibr = ibsub.add_parser("remove", help="Remove a queued URL.")
    ibr.add_argument("url")
    ibr.add_argument("--vault", default=None)
    ibr.set_defaults(func=_cmd_inbox)
    ibn = ibsub.add_parser("run", help="Fetch all queued URLs into raw/ (no LLM).")
    ibn.add_argument("--vault", default=None)
    ibn.add_argument("--backend", choices=["auto", "urllib", "chromium", "cloud"], default="auto")
    ibn.add_argument("--today", default=None, help="YYYY-MM-DD (default: today)")
    ibn.set_defaults(func=_cmd_inbox)

    pfe = sub.add_parser("fetch", help="Fetch one URL into raw/ (single-shot, no LLM).")
    pfe.add_argument("url")
    pfe.add_argument("--backend", choices=["auto", "urllib", "chromium", "cloud"], default="auto")
    pfe.add_argument("--vault", default=None)
    pfe.add_argument("--today", default=None, help="YYYY-MM-DD (default: today)")
    pfe.set_defaults(func=_cmd_fetch)

    psch = sub.add_parser("schema", help="Show page-type schemas (conventions).")
    schsub = psch.add_subparsers(dest="schema_cmd", required=True)
    psl = schsub.add_parser("list", help="List page types + their requirements.")
    psl.add_argument("--vault", default=None, help="apply a vault's schema overrides")
    psl.set_defaults(func=_cmd_schema)
    pss = schsub.add_parser("show", help="Show one type's effective schema.")
    pss.add_argument("type")
    pss.add_argument("--vault", default=None, help="apply a vault's schema overrides")
    pss.set_defaults(func=_cmd_schema)

    psr = sub.add_parser("search", help="Web search via the configured provider.")
    psr.add_argument("query")
    psr.add_argument("--provider", default=None)
    psr.add_argument("--limit", type=int, default=10)
    psr.set_defaults(func=_cmd_search)

    pse = sub.add_parser("serve", help="Run the local query HTTP API (retrieve-only).")
    pse.add_argument("--host", default="127.0.0.1", help="bind host (default: localhost)")
    pse.add_argument("--port", type=int, default=8765)
    pse.add_argument("--vault", default=None, help="pin a vault by name (default: active)")
    pse.add_argument("--limit", type=int, default=10, help="max hits per response (cap)")
    pse.set_defaults(func=_cmd_serve)

    pvw = sub.add_parser("view", help="Open the vault/page/search in a note viewer (obsidian/logseq).")
    pvw.add_argument("page", nargs="?", default=None, help="page relpath or slug to open")
    pvw.add_argument("--search", default=None, help="open the viewer's search with this query")
    pvw.add_argument("--viewer", choices=["obsidian", "logseq"], default=None,
                     help="override the configured viewer for this call")
    pvw.add_argument("--vault", default=None, help="vault name (default: active)")
    pvw.add_argument("--print", action="store_true", help="print the URI instead of launching")
    pvw.set_defaults(func=_cmd_view)

    prc = sub.add_parser("recall", help="Wiki recall for agent hooks (preamble/prompt). See setup recall.")
    prc.add_argument("action", choices=["preamble", "prompt"])
    prc.add_argument("--text", default=None, help="prompt text (default: read stdin)")
    prc.set_defaults(func=_cmd_recall)

    pset = sub.add_parser("setup", help="Interactive setup wizard (run after install).")
    pset.add_argument(
        "section", nargs="?",
        choices=["vault", "hosts", "search", "serve", "personas", "tts", "import", "viewer", "agents", "recall"], default=None,
    )
    pset.add_argument(
        "--noninteractive", action="store_true",
        help="create from flags/defaults without prompting",
    )
    pset.add_argument("--name", default="default")
    pset.add_argument("--mode", choices=["memo", "wiki"], default="wiki")
    pset.add_argument("--type", choices=["markdown", "obsidian"], default="markdown")
    pset.add_argument("--location", default="global")
    pset.add_argument("--provider", default=None)
    pset.add_argument("--api-key", dest="api_key", default=None)
    pset.add_argument("--zone", default=None)
    pset.add_argument("--token", default=None)
    pset.add_argument("--generate-token", dest="generate_token", action="store_true")
    pset.add_argument("--enable", default=None, help="comma-separated persona names")
    pset.add_argument("--main", default=None, help="main persona name")
    pset.add_argument("--host", default=None, help="comma-separated hosts (claude,codex,gemini)")
    pset.add_argument("--base-dir", dest="base_dir", default=None, help="dir for host instruction files")
    pset.add_argument("--voice-id", dest="voice_id", default=None)
    pset.add_argument("--src-dir", dest="src_dir", default=None)
    pset.add_argument("--viewer", choices=["obsidian", "logseq"], default=None,
                      help="viewer for `omw setup viewer` (default obsidian)")
    pset.add_argument("--agents", default=None,
                      help="comma-separated agents for `omw setup agents` (claude,codex,hermes,gemini)")
    pset.add_argument("--strategy", choices=["fts", "embedding", "hybrid", "llm"], default=None,
                      help="retrieval strategy for `omw setup recall`")
    pset.add_argument("--submode", choices=["route", "generative"], default=None,
                      help="llm submode for `omw setup recall` (when --strategy llm)")
    pset.set_defaults(func=_cmd_setup)

    pimp = sub.add_parser("import", help="Import folder/Obsidian/Notion into a vault.")
    pimp.add_argument("--source", choices=["folder", "obsidian", "notion"], required=True)
    pimp.add_argument("--src-dir", dest="src_dir", default=None)
    pimp.add_argument("--notion-id", dest="notion_id", default=None)
    pimp.add_argument("--layer", choices=["raw", "wiki"], default="raw")
    pimp.add_argument("--vault", default=None)
    pimp.set_defaults(func=_cmd_import)

    sub.add_parser(
        "doctor", help="Validate omw config + install."
    ).set_defaults(func=_cmd_doctor)

    for op in AGENTIC_OPS:
        ap = sub.add_parser(op, help=f"(needs a Claude session) {op}")
        ap.set_defaults(func=_cmd_agentic, op=op)

    return p


def main(argv: list[str] | None = None) -> int:
    try:
        argv = list(sys.argv[1:] if argv is None else argv)
        parser = build_parser()
        if not argv or argv[0] in ("-h", "--help", "help"):
            from scripts import banner
            banner.render(animate=False)   # static, self-gated for TTY/NO_COLOR/CI
            parser.print_help()
            sys.stdout.flush()  # surface a broken pipe here (block-buffered stdout)
            return 0
        args = parser.parse_args(argv)
        rc = args.func(args)
        sys.stdout.flush()  # surface a broken pipe here, not at interpreter shutdown
        return rc
    except BrokenPipeError:
        try:
            import os as _os
            _os.dup2(_os.open(_os.devnull, _os.O_WRONLY), sys.stdout.fileno())
        except Exception:
            pass
        return 0


if __name__ == "__main__":
    sys.exit(main())
