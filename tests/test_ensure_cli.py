# tests/test_ensure_cli.py
import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "bin" / "ensure-cli.sh"


def _run(env_extra, path_dir):
    # Run script with minimal PATH (test PATH only). Bash location must be in original PATH.
    import shutil
    bash_path = shutil.which("bash") or "/bin/bash"
    env = dict(os.environ, PATH=str(path_dir), **env_extra)
    return subprocess.run([bash_path, str(SCRIPT)], capture_output=True, text=True, env=env)


def test_prints_omw_bin_when_already_on_path(tmp_path):
    # Fake an `omw` on PATH; the script must detect it and NOT install.
    fake = tmp_path / "omw"
    fake.write_text("#!/usr/bin/env bash\necho fake omw\n")
    fake.chmod(0o755)
    r = _run({"OMW_BOOTSTRAP_YES": "0"}, tmp_path)
    assert r.returncode == 0
    assert f"OMW_BIN={fake}" in r.stdout


def test_no_silent_install_when_absent_and_unconfirmed(tmp_path):
    # Empty PATH (no omw, no pipx/pip resolvable) + non-interactive + no YES.
    r = _run({"OMW_BOOTSTRAP_YES": "0"}, tmp_path)
    assert r.returncode == 3
    assert "pipx install oh-my-wiki" in (r.stdout + r.stderr)  # manual one-liner shown
    assert "OMW_BIN=" not in r.stdout                          # nothing installed/resolved
