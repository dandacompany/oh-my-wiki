"""Run one generated hook command with a hard child-process deadline.

Host-level hook timeouts are not enough when a shell command substitution leaves
its child alive. This small wrapper owns the child process group and terminates it
before the host's own timeout, so recall always fails open.
"""
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys


def run(argv: list[str], *, timeout: float) -> int:
    kwargs = {"start_new_session": True} if os.name == "posix" else {}
    proc = subprocess.Popen(argv, **kwargs)
    try:
        return proc.wait(timeout=max(0.05, timeout))
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        else:
            proc.terminate()
        try:
            proc.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            if os.name == "posix":
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            else:
                proc.kill()
            proc.wait()
        print(f"omw hook watchdog: stopped after {timeout:g}s", file=sys.stderr)
        return 124


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--timeout", type=float, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        return 2
    return run(command, timeout=args.timeout)


if __name__ == "__main__":
    raise SystemExit(main())
