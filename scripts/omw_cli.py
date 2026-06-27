"""User-facing omw CLI: deterministic ops + the setup wizard entrypoint.

The human-facing tool (install + setup + deterministic vault management).
Natural-language work (ingest/query/research/personas) happens inside a Claude
session via the omw skill; the skill may call these deterministic subcommands.
"""
from __future__ import annotations

import argparse
import json
import sys

from scripts import adapters, lint, nextstep, registry, reindex, vault_ops, wizard
from scripts import history as _history
from scripts.paths import ensure_home, registry_path, resolve_vault_root

AGENTIC_OPS = [
    "ingest", "query", "open", "edit", "move", "delete",
    "autoresearch", "persona-factcheck", "persona-consistency",
    "persona-terminology",
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
        for v in registry.list_vaults(db, include_archived=getattr(args, "all", False))
    ]
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def _cmd_vault_archive(args) -> int:
    db = registry_path()
    try:
        vault_ops.archive(db, args.name)
    except registry.VaultError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"archived: {args.name}")
    return 0


def _cmd_vault_unarchive(args) -> int:
    db = registry_path()
    try:
        vault_ops.unarchive(db, args.name)
    except registry.VaultError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"unarchived: {args.name}")
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


def _cmd_vault_info(args) -> int:
    db = registry_path()
    try:
        card = vault_ops.info(db, args.name)
    except registry.VaultError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(card, ensure_ascii=False, indent=2))
    return 0


def _cmd_vault_current(args) -> int:
    db = registry_path()
    row = vault_ops.current(db)
    if row is None:
        print("error: no active vault", file=sys.stderr)
        return 1
    if getattr(args, "json", False):
        print(json.dumps(dict(row), ensure_ascii=False, indent=2))
    else:
        print(row["name"])
    return 0


def _cmd_vault_rename(args) -> int:
    db = registry_path()
    try:
        vault_ops.rename(db, args.old, args.new)
    except registry.VaultError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"renamed: {args.old} -> {args.new}")
    return 0


def _cmd_vault_move(args) -> int:
    db = registry_path()
    try:
        out = vault_ops.move(db, args.name, args.new_path)
    except registry.VaultError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"moved: {out['from']} -> {out['to']}")
    return 0


def _cmd_vault_set(args) -> int:
    db = registry_path()
    try:
        vault_ops.set_(db, args.name, mode=args.mode, config_pairs=args.config)
    except registry.VaultError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"updated: {args.name}")
    return 0


def _cmd_vault_delete(args) -> int:
    from datetime import datetime, timezone
    db = registry_path()
    now_ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    try:
        out = vault_ops.delete(db, args.name, hard=args.hard, yes=args.yes,
                               now_ts=now_ts)
    except registry.VaultError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if out["mode"] == "soft":
        print(f"deleted (soft): moved to {out['trash']}")
    else:
        print(f"deleted (hard): {args.name}")
    return 0


def _cmd_lint(args) -> int:
    db = registry_path()
    row = _require_vault_row(db, args.vault)
    if row is None:
        return 1
    print(json.dumps(lint.check(db, vault_id=row["id"]), ensure_ascii=False, indent=2))
    return 0


def _cmd_fields(args) -> int:
    from pathlib import Path
    from scripts import frontmatter, inline_fields
    db = registry_path()
    row = _require_vault_row(db, args.vault)
    if row is None:
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
    row = _require_vault_row(db, args.vault)
    if row is None:
        return 1
    vault_id = row["id"]
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
    row = _require_vault_row(db, args.vault)
    if row is None:
        return 1
    vault_id = row["id"]
    today = args.today or date.today().isoformat()
    if args.review_cmd == "due":
        rows = review.due_pages(db, vault_id=vault_id, today=today,
                                include_unscheduled=not args.scheduled_only)
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    if args.review_cmd == "audit":
        rows = review.audit(db, vault_id=vault_id, today=today, apply=args.apply)
        print(json.dumps({"applied": args.apply, "findings": rows}, ensure_ascii=False, indent=2))
        return 0
    if args.review_cmd == "use":
        ok = review.record_use(db, vault_id=vault_id, relpaths=[args.relpath], today=today)
        print(json.dumps({"relpath": args.relpath, "recorded": ok, "date": today}, ensure_ascii=False))
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
    vault = _require_vault_row(db, args.vault)
    if vault is None:
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
    row = _require_vault_row(db, args.vault)
    if row is None:
        return 1
    try:
        out = supersede.mark_superseded(db, vault_id=row["id"], relpath=args.relpath,
                                        by_slug=args.by)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def _require_vault_row(db, name):
    """Resolve the target vault row (explicit --vault name, else active) with a
    consistent CLI error to stderr + None on failure. Single source for vault-scoped
    command resolution."""
    if not db.exists():
        print("error: no registry; run `omw status` to set up", file=sys.stderr)
        return None
    if name:
        match = [v for v in registry.list_vaults(db) if v["name"] == name]
        if not match:
            print(f"error: vault {name!r} not found", file=sys.stderr)
            return None
        return match[0]
    active = registry.get_active(db)
    if active is None:
        print("error: no active vault; pass --vault <name>", file=sys.stderr)
        return None
    return active


def _cmd_inbox(args) -> int:
    from datetime import date
    from scripts import inbox
    db = registry_path()
    vault = _require_vault_row(db, args.vault)
    if vault is None:
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
    if args.inbox_cmd == "retry":
        print(json.dumps({"retried": inbox.retry(db, vault_id=vault["id"])}, ensure_ascii=False))
        return 0
    if args.inbox_cmd == "add-feed":
        res = inbox.add_feed(db, vault_id=vid, feed_url=args.feed_url)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    return 1


def _cmd_history(args) -> int:
    db = registry_path()
    registry.init_db(db)   # idempotent: ensures the interactions table exists on a pre-existing DB
    vault = _require_vault_row(db, args.vault)
    if vault is None:
        return 1
    vid = vault["id"]
    cmd = args.history_cmd
    if cmd == "log":
        try:
            i = _history.log(db, vault_id=vid, request_type=args.type, request=args.request,
                             summary=args.summary, outcome=args.outcome, revises_id=args.revises,
                             focus=args.focus, refs=args.ref or [], tags=args.tag or [])
        except _history.HistoryError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        print(json.dumps({"id": i, "vault": vault["name"], "type": args.type}, ensure_ascii=False))
        return 0
    if cmd == "similar":
        print(json.dumps(_history.similar(db, vault_id=vid, text=args.text, limit=args.limit,
                                          request_type=args.type), ensure_ascii=False, indent=2))
        return 0
    if cmd == "prefs":
        print(json.dumps(_history.prefs(db, vault_id=vid, request_type=args.type),
                         ensure_ascii=False, indent=2))
        return 0
    if cmd == "find":
        print(json.dumps(_history.find(db, vault_id=vid, query=args.query, limit=args.limit),
                         ensure_ascii=False, indent=2))
        return 0
    if cmd == "list":
        print(json.dumps(_history.list_(db, vault_id=vid, request_type=args.type,
                                        outcome=args.outcome, since=args.since, ref=args.ref,
                                        limit=args.limit), ensure_ascii=False, indent=2))
        return 0
    if cmd == "show":
        row = _history.get(db, vault_id=vid, id_=args.id)
        if row is None:
            print(f"error: no interaction #{args.id} in this vault", file=sys.stderr)
            return 1
        print(json.dumps(row, ensure_ascii=False, indent=2))
        return 0
    return 1


def _cmd_fetch(args) -> int:
    import sqlite3
    from datetime import date
    from scripts import fetch, ingest, reindex, search
    from scripts.fetch_errors import FetchError
    db = registry_path()
    vault = _require_vault_row(db, args.vault)
    if vault is None:
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
        row = _require_vault_row(db, args.vault)
        if row is None:
            return 1
        vault_path = row["path"]
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
    from scripts import config, paths, import_source
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
    row = _require_vault_row(db, args.vault)
    if row is None:
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
        if getattr(args, "no_fallback", False):
            results = _search.search(args.query, provider=args.provider, limit=args.limit)
            print(json.dumps(results, ensure_ascii=False, indent=2))
        else:
            out = _search.search_with_fallback(args.query, provider=args.provider,
                                               limit=args.limit)
            print(json.dumps(out, ensure_ascii=False, indent=2))
    except _search.SearchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def _cmd_context(args) -> int:
    from scripts import query_pipeline
    db = registry_path()
    vault = _require_vault_row(db, args.vault)
    if vault is None:
        return 1
    out = query_pipeline.context(db, vault_id=vault["id"], q=args.query, limit=args.limit)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def _cmd_find(args) -> int:
    from scripts import search_index
    db = registry_path()
    vault = _require_vault_row(db, args.vault)
    if vault is None:
        return 1
    hits = search_index.query(db, vault_id=vault["id"], query=args.query, limit=args.limit)
    if args.find_json:
        print(json.dumps(hits, ensure_ascii=False, indent=2))
        return 0
    if not hits:
        print(f"(no matches for {args.query!r} in {vault['name']})")
        return 0
    for h in hits:
        title = h.get("title") or h.get("relpath")
        score = h.get("score", 0)
        print(f"{score:>6.2f}  {h['relpath']}  —  {title}")
    return 0


def _cmd_list(args) -> int:
    db = registry_path()
    vault = _require_vault_row(db, args.vault)
    if vault is None:
        return 1
    rows = registry.list_notes_faceted(
        db, vault_id=vault["id"], tag=args.tag, type_=args.type,
        status=args.status, layer=args.layer, visibility=args.visibility)
    out = [{"relpath": r["relpath"], "title": r["title"], "type": r["type"],
            "status": r["status"], "visibility": r["visibility"]} for r in rows]
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def _cmd_export(args) -> int:
    from scripts import exporter
    db = registry_path()
    vault = _require_vault_row(db, args.vault)
    if vault is None:
        return 1
    # Refresh the index first so [[wikilinks]] are resolved before computing
    # the dangling manifest.  Without this, dst_note_id=NULL for every link and
    # every outbound link would be reported as dangling (even in-slice ones).
    # Incremental is mtime-gated (cheap) and re-resolves links globally.
    try:
        reindex.incremental(db, vault_id=vault["id"])
    except Exception:
        pass  # best-effort; export still runs on whatever is already indexed
    try:
        res = exporter.export(db, vault_id=vault["id"], out_dir=args.out,
                              zip_path=args.zip_path, tag=args.tag, type_=args.type,
                              visibility=args.visibility, force=args.force)
    except exporter.ExportError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


def _cmd_view(args) -> int:
    from scripts import view
    return view.run(args)


def _cmd_reindex(args) -> int:
    import json
    from scripts import reindex
    db = registry_path()
    vault = _require_vault_row(db, args.vault)
    if vault is None:
        return 1
    mode = "full" if args.full else "incremental"
    fn = reindex.full if args.full else reindex.incremental
    indexed = fn(db, vault_id=vault["id"])
    print(json.dumps({"vault": vault["name"], "mode": mode, "indexed": indexed},
                     ensure_ascii=False))
    return 0


def _cmd_connections(args) -> int:
    import json
    from scripts import community, reindex
    db = registry_path()
    vault = _require_vault_row(db, args.vault)
    if vault is None:
        return 1
    # Refresh the index first so body [[wikilinks]] written directly into pages
    # (e.g. during ingest distillation) are registered before the graph is built.
    # Incremental is mtime-gated (cheap) and re-resolves links globally; opt out
    # with --no-reindex for a pure read of the current index.
    if not getattr(args, "no_reindex", False):
        try:
            reindex.incremental(db, vault_id=vault["id"])
        except Exception:
            pass  # best-effort; analyze still runs on whatever is already indexed
    rep = community.analyze(db, vault_id=vault["id"], min_bridge_score=args.min_bridge_score)
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    if not rep.get("communities"):
        print("hint: empty graph — no resolved wiki↔wiki [[wikilinks]] were found. Add links "
              "between pages (and finish writing them) before analyzing; connections auto-reindexes, "
              "but pages with no [[wikilinks]] produce no graph.", file=sys.stderr)
    return 0


def _cmd_gate(args) -> int:
    from datetime import datetime
    from scripts import gate
    now = datetime.now()
    if args.gate_cmd == "note":
        try:
            gate.note(args.kind, now=now)
            print(json.dumps({"noted": args.kind}, ensure_ascii=False))
        except ValueError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        return 0
    # check (best-effort, non-blocking)
    try:
        from scripts import config, maint
        cfg_all = config.load_config().get("gate", {}) or {}
        mode = cfg_all.get("mode", "off")
        if mode == "off":
            return 0
        db = registry_path()
        vault = _require_vault_row(db, args.vault)
        if vault is None:
            return 0
        from datetime import date
        today = args.today or date.today().isoformat()
        st = maint.status(db, vault_id=vault["id"], today=today)
        cfg = {"cooldown_min": cfg_all.get("cooldown_min", 30),
               "marker_ttl_min": cfg_all.get("marker_ttl_min", 120),
               "threshold": cfg_all.get("debt_threshold", gate.DEFAULT_THRESHOLD)}
        state = gate.load_state()
        decision = gate.decide(state, st, now=now, cfg=cfg)
        out = gate.render(decision, mode=mode)
        if out:
            print(out)
            gate.record_prompt(state, now=now)
    except Exception:
        return 0
    return 0


def _cmd_maint(args) -> int:
    from datetime import date
    from scripts import maint
    db = registry_path()
    vault = _require_vault_row(db, args.vault)
    if vault is None:
        return 1
    today = args.today or date.today().isoformat()
    st = maint.status(db, vault_id=vault["id"], today=today)
    print(json.dumps(st, ensure_ascii=False))
    if getattr(args, "exit_code", False):
        return 1 if (st["stale"] or st["expired"] or st["lint_issues"]) else 0
    return 0


def _cmd_recall(args) -> int:
    from scripts import recall
    if args.action == "preamble":
        out = recall.preamble()
    elif args.action == "pretool":
        out = recall.pretool(None)
    else:
        out = recall.prompt(args.text)
    rendered = recall._format_output(out or "", args.fmt, args.event)
    if rendered:
        print(rendered)
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
            return setup_wizard.run_all(noninteractive=False, base_dir=args.base_dir,
                                        dry_run=args.dry_run)
        return setup_wizard.run(
            section=None, noninteractive=args.noninteractive,
            name=args.name, mode=args.mode or "wiki", type_=args.type, location=args.location,
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
            profile=getattr(args, "profile", None),
            workspace=getattr(args, "workspace", None),
            dry_run=args.dry_run,
        )
    if args.section == "search":
        return setup_wizard.setup_search(
            noninteractive=args.noninteractive,
            provider=args.provider,
            api_key=args.api_key,
            zone=args.zone,
            create_zone=args.create_zone,
        )
    if args.section == "fetch":
        return setup_wizard.setup_fetch(
            noninteractive=args.noninteractive,
            provider=args.provider,
            api_key=args.api_key,
            zone=args.zone,
            create_zone=args.create_zone,
        )
    if args.section == "import":
        return setup_wizard.setup_import(
            token=args.token, src_dir=args.src_dir, noninteractive=args.noninteractive)
    if args.section == "viewer":
        return setup_wizard.setup_viewer(viewer=args.viewer, noninteractive=args.noninteractive)
    if args.section == "agents":
        agents = [s.strip() for s in args.agents.split(",") if s.strip()] if args.agents else None
        return setup_wizard.setup_agents(agents=agents, noninteractive=args.noninteractive,
                                         dry_run=args.dry_run)
    if args.section == "recall":
        hosts = [s.strip() for s in args.host.split(",") if s.strip()] if args.host else None
        return setup_wizard.setup_recall(
            mode=args.provider, strategy=args.strategy, submode=args.submode,
            hosts=hosts, base_dir=args.base_dir, noninteractive=args.noninteractive,
            provider=args.embed_provider, model=args.embed_model, dim=args.embed_dim,
            profile=getattr(args, "profile", None),
            workspace=getattr(args, "workspace", None),
            dry_run=args.dry_run,
        )
    if args.section == "gate":
        hosts = [s.strip() for s in args.host.split(",") if s.strip()] if args.host else None
        return setup_wizard.setup_gate(
            mode=args.mode or "enforce", hosts=hosts, noninteractive=args.noninteractive)
    if args.section == "playwright":
        return setup_wizard.setup_playwright(noninteractive=args.noninteractive)
    return setup_wizard.run(
        section=args.section,
        noninteractive=args.noninteractive,
        name=args.name,
        mode=args.mode or "wiki",
        type_=args.type,
        location=args.location,
    )


def _cmd_persona_run(args) -> int:
    import json as _json
    from pathlib import Path
    from scripts import persona_run, hermes_detect
    if args.apply_path:
        try:
            out = persona_run.apply_proposal(Path(args.apply_path))
        except persona_run.RunError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"applied: {out}")
        return 0
    db = registry_path()
    vault = _require_vault_row(db, args.vault)
    if vault is None:
        return 1
    source = None
    if args.page:
        source = {"vault_relpath": args.page}
    elif args.file:
        source = {"file": args.file}
    elif args.text:
        source = {"text": args.text}
    runner_name = getattr(args, "runner", "host")
    if runner_name == "hermes-delegate":
        source_display = (
            (source or {}).get("vault_relpath")
            or (source or {}).get("file")
            or (source or {}).get("text")
            or "(none)"
        )
        print("→ procedure: runner-hermes-delegate  (host calls delegate_task)")
        print(f"  role: {args.role}")
        print(f"  source: {source_display}")
        print("  steps: commands/runner-hermes-delegate.md")
        print("  hint: omw cannot call delegate_task; YOU (the Hermes host) execute the steps file.")
        return 0
    from scripts import runners
    try:
        runner = runners.resolve_runner(runner_name)
    except runners.RunnerUnavailable as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if runner.name == "host":
        return persona_run.run(args.role, db_path=db, vault_id=vault["id"],
                               source=source, backend=args.backend)
    # hermes-kanban
    try:
        from scripts.runners.hermes_kanban import KanbanError
        out = runner.run_one(
            args.role, db_path=db, vault_id=vault["id"],
            source=source, backend=getattr(args, "backend", None),
            apply=False, override_cli_path=None,
            assignee=getattr(args, "assignee", None),
        )
    except hermes_detect.AmbiguousProfile as exc:
        print(
            f"error: multiple Hermes profiles; pass --assignee "
            f"(choices: {', '.join(exc.choices)})",
            file=sys.stderr,
        )
        return 2
    except KanbanError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(_json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def _cmd_persona_bundle(args) -> int:
    import json
    from scripts import persona_bundle, hermes_detect
    if args.bundle_cmd == "list":
        print(json.dumps(persona_bundle.list_bundles(), ensure_ascii=False, indent=2))
        return 0
    if args.bundle_cmd == "show":
        try:
            spec = persona_bundle.load_bundle(args.name)
        except persona_bundle.BundleError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(spec, ensure_ascii=False, indent=2))
        return 0
    # run
    runner_name = getattr(args, "runner", "host")
    if runner_name == "hermes-delegate":
        print(
            "error: hermes-delegate runner supports only persona-run; "
            "use hermes-kanban for teams/fan-out",
            file=sys.stderr,
        )
        return 2
    db = registry_path()
    vault = _require_vault_row(db, args.vault)
    if vault is None:
        return 1
    if runner_name == "host":
        return persona_bundle.run_bundle(args.name, db_path=db, vault_id=vault["id"],
                                         page=args.page, backend=args.backend)
    # hermes-kanban
    from scripts import runners
    try:
        runner = runners.resolve_runner(runner_name)
    except runners.RunnerUnavailable as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    try:
        from scripts.runners.hermes_kanban import KanbanError
        out = runner.run_bundle(
            args.name, db_path=db, vault_id=vault["id"],
            page=getattr(args, "page", None),
            backend=getattr(args, "backend", None),
            override_cli_path=None,
            assignee=getattr(args, "assignee", None),
        )
    except hermes_detect.AmbiguousProfile as exc:
        print(
            f"error: multiple Hermes profiles; pass --assignee "
            f"(choices: {', '.join(exc.choices)})",
            file=sys.stderr,
        )
        return 2
    except KanbanError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def _cmd_persona_fanout(args) -> int:
    import json
    from scripts import persona_fanout, hermes_detect
    runner_name = getattr(args, "runner", "host")
    if runner_name == "hermes-delegate":
        print(
            "error: hermes-delegate runner supports only persona-run; "
            "use hermes-kanban for teams/fan-out",
            file=sys.stderr,
        )
        return 2
    pages = [p.strip() for p in args.pages.split(",") if p.strip()] if args.pages else None
    # Only need a vault row when resolving by facet (no explicit pages list).
    db = registry_path()
    vault_id = None
    if not pages:
        vault = _require_vault_row(db, args.vault)
        if vault is None:
            return 1
        vault_id = vault["id"]
    if runner_name == "host":
        try:
            out = persona_fanout.resolve(
                args.role, db_path=db, vault_id=vault_id, pages=pages,
                tag=args.tag, type=args.type, status=args.status, layer=args.layer,
                visibility=args.visibility, backend=args.backend)
        except persona_fanout.FanoutError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    # hermes-kanban
    from scripts import runners
    try:
        runner = runners.resolve_runner(runner_name)
    except runners.RunnerUnavailable as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    try:
        from scripts.runners.hermes_kanban import KanbanError
        out = runner.resolve_fanout(
            args.role, db_path=db, vault_id=vault_id, pages=pages,
            tag=getattr(args, "tag", None), type=getattr(args, "type", None),
            status=getattr(args, "status", None), layer=getattr(args, "layer", None),
            visibility=getattr(args, "visibility", None),
            backend=getattr(args, "backend", None),
            assignee=getattr(args, "assignee", None),
            override_cli_path=None,
        )
    except hermes_detect.AmbiguousProfile as exc:
        print(
            f"error: multiple Hermes profiles; pass --assignee "
            f"(choices: {', '.join(exc.choices)})",
            file=sys.stderr,
        )
        return 2
    except KanbanError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def _cmd_merge(args) -> int:
    import json
    from scripts import merge, registry, links, frontmatter
    db = registry_path()
    vault = _require_vault_row(db, getattr(args, "vault", None))
    if vault is None:
        return 1
    vid = vault["id"]
    if args.apply_path:
        winner_prop = args.apply_path
        if not winner_prop.endswith(".proposed.md"):
            print("error: --apply expects a <winner>.proposed.md path", file=sys.stderr)
            return 1
        root = registry.get_vault_root(db, vid)
        _wm, wbody = frontmatter.parse((root / winner_prop).read_text(encoding="utf-8"))
        import re as _re
        m = _re.search(r"## Merged from \[\[([^\]]+)\]\]", wbody)
        if not m:
            print("error: winner proposal has no '## Merged from' marker", file=sys.stderr)
            return 1
        src_slug = m.group(1)
        # collect ALL staged source proposals whose slug matches
        matches = [
            str(p.relative_to(root))
            for p in root.rglob("*.proposed.md")
            if links._slugify(p.name[: -len(".proposed.md")]) == src_slug
        ]
        if not matches:
            print(f"error: no staged source proposal for slug {src_slug!r}", file=sys.stderr)
            return 1
        if len(matches) > 1:
            print(
                f"error: multiple staged proposals match slug {src_slug!r}: "
                f"{', '.join(sorted(matches))}; remove the stale one(s) and retry",
                file=sys.stderr,
            )
            return 1
        src_prop = matches[0]
        try:
            out = merge.apply(db, vault_id=vid, winner_proposal=winner_prop,
                              source_proposal=src_prop)
        except merge.MergeError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        print(json.dumps(out, ensure_ascii=False))
        return 0
    if not args.source or not args.target:
        print("error: provide <source> <target>, or --apply <proposal>", file=sys.stderr)
        return 1
    try:
        out = merge.stage(db, vault_id=vid, source_relpath=args.source,
                          target_relpath=args.target, force=args.force)
    except merge.MergeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(json.dumps(out, ensure_ascii=False))
    print(f"staged. Review {out['winner_proposal']}, then: "
          f"omw merge --apply {out['winner_proposal']}")
    return 0


def _cmd_help(args) -> int:
    from scripts import help_overview
    print(help_overview.render())
    return 0


def _cmd_version(args) -> int:
    from scripts import banner
    print(f"omw {banner.version()}")
    return 0


def _cmd_doctor(args) -> int:
    from scripts import setup_wizard
    return setup_wizard.doctor()


def _cmd_update(args) -> int:
    from scripts import update
    return update.run(check_only=args.check, assume_yes=args.yes,
                      refresh=not args.no_refresh)


def _cmd_uninstall(args) -> int:
    from scripts import uninstall
    base = args.base_dir or None
    hosts = [h.strip() for h in args.host.split(",") if h.strip()] if args.host else None
    p = uninstall.plan(base, hosts=hosts)
    interactive = (not args.yes) and sys.stdin.isatty()

    def _print_plan(title):
        print(title)
        for h in p["hosts"]:
            print(f"  block   {h['host']:<9} {h['path']}  [{', '.join(h['markers'])}]")
        for hk in p["hooks"]:
            print(f"  hooks   {hk['host']:<9} {hk['path']}  ({hk['count']})")
        for sk in p["skills"]:
            print(f"  skill   {sk['agent']:<9} {sk['path']}")
        if not (p["hosts"] or p["hooks"] or p["skills"]):
            print("  (no omw host integration detected)")

    if args.dry_run:
        _print_plan("omw uninstall — dry run (nothing will be removed):")
        if args.purge:
            print(f"  purge   {p['home']['path']}  (config/.env/registry — vaults kept)")
        if args.vaults:
            for v in p["home"]["vaults"]:
                print(f"  VAULT   {v['name']}  {v['path']}  (DELETE content)")
        print(f"\nFinish with: {p['pip_hint']}")
        return 0

    purge, vaults = args.purge, args.vaults
    if interactive:
        _print_plan("omw uninstall — the following omw integration was detected:")
        if input("\nRemove omw's host blocks, hooks, and skill bundle? [y/N] ").strip().lower() not in ("y", "yes"):
            print("aborted — nothing removed.")
            return 0
        if not purge and input("Also purge ~/.omw config + secrets + registry? [y/N] ").strip().lower() in ("y", "yes"):
            purge = True
        if not vaults and input("Also DELETE vault content? type 'delete' to confirm: ").strip() == "delete":
            vaults = True
    else:
        # non-interactive safe fallback: Tier 1 (+ explicit flags). --vaults needs --yes.
        if vaults and not args.yes:
            print("error: --vaults deletes user content; pass --yes to confirm (non-interactive)",
                  file=sys.stderr)
            return 1

    res = uninstall.apply(p, purge=purge, vaults=vaults)
    print(f"✓ removed: {len(res['blocks_removed'])} block-set(s), "
          f"{len(res['hooks_removed'])} hook config(s), {len(res['skills_removed'])} skill bundle(s)"
          + (" · purged ~/.omw config/registry" if res["purged"] else "")
          + (f" · deleted {len(res['vaults_deleted'])} vault(s)" if res["vaults_deleted"] else ""))
    print(f"To remove the package itself: {res['pip_hint']}")
    return 0


def _cmd_embed(args) -> int:
    from scripts import embed_admin
    db = registry_path()
    sub = args.embed_cmd
    if sub == "status":
        print(json.dumps(embed_admin.status(db), ensure_ascii=False, indent=2))
        return 0
    if sub == "list":
        print(json.dumps(embed_admin.list_models(db), ensure_ascii=False, indent=2))
        return 0
    if sub == "install":
        ok = embed_admin.embed_install.ensure_fastembed(assume_yes=True)
        print("fastembed ready" if ok else "error: fastembed install failed",
              file=sys.stderr if not ok else sys.stdout)
        if not ok:
            return 1
        # Best-effort: pre-warm the active model so the first embed() call is fast.
        # A failure here is non-fatal — install already succeeded.
        try:
            from scripts import embed as _embed, config as _config
            emb_cfg = (_config.load_config().get("recall") or {}).get("embedding") or {}
            if not emb_cfg.get("provider") or emb_cfg.get("provider") == "none":
                emb_cfg = {"provider": "fastembed", "model": _embed.DEFAULT_LOCAL_MODEL, "dim": 384}
            embedder = _embed.get_embedder(emb_cfg)
            if embedder is not None:
                embedder.embed(["warm"])
                print(f"model warmed: {emb_cfg.get('model', _embed.DEFAULT_LOCAL_MODEL)}")
        except Exception as _warm_err:
            print(f"warning: model warm failed (non-fatal): {_warm_err}", file=sys.stderr)
        return 0
    if sub == "reindex":
        out = embed_admin.reindex_all(db)
        print(f"reindexed {out['vaults_reindexed']} vault(s)")
        return 0
    if sub == "use":
        out = embed_admin.switch_model(db, args.model, assume_yes=args.yes)
        if not out["ok"]:
            print(f"error: {out['detail']}", file=sys.stderr)
            return 1
        print(f"using {out['model']} (dim {out['dim']}); reindexed {out['vaults_reindexed']} vault(s)")
        return 0
    if sub == "add":
        out = embed_admin.add_model(db, args.model, assume_yes=args.yes)
        if not out["ok"]:
            print(f"error: {out['detail']}", file=sys.stderr)
            return 1
        print(f"registered {out['model']} (dim {out['dim']})")
        return 0
    print(f"error: unknown embed subcommand {sub!r}", file=sys.stderr)
    return 1


def _cmd_agentic(args) -> int:
    from scripts import ops_registry as reg
    from scripts import cards
    spec = reg.get(args.op)
    bound = {a.name.lstrip("-").replace("-", "_"): getattr(args, a.name.lstrip("-").replace("-", "_"), None)
             for a in spec.args}
    if getattr(args, "card_json", False):
        print(cards.render_card_json(spec, bound))
    else:
        print(cards.render_card(spec, bound))
    return 0


def _cmd_report(args) -> int:
    from datetime import date
    from scripts import report
    db = registry_path()
    if not db.exists():
        print("error: no registry; run `omw status` to set up", file=sys.stderr)
        return 1
    if args.vault:
        vault = _require_vault_row(db, args.vault)
        if vault is None:
            return 1
        vault_id = vault["id"]
    else:
        active = registry.get_active(db)
        vault_id = active["id"] if active else None
    today = getattr(args, "today", None) or date.today().isoformat()
    data = report.build(db, vault_id, today=today, no_reindex=args.no_reindex)
    if args.report_json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(report.render(data))
    return 0


def _cmd_next(args) -> int:
    from datetime import date
    db = registry_path()
    vault = _require_vault_row(db, args.vault)
    if vault is None:
        return 1
    today = args.today or date.today().isoformat()
    sig = nextstep.signals(db, vault["id"], today=today)
    ranked = nextstep.suggest(sig)
    if args.next_json:
        print(json.dumps(ranked, ensure_ascii=False, indent=2))
        return 0
    for i, s in enumerate(ranked, 1):
        print(f"{i}. {s['action']} — {s['reason']}\n   → {s['command']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="omw",
        description=(
            "oh-my-wiki user CLI — install/setup + deterministic vault ops. "
            "Natural-language work happens in a Claude session via the omw skill."
        ),
        epilog="Run `omw help` for a guided overview of all commands by lifecycle phase.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("help", help="Guided overview of all commands by lifecycle phase.").set_defaults(
        func=_cmd_help
    )

    sub.add_parser("version", help="Print the installed omw version.").set_defaults(
        func=_cmd_version
    )

    sub.add_parser("status", help="Show registry state as JSON.").set_defaults(
        func=_cmd_status
    )

    pv = sub.add_parser("vault", help="Deterministic vault management.")
    vsub = pv.add_subparsers(dest="vault_cmd", required=True)
    plist_v = vsub.add_parser("list", help="List vaults as JSON.")
    plist_v.add_argument("--all", action="store_true",
                         help="Include archived vaults.")
    plist_v.set_defaults(func=_cmd_vault_list)

    par = vsub.add_parser("archive", help="Archive a vault (hidden from list; index kept).")
    par.add_argument("name")
    par.set_defaults(func=_cmd_vault_archive)

    pun = vsub.add_parser("unarchive", help="Restore an archived vault.")
    pun.add_argument("name")
    pun.set_defaults(func=_cmd_vault_unarchive)

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

    pi = vsub.add_parser("info", help="Show one vault's details as JSON.")
    pi.add_argument("name")
    pi.set_defaults(func=_cmd_vault_info)

    pcur = vsub.add_parser("current", help="Print the active vault's name.")
    pcur.add_argument("--json", action="store_true", help="Print the full row as JSON.")
    pcur.set_defaults(func=_cmd_vault_current)

    pr = vsub.add_parser("rename", help="Rename a vault's registry label (index preserved).")
    pr.add_argument("old")
    pr.add_argument("new")
    pr.set_defaults(func=_cmd_vault_rename)

    pmv = vsub.add_parser("move", help="Move a vault's folder on disk + update its path.")
    pmv.add_argument("name")
    pmv.add_argument("new_path", metavar="new-path")
    pmv.set_defaults(func=_cmd_vault_move)

    pset = vsub.add_parser("set", help="Edit a vault's mode and/or config (k=v).")
    pset.add_argument("name")
    pset.add_argument("--mode", help="New mode (memo|wiki|personal|book|business|github-codebase|website).")
    pset.add_argument("--config", action="append", metavar="k=v",
                      help="Set a config key (repeatable).")
    pset.set_defaults(func=_cmd_vault_set)

    pdel = vsub.add_parser("delete",
                           help="Delete a vault: soft (to trash) by default; --hard --yes to purge.")
    pdel.add_argument("name")
    pdel.add_argument("--hard", action="store_true",
                      help="Permanently remove the folder (requires --yes).")
    pdel.add_argument("--yes", action="store_true",
                      help="Confirm an irreversible --hard delete.")
    pdel.set_defaults(func=_cmd_vault_delete)

    pl = sub.add_parser("lint", help="Run deterministic lint over a vault.")
    pl.add_argument("--vault", default=None, help="vault name (default: active)")
    pl.set_defaults(func=_cmd_lint)

    prx = sub.add_parser("reindex",
                         help="Rescan vault files into the registry (registers body [[wikilinks]] for search/connections).")
    prx.add_argument("--vault", default=None, help="vault name (default: active)")
    prx.add_argument("--full", action="store_true",
                     help="full rescan (default: incremental, mtime-gated)")
    prx.set_defaults(func=_cmd_reindex)

    pcon = sub.add_parser("connections",
                          help="Detect link-graph communities + surprising bridges/hubs (auto-reindexes first).")
    pcon.add_argument("--vault", default=None, help="vault name (default: active)")
    pcon.add_argument("--min-bridge-score", dest="min_bridge_score", type=int, default=0,
                      help="drop bridges below this score (deg(src)*deg(dst))")
    pcon.add_argument("--no-reindex", dest="no_reindex", action="store_true",
                      help="skip the incremental reindex that registers newly-written page links first")
    pcon.set_defaults(func=_cmd_connections)

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
    pra = rsub.add_parser("audit", help="Deterministic freshness audit: stale/expired pages (report-only unless --apply).")
    pra.add_argument("--apply", action="store_true", help="write stale flags + confidence demotions (default: report only)")
    pra.add_argument("--vault", default=None, help="vault name (default: active)")
    pra.add_argument("--today", default=None, help="YYYY-MM-DD (default: today)")
    pra.set_defaults(func=_cmd_review)
    pru = rsub.add_parser("use", help="Record that a page was surfaced today (reactivates freshness).")
    pru.add_argument("relpath")
    pru.add_argument("--vault", default=None, help="vault name (default: active)")
    pru.add_argument("--today", default=None, help="YYYY-MM-DD (default: today)")
    pru.set_defaults(func=_cmd_review)

    psup = sub.add_parser("supersede", help="Mark a page superseded (status + superseded_by).")
    psup.add_argument("relpath")
    psup.add_argument("--by", required=True, help="slug of the superseding page")
    psup.add_argument("--vault", default=None, help="vault name (default: active)")
    psup.set_defaults(func=_cmd_supersede)

    pmg = sub.add_parser("merge", help="Consolidate a source page into a target (staged proposal).")
    pmg.add_argument("source", nargs="?", default=None)
    pmg.add_argument("target", nargs="?", default=None)
    pmg.add_argument("--force", action="store_true")
    pmg.add_argument("--apply", dest="apply_path", default=None)
    pmg.set_defaults(func=_cmd_merge)

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
    ibt = ibsub.add_parser("retry", help="Reset failed items to queued.")
    ibt.add_argument("--vault", default=None)
    ibt.set_defaults(func=_cmd_inbox)
    ibf = ibsub.add_parser("add-feed", help="Parse an RSS/Atom feed and queue its entry links.")
    ibf.add_argument("feed_url")
    ibf.add_argument("--vault", default=None)
    ibf.set_defaults(func=_cmd_inbox)

    phi = sub.add_parser("history", help="Record + recall request/work history (per vault).")
    phi.add_argument("--vault", default=None, help="vault name (default: active)")
    hsub = phi.add_subparsers(dest="history_cmd", required=True)

    hlog = hsub.add_parser("log", help="Record one unit of work.")
    hlog.add_argument("--type", required=True, choices=list(_history.REQUEST_TYPES))
    hlog.add_argument("--request", required=True)
    hlog.add_argument("--summary", default=None)
    hlog.add_argument("--outcome", default="new", choices=list(_history.OUTCOMES))
    hlog.add_argument("--revises", type=int, default=None)
    hlog.add_argument("--focus", default=None)
    hlog.add_argument("--ref", action="append", default=None)
    hlog.add_argument("--tag", action="append", default=None)
    hlog.set_defaults(func=_cmd_history)

    hsim = hsub.add_parser("similar", help="Rank past requests similar to TEXT.")
    hsim.add_argument("text")
    hsim.add_argument("--limit", type=int, default=8)
    hsim.add_argument("--type", default=None)
    hsim.set_defaults(func=_cmd_history)

    hpref = hsub.add_parser("prefs", help="Aggregate recurring revision focus.")
    hpref.add_argument("--type", default=None)
    hpref.set_defaults(func=_cmd_history)

    hfind = hsub.add_parser("find", help="Token search over request/summary/focus.")
    hfind.add_argument("query")
    hfind.add_argument("--limit", type=int, default=10)
    hfind.set_defaults(func=_cmd_history)

    hlist = hsub.add_parser("list", help="Faceted listing.")
    hlist.add_argument("--type", default=None)
    hlist.add_argument("--outcome", default=None, choices=list(_history.OUTCOMES))
    hlist.add_argument("--since", default=None)
    hlist.add_argument("--ref", default=None)
    hlist.add_argument("--limit", type=int, default=50)
    hlist.set_defaults(func=_cmd_history)

    hshow = hsub.add_parser("show", help="Show one interaction by id.")
    hshow.add_argument("id", type=int)
    hshow.set_defaults(func=_cmd_history)

    pemb = sub.add_parser("embed", help="Local embedding model management.")
    embsub = pemb.add_subparsers(dest="embed_cmd", required=True)
    embsub.add_parser("status", help="Show embedding provider/model/strategy + counts (JSON).").set_defaults(func=_cmd_embed)
    embsub.add_parser("list", help="List known + registered models (JSON).").set_defaults(func=_cmd_embed)
    eu = embsub.add_parser("use", help="Switch model (reset + reindex).")
    eu.add_argument("model")
    eu.add_argument("--yes", action="store_true")
    eu.set_defaults(func=_cmd_embed)
    ea = embsub.add_parser("add", help="Register a custom fastembed model.")
    ea.add_argument("model")
    ea.add_argument("--yes", action="store_true")
    ea.set_defaults(func=_cmd_embed)
    embsub.add_parser("install", help="Install fastembed + warm the active model.").set_defaults(func=_cmd_embed)
    embsub.add_parser("reindex", help="Re-embed all vaults with the active model.").set_defaults(func=_cmd_embed)

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
    psr.add_argument("--no-fallback", dest="no_fallback", action="store_true",
                     help="disable provider fallback (single configured provider only)")
    psr.set_defaults(func=_cmd_search)

    pctx = sub.add_parser("context", help="Cited-context retrieval (JSON) for grounded answers.")
    pctx.add_argument("query")
    pctx.add_argument("--limit", type=int, default=8)
    pctx.add_argument("--vault", default=None)
    pctx.set_defaults(func=_cmd_context)

    pfd = sub.add_parser("find", help="Deterministic full-text search over the vault index.")
    pfd.add_argument("query")
    pfd.add_argument("--limit", type=int, default=10)
    pfd.add_argument("--vault", default=None)
    pfd.add_argument("--json", dest="find_json", action="store_true")
    pfd.set_defaults(func=_cmd_find)

    plist = sub.add_parser("list", help="Faceted note listing as JSON.")
    plist.add_argument("--tag", default=None)
    plist.add_argument("--type", default=None)
    plist.add_argument("--status", default=None)
    plist.add_argument("--layer", default=None)
    plist.add_argument("--visibility", default=None)
    plist.add_argument("--vault", default=None)
    plist.set_defaults(func=_cmd_list)

    pexp = sub.add_parser("export", help="Export a vault slice to a self-contained Markdown dir/zip.")
    pexp.add_argument("--tag", default=None)
    pexp.add_argument("--type", default=None)
    pexp.add_argument("--visibility", default=None)
    pexp.add_argument("--out", default=None)
    pexp.add_argument("--zip", dest="zip_path", default=None)
    pexp.add_argument("--vault", default=None)
    pexp.add_argument("--force", action="store_true")
    pexp.set_defaults(func=_cmd_export)

    pnx = sub.add_parser("next", help="Recommend the next knowledge-lifecycle action(s).")
    pnx.add_argument("--vault", default=None)
    pnx.add_argument("--json", dest="next_json", action="store_true")
    pnx.add_argument("--today", default=None, help="YYYY-MM-DD (default: today)")
    pnx.set_defaults(func=_cmd_next)

    prep = sub.add_parser("report", help="Aggregate vault stats + health into one report.")
    prep.add_argument("--vault", default=None, help="vault name (default: active)")
    prep.add_argument("--no-reindex", action="store_true",
                      help="skip the pre-report incremental reindex")
    prep.add_argument("--json", dest="report_json", action="store_true",
                      help="emit the structured report as JSON")
    prep.add_argument("--today", default=None, help=argparse.SUPPRESS)
    prep.set_defaults(func=_cmd_report)

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
    prc.add_argument("action", choices=["preamble", "prompt", "pretool"])
    prc.add_argument("--text", default=None, help="prompt text (default: read stdin)")
    prc.add_argument("--format", dest="fmt", default="plain",
                     choices=["plain", "claude-json", "gemini-json", "hermes-json"],
                     help="stdout shape for the calling host's hook system")
    prc.add_argument("--event", default="", help="concrete host event name (for json formats)")
    prc.set_defaults(func=_cmd_recall)

    pm = sub.add_parser("maint", help="Knowledge-maintenance status (cron-friendly).")
    msub = pm.add_subparsers(dest="maint_cmd", required=True)
    pms = msub.add_parser("status", help="Print stale/expired/lint counts as JSON.")
    pms.add_argument("--vault", default=None, help="vault name (default: active)")
    pms.add_argument("--today", default=None, help="YYYY-MM-DD (default: today)")
    pms.add_argument("--exit-code", dest="exit_code", action="store_true",
                     help="exit 1 if any maintenance is due (for cron)")
    pms.set_defaults(func=_cmd_maint)

    pg = sub.add_parser("gate", help="Maintenance gate: note semantic moments / check at turn end.")
    gsub = pg.add_subparsers(dest="gate_cmd", required=True)
    pgn = gsub.add_parser("note", help="Record a semantic moment (research|synthesis|ingest|recall-stale).")
    pgn.add_argument("kind", choices=["research", "synthesis", "ingest", "recall-stale"])
    pgn.set_defaults(func=_cmd_gate)
    pgc = gsub.add_parser("check", help="Turn-end gate check (hook entrypoint). Silent unless open.")
    pgc.add_argument("--vault", default=None)
    pgc.add_argument("--today", default=None)
    pgc.set_defaults(func=_cmd_gate)

    pset = sub.add_parser("setup", help="Interactive setup wizard (run after install).")
    pset.add_argument(
        "section", nargs="?",
        choices=["vault", "hosts", "search", "fetch", "serve", "personas", "import", "viewer", "agents", "recall", "gate", "playwright"], default=None,
    )
    pset.add_argument(
        "--noninteractive", action="store_true",
        help="create from flags/defaults without prompting",
    )
    pset.add_argument("--dry-run", dest="dry_run", action="store_true",
                      help="preview recall/persona/agent host-config writes (blocks, hooks, skills); make none")
    pset.add_argument("--name", default="default")
    pset.add_argument("--mode", default=None,
                      help="vault mode (memo|wiki) for `omw setup vault`, "
                           "or gate mode (off|advisory|enforce) for `omw setup gate`")
    pset.add_argument("--type", choices=["markdown", "obsidian"], default="markdown")
    pset.add_argument("--location", default="global")
    pset.add_argument("--provider", default=None)
    pset.add_argument("--api-key", dest="api_key", default=None)
    pset.add_argument("--zone", default=None)
    pset.add_argument("--create-zone", dest="create_zone", action="store_true",
                      help="for `omw setup search --provider brightdata`: auto-create a "
                           "Bright Data zone if the account has none (may incur charges)")
    pset.add_argument("--token", default=None)
    pset.add_argument("--generate-token", dest="generate_token", action="store_true")
    pset.add_argument("--enable", default=None, help="comma-separated persona names")
    pset.add_argument("--main", default=None, help="main persona name")
    pset.add_argument("--host", default=None, help="comma-separated hosts (claude,codex,gemini)")
    pset.add_argument("--base-dir", dest="base_dir", default=None, help="dir for host instruction files")
    pset.add_argument("--src-dir", dest="src_dir", default=None)
    pset.add_argument("--viewer", choices=["obsidian", "logseq"], default=None,
                      help="viewer for `omw setup viewer` (default obsidian)")
    pset.add_argument("--agents", default=None,
                      help="comma-separated agents for `omw setup agents` (claude,codex,hermes,gemini)")
    pset.add_argument("--strategy", choices=["fts", "embedding", "hybrid", "llm"], default=None,
                      help="retrieval strategy for `omw setup recall`")
    pset.add_argument("--submode", choices=["route", "generative"], default=None,
                      help="llm submode for `omw setup recall` (when --strategy llm)")
    pset.add_argument("--embed-provider", dest="embed_provider", default=None,
                      help="embedding provider for `omw setup recall` (none|openai|fake)")
    pset.add_argument("--embed-model", dest="embed_model", default=None,
                      help="embedding model name for `omw setup recall`")
    pset.add_argument("--embed-dim", dest="embed_dim", type=int, default=None,
                      help="embedding dimension for `omw setup recall`")
    pset.add_argument("--profile", default=None,
                      help="hermes profile name for `omw setup personas/recall`")
    pset.add_argument("--workspace", default=None,
                      help="openclaw workspace path for `omw setup personas/recall`")
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

    pup = sub.add_parser("update", help="Self-upgrade omw + refresh managed blocks.")
    pup.add_argument("--check", action="store_true")
    pup.add_argument("--yes", action="store_true")
    pup.add_argument("--no-refresh", dest="no_refresh", action="store_true")
    pup.set_defaults(func=_cmd_update)

    pun = sub.add_parser("uninstall", help="Remove omw's host integration (blocks/hooks/skill).")
    pun.add_argument("--host", default=None, help="limit to host(s), comma-separated (default: auto-detect)")
    pun.add_argument("--purge", action="store_true",
                     help="also remove ~/.omw config + secrets + registry (keeps vaults)")
    pun.add_argument("--vaults", action="store_true",
                     help="also DELETE vault content (requires --yes when non-interactive)")
    pun.add_argument("--dry-run", action="store_true", help="preview only, write nothing")
    pun.add_argument("--yes", action="store_true", help="skip confirmations (non-interactive)")
    pun.add_argument("--base-dir", default=None, help=argparse.SUPPRESS)
    pun.set_defaults(func=_cmd_uninstall)

    ppr = sub.add_parser("persona-run", help="Dispatch a persona as an isolated one-shot subagent.")
    ppr.add_argument("role")
    g = ppr.add_mutually_exclusive_group()
    g.add_argument("--page", default=None)
    g.add_argument("--file", default=None)
    g.add_argument("--text", default=None)
    ppr.add_argument("--vault", default=None)
    ppr.add_argument("--backend", choices=["claude", "codex", "gemini", "opencode"], default=None)
    ppr.add_argument("--apply", dest="apply_path", default=None,
                     help="apply a staged <target>.proposed.md")
    ppr.add_argument("--runner", choices=["host", "hermes-kanban", "hermes-delegate"],
                     default="host",
                     help="where to execute (default host; hermes-* needs a Hermes session)")
    ppr.add_argument("--assignee", default=None,
                     help="Hermes profile to assign cards to (hermes-kanban; default = current session profile)")
    ppr.set_defaults(func=_cmd_persona_run)

    pb = sub.add_parser("persona-bundle", help="Run a named team of personas in sequence.")
    bsub = pb.add_subparsers(dest="bundle_cmd", required=True)
    bsub.add_parser("list", help="List available bundles (JSON)")
    pbs = bsub.add_parser("show", help="Show one bundle's spec (JSON)")
    pbs.add_argument("name")
    pbr = bsub.add_parser("run", help="Run a bundle's personas in order")
    pbr.add_argument("name")
    pbr.add_argument("--page", default=None)
    pbr.add_argument("--vault", default=None)
    pbr.add_argument("--backend", choices=["claude", "codex", "gemini", "opencode"],
                     default=None)
    pbr.add_argument("--runner", choices=["host", "hermes-kanban", "hermes-delegate"],
                     default="host",
                     help="where to execute (default host; hermes-* needs a Hermes session)")
    pbr.add_argument("--assignee", default=None,
                     help="Hermes profile to assign cards to (hermes-kanban; default = current session profile)")
    pb.set_defaults(func=_cmd_persona_bundle)

    pf = sub.add_parser("persona-fanout",
                        help="Resolve a page list + emit per-page persona-run commands.")
    pf.add_argument("role")
    pf.add_argument("--pages", default=None, help="comma-separated relpaths")
    pf.add_argument("--tag", default=None)
    pf.add_argument("--type", default=None)
    pf.add_argument("--status", default=None)
    pf.add_argument("--layer", default=None)
    pf.add_argument("--visibility", default=None)
    pf.add_argument("--vault", default=None)
    pf.add_argument("--backend", choices=["claude", "codex", "gemini", "opencode"],
                    default=None)
    pf.add_argument("--runner", choices=["host", "hermes-kanban", "hermes-delegate"],
                    default="host",
                    help="where to execute (default host; hermes-* needs a Hermes session)")
    pf.add_argument("--assignee", default=None,
                    help="Hermes profile to assign cards to (hermes-kanban; default = current session profile)")
    pf.set_defaults(func=_cmd_persona_fanout)

    from scripts import ops_registry as _reg
    for _name in _reg.PROCEDURE_NAMES:
        _spec = _reg.get(_name)
        ap = sub.add_parser(_name, help=f"(omw skill procedure) {_spec.summary}")
        for _a in _spec.args:
            if _a.name.startswith("--"):
                if _a.name == "--no-synthesis":
                    ap.add_argument(_a.name, dest="no_synthesis", action="store_true", help=_a.hint)
                else:
                    ap.add_argument(_a.name, default=None, help=_a.hint)
            else:
                _req = _a.required
                ap.add_argument(_a.name, nargs=None if _req else "?", default=None, help=_a.hint)
        ap.add_argument("--json", dest="card_json", action="store_true",
                        help="emit the procedure card as JSON")
        ap.set_defaults(func=_cmd_agentic, op=_name)

    return p


def main(argv: list[str] | None = None) -> int:
    try:
        argv = list(sys.argv[1:] if argv is None else argv)
        parser = build_parser()
        if not argv or argv[0] in ("-h", "--help", "help"):
            # Top-level help is the lifecycle-grouped overview (not argparse's flat
            # subcommand dump) — categorized by phase, [CLI]/[skill] tagged. Per-command
            # detail stays on `omw <command> -h` (argparse).
            from scripts import banner, help_overview
            banner.render(animate=False)   # static, self-gated for TTY/NO_COLOR/CI
            print(help_overview.render())
            sys.stdout.flush()  # surface a broken pipe here (block-buffered stdout)
            return 0
        if argv[0] in ("-v", "--version", "version"):
            # Early-exit (like help) — sidesteps the required-subparser argparse path
            # and the banner, printing just the version for all three forms.
            from scripts import banner
            print(f"omw {banner.version()}")
            sys.stdout.flush()
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
