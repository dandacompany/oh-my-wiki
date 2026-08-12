import sqlite3
import subprocess
import sys
import time

import pytest

from scripts import registry


def test_waiting_writer_does_not_block_reads_and_reports_owner_pid(tmp_path):
    db = tmp_path / "registry.db"
    registry.init_db(db)
    code = """
import os, sys, time
from pathlib import Path
from scripts import registry
db = Path(sys.argv[1])
conn = registry.connect(db)
conn.execute('BEGIN IMMEDIATE')
conn.execute("INSERT INTO vaults(name,path,type,mode,is_active,created_at,last_used) VALUES ('held','/tmp/held','markdown','wiki',0,'now','now')")
print(os.getpid(), flush=True)
time.sleep(3)
conn.commit()
conn.close()
"""
    proc = subprocess.Popen(
        [sys.executable, "-c", code, str(db)],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    try:
        owner_pid = int(proc.stdout.readline().strip())
        started = time.monotonic()
        assert registry.list_vaults(db) == []
        assert time.monotonic() - started < 1

        blocked = registry.connect(db, busy_timeout_ms=25)
        try:
            with pytest.raises(sqlite3.OperationalError, match=fr"writer PID {owner_pid}"):
                blocked.execute(
                    "INSERT INTO vaults(name,path,type,mode,is_active,created_at,last_used) "
                    "VALUES ('blocked','/tmp/blocked','markdown','wiki',0,'now','now')"
                )
        finally:
            blocked.close()
    finally:
        proc.terminate()
        proc.wait(timeout=2)
