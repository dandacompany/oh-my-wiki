"""Admin/logic hub for the local embedding model: install, switch (with vector
reset + reindex), introspect, and register models. Single source of truth shared
by the `omw embed` CLI op and the setup wizard."""
from __future__ import annotations

import copy
import shutil
import sqlite3
import tempfile
from pathlib import Path

from scripts import config, embed, embed_install, paths, reindex, registry, vector_index


def _wiki_count(db_path, vault_id: int) -> int:
    conn = registry.connect(db_path)
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM notes WHERE vault_id=? "
            "AND relpath LIKE 'wiki/%' AND parse_error=0",
            (vault_id,),
        ).fetchone()
        return int(row["c"]) if row else 0
    finally:
        conn.close()


def resolve_dim(db_path, model: str) -> int:
    """Known dim, else probe by embedding one string with the model."""
    if model in embed.KNOWN_MODEL_DIMS:
        return embed.KNOWN_MODEL_DIMS[model]
    emb = embed.get_embedder({"provider": "fastembed", "model": model})
    vec = emb.embed(embed.passage_texts(emb, ["probe"]))[0]
    return len(vec)


def _copy_registry(source_path, target_path: Path) -> None:
    """Take a consistent SQLite snapshot, including committed WAL content."""
    source = registry.connect(source_path)
    target = sqlite3.connect(target_path)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()


def _rebuild_staged(db_path, embedding_config: dict, *,
                    before_promote=None, restore_before_promote=None) -> dict:
    """Rebuild in a disposable DB; expose only a complete vector index."""
    embedder = embed.get_embedder(embedding_config)
    if embedder is None:
        return {"ok": False, "vaults_reindexed": 0,
                "failures": [{"vault": None,
                              "detail": "embedding provider is not configured"}]}
    if not vector_index.available():
        return {"ok": False, "vaults_reindexed": 0,
                "failures": [{"vault": None, "detail": "sqlite-vec is not installed"}]}

    with tempfile.TemporaryDirectory(prefix="omw-embed-") as tmp:
        original = Path(tmp) / "original.db"
        staged = Path(tmp) / "staged.db"
        _copy_registry(db_path, original)
        shutil.copyfile(original, staged)
        vector_index.reset(staged)
        vector_index.prepare(staged, embedder=embedder)

        n = 0
        failures = []
        for vault in registry.list_vaults(staged):
            try:
                stored = reindex.refresh_embeddings(
                    staged,
                    vault_id=vault["id"],
                    relpaths=None,
                    strict=True,
                    embedding_config=embedding_config,
                )
                expected = _wiki_count(staged, vault["id"])
                if stored != expected:
                    raise RuntimeError(
                        f"no vectors or incomplete vector index: stored {stored} of {expected} "
                        "indexed wiki pages"
                    )
                n += 1
            except Exception as exc:
                failures.append({"vault": vault["name"], "detail": str(exc)})
        if failures:
            return {"ok": False, "vaults_reindexed": n, "failures": failures}

        try:
            if before_promote is not None:
                before_promote()
            vector_index.replace_from(db_path, staged)
        except Exception as exc:
            if restore_before_promote is not None:
                restore_before_promote()
            return {"ok": False, "vaults_reindexed": 0,
                    "failures": [{"vault": None, "detail": str(exc)}]}
        return {"ok": True, "vaults_reindexed": n, "failures": []}


def switch_model(db_path, model: str, *, assume_yes: bool = False,
                 interactive: bool = True) -> dict:
    if not embed_install.ensure_local_embedding(
        assume_yes=assume_yes, interactive=interactive
    ):
        return {"ok": False, "model": model, "dim": None, "vaults_reindexed": 0,
                "detail": "fastembed/sqlite-vec not installed"}
    try:
        dim = resolve_dim(db_path, model)
    except Exception as exc:
        return {"ok": False, "model": model, "dim": None, "vaults_reindexed": 0,
                "detail": f"could not load model {model!r}: {exc}"}
    embedding_config = {"provider": "fastembed", "model": model, "dim": dim}
    previous = copy.deepcopy(config.load_config())
    updated = copy.deepcopy(previous)
    recall_cfg = updated.setdefault("recall", {})
    prior_embedding = recall_cfg.get("embedding") or {}
    recall_cfg["embedding"] = {**prior_embedding, **embedding_config}
    result = _rebuild_staged(
        db_path,
        embedding_config,
        before_promote=lambda: config.save_config(updated),
        restore_before_promote=lambda: config.save_config(previous),
    )
    if not result["ok"]:
        detail = "; ".join(
            f"{item['vault'] or 'preflight'}: {item['detail']}"
            for item in result["failures"]
        )
        return {
            "ok": False,
            "model": model,
            "dim": dim,
            "vaults_reindexed": result["vaults_reindexed"],
            "detail": detail,
        }
    return {"ok": True, "model": model, "dim": dim,
            "vaults_reindexed": result["vaults_reindexed"], "detail": None}


def add_model(db_path, model: str, *, assume_yes: bool = False,
              interactive: bool = True) -> dict:
    if not embed_install.ensure_local_embedding(
        assume_yes=assume_yes, interactive=interactive
    ):
        return {"ok": False, "model": model, "dim": None,
                "detail": "fastembed/sqlite-vec not installed"}
    try:
        dim = resolve_dim(db_path, model)
    except Exception as exc:
        return {"ok": False, "model": model, "dim": None, "detail": f"invalid model: {exc}"}
    emb_cfg = (config.load_config().get("recall") or {}).get("embedding") or {}
    known = list(emb_cfg.get("known_models") or [])
    if model not in known:
        known.append(model)
        config.set_config("recall.embedding.known_models", known)
    return {"ok": True, "model": model, "dim": dim, "detail": None}


def list_models(db_path) -> dict:
    emb_cfg = (config.load_config().get("recall") or {}).get("embedding") or {}
    known = list(dict.fromkeys(list(embed.KNOWN_MODEL_DIMS) + list(emb_cfg.get("known_models") or [])))
    return {"active": emb_cfg.get("model") or embed.DEFAULT_LOCAL_MODEL, "known": known}


def reindex_all(db_path) -> dict:
    cfg = config.load_config().get("recall") or {}
    emb_cfg = cfg.get("embedding") or {}
    return _rebuild_staged(db_path, emb_cfg)


def status(db_path) -> dict:
    cfg = config.load_config().get("recall") or {}
    emb = cfg.get("embedding") or {}
    vaults = []
    if vector_index.available():
        for v in registry.list_vaults(db_path):
            cnt = vector_index.count(db_path, vault_id=v["id"])
            indexed = _wiki_count(db_path, v["id"])
            vaults.append({"name": v["name"], "embedded": cnt, "indexed": indexed,
                           "coverage": round(cnt / indexed, 4) if indexed else 1.0})
    else:
        vaults = [
            {"name": v["name"], "embedded": 0,
             "indexed": _wiki_count(db_path, v["id"]), "coverage": 0.0}
            for v in registry.list_vaults(db_path)
        ]
    from scripts import recall
    effective_recall_cfg = recall._cfg()
    index_meta = vector_index.meta(db_path)
    # A contract mismatch silently disables vector search, and comparing only
    # model and dim misses it — those are the two fields that keep matching
    # when a library upgrade changes the fingerprint.
    # active_embedder, not get_embedder: it recovers the stored contract after
    # an interrupted model switch, and reporting that as a fault would push a
    # destructive reindex for something the query path already handles.
    contract = vector_index.contract_from_meta(
        index_meta, embed.active_embedder(db_path, emb))
    diagnostics = list(recall.threshold_diagnostics(effective_recall_cfg))
    if not contract["matches"]:
        diagnostics.append(vector_index.describe_mismatch(contract))
        for field, sides in sorted(contract["mismatched"].items()):
            diagnostics.append(
                f"  {field}: indexed={sides['indexed']!r} current={sides['current']!r}")
    return {
        "provider": emb.get("provider") or "none",
        "model": emb.get("model") or embed.DEFAULT_LOCAL_MODEL,
        "dim": emb.get("dim"),
        "index_model": (index_meta or {}).get("model"),
        "index_dim": (index_meta or {}).get("dim"),
        "prefix_scheme": contract["current"].get("prefix_scheme"),
        "fingerprint": contract["current"].get("fingerprint"),
        "index_fingerprint": contract["indexed"].get("fingerprint"),
        "index_distance_metric": contract["indexed"].get("distance_metric"),
        "contract_matches": contract["matches"],
        "strategy": cfg.get("strategy") or "fts",
        "fastembed_available": embed_install.fastembed_available(),
        "vector_index_available": vector_index.available(),
        "cache_dir": str(paths.omw_home() / "models" / "fastembed"),
        "score_thresholds": {
            strategy: recall.score_threshold(effective_recall_cfg, strategy)
            for strategy in ("fts", "embedding", "hybrid")
        },
        "diagnostics": diagnostics,
        "vaults": vaults,
    }
