"""#917+#918: verify_chain_isolation.sh must not die silently on a missing
key and must not treat sqlite3 failures as clean.

On base, a blockchain.env without supported_chains aborted the run under
set -e/pipefail (the documented warn-and-skip never printed), and a
failed sqlite3 query reported "no cross-chain rows" instead of an error.
"""

import os
import sqlite3
import subprocess
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "monitoring" / "verify_chain_isolation.sh"


def _run(tmp_path, env_text, db_fn=None):
    tmp_path = Path(tmp_path)
    env_file = tmp_path / "blockchain.env"
    env_file.write_text(env_text)
    chain_dir = tmp_path / "data" / "ait-x"
    chain_dir.mkdir(parents=True)
    if db_fn:
        db_fn(chain_dir / "chain.db")
    env = dict(
        os.environ,
        AITBC_DATA_DIR=str(tmp_path / "data"),
        AITBC_CHAIN_ISO_LOG=str(tmp_path / "log.txt"),
        AITBC_BLOCKCHAIN_ENV=str(env_file),
    )
    r = subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True, timeout=60)
    log = (tmp_path / "log.txt").read_text() if (tmp_path / "log.txt").exists() else ""
    return r, log


def _clean_db(p):
    con = sqlite3.connect(p)
    con.executescript(
        "CREATE TABLE block(height INT, chain_id TEXT);"
        "CREATE TABLE account(a TEXT, chain_id TEXT);"
        'CREATE TABLE "transaction"(h TEXT, chain_id TEXT);'
    )
    con.commit()
    con.close()


def test_missing_supported_chains_warns_and_continues(tmp_path):
    """#917: a file with only CHAIN_ID must warn and still run the db check."""
    r, log = _run(tmp_path, "CHAIN_ID=ait-x\n", _clean_db)
    assert "declares no supported_chains" in log
    assert "Checking database:" in log
    assert "Chain Isolation Verification Completed" in log


def test_sqlite_failure_counts_as_error_not_clean(tmp_path):
    """#918: a db missing the queried tables errors out instead of
    reporting 'no cross-chain rows'."""

    def broken_db(p):
        con = sqlite3.connect(p)
        con.execute("CREATE TABLE unrelated(x INT)")
        con.commit()
        con.close()

    r, log = _run(tmp_path, "CHAIN_ID=ait-x\nsupported_chains=ait-x\n", broken_db)
    assert "sqlite3 query failed" in log
    assert "No cross-chain blocks" not in log
    assert "VIOLATIONS DETECTED" in log
    assert r.returncode == 1
