"""Admin/logic hub for the local embedding model: install, switch (with vector
reset + reindex), introspect, and register models. Single source of truth shared
by the `omw embed` CLI op and the setup wizard."""
from __future__ import annotations

from scripts import config, embed, embed_install, reindex, registry, vector_index


def resolve_dim(db_path, model: str) -> int:
    """Known dim, else probe by embedding one string with the model."""
    if model in embed.KNOWN_MODEL_DIMS:
        return embed.KNOWN_MODEL_DIMS[model]
    emb = embed.get_embedder({"provider": "fastembed", "model": model})
    vec = emb.embed(["probe"])[0]
    return len(vec)


def switch_model(db_path, model: str, *, assume_yes: bool = False,
                 interactive: bool = True) -> dict:
    if not embed_install.ensure_fastembed(assume_yes=assume_yes, interactive=interactive):
        return {"ok": False, "model": model, "dim": None, "vaults_reindexed": 0,
                "detail": "fastembed not installed"}
    try:
        dim = resolve_dim(db_path, model)
    except Exception as exc:
        return {"ok": False, "model": model, "dim": None, "vaults_reindexed": 0,
                "detail": f"could not load model {model!r}: {exc}"}
    config.set_config("recall.embedding.provider", "fastembed")
    config.set_config("recall.embedding.model", model)
    config.set_config("recall.embedding.dim", dim)
    vector_index.reset(db_path)
    n = 0
    failed = False
    conn = registry.connect(db_path)
    try:
        vaults = registry.list_vaults(db_path)
    finally:
        conn.close()
    for v in vaults:
        try:
            reindex.refresh_embeddings(db_path, vault_id=v["id"], relpaths=None)
        except Exception:
            pass
        # Check how many wiki notes exist in this vault
        db_conn = registry.connect(db_path)
        try:
            row = db_conn.execute(
                "SELECT COUNT(*) AS c FROM notes WHERE vault_id=? AND relpath LIKE 'wiki/%' AND parse_error=0",
                (v["id"],),
            ).fetchone()
            wiki_count = int(row["c"]) if row else 0
        except Exception:
            wiki_count = 0
        finally:
            db_conn.close()
        vec_count = vector_index.count(db_path, vault_id=v["id"])
        if wiki_count > 0:
            if vec_count > 0:
                n += 1
            else:
                failed = True
    if failed:
        return {
            "ok": False,
            "model": model,
            "dim": dim,
            "vaults_reindexed": n,
            "detail": "embedding produced no vectors (model id may be unsupported)",
        }
    return {"ok": True, "model": model, "dim": dim, "vaults_reindexed": n, "detail": None}


def add_model(db_path, model: str, *, assume_yes: bool = False,
              interactive: bool = True) -> dict:
    if not embed_install.ensure_fastembed(assume_yes=assume_yes, interactive=interactive):
        return {"ok": False, "model": model, "dim": None, "detail": "fastembed not installed"}
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
    n = 0
    for v in registry.list_vaults(db_path):
        try:
            reindex.refresh_embeddings(db_path, vault_id=v["id"], relpaths=None)
            n += 1
        except Exception:
            pass
    return {"ok": True, "vaults_reindexed": n}


def status(db_path) -> dict:
    cfg = config.load_config().get("recall") or {}
    emb = cfg.get("embedding") or {}
    vaults = []
    if vector_index.available():
        for v in registry.list_vaults(db_path):
            cnt = vector_index.count(db_path, vault_id=v["id"])
            vaults.append({"name": v["name"], "embedded": cnt})
    else:
        vaults = [{"name": v["name"], "embedded": 0} for v in registry.list_vaults(db_path)]
    return {
        "provider": emb.get("provider") or "none",
        "model": emb.get("model") or embed.DEFAULT_LOCAL_MODEL,
        "dim": emb.get("dim"),
        "strategy": cfg.get("strategy") or "fts",
        "fastembed_available": embed_install.fastembed_available(),
        "vector_index_available": vector_index.available(),
        "vaults": vaults,
    }
