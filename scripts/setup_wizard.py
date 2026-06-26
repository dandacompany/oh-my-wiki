"""omw setup wizard + doctor.

Non-interactive (flag-driven) is the tested contract. Interactive prompting uses
questionary if available (the `wizard` extra); otherwise it degrades to input().
The first slice writes config.yaml; secrets (search/persona/TTS) come in later slices.
"""
from __future__ import annotations

import importlib
import json
import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

from scripts import adapters, config, registry, reindex, viewers
from scripts.paths import ensure_home, omw_home, registry_path, resolve_vault_root
from scripts.viewers.base import VaultRef


_WIZARD_UI_TRIED = False


def _questionary_available() -> bool:
    try:
        import questionary  # noqa: F401
        return True
    except ImportError:
        return False


def ensure_wizard_ui() -> bool:
    """Best-effort: make the questionary arrow-key TUI available for interactive setup.

    Confirm-first; never silent; one attempt per process. Returns True if available.
    Any failure degrades silently to the comma-text fallback (never raises).
    """
    global _WIZARD_UI_TRIED
    if _questionary_available():
        return True
    if _WIZARD_UI_TRIED:
        return False
    _WIZARD_UI_TRIED = True
    assume_yes = os.environ.get("OMW_BOOTSTRAP_YES") == "1"
    if not assume_yes:
        if not sys.stdin.isatty():
            return False
        try:
            ans = input("화살표키 선택 UI(questionary)가 없습니다. 지금 설치할까요? [y/N] ")
        except EOFError:
            return False
        if not ans.strip().lower().startswith("y"):
            return False
    from scripts import platform_env
    try:
        subprocess.run(platform_env.pip_install_argv("questionary"), check=True)
        importlib.invalidate_caches()
    except Exception:
        return False
    return _questionary_available()


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
    in_wizard: bool = False,
) -> int:
    interactive = (not noninteractive) and sys.stdin.isatty()
    if interactive:
        return _run_interactive(name, mode, type_, location, in_wizard=in_wizard)
    ensure_home()
    _ensure_vault(name, mode, type_, location)
    _write_config(name)
    print(json.dumps(
        {"setup": "ok", "default_vault": name,
         "vault_path": str(resolve_vault_root(name, location)), "home": str(omw_home())},
        ensure_ascii=False,
    ))
    return 0


def _run_interactive(name: str, mode: str, type_: str, location: str,
                     *, in_wizard: bool = False) -> int:
    name = _prompt("text", "Vault name", default=name) or name
    mode = _prompt("select", "Mode", choices=["wiki", "memo"], default=mode) or mode
    type_ = _prompt("select", "Type", choices=["obsidian", "markdown"], default=type_) or type_
    loc_default = location if location in ("global", "project") else "custom path…"
    loc_choice = _prompt("select", "Location",
                         choices=["global", "project", "custom path…"], default=loc_default)
    if loc_choice == "custom path…":
        location = _prompt("text", "Absolute vault path", default=location) or location
    elif loc_choice:
        location = loc_choice
    ensure_home()
    _ensure_vault(name, mode, type_, location)
    _write_config(name)
    vault_path = resolve_vault_root(name, location)
    if in_wizard:
        print(f"✓ vault '{name}' ({mode}/{type_}) at {vault_path}")
    else:
        print(
            f"setup complete — vault '{name}' ({mode}/{type_}) at {vault_path}. "
            f"Configure search/fetch/persona/recall sections anytime with 'omw setup search' / "
            f"'omw setup fetch' / 'omw setup personas' / 'omw setup recall'."
        )
    return 0


def _checkbox_spec(choices):
    """Normalize checkbox choices (plain str or {"name","checked"}) into
    (names, checked_names, has_checked_flag)."""
    names, checked = [], []
    has_flag = False
    for c in choices or []:
        if isinstance(c, dict):
            names.append(c["name"])
            if "checked" in c:
                has_flag = True
            if c.get("checked"):
                checked.append(c["name"])
        else:
            names.append(c)
    return names, checked, has_flag


def _prompt(kind: str, message: str, *, choices=None, default=None):
    """questionary prompt with an input() fallback (used when questionary is absent).

    kind: "text" | "password" | "select" | "confirm" | "checkbox".
    Returns: str | bool | list[str] | None depending on kind.
    """
    ensure_wizard_ui()  # one-shot, best-effort: install the arrow-key TUI if interactive & missing
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
            names, checked, has_flag = _checkbox_spec(choices)
            if has_flag:
                qchoices = [questionary.Choice(n, checked=(n in checked)) for n in names]
            else:
                qchoices = names
            return questionary.checkbox(message, choices=qchoices).ask()
        raise ValueError(f"unknown prompt kind: {kind!r}")
    except ImportError:
        if kind == "confirm":
            ans = input(f"{message} [{'Y/n' if default else 'y/N'}]: ").strip().lower()
            return bool(default) if not ans else ans in ("y", "yes")
        if kind == "checkbox":
            names, checked, has_flag = _checkbox_spec(choices)
            hint = "blank = keep checked" if has_flag else "blank = all"
            raw = input(f"{message} (comma-separated, {hint}): ").strip()
            if raw:
                return [s.strip() for s in raw.split(",") if s.strip()]
            return list(checked) if has_flag else list(names)
        if kind == "password":
            import getpass
            try:
                return getpass.getpass(f"{message}: ") or default
            except (OSError, EOFError):
                ans = input(f"{message}: ").strip()
                return ans or default
        if kind == "select":
            # No questionary arrow-UI: show all choices so the user knows the options
            # (e.g. that 'skip' is available), not just the default.
            opts = "/".join(str(c) for c in (choices or []))
            prompt = f"{message} ({opts})" if opts else message
            suffix = f" [{default}]" if default else ""
            ans = input(f"{prompt}{suffix}: ").strip()
            return ans or default
        suffix = f" [{default}]" if default else ""
        ans = input(f"{message}{suffix}: ").strip()
        return ans or default


#: provider -> ordered list of (field, env var) the wizard must write.
#: Multi-secret providers (e.g. brightdata) are only enabled once ALL are present.
#: Order matters: brightdata's "zone" resolution reads the already-resolved "api_key"
#: from `supplied`, so "api_key" MUST precede "zone" here.
_PROVIDER_SECRETS = {
    "brave":      [("api_key", "BRAVE_API_KEY")],
    "tavily":     [("api_key", "TAVILY_API_KEY")],
    "exa":        [("api_key", "EXA_API_KEY")],
    "firecrawl":  [("api_key", "FIRECRAWL_API_KEY")],
    "brightdata": [("api_key", "BRIGHTDATA_API_KEY"), ("zone", "BRIGHTDATA_ZONE")],
}


def _resolve_brightdata_zone(api_key: str, *, zone: str | None, interactive: bool,
                             create_zone: bool) -> str | None:
    """Find or create a usable Bright Data zone for the given key.

    Override: an explicit `zone` is used verbatim (no API call). Otherwise list the
    account's zones and prefer a SERP-capable one (so search works); fall back to an
    unblocker zone (scrape works, SERP may not — warn); if none exist, create one only
    when allowed (`--create-zone`, or an interactive confirm — creation may incur charges).
    Returns the chosen/created zone name, or None to defer. Never raises.
    """
    if zone:
        return zone
    from scripts.search.providers import brightdata
    try:
        zones = brightdata.list_zones(api_key)
    except Exception as exc:  # base.SearchError or any HTTP/network failure
        print(f"  could not list Bright Data zones ({exc}); set one later with "
              f"`omw setup search --provider brightdata --api-key <key> --zone <name>`.")
        return None
    serp = [z["name"] for z in zones
            if isinstance(z, dict) and z.get("type") == "serp" and z.get("name")]
    unblocker = [z["name"] for z in zones
                 if isinstance(z, dict) and z.get("type") == "unblocker" and z.get("name")]
    if serp:
        if interactive and len(serp) > 1:
            return _prompt("select", "Bright Data SERP zone", choices=serp) or serp[0]
        print(f"  using Bright Data SERP zone '{serp[0]}'.")
        return serp[0]
    if unblocker:
        # A non-SERP unblocker zone serves scrape but NOT `omw search`. Don't enable a
        # config we predict won't work — defer and nudge toward creating a SERP zone.
        print(f"  found only a non-SERP Bright Data zone ('{unblocker[0]}'); web search needs a "
              f"SERP-enabled zone. Re-run with --create-zone (may incur charges) or pass "
              f"--zone <serp-zone> to use an existing one.")
        return None
    # No usable zone — create only with explicit opt-in.
    do_create = create_zone
    if interactive and not do_create:
        do_create = _prompt("confirm",
                            f"No usable Bright Data zone found. Create "
                            f"'{brightdata.DEFAULT_ZONE_NAME}' now? (may incur charges)")
    if not do_create:
        return None
    try:
        name = brightdata.create_zone(api_key)
        print(f"  created Bright Data zone '{name}'.")
        return name
    except Exception as exc:
        print(f"  could not create a Bright Data zone ({exc}); the API key may lack the "
              f"Admin/Ops role. Create a zone in the dashboard and pass --zone <name>.")
        return None


#: providers that implement scrape() — the only valid `omw setup fetch` choices.
_SCRAPE_PROVIDERS = ("brightdata", "firecrawl")


def _setup_provider_section(*, section: str, label: str, allowed: list[str],
                            noninteractive: bool, provider: str | None,
                            api_key: str | None, zone: str | None,
                            create_zone: bool) -> int:
    """Shared provider+secret(+brightdata zone) writer for `setup search`/`setup fetch`.

    `section` selects the config prefix (`<section>.provider`/`.enabled`); `allowed`
    restricts the provider menu. Writes per-provider secret env vars (shared across
    sections) and records the chosen provider under `<section>`.
    """
    from scripts import config
    interactive = (not noninteractive) and sys.stdin.isatty()
    if interactive:
        try:
            import questionary  # type: ignore
            provider = questionary.select(
                f"{label} provider", choices=list(allowed) + ["skip"]).ask() or "skip"
        except Exception:
            provider = input(f"{label} provider {list(allowed)} [skip]: ").strip() or "skip"
    if not provider or provider == "skip":
        print(f"{section} setup skipped — re-run `omw setup {section}` anytime.")
        return 0
    if provider not in allowed:
        print(f"error: {provider!r} is not a valid {label.lower()} provider; "
              f"choose from {list(allowed)}", file=sys.stderr)
        return 1
    supplied = {"api_key": api_key, "zone": zone}
    all_present = True
    for field, env_var in _PROVIDER_SECRETS[provider]:
        val = supplied.get(field)
        # brightdata's zone is resolved via the Account Management API, not a plain prompt.
        if provider == "brightdata" and field == "zone":
            key = supplied.get("api_key")
            val = _resolve_brightdata_zone(key, zone=val, interactive=interactive,
                                           create_zone=create_zone) if key else None
        elif interactive and not val:
            val = _prompt("password", f"{field} (blank to defer)") or None
        if val:
            config.set_secret(env_var, val)
            supplied[field] = val  # later fields (zone) read the resolved api_key
        else:
            all_present = False
    # search + fetch both on brightdata share the single BRIGHTDATA_ZONE secret — a
    # per-role zone isn't possible, so warn rather than silently coupling them.
    if (section == "fetch" and provider == "brightdata"
            and (config.load_config().get("search") or {}).get("provider") == "brightdata"):
        print("  note: search and fetch both use brightdata — they share the same "
              "BRIGHTDATA_ZONE secret (a different zone per role isn't supported).")
    config.set_config(f"{section}.provider", provider)
    config.set_config(f"{section}.enabled", all_present)
    if all_present:
        print(f"✓ {label.lower()} provider '{provider}' configured.")
    else:
        print(f"recorded provider '{provider}' — add missing key(s) with "
              f"`omw setup {section} --provider {provider} --api-key <key>` "
              f"(brightdata also needs --zone).")
    return 0


def setup_search(*, noninteractive: bool = False, provider: str | None = None,
                 api_key: str | None = None, zone: str | None = None,
                 create_zone: bool = False) -> int:
    return _setup_provider_section(
        section="search", label="Search", allowed=list(_PROVIDER_SECRETS),
        noninteractive=noninteractive, provider=provider, api_key=api_key,
        zone=zone, create_zone=create_zone)


def setup_fetch(*, noninteractive: bool = False, provider: str | None = None,
                api_key: str | None = None, zone: str | None = None,
                create_zone: bool = False) -> int:
    """Configure the cloud page-unlock / browser (scrape) provider independently of
    search. Only scrape-capable providers are offered."""
    return _setup_provider_section(
        section="fetch", label="Fetch", allowed=list(_SCRAPE_PROVIDERS),
        noninteractive=noninteractive, provider=provider, api_key=api_key,
        zone=zone, create_zone=create_zone)


def setup_personas(*, enabled: list[str] | None = None, main: str | None = None,
                   hosts: list[str] | None = None, base_dir=None,
                   noninteractive: bool = False,
                   profile: str | None = None, workspace: str | None = None) -> int:
    """Record the enabled persona roster + main, and export to host instruction files."""
    from pathlib import Path
    from scripts import config, personas, persona_export
    from scripts import hosts as hostsmod
    specs = personas.list_personas()
    all_names = [p["name"] for p in specs]
    descriptions = {p["name"]: p.get("description", "") for p in specs}
    interactive = (not noninteractive) and sys.stdin.isatty()
    # Load persisted config to use as fallback (preserve on re-run).
    cur_cfg = config.load_config().get("personas") or {}
    cur_enabled = cur_cfg.get("enabled")   # list or None
    cur_main = cur_cfg.get("main")         # str or None
    # Validate cur_enabled: drop any persona names that no longer exist.
    if cur_enabled is not None:
        cur_enabled = [n for n in cur_enabled if n in all_names] or None
    if interactive and enabled is None:
        picked = _prompt("checkbox", "Enable personas", choices=all_names)
        enabled = picked or list(all_names)
    if interactive and main is None:
        _eff_enabled = enabled or cur_enabled or all_names
        default_main = (cur_main if cur_main and cur_main in _eff_enabled
                        else ("wiki-librarian" if "wiki-librarian" in _eff_enabled
                              else (_eff_enabled[0] if _eff_enabled else None)))
        main = _prompt("select", "Main persona", choices=enabled or all_names,
                       default=default_main) or None
    if interactive and hosts is None:
        # Convention-level picker: codex+opencode share AGENTS.md → one entry.
        choices_meta = hostsmod.instruction_choices()
        choice_labels = [f"{', '.join(c['members'])} ({c['file']})" for c in choices_meta]
        picked_labels = _prompt("checkbox", "Export to hosts", choices=choice_labels) or []
        # Map labels back to flat host list by expanding members of each picked choice.
        picked_hosts: list[str] = []
        for label, meta in zip(choice_labels, choices_meta):
            if label in picked_labels:
                picked_hosts.extend(meta["members"])
        hosts = picked_hosts or None
        # Scoped host sub-prompts: ask for profile/workspace when not yet provided.
        if hosts:
            for host in hosts:
                if not hostsmod.is_scoped(host):
                    continue
                if host == "hermes" and profile is None:
                    profiles = hostsmod.list_profiles()
                    if profiles:
                        profile = _prompt("select", "Hermes profile",
                                          choices=profiles,
                                          default=hostsmod.active_profile()) or profiles[0]
                    else:
                        profile = hostsmod.active_profile()
                elif host == "openclaw" and workspace is None:
                    workspaces = hostsmod.list_workspaces()
                    if workspaces:
                        workspace = _prompt("select", "OpenClaw workspace",
                                            choices=workspaces,
                                            default=hostsmod.default_workspace()) or workspaces[0]
                    else:
                        workspace = hostsmod.default_workspace()
    # Non-interactive fallback: preserve previously saved roster if no explicit arg.
    if enabled is None:
        enabled = list(cur_enabled) if cur_enabled else list(all_names)
    unknown = [n for n in enabled if n not in all_names]
    if unknown:
        print(f"error: unknown persona(s): {unknown}", file=sys.stderr)
        return 1
    if main is None:
        if cur_main and cur_main in enabled:
            main = cur_main
        elif "wiki-librarian" in enabled:
            main = "wiki-librarian"
        else:
            main = enabled[0] if enabled else None
    if main is not None and main not in enabled:
        print(f"error: main persona {main!r} not in enabled set", file=sys.stderr)
        return 1
    if hosts is None:
        # Non-interactive default: repo-trio hosts only (no scoped hosts auto-selected).
        hosts = [h for h, d in hostsmod.HOSTS.items() if d["kind"] == "repo"]
    base = Path(base_dir) if base_dir else Path.cwd()
    # Filter to only hosts that can be resolved — mirror setup_recall's per-host skip pattern.
    resolvable: list[str] = []
    for host in hosts:
        try:
            hostsmod.resolve_instruction_path(host, base, profile=profile, workspace=workspace)
            resolvable.append(host)
        except ValueError as exc:
            print(f"  - {host}: skipped ({exc})")
    config.set_config("personas.enabled", enabled)
    config.set_config("personas.main", main)
    written = persona_export.export_personas(
        enabled=enabled, main=main, descriptions=descriptions,
        base_dir=base, hosts=resolvable, profile=profile, workspace=workspace,
    )
    from scripts import commandmap
    commandmap.export(base, resolvable, profile=profile, workspace=workspace)
    print(f"✓ personas: {len(enabled)} enabled, main={main}; "
          f"exported to {', '.join(p.name for p in written)}")
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

    if choice == "obsidian":
        from scripts import platform_env
        from scripts.viewers import obsidian as _ob
        interactive = (not noninteractive) and sys.stdin.isatty()
        if not _ob.obsidian_installed():
            _ok, msg = _ob.install_obsidian(
                assume_yes=os.environ.get("OMW_BOOTSTRAP_YES") == "1",
                interactive=interactive)
            print(f"  obsidian: {msg}")
        if platform_env.is_wsl():
            wp = platform_env.windows_user_profile()
            winuser = wp.name if wp is not None else "<windows-user>"
            print("  ⚠️  WSL 감지 — Windows Obsidian으로 \\\\wsl.localhost 경로를 열면 "
                  "fs.watch EISDIR로 실패합니다. 두 가지 중 하나로 여세요:")
            print("    ① 리눅스 Obsidian을 WSL에 설치(위 부트스트랩) → `obsidian`으로 WSLg 실행 "
                  "(vault는 그대로, 네이티브 watch).")
            print("    ② 기존 Windows Obsidian을 쓰려면 vault를 Windows 드라이브에 두세요:")
            print(f"         omw vault create {row['name']} --mode wiki --type obsidian \\")
            print(f"           --location \"/mnt/c/Users/{winuser}/omw-vaults/{row['name']}\"")
            if _ob.register_vault_windows(root):
                print("  → Windows obsidian.json에도 등록했습니다(앱 재시작 후 인식).")

    written, hints = v.scaffold_config(ref)
    print(f"viewer: {choice}  vault: {row['name']}  ({root})")
    for p in written:
        print(f"  wrote {p}")
    for h in hints:
        print(f"  note: {h}")
    return 0


def _install_hermes_profiles(interactive: bool) -> list[dict]:
    """Install/refresh OMW into selected hermes profiles. Interactive shows a
    profile checkbox (already-installed pre-checked); noninteractive refreshes the
    already-installed profiles (main fallback when none)."""
    from scripts import agent_skills
    targets = agent_skills.hermes_profile_targets()
    by_name = {t["name"]: t for t in targets}
    installed = [t["name"] for t in targets if t["installed"]]

    if interactive and len(targets) > 1:
        default_checked = installed or [t["name"] for t in targets]
        choices = [{"name": t["name"], "checked": t["name"] in default_checked} for t in targets]
        picked = _prompt("checkbox", "Install OMW skill into which hermes profiles?",
                         choices=choices)
        if picked is not None and picked == []:
            print("  - hermes: no profiles selected, skipping")
            return []
        chosen = picked if picked is not None else default_checked
    else:
        chosen = installed or ["main"]

    results = []
    for name in chosen:
        t = by_name.get(name)
        if t is None:
            continue
        r = agent_skills.install_into_dir(t["skills_dir"])
        r = {"agent": "hermes", "name": name, **r}
        results.append(r)
    return results


def setup_agents(*, agents: list[str] | None = None, noninteractive: bool = False) -> int:
    """Install the OMW skill into selected agents' skill systems."""
    from scripts import agent_skills
    detected = agent_skills.detect_agents()
    interactive = (not noninteractive) and sys.stdin.isatty()
    if agents is None:
        if not detected:
            print("no agents detected (claude/codex/hermes/gemini) — skipping skill install.")
            return 0
        if interactive:
            picked = _prompt("checkbox", "Install OMW skill into which agents?", choices=detected)
            agents = picked if picked is not None else detected
        else:
            agents = detected
    targets, skipped = [], []
    for a in agents:
        (targets if (not detected or a in detected) else skipped).append(a)
    for a in skipped:
        print(f"  - {a}: not installed, skipped")
    if not targets:
        print("agents setup skipped — no selected agent is installed.")
        return 0
    hermes_selected = "hermes" in targets
    non_hermes = [a for a in targets if a != "hermes"]
    results = agent_skills.install_many(non_hermes) if non_hermes else []
    if hermes_selected:
        results = results + _install_hermes_profiles(interactive)
    for r in results:
        mark = "✓" if r.get("ok") else "✗"
        detail = f" ({r['detail']})" if r.get("detail") else ""
        label = r["agent"] + (f"/{r['name']}" if r.get("name") else "")
        print(f"  {mark} {label} [{r.get('method') or '—'}]{detail}")
        if r.get("dest"):
            print(f"      → {r['dest']}")
    if any(r.get("method") == "skills-cli" and (r.get("dest") or "").find(".agents/skills") >= 0
           for r in results):
        print("  note: 프로젝트 로컬(.agents/skills)에 설치됐습니다 — 해당 폴더에서 "
              "codex/claude를 실행해야 스킬이 인식됩니다.")
    return 0 if all(r.get("ok") for r in results) else 1


def setup_recall(*, mode: str | None = None, strategy: str | None = None,
                 submode: str | None = None, hosts: list[str] | None = None,
                 base_dir=None, noninteractive: bool = False,
                 provider: str | None = None, model: str | None = None,
                 dim: int | None = None,
                 profile: str | None = None, workspace: str | None = None) -> int:
    """Configure auto wiki-recall (two axes):
      mode     — trigger: off | advisory | auto
      strategy — retrieval: fts | embedding | hybrid | llm (+ llm.submode)
    Sets config and injects the host-agnostic Tier-1 guidance block into each
    host's instruction file. Host-neutral by design — not Claude-only.
    All strategies (fts/embedding/hybrid/llm) are implemented; `llm` is agent-delegated
    guidance (advisory-natured — no hook-side LLM call)."""
    from pathlib import Path
    from scripts import config, recall
    cur = config.load_config().get("recall") or {}
    cur_mode = cur.get("mode", "auto")
    cur_strat = cur.get("strategy", "fts")
    cur_sub = (cur.get("llm") or {}).get("submode", "route")
    cur_emb = cur.get("embedding") or {}
    choices = ["auto", "advisory", "off"]
    interactive = (not noninteractive) and sys.stdin.isatty()
    if interactive and mode is None:
        mode = _prompt("select", "Wiki recall mode (trigger)", choices=choices, default=cur_mode) or cur_mode
    mode = mode or cur_mode
    if mode not in choices:
        print(f"error: unknown recall mode {mode!r}; choose from {choices}", file=sys.stderr)
        return 1
    config.set_config("recall.mode", mode)
    if mode == "off":
        print("recall disabled (recall.mode=off). Re-run `omw setup recall` to enable.")
        return 0
    # Axis 2 — retrieval strategy (fts/embedding/hybrid deterministic; llm agent-delegated).
    if interactive and strategy is None:
        strategy = _prompt("select", "Retrieval strategy", choices=list(recall.STRATEGIES),
                           default=cur_strat) or cur_strat
    strategy = strategy or cur_strat
    if strategy not in recall.STRATEGIES:
        print(f"error: unknown strategy {strategy!r}; choose from {list(recall.STRATEGIES)}", file=sys.stderr)
        return 1
    config.set_config("recall.strategy", strategy)
    if strategy == "llm":
        if interactive and submode is None:
            submode = _prompt("select", "LLM submode", choices=list(recall.LLM_SUBMODES),
                              default=cur_sub) or cur_sub
        submode = submode or cur_sub
        if submode not in recall.LLM_SUBMODES:
            print(f"error: unknown llm submode {submode!r}; choose from {list(recall.LLM_SUBMODES)}",
                  file=sys.stderr)
            return 1
        config.set_config("recall.llm.submode", submode)
        configure_recall(strategy=strategy, provider="none", mode=mode, submode=submode,
                         noninteractive=True)
    if strategy in {"embedding", "hybrid"}:
        if interactive and provider is None:
            provider = _prompt("select", "Embedding provider",
                               choices=["none", "openai", "fake"],
                               default=cur_emb.get("provider", "none")) or "none"
            if provider not in ("none", ""):
                model = model or (_prompt("text", "Embedding model",
                                          default=cur_emb.get("model", "text-embedding-3-small"))
                                  or cur_emb.get("model", "text-embedding-3-small"))
                _dim_str = _prompt("text", "Embedding dim",
                                   default=str(cur_emb.get("dim", 1536))) or str(cur_emb.get("dim", 1536))
                dim = int(_dim_str)
        configure_recall(
            strategy=strategy,
            provider=provider or cur_emb.get("provider", "none"),
            model=model or cur_emb.get("model", "text-embedding-3-small"),
            dim=int(dim) if dim else cur_emb.get("dim", 1536),
            mode=mode,
            submode=submode,
            noninteractive=True,
        )
    if strategy not in recall._IMPLEMENTED_STRATEGIES:  # only an unrecognized strategy
        print(f"  note: strategy '{strategy}'는 인식되지 않음 — 런타임에 'fts'로 폴백합니다.")
    warn = recall.cost_warning(mode, strategy)
    if warn:
        print(f"  {warn}")
    from scripts import hosts as hostsmod
    if interactive and hosts is None:
        # Convention-level picker: codex+opencode share AGENTS.md → one entry.
        choices_meta = hostsmod.instruction_choices()
        choice_labels = [f"{', '.join(c['members'])} ({c['file']})" for c in choices_meta]
        picked_labels = _prompt("checkbox", "Inject recall guidance into hosts",
                                choices=choice_labels) or []
        picked_hosts: list[str] = []
        for label, meta in zip(choice_labels, choices_meta):
            if label in picked_labels:
                picked_hosts.extend(meta["members"])
        hosts = picked_hosts or None
        # Scoped host sub-prompts.
        if hosts:
            for host in hosts:
                if not hostsmod.is_scoped(host):
                    continue
                if host == "hermes" and profile is None:
                    profiles = hostsmod.list_profiles()
                    if profiles:
                        profile = _prompt("select", "Hermes profile",
                                          choices=profiles,
                                          default=hostsmod.active_profile()) or profiles[0]
                    else:
                        profile = hostsmod.active_profile()
                elif host == "openclaw" and workspace is None:
                    workspaces = hostsmod.list_workspaces()
                    if workspaces:
                        workspace = _prompt("select", "OpenClaw workspace",
                                            choices=workspaces,
                                            default=hostsmod.default_workspace()) or workspaces[0]
                    else:
                        workspace = hostsmod.default_workspace()
    if hosts is None:
        # Non-interactive default: repo-trio hosts only.
        hosts = [h for h, d in hostsmod.HOSTS.items() if d["kind"] == "repo"]
    base = Path(base_dir) if base_dir else Path.cwd()
    block = recall.render_recall_block(mode)
    written: list[Path] = []
    seen: set = set()
    for host in hosts:
        try:
            path = hostsmod.resolve_instruction_path(host, base,
                                                     profile=profile, workspace=workspace)
        except ValueError as exc:
            print(f"  - {host}: skipped ({exc})")
            continue
        if path not in seen:
            seen.add(path)
            recall.upsert_block(path, block)     # Tier 1: guidance in instruction file
            recall.upsert_block(path, recall.render_always_on_block(),
                                marker=recall.ALWAYS_ON_MARKER)  # wiki-first (soft enforcement)
            written.append(path)
    from scripts import commandmap
    commandmap.export(base, hosts, profile=profile, workspace=workspace)
    print(f"✓ recall mode '{mode}'; guidance injected into "
          f"{', '.join(p.name for p in written) or '(none)'}.")
    # Tier 2: wire the host's native SessionStart + UserPromptSubmit hooks (global config).
    hook_capable = recall.host_hook_configs()
    for host in hosts:
        if host in hook_capable:
            changed, detail = recall.wire_host(host)
            print(f"  {'✓' if changed else '–'} {host} hooks: {detail}")
        else:
            print(f"  – {host}: block-only (no native hook)")
    return 0


def setup_gate(mode="enforce", hosts=None, noninteractive=False) -> int:
    """Configure gate.mode and wire/unwire the Stop hook on each host."""
    import json
    from scripts import config, gate, recall
    if mode not in ("off", "advisory", "enforce"):
        print(f"error: invalid mode {mode!r}", flush=True)
        return 1
    config.set_config("gate.mode", mode)
    hosts = hosts or list(recall.host_hook_configs().keys())
    results = {}
    for h in hosts:
        if mode == "off":
            changed, detail = gate.unwire_host(h)
        else:
            changed, detail = gate.wire_host(h)
        results[h] = detail
    print(json.dumps({"gate.mode": mode, "hosts": results}, ensure_ascii=False))
    return 0


def configure_recall(*, strategy="fts", provider="none", model="text-embedding-3-small",
                     dim=1536, mode=None, submode: str | None = None,
                     noninteractive=False) -> None:
    """Persist recall strategy + embedding provider. Prints the scale guard note."""
    from scripts import config, recall
    if mode:
        config.set_config("recall.mode", mode)
    config.set_config("recall.strategy", strategy)
    config.set_config("recall.embedding.provider", provider)
    if provider not in ("none", ""):
        config.set_config("recall.embedding.model", model)
        config.set_config("recall.embedding.dim", int(dim))
        print("참고: 위키가 1차 연료입니다. embedding/hybrid는 페이지가 수천+로 커져 "
              "FTS 정밀도가 떨어질 때 켜는 롱테일 검색 축입니다 (opt-in).")
    if strategy == "llm" and submode:
        config.set_config("recall.llm.submode", submode)
    warn = recall.cost_warning(mode or "auto", strategy)
    if warn:
        print(warn)


def run_all(*, noninteractive: bool = False, base_dir=None) -> int:
    """Top-level interactive wizard: walk every section in order with per-step skip.

    Returns the first non-zero section result (continuing through the rest), else 0.
    """
    from scripts import banner
    banner.render()   # animated when interactive TTY; static/suppressed otherwise
    first_error = 0
    steps = [
        ("vault", lambda: run(noninteractive=noninteractive, in_wizard=True)),
        ("search", lambda: setup_search(noninteractive=noninteractive)),
        ("serve", lambda: setup_serve(noninteractive=noninteractive)),
        ("personas", lambda: setup_personas(noninteractive=noninteractive, base_dir=base_dir)),
        ("import", lambda: setup_import(noninteractive=noninteractive)),
        ("viewer", lambda: setup_viewer(noninteractive=noninteractive)),
        ("agents", lambda: setup_agents(noninteractive=noninteractive)),
        ("recall", lambda: setup_recall(noninteractive=noninteractive, base_dir=base_dir)),
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


def playwright_installed() -> bool:
    try:
        from scripts import fetch_chromium
        return fetch_chromium.available()
    except Exception:
        return False


def install_playwright(*, assume_yes: bool = False, interactive: bool = True) -> tuple[bool, str]:
    from scripts import platform_env
    if playwright_installed():
        return True, "Playwright(chromium)가 이미 설치돼 있습니다."
    argv = platform_env.pip_install_argv("playwright")
    browser = [sys.executable, "-m", "playwright", "install", "--with-deps", "chromium"]
    manual = " ".join(argv) + " && " + " ".join(browser)
    if not assume_yes:
        if not interactive:
            return False, f"설치를 건너뜁니다. 직접: {manual}"
        try:
            ans = input("Playwright(chromium)가 없습니다. 지금 설치할까요? [y/N] ")
        except EOFError:
            return False, f"설치를 건너뜁니다. 직접: {manual}"
        if not ans.strip().lower().startswith("y"):
            return False, f"설치를 건너뜁니다. 직접: {manual}"
    try:
        subprocess.run(argv, check=True)
        subprocess.run(browser, check=True)
    except Exception as e:
        return False, f"설치 실패 ({e}). 직접: {manual}"
    return True, "Playwright + chromium 설치 완료."


def setup_playwright(*, noninteractive: bool = False) -> int:
    """Set up Playwright (chromium). Best-effort: returns 0 even if not installed."""
    import os
    interactive = (not noninteractive) and sys.stdin.isatty()
    _ok, msg = install_playwright(
        assume_yes=os.environ.get("OMW_BOOTSTRAP_YES") == "1",
        interactive=interactive)
    print(f"playwright: {msg}")
    return 0


def doctor_checks() -> dict:
    """Structured install/config health. No printing — the SSOT consumed by both
    doctor() (renderer) and report.build() (install-health summary)."""
    import shutil
    from pathlib import Path as _P
    import scripts.fetch_chromium as _fc
    from scripts import platform_env as _pe

    home = omw_home()
    db = registry_path()
    items: list[dict] = []
    items.append({"name": "omw home", "ok": home.exists(), "detail": str(home),
                  "hint": "" if home.exists() else "run: omw setup"})
    items.append({"name": "registry", "ok": db.exists(), "detail": str(db),
                  "hint": "" if db.exists() else "missing"})

    vaults = registry.list_vaults(db) if db.exists() else []
    sandbox_warning = ""
    if vaults:
        cwd = _P.cwd()
        proj = [v for v in vaults if str(v["path"]).startswith(str(cwd))]
        if proj and not str(db).startswith(str(cwd)):
            sandbox_warning = (
                f"registry lives at {db} (outside this folder); agents with a "
                "workspace-write sandbox may hit 'readonly database' on reindex — "
                "approve the write, or set OMW_HOME to a path inside the workspace")

    ytdlp_ok = bool(shutil.which("yt-dlp"))
    items.append({"name": "yt-dlp", "ok": ytdlp_ok, "detail": "",
                  "hint": "" if ytdlp_ok else " ".join(_pe.pip_install_argv("yt-dlp")) + " — for YouTube"})
    chromium_ok = _fc.available()
    items.append({"name": "chromium", "ok": chromium_ok, "detail": "",
                  "hint": "" if chromium_ok else "run: omw setup playwright — for SPA pages"})
    try:
        import questionary  # noqa: F401
        wizard_ok = True
    except Exception:
        wizard_ok = False
    items.append({"name": "wizard UI", "ok": wizard_ok, "detail": "",
                  "hint": "" if wizard_ok else " ".join(_pe.pip_install_argv("oh-my-wiki[wizard]")) + " — arrow-key setup UI; falls back to plain text"})

    ok = all(i["ok"] for i in items if i["name"] in ("omw home", "registry"))
    return {"ok": ok, "items": items, "vaults": [dict(v) for v in vaults],
            "sandbox_warning": sandbox_warning, "home": str(home), "registry": str(db)}


def doctor() -> int:
    d = doctor_checks()
    home_ok = d["items"][0]["ok"]
    reg_ok = d["items"][1]["ok"]
    print(f"omw home:   {d['home']}  {'ok' if home_ok else 'missing (run: omw setup)'}")
    print(f"registry:   {d['registry']}  {'ok' if reg_ok else 'missing'}")
    if d["vaults"]:
        for v in d["vaults"]:
            mark = "*" if v["is_active"] else " "
            print(f"  {mark} {v['name']} ({v['mode']}/{v['type']}) {v['path']}")
        if d["sandbox_warning"]:
            print(f"  ! {d['sandbox_warning']}")
    else:
        print("  no vaults registered — run: omw setup")

    yt = "ok" if next(i for i in d["items"] if i["name"] == "yt-dlp")["ok"] \
        else f"missing ({next(i for i in d['items'] if i['name'] == 'yt-dlp')['hint']})"
    chromium = "ok" if next(i for i in d["items"] if i["name"] == "chromium")["ok"] \
        else f"missing ({next(i for i in d['items'] if i['name'] == 'chromium')['hint']})"
    wiz = "ok" if next(i for i in d["items"] if i["name"] == "wizard UI")["ok"] \
        else f"missing ({next(i for i in d['items'] if i['name'] == 'wizard UI')['hint']})"
    print(f"fetch yt-dlp:  {yt}")
    print(f"fetch chromium: {chromium}")
    print(f"wizard UI:     {wiz}")
    return 0
