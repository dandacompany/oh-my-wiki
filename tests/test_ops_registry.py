import re
from pathlib import Path

from scripts import omw_cli
from scripts import ops_registry as reg


# commands/*.md that intentionally have no registered op of the same name.
# Anything NOT listed here must map to a procedure — see test_no_orphan_command_files.
_NON_OP_COMMAND_DOCS = {
    # shared includes / host-runner guidance, not op cards
    "menu.md", "migrate.md", "recall-llm.md", "runner-hermes-delegate.md",
    # persona cards — dispatched by role via `omw persona-run`, not by op name
    "persona-audit.md", "persona-curate-index.md", "persona-librarian.md",
    # legacy vault docs: these names are already pinned as stale op names in
    # tests/test_skill_no_stale_triggers.py (folded into `omw vault …` / `omw import`).
    "vault-forget.md", "vault-import-memo.md", "vault-list.md",
    "vault-setup.md", "vault-use.md",
}


def test_every_op_is_wellformed():
    for op in reg.OPS:
        assert op.kind in ("deterministic", "procedure"), op.name
        if op.kind == "procedure":
            assert op.procedure_file, f"{op.name} procedure missing procedure_file"
            assert op.cli_template is None, f"{op.name} procedure must not set cli_template"
        else:
            assert op.procedure_file is None, f"{op.name} deterministic must not set procedure_file"
        for a in op.args:
            assert a.name and a.hint, op.name


def test_find_is_deterministic_not_procedure():
    assert reg.get("find").kind == "deterministic"
    assert "find" not in reg.procedures()


def test_team_run_is_not_registered():
    assert reg.get("team-run") is None
    assert "team-run" not in reg.names()


def test_procedures_match_expected_agentic_set():
    assert set(reg.procedures()) == {
        "ingest", "query", "open", "edit", "move", "delete", "autoresearch",
        "persona-factcheck", "persona-consistency", "persona-terminology",
        "summary", "synthesis", "distill",
    }


def test_distill_is_a_procedure_so_it_gets_an_op_skill():
    """`distill` must be a procedure, not a deterministic op.

    Only procedures get an ``omw-<op>`` agent skill (agent_skills._op_skill_procedures),
    so registering the new-page path as deterministic would leave the natural-language
    surface empty — the exact gap that made an agent bypass the procedures.
    """
    op = reg.get("distill")
    assert op is not None, "distill must be registered"
    assert op.kind == "procedure"
    assert op.procedure_file == "commands/distill.md"
    assert (_ROOT / op.procedure_file).is_file()


def test_no_orphan_command_files():
    """Every commands/*.md must belong to a registered op.

    The reverse of test_no_dangling_op_references: that one catches a doc naming a
    verb with no op; this one catches a command file with no op to invoke it. A
    deterministic op may also carry a card (fetch/lint/next/…), so this checks all
    registered names, not just procedures. Files listed in _NON_OP_COMMAND_DOCS are
    deliberate non-op docs.
    """
    known = set(reg.names())
    orphans = sorted(
        p.name for p in (_ROOT / "commands").glob("*.md")
        if p.stem not in known and p.name not in _NON_OP_COMMAND_DOCS
    )
    assert not orphans, f"command files with no registered op: {orphans}"


def test_autoresearch_args():
    a = {x.name: x for x in reg.get("autoresearch").args}
    assert a["topic"].required is True
    assert "--rounds" in a
    assert reg.get("autoresearch").uses == ("search", "fetch", "reindex")


_ROOT = Path(__file__).resolve().parent.parent


def test_cli_agentic_ops_match_registry_procedures():
    assert set(omw_cli.AGENTIC_OPS) == set(reg.procedures())


def test_recall_hook_verbs_are_registered_deterministic():
    text = (_ROOT / "scripts" / "recall.py").read_text(encoding="utf-8")
    for verb in re.findall(r"omw ([a-z][a-z-]+) \"", text):
        spec = reg.get(verb)
        assert spec is not None, f"recall hint references unknown op: {verb}"
        assert spec.kind == "deterministic", f"recall hint points at a procedure: {verb}"


def test_persona_run_registered_deterministic():
    assert reg.get("persona-run") is not None
    assert reg.get("persona-run").kind == "deterministic"


def test_no_dangling_op_references():
    known = set(reg.names())
    # Backtick-anchored scan: every genuine op reference in docs is written as `omw verb …`,
    # never in raw prose. This excludes prose ("omw deliberately"), module docstrings,
    # headings, and placeholders (e.g. `omw <op> --help`).
    allow = set()  # Backtick-anchored regex needs no prose allowlist
    sources = [
        _ROOT / "SKILL.md",
        _ROOT / "scripts" / "gate.py",
        *(_ROOT / "commands").glob("*.md"),
    ]
    bad = []
    for path in sources:
        text = path.read_text(encoding="utf-8")
        for verb in re.findall(r"`omw ([a-z][a-z-]+)", text):
            if verb not in known and verb not in allow:
                bad.append(f"{path.name}: omw {verb}")
    assert not bad, f"dangling op references: {sorted(set(bad))}"


def test_gate_prose_points_at_real_persona_run():
    text = (_ROOT / "scripts" / "gate.py").read_text(encoding="utf-8")
    if "persona-run" in text:
        assert reg.get("persona-run") is not None  # referenced op must exist
    # and the Workstream-D placeholder must be gone from gate prose
    assert "Workstream D" not in text


def test_search_op_has_no_fallback_flag():
    names = [a.name for a in reg.get("search").args]
    assert "--no-fallback" in names


def test_next_registered_deterministic():
    assert reg.get("next") is not None
    assert reg.get("next").kind == "deterministic"


def test_fetch_command_doc_exists_and_clean():
    from pathlib import Path
    p = Path(__file__).resolve().parent.parent / "commands" / "fetch.md"
    assert p.exists(), "commands/fetch.md should document native-fetch-first"
    text = p.read_text(encoding="utf-8")
    # every backtick `omw <verb>` in it must be a registered op
    import re
    for verb in re.findall(r"`omw ([a-z][a-z-]+)", text):
        assert reg.get(verb) is not None, f"fetch.md references unknown op: {verb}"


def test_next_command_doc_exists_and_clean():
    from pathlib import Path
    import re
    p = Path(__file__).resolve().parent.parent / "commands" / "next.md"
    assert p.exists(), "commands/next.md should document the after-each-task proposal"
    for verb in re.findall(r"`omw ([a-z][a-z-]+)", p.read_text(encoding="utf-8")):
        assert reg.get(verb) is not None, f"next.md references unknown op: {verb}"


def test_ingest_doc_has_link_suggest_step():
    from pathlib import Path
    p = Path(__file__).resolve().parent.parent / "commands" / "ingest.md"
    assert "omw links suggest" in p.read_text(encoding="utf-8")


def test_ingest_doc_mentions_source_raw():
    from pathlib import Path
    assert "source_raw" in (Path(__file__).resolve().parent.parent / "commands" / "ingest.md").read_text(encoding="utf-8")


def test_update_registered_deterministic():
    assert reg.get("update") is not None and reg.get("update").kind == "deterministic"


def test_merge_registered_deterministic():
    assert reg.get("merge") is not None and reg.get("merge").kind == "deterministic"


def test_context_registered_deterministic():
    assert reg.get("context") is not None and reg.get("context").kind == "deterministic"


def test_list_registered_deterministic():
    assert reg.get("list") is not None and reg.get("list").kind == "deterministic"


def test_export_registered_deterministic():
    assert reg.get("export") is not None and reg.get("export").kind == "deterministic"


def test_persona_fanout_registered_deterministic():
    op = reg.get("persona-fanout")
    assert op is not None
    assert op.kind == "deterministic"
    assert op.triggers  # routable: must have triggers (test_triggers guard)


def test_persona_bundle_registered_deterministic():
    op = reg.get("persona-bundle")
    assert op is not None
    assert op.kind == "deterministic"
    assert op.triggers  # routable: must have triggers (test_triggers guard)


def test_skill_md_procedure_list_matches_registry():
    """SKILL.md's hand-written Procedures sentence must list every registered procedure.

    The surrounding prose tells readers not to hand-maintain an op table because it
    drifts — and it did: `summary`/`synthesis` were registered but never added here.
    """
    text = (_ROOT / "SKILL.md").read_text(encoding="utf-8")
    m = re.search(r"Procedures:\s*(.+?)\.\n", text, re.S)
    assert m, "SKILL.md must keep a `Procedures:` sentence in the command-map section"
    listed = set(re.findall(r"`([a-z][a-z-]+)`", m.group(1)))
    assert listed == set(reg.procedures()), (
        f"SKILL.md Procedures drift — missing {sorted(set(reg.procedures()) - listed)}, "
        f"extra {sorted(listed - set(reg.procedures()))}"
    )
