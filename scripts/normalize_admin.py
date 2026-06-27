"""Switch the search normalizer provider (heuristic | kiwi), then reindex so the
FTS analyzer-version gate rebuilds. Single source of truth for activation; mirrors
embed_admin.switch_model (which imports registry/reindex at module top)."""
from __future__ import annotations

from scripts import config, kiwi_install, reindex, registry

PROVIDERS = ("heuristic", "kiwi")


def switch_provider(db_path, provider: str, *, assume_yes: bool = False,
                    interactive: bool = True) -> dict:
    if provider not in PROVIDERS:
        return {"ok": False, "provider": provider, "vaults_reindexed": 0,
                "detail": f"unknown provider {provider!r}; choose from {list(PROVIDERS)}"}
    if provider == "kiwi":
        if not kiwi_install.ensure_kiwi(assume_yes=assume_yes, interactive=interactive):
            return {"ok": False, "provider": provider, "vaults_reindexed": 0,
                    "detail": "kiwipiepy not installed"}
    config.set_config("recall.normalizer", provider)
    n = 0
    for v in registry.list_vaults(db_path):
        try:
            reindex.full(db_path, vault_id=v["id"])
            n += 1
        except Exception:
            pass
    return {"ok": True, "provider": provider, "vaults_reindexed": n, "detail": None}
