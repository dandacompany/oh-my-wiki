"""omw-<op> procedure slash-command family: generated 1:1 from ops_registry."""
import re

import scripts.agent_skills as ask
from scripts import ops_registry as reg


def _frontmatter(text: str) -> dict:
    m = re.search(r"^---\n(.*?)\n---", text, re.S)
    assert m, "no frontmatter"
    fm = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip()
    return fm


def test_op_skill_names_track_procedures():
    # The family is exactly one skill per procedure op — auto-follows the registry.
    assert set(ask.op_skill_names()) == {f"omw-{p}" for p in reg.procedures()}
    assert len(ask.op_skill_names()) == len(reg.procedures())


def test_op_skill_md_wellformed_for_every_procedure():
    for name in reg.procedures():
        op = reg.get(name)
        md = ask._op_skill_md(op)
        fm = _frontmatter(md)
        # name matches the dir the family installs into
        assert fm["name"] == f"omw-{name}"
        # description: non-empty, single line, YAML-safe (no ": ", no leading "[")
        desc = fm["description"]
        assert desc and "\n" not in desc
        assert ": " not in desc, f"colon-space breaks YAML plain scalar in {name}"
        assert not desc.startswith("["), f"leading [ parses as YAML list in {name}"
        assert "<" not in desc and ">" not in desc, f"angle bracket in description of {name}"
        assert "argument-hint" in fm
        # body forwards to the canonical command card (single source of truth)
        assert op.procedure_file in md
        assert "oh-my-wiki" in md  # loads the canonical skill's rules


def test_arg_hint_marks_required_vs_optional():
    # required → <name>, optional/flags → [name]
    hint = ask._arg_hint(reg.get("move"))       # src (req), dst (req)
    assert hint == "<src> <dst>"
    hint2 = ask._arg_hint(reg.get("autoresearch"))  # topic (req) + 2 optional flags
    assert hint2.startswith("<topic>")
    assert "[--rounds]" in hint2 and "[--no-synthesis]" in hint2


def test_install_op_skills_into_dir_writes_family(tmp_path):
    dests = ask.install_op_skills_into_dir(tmp_path)
    assert len(dests) == len(reg.procedures())
    for name in reg.procedures():
        skill = tmp_path / f"omw-{name}" / "SKILL.md"
        assert skill.is_file(), f"omw-{name} not written"
        assert f"omw-{name}" in skill.read_text()


def test_install_into_dir_includes_op_family(tmp_path):
    res = ask.install_into_dir(tmp_path)
    assert res["ok"] is True
    assert res.get("op_skills") == len(reg.procedures())
    # canonical + alias + family all coexist
    assert (tmp_path / "oh-my-wiki" / "SKILL.md").is_file()
    assert (tmp_path / "omw" / "SKILL.md").is_file()
    assert (tmp_path / "omw-ingest" / "SKILL.md").is_file()


def test_op_skill_replaces_dangling_symlink(tmp_path):
    (tmp_path / "omw-ingest").symlink_to(tmp_path / "gone")  # dangling
    ask.install_op_skills_into_dir(tmp_path)
    dest = tmp_path / "omw-ingest"
    assert not dest.is_symlink() and (dest / "SKILL.md").is_file()
