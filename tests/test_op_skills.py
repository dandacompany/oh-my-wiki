"""omw-<op> op family + omw-<role> persona family: generated from the registries.

- op family  = non-persona procedures (ingest/query/open/edit/move/delete/autoresearch)
- role family = every persona in the roster (omw-<role>, e.g. omw-fact-checker)
Persona procedures do NOT get an omw-<op> skill — the omw-<role> family covers them.
"""
import re

import scripts.agent_skills as ask
from scripts import ops_registry as reg
from scripts import personas


def _frontmatter(text: str) -> dict:
    m = re.search(r"^---\n(.*?)\n---", text, re.S)
    assert m, "no frontmatter"
    fm = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip()
    return fm


def _non_persona_procs():
    return [p for p in reg.procedures() if not p.startswith("persona-")]


# ── op family ────────────────────────────────────────────────────────────────

def test_op_skill_names_track_non_persona_procedures():
    assert set(ask.op_skill_names()) == {f"omw-{p}" for p in _non_persona_procs()}
    # persona procedures are excluded — covered by the role family instead
    assert not any(n.startswith("omw-persona-") for n in ask.op_skill_names())


def test_op_skill_md_wellformed():
    for name in _non_persona_procs():
        op = reg.get(name)
        fm = _frontmatter(ask._op_skill_md(op))
        assert fm["name"] == f"omw-{name}"
        desc = fm["description"]
        assert desc and "\n" not in desc
        assert ": " not in desc and not desc.startswith("[")
        assert "<" not in desc and ">" not in desc
        assert "argument-hint" in fm
        assert op.procedure_file in ask._op_skill_md(op)
        assert "oh-my-wiki" in ask._op_skill_md(op)


def test_arg_hint_marks_required_vs_optional():
    assert ask._arg_hint(reg.get("move")) == "<src> <dst>"
    h = ask._arg_hint(reg.get("autoresearch"))
    assert h.startswith("<topic>") and "[--rounds]" in h and "[--no-synthesis]" in h


def test_install_op_skills_excludes_persona(tmp_path):
    dests = ask.install_op_skills_into_dir(tmp_path)
    assert len(dests) == len(_non_persona_procs())
    assert (tmp_path / "omw-ingest" / "SKILL.md").is_file()
    assert not (tmp_path / "omw-persona-factcheck").exists()


# ── role (persona) family ────────────────────────────────────────────────────

def test_role_skill_names_track_roster():
    assert set(ask.role_skill_names()) == {
        f"omw-{ask._role_slash(p['name'])}" for p in personas.list_personas()}


def test_role_slash_drops_wiki_prefix():
    # slash name shortens wiki-*; other roles unchanged
    assert ask._role_slash("wiki-librarian") == "librarian"
    assert ask._role_slash("wiki-auditor") == "auditor"
    assert ask._role_slash("curator") == "curator"
    assert ask._role_slash("fact-checker") == "fact-checker"


def test_role_skill_md_wellformed():
    for p in personas.list_personas():
        role = p["name"]
        slash = ask._role_slash(role)
        md = ask._role_skill_md(p)
        fm = _frontmatter(md)
        assert fm["name"] == f"omw-{slash}"          # skill/dir uses the short slash
        desc = fm["description"]
        assert desc and "\n" not in desc
        assert ": " not in desc and not desc.startswith("[")
        assert "<" not in desc and ">" not in desc
        assert "argument-hint" in fm
        assert f"omw persona-run {role}" in md        # dispatch keeps the FULL role name
        assert "oh-my-wiki" in md


def test_install_role_skills_writes_family(tmp_path):
    dests = ask.install_role_skills_into_dir(tmp_path)
    assert len(dests) == len(personas.list_personas())
    assert (tmp_path / "omw-fact-checker" / "SKILL.md").is_file()
    assert (tmp_path / "omw-librarian" / "SKILL.md").is_file()      # shortened
    assert (tmp_path / "omw-auditor" / "SKILL.md").is_file()
    assert not (tmp_path / "omw-wiki-librarian").exists()           # long form not written


# ── install / legacy cleanup ─────────────────────────────────────────────────

def test_install_into_dir_includes_both_families_and_cleans_legacy(tmp_path):
    # leftover skills from earlier versions must be removed on install
    for stale in ("omw-persona-factcheck", "omw-wiki-librarian"):
        d = tmp_path / stale
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text("stale")

    res = ask.install_into_dir(tmp_path)
    assert res["ok"] is True
    assert res.get("op_skills") == len(_non_persona_procs())
    assert res.get("role_skills") == len(personas.list_personas())
    # canonical + alias + op + role coexist; legacy gone
    assert (tmp_path / "oh-my-wiki" / "SKILL.md").is_file()
    assert (tmp_path / "omw" / "SKILL.md").is_file()
    assert (tmp_path / "omw-ingest" / "SKILL.md").is_file()
    assert (tmp_path / "omw-curator" / "SKILL.md").is_file()
    assert (tmp_path / "omw-librarian" / "SKILL.md").is_file()
    assert not (tmp_path / "omw-persona-factcheck").exists()
    assert not (tmp_path / "omw-wiki-librarian").exists()  # 2.41.0 long form cleaned


def test_role_skill_replaces_dangling_symlink(tmp_path):
    (tmp_path / "omw-curator").symlink_to(tmp_path / "gone")  # dangling
    ask.install_role_skills_into_dir(tmp_path)
    dest = tmp_path / "omw-curator"
    assert not dest.is_symlink() and (dest / "SKILL.md").is_file()
