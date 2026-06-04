"""omw setup wizard + doctor.

Non-interactive (flag-driven) is the tested contract. Interactive prompting uses
questionary if available (the `wizard` extra); otherwise it degrades to input().
The first slice writes config.yaml; secrets (search/persona/TTS) come in later slices.
"""
from __future__ import annotations

import json
import secrets
import shutil
import sys
from pathlib import Path

from scripts import adapters, config, registry, reindex, viewers
from scripts.paths import ensure_home, omw_home, registry_path, resolve_vault_root
from scripts.viewers.base import VaultRef


def _ensure_vault(name: str, mode: str, type_: str, location: str) -> None:
    ensure_home()
    db = registry_path()
    if not db.exists():
        registry.init_db(db)
    if any(v["name"] == name for v in registry.list_vaults(db)):
        return  # idempotent: vault already registered
    root = resolve_vault_root(name, location)
    root.mkdir(parents=True, exist_ok=True)
    adapters.get_adapter(type_, vault_name=name).init_vault(root, mode)
    vault = registry.add_vault(db, name=name, path=root, type_=type_, mode=mode)
    registry.set_active(db, name)
    reindex.full(db, vault_id=vault["id"])


def _write_config(default_vault: str) -> None:
    # Merge (not overwrite) so a previously-configured search section survives.
    from scripts import config
    config.set_config("version", 1)
    config.set_config("default_vault", default_vault)
    config.set_config("ui.language", "ko")


def run(
    *,
    section: str | None = None,
    noninteractive: bool = False,
    name: str = "default",
    mode: str = "wiki",
    type_: str = "markdown",
    location: str = "global",
) -> int:
    interactive = (not noninteractive) and sys.stdin.isatty()
    if interactive:
        return _run_interactive(name, mode, type_, location)
    ensure_home()
    _ensure_vault(name, mode, type_, location)
    _write_config(name)
    print(json.dumps(
        {"setup": "ok", "default_vault": name, "home": str(omw_home())},
        ensure_ascii=False,
    ))
    return 0


def _run_interactive(name: str, mode: str, type_: str, location: str) -> int:
    try:
        import questionary  # type: ignore

        def ask(msg: str, default: str) -> str:
            return questionary.text(msg, default=default).ask() or default
    except Exception:
        def ask(msg: str, default: str) -> str:
            got = input(f"{msg} [{default}]: ").strip()
            return got or default

    name = ask("Vault name", name)
    mode = ask("Mode (memo/wiki)", mode)
    type_ = ask("Type (markdown/obsidian)", type_)
    location = ask("Location (global/project/<abs path>)", location)
    ensure_home()
    _ensure_vault(name, mode, type_, location)
    _write_config(name)
    print(
        f"setup complete — vault '{name}' at {omw_home()}. "
        f"Search/persona/TTS sections: configure later with 'omw setup search' (coming soon)."
    )
    return 0


def _prompt(kind: str, message: str, *, choices=None, default=None):
    """questionary prompt with an input() fallback (used when questionary is absent).

    kind: "text" | "password" | "select" | "confirm" | "checkbox".
    Returns: str | bool | list[str] | None depending on kind.
    """
    try:
        import questionary  # type: ignore
        if kind == "password":
            return questionary.password(message).ask()
        if kind == "select":
            return questionary.select(message, choices=choices, default=default).ask()
        if kind == "text":
            return questionary.text(message, default=default or "").ask()
        if kind == "confirm":
            return questionary.confirm(message, default=bool(default)).ask()
        if kind == "checkbox":
            return questionary.checkbox(message, choices=choices).ask()
        raise ValueError(f"unknown prompt kind: {kind!r}")
    except ImportError:
        if kind == "confirm":
            ans = input(f"{message} [{'Y/n' if default else 'y/N'}]: ").strip().lower()
            return bool(default) if not ans else ans in ("y", "yes")
        if kind == "checkbox":
            raw = input(f"{message} (comma-separated, blank = all): ").strip()
            return [s.strip() for s in raw.split(",") if s.strip()] if raw else list(choices or [])
        if kind == "password":
            import getpass
            try:
                return getpass.getpass(f"{message}: ") or default
            except (OSError, EOFError):
                ans = input(f"{message}: ").strip()
                return ans or default
        suffix = f" [{default}]" if default else ""
        ans = input(f"{message}{suffix}: ").strip()
        return ans or default


#: provider -> ordered list of (field, env var) the wizard must write.
#: Multi-secret providers (e.g. brightdata) are only enabled once ALL are present.
_PROVIDER_SECRETS = {
    "brave":      [("api_key", "BRAVE_API_KEY")],
    "tavily":     [("api_key", "TAVILY_API_KEY")],
    "exa":        [("api_key", "EXA_API_KEY")],
    "firecrawl":  [("api_key", "FIRECRAWL_API_KEY")],
    "brightdata": [("api_key", "BRIGHTDATA_API_KEY"), ("zone", "BRIGHTDATA_ZONE")],
}


def setup_search(*, noninteractive: bool = False, provider: str | None = None,
                 api_key: str | None = None, zone: str | None = None) -> int:
    from scripts import config
    interactive = (not noninteractive) and sys.stdin.isatty()
    if interactive:
        try:
            import questionary  # type: ignore
            provider = questionary.select(
                "Search provider", choices=list(_PROVIDER_SECRETS) + ["skip"]).ask() or "skip"
        except Exception:
            provider = input(f"Search provider {list(_PROVIDER_SECRETS)} [skip]: ").strip() or "skip"
    if not provider or provider == "skip":
        print("search setup skipped — re-run `omw setup search` anytime.")
        return 0
    if provider not in _PROVIDER_SECRETS:
        print(f"error: unknown provider {provider!r}; choose from {list(_PROVIDER_SECRETS)}",
              file=sys.stderr)
        return 1
    supplied = {"api_key": api_key, "zone": zone}
    all_present = True
    for field, env_var in _PROVIDER_SECRETS[provider]:
        val = supplied.get(field)
        if interactive and not val:
            val = _prompt("password", f"{field} (blank to defer)") or None
        if val:
            config.set_secret(env_var, val)
        else:
            all_present = False
    config.set_config("search.provider", provider)
    config.set_config("search.enabled", all_present)
    if all_present:
        print(f"✓ search provider '{provider}' configured.")
    else:
        print(f"recorded provider '{provider}' — add missing key(s) with "
              f"`omw setup search --provider {provider} --api-key <key>` "
              f"(brightdata also needs --zone).")
    return 0


def setup_personas(*, enabled: list[str] | None = None, main: str | None = None,
                   hosts: list[str] | None = None, base_dir=None,
                   noninteractive: bool = False) -> int:
    """Record the enabled persona roster + main, and export to host instruction files."""
    from pathlib import Path
    from scripts import config, personas, persona_export
    specs = personas.list_personas()
    all_names = [p["name"] for p in specs]
    descriptions = {p["name"]: p.get("description", "") for p in specs}
    interactive = (not noninteractive) and sys.stdin.isatty()
    if interactive and enabled is None:
        picked = _prompt("checkbox", "Enable personas", choices=all_names)
        enabled = picked or list(all_names)
    if interactive and main is None:
        default_main = ("operations-orchestrator" if "operations-orchestrator" in (enabled or all_names)
                        else ((enabled or all_names)[0] if (enabled or all_names) else None))
        main = _prompt("select", "Main persona", choices=enabled or all_names,
                       default=default_main) or None
    if interactive and hosts is None:
        hosts = _prompt("checkbox", "Export to hosts",
                        choices=list(persona_export.HOST_FILES)) or None
    if enabled is None:
        enabled = list(all_names)
    unknown = [n for n in enabled if n not in all_names]
    if unknown:
        print(f"error: unknown persona(s): {unknown}", file=sys.stderr)
        return 1
    if main is None:
        main = "operations-orchestrator" if "operations-orchestrator" in enabled \
            else (enabled[0] if enabled else None)
    if main is not None and main not in enabled:
        print(f"error: main persona {main!r} not in enabled set", file=sys.stderr)
        return 1
    if hosts is None:
        hosts = list(persona_export.HOST_FILES)
    base = Path(base_dir) if base_dir else Path.cwd()
    config.set_config("personas.enabled", enabled)
    config.set_config("personas.main", main)
    written = persona_export.export_personas(
        enabled=enabled, main=main, descriptions=descriptions,
        base_dir=base, hosts=hosts,
    )
    print(f"✓ personas: {len(enabled)} enabled, main={main}; "
          f"exported to {', '.join(p.name for p in written)}")
    return 0


def setup_tts(*, provider: str | None = None, voice_id: str | None = None,
              api_key: str | None = None, noninteractive: bool = False) -> int:
    """Configure a TTS provider + voice. Key -> ~/.omw/.env (0600). Mirrors setup_search."""
    from scripts import config
    interactive = (not noninteractive) and sys.stdin.isatty()
    if interactive and provider is None:
        provider = _prompt("select", "TTS provider", choices=["elevenlabs", "skip"],
                           default="elevenlabs") or "skip"
        if provider == "skip":
            print("tts setup skipped — re-run `omw setup tts` anytime.")
            return 0
        if not voice_id:
            voice_id = _prompt("text", "Voice ID (blank to defer)") or None
        if not api_key:
            api_key = _prompt("password", "API key (blank to defer)") or None
    provider = provider or "elevenlabs"
    if api_key:
        config.set_secret(f"{provider.upper()}_API_KEY", api_key)
    config.set_config("tts.provider", provider)
    config.set_config("tts.voice_id", voice_id)
    enabled = bool(api_key and voice_id)
    config.set_config("tts.enabled", enabled)
    if enabled:
        print(f"✓ tts provider '{provider}' configured (voice {voice_id}).")
    else:
        print(f"tts provider '{provider}' recorded — provide --api-key + --voice-id to enable.")
    return 0


def setup_serve(*, token: str | None = None, generate_token: bool = False,
                noninteractive: bool = False) -> int:
    """Configure OMW_SERVE_TOKEN in ~/.omw/.env (0600)."""
    from scripts import config
    interactive = (not noninteractive) and sys.stdin.isatty()
    if interactive and not token and not generate_token:
        if _prompt("confirm", "Generate a new serve token?", default=True):
            generate_token = True
        else:
            token = _prompt("password", "Paste OMW_SERVE_TOKEN (blank to skip)") or None
    if generate_token:
        token = secrets.token_urlsafe(32)
    if not token:
        if interactive:
            print("serve setup skipped — re-run `omw setup serve` anytime.")
            return 0
        print("error: provide --token <t> or --generate-token", file=sys.stderr)
        return 1
    config.set_secret("OMW_SERVE_TOKEN", token)
    print(f"✓ serve token configured ({len(token)} chars). Start with: omw serve")
    return 0


def setup_import(*, token: str | None = None, src_dir: str | None = None,
                 noninteractive: bool = False) -> int:
    """Configure import: Notion API key (-> .env 0600) + default source folder."""
    from scripts import config
    interactive = (not noninteractive) and sys.stdin.isatty()
    if interactive:
        if token is None:
            token = _prompt("password", "Notion API key (blank to skip)") or None
        if src_dir is None:
            src_dir = _prompt("text", "Default import folder (blank to skip)") or None
    if token:
        config.set_secret("NOTION_API_KEY", token)
    if src_dir:
        config.set_config("import.default_src", src_dir)
    print("✓ import configured." if (token or src_dir)
          else "import setup skipped — re-run `omw setup import` anytime.")
    return 0


def setup_viewer(*, viewer: str | None = None, vault: str | None = None,
                 noninteractive: bool = False) -> int:
    """Pick a viewer (default obsidian), store it, and scaffold its config into the vault."""
    choice = viewer or "obsidian"
    if choice not in viewers.VIEWER_NAMES:
        print(f"error: unknown viewer {choice!r}; choices: {', '.join(viewers.VIEWER_NAMES)}",
              file=sys.stderr)
        return 1
    config.set_config("viewer.default", choice)

    db = registry_path()
    row = (next((v for v in registry.list_vaults(db) if v["name"] == vault), None)
           if vault else registry.get_active(db))
    if row is None:
        print(f"viewer default set to {choice!r}. (no active vault to scaffold; "
              f"create one then re-run `omw setup viewer`)")
        return 0

    root = Path(row["path"])
    v = viewers.get_viewer(choice)
    ref = VaultRef(root=root, name=root.name)
    written, hints = v.scaffold_config(ref)
    print(f"viewer: {choice}  vault: {row['name']}  ({root})")
    for p in written:
        print(f"  wrote {p}")
    for h in hints:
        print(f"  note: {h}")
    return 0


def run_all(*, noninteractive: bool = False, base_dir=None) -> int:
    """Top-level interactive wizard: walk every section in order with per-step skip.

    Returns the first non-zero section result (continuing through the rest), else 0.
    """
    from scripts import banner
    banner.render()   # animated when interactive TTY; static/suppressed otherwise
    first_error = 0
    steps = [
        ("vault", lambda: run(noninteractive=noninteractive)),
        ("search", lambda: setup_search(noninteractive=noninteractive)),
        ("serve", lambda: setup_serve(noninteractive=noninteractive)),
        ("tts", lambda: setup_tts(noninteractive=noninteractive)),
        ("personas", lambda: setup_personas(noninteractive=noninteractive, base_dir=base_dir)),
        ("import", lambda: setup_import(noninteractive=noninteractive)),
        ("viewer", lambda: setup_viewer(noninteractive=noninteractive)),
    ]
    for name, fn in steps:
        try:
            rc = fn()
        except Exception as exc:  # one bad section must not abort the whole wizard
            print(f"error: section {name!r} failed: {exc}", file=sys.stderr)
            rc = 1
        if rc != 0 and first_error == 0:
            first_error = rc
    print("omw setup complete.")
    return first_error


def doctor() -> int:
    home = omw_home()
    db = registry_path()
    print(f"omw home:   {home}  {'ok' if home.exists() else 'missing (run: omw setup)'}")
    print(f"registry:   {db}  {'ok' if db.exists() else 'missing'}")
    vaults = registry.list_vaults(db) if db.exists() else []
    if vaults:
        for v in vaults:
            mark = "*" if v["is_active"] else " "
            print(f"  {mark} {v['name']} ({v['mode']}/{v['type']}) {v['path']}")
    else:
        print("  no vaults registered — run: omw setup")
    import scripts.fetch_chromium as _fc
    ytdlp = "ok" if shutil.which("yt-dlp") else "missing (pip install yt-dlp — for YouTube)"
    chromium = "ok" if _fc.available() else "missing (pip install playwright && playwright install chromium — for SPA pages)"
    print(f"fetch yt-dlp:  {ytdlp}")
    print(f"fetch chromium: {chromium}")
    return 0
