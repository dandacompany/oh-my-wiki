from pathlib import Path
def test_install_sh_has_break_system_packages_retry():
    text = Path(__file__).resolve().parents[1].joinpath("bin/install.sh").read_text()
    assert "--break-system-packages" in text, "install.sh must retry pip on PEP 668 envs"
