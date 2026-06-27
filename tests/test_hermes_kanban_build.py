from scripts import hermes_kanban as hk


def test_build_create_argv_shape():
    argv = hk.build_create_argv(
        "/usr/bin/hermes",
        title="fact-checker: p.md",
        body="BODY",
        assignee="sophie",
        skills=[hk.WORKER_SKILL],
        parents=("t-1", "t-2"),
        model="",
    )
    assert argv[:3] == ["/usr/bin/hermes", "kanban", "create"]
    assert "fact-checker: p.md" in argv
    assert argv[argv.index("--assignee") + 1] == "sophie"
    assert argv[argv.index("--body") + 1] == "BODY"
    assert argv[argv.index("--skill") + 1] == "omw-kanban-worker"
    # both parents present
    assert argv.count("--parent") == 2
    parent_vals = [argv[i + 1] for i, a in enumerate(argv) if a == "--parent"]
    assert parent_vals == ["t-1", "t-2"]
    # machine-parseable output requested; no initial-status (default handles gating)
    assert "--json" in argv
    assert "--initial-status" not in argv
    # empty model omitted
    assert "--model" not in argv


def test_build_create_argv_includes_model_when_set():
    argv = hk.build_create_argv(
        "hermes", title="t", body="b", assignee="a",
        skills=["omw-kanban-worker"], model="gpt-5.5",
    )
    assert argv[argv.index("--model") + 1] == "gpt-5.5"


def test_build_card_body_embeds_persona_and_input(monkeypatch):
    monkeypatch.setattr(
        "scripts.personas.load_persona",
        lambda role: {"name": role, "body": "PERSONA-SYSTEM-PROMPT"},
    )
    monkeypatch.setattr(
        "scripts.persona_run._gather_inputs",
        lambda role, *, db_path, vault_id, source=None: ("DETERMINISTIC-INPUT", {}),
    )
    body = hk.build_card_body("fact-checker", db_path="db", vault_id=1,
                              source={"vault_relpath": "p.md"})
    assert "PERSONA-SYSTEM-PROMPT" in body
    assert "DETERMINISTIC-INPUT" in body
    assert "fact-checker" in body  # role named in the header
