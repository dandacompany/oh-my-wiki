from pathlib import Path
REPO = Path(__file__).resolve().parents[1]

def test_no_plugin_marketplace_in_install_docs():
    for name in ["README.md", "TUTORIAL.md", "TUTORIAL.ko.md", "SKILL.md"]:
        t = (REPO / name).read_text(encoding="utf-8")
        assert "/plugin marketplace" not in t, f"{name} still has marketplace install"
        assert "oh-my-wiki-marketplace" not in t, f"{name} still references the marketplace"

def test_readme_orders_pypi_first():
    t = (REPO / "README.md").read_text(encoding="utf-8")
    assert t.index("pipx install oh-my-wiki") < t.index("git clone https://github.com/dandacompany/oh-my-wiki")
