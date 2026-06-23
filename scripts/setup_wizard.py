"""omw setup wizard + doctor.

Non-interactive (flag-driven) is the tested contract. Interactive prompting uses
questionary if available (the `wizard` extra); otherwise it degrades to input().
The first slice writes config.yaml; secrets (search/persona/TTS) come in later slices.
"""
from __future__ import annotations

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
    vault_path = resolve_vault_root(name, location)
    if in_wizard:
        # The top-level wizard continues into search/serve/... right after this,
        # so don't tell the user to "configure later" — just confirm the vault.
        print(f"✓ vault '{name}' ({mode}/{type_}) at {vault_path}")
    else:
        print(
            f"setup complete — vault '{name}' ({mode}/{type_}) at {vault_path}. "
            f"Configure search/persona/recall sections anytime with 'omw setup search' / "
            f"'omw setup personas' / 'omw setup recall'."
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
        default_main = ("wiki-librarian" if "wiki-librarian" in (enabled or all_names)
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
        main = "wiki-librarian" if "wiki-librarian" in enabled \
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
    results = agent_skills.install_many(targets)
    for r in results:
        mark = "✓" if r.get("ok") else "✗"
        detail = f" ({r['detail']})" if r.get("detail") else ""
        print(f"  {mark} {r['agent']} [{r.get('method') or '—'}]{detail}")
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
                 dim: int | None = None) -> int:
    """Configure auto wiki-recall (two axes):
      mode     — trigger: off | advisory | auto
      strategy — retrieval: fts | embedding | hybrid | llm (+ llm.submode)
    Sets config and injects the host-agnostic Tier-1 guidance block into each
    host's instruction file. Host-neutral by design — not Claude-only.
    All strategies (fts/embedding/hybrid/llm) are implemented; `llm` is agent-delegated
    guidance (advisory-natured — no hook-side LLM call)."""
    from pathlib import Path
    from scripts import config, persona_export, recall
    choices = ["auto", "advisory", "off"]
    interactive = (not noninteractive) and sys.stdin.isatty()
    if interactive and mode is None:
        mode = _prompt("select", "Wiki recall mode (trigger)", choices=choices, default="auto") or "auto"
    mode = mode or "auto"
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
                           default="fts") or "fts"
    strategy = strategy or "fts"
    if strategy not in recall.STRATEGIES:
        print(f"error: unknown strategy {strategy!r}; choose from {list(recall.STRATEGIES)}", file=sys.stderr)
        return 1
    config.set_config("recall.strategy", strategy)
    if strategy == "llm":
        if interactive and submode is None:
            submode = _prompt("select", "LLM submode", choices=list(recall.LLM_SUBMODES),
                              default="route") or "route"
        submode = submode or "route"
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
                               choices=["none", "openai", "fake"], default="none") or "none"
            if provider not in ("none", ""):
                model = model or (_prompt("text", "Embedding model",
                                          default="text-embedding-3-small") or "text-embedding-3-small")
                _dim_str = _prompt("text", "Embedding dim", default="1536") or "1536"
                dim = int(_dim_str)
        configure_recall(
            strategy=strategy,
            provider=provider or "none",
            model=model or "text-embedding-3-small",
            dim=int(dim) if dim else 1536,
            mode=mode,
            submode=submode,
            noninteractive=True,
        )
    if strategy not in recall._IMPLEMENTED_STRATEGIES:  # only an unrecognized strategy
        print(f"  note: strategy '{strategy}'는 인식되지 않음 — 런타임에 'fts'로 폴백합니다.")
    warn = recall.cost_warning(mode, strategy)
    if warn:
        print(f"  {warn}")
    if interactive and hosts is None:
        hosts = _prompt("checkbox", "Inject recall guidance into hosts",
                        choices=list(persona_export.HOST_FILES)) or None
    if hosts is None:
        hosts = list(persona_export.HOST_FILES)
    base = Path(base_dir) if base_dir else Path.cwd()
    block = recall.render_recall_block(mode)
    written = []
    for host in hosts:
        if host not in persona_export.HOST_FILES:
            print(f"  - {host}: unknown host, skipped")
            continue
        path = base / persona_export.HOST_FILES[host]
        recall.upsert_block(path, block)     # Tier 1: guidance in instruction file
        recall.upsert_block(path, recall.render_always_on_block(),
                            marker=recall.ALWAYS_ON_MARKER)  # wiki-first (soft enforcement)
        written.append(path)
    print(f"✓ recall mode '{mode}'; guidance injected into "
          f"{', '.join(p.name for p in written) or '(none)'}.")
    # Tier 2: wire the host's native SessionStart + UserPromptSubmit hooks (global config).
    for host in hosts:
        if host not in recall.host_hook_configs():
            continue
        changed, detail = recall.wire_host(host)
        print(f"  {'✓' if changed else '–'} {host} hooks: {detail}")
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
    ok, msg = install_playwright(
        assume_yes=os.environ.get("OMW_BOOTSTRAP_YES") == "1",
        interactive=interactive)
    print(f"playwright: {msg}")
    return 0


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
        # Sandbox advisory: project-local vaults index into the GLOBAL registry
        # (~/.omw), which lives outside an agent's workspace-write sandbox — so
        # reindex can fail with "readonly database" without an approval/escalation.
        from pathlib import Path as _P
        cwd = _P.cwd()
        proj = [v for v in vaults if str(v["path"]).startswith(str(cwd))]
        if proj and not str(db).startswith(str(cwd)):
            print(f"  ! registry lives at {db} (outside this folder). Agents with a "
                  f"workspace-write sandbox may hit 'readonly database' on reindex —\n"
                  f"    approve the write, or set OMW_HOME to a path inside the workspace.")
    else:
        print("  no vaults registered — run: omw setup")
    import scripts.fetch_chromium as _fc
    ytdlp = "ok" if shutil.which("yt-dlp") else "missing (pip install yt-dlp — for YouTube)"
    chromium = "ok" if _fc.available() else "missing (pip install playwright && playwright install chromium — for SPA pages)"
    print(f"fetch yt-dlp:  {ytdlp}")
    print(f"fetch chromium: {chromium}")
    try:
        import questionary  # noqa: F401
        wizard_ui = "ok"
    except Exception:
        wizard_ui = "missing (pip install 'oh-my-wiki[wizard]' — arrow-key setup UI; falls back to plain text)"
    print(f"wizard UI:     {wizard_ui}")
    return 0
