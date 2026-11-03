"""DEPLOY-ENV-APPEND-NO-NEWLINE-1 — default appenders must not corrupt the last line.

The env-default appenders (consensus flags, gossip transport) did
``echo "K=v" >> "$BLOCKCHAIN_ENV_FILE"``. A file whose last line lacks a
trailing newline got the appended assignment glued onto it —
``PROPOSER_ID=0x..BLOCK_SCOPED_PREREGISTERED_TRANSACTIONS=true`` — corrupting
the existing key and not setting the new one. All appends now go through the
shared helper ``systemd-env.sh append``, which writes a newline first when
the file's last byte isn't one. Running the defaults twice still adds each
key once (the grep guards are unchanged).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
UPDATE_SH = REPO_ROOT / "scripts" / "deployment" / "update.sh"
HELPER = REPO_ROOT / "scripts" / "utils" / "systemd-env.sh"


def _run_defaults(tmp_path: Path, contents: bytes, twice: bool = False) -> str:
    env_file = tmp_path / "blockchain.env"
    env_file.write_bytes(contents)
    script = f"""
        source {UPDATE_SH}
        BLOCKCHAIN_ENV_FILE={env_file}
        NODE_ENV_FILE={tmp_path}/node.env
        ensure_consensus_env_defaults
        ensure_gossip_defaults
    """
    if twice:
        script += "ensure_consensus_env_defaults\nensure_gossip_defaults\n"
    env = {**os.environ, "AITBC_ROOT": str(REPO_ROOT)}
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stderr
    return env_file.read_text()


def test_append_to_file_without_trailing_newline(tmp_path):
    text = _run_defaults(tmp_path, b"BLOCKCHAIN_MODE=follower\nPROPOSER_ID=0xABC")

    lines = text.splitlines()
    assert "PROPOSER_ID=0xABC" in lines  # not glued to the appended key
    assert "BLOCK_SCOPED_PREREGISTERED_TRANSACTIONS=true" in lines
    assert "SYNC_STATE_ROOT_VALIDATION_ENABLED=true" in lines


def test_repeated_runs_add_each_key_once(tmp_path):
    text = _run_defaults(tmp_path, b"BLOCKCHAIN_MODE=follower\nPROPOSER_ID=0xABC", twice=True)
    assert text.count("BLOCK_SCOPED_PREREGISTERED_TRANSACTIONS=true") == 1
    assert text.count("SYNC_STATE_ROOT_VALIDATION_ENABLED=true") == 1
    assert text.count("subscription_enabled=true") == 1


def test_append_helper_itself_handles_a_missing_final_newline(tmp_path):
    f = tmp_path / "x.env"
    f.write_bytes(b"A=1")
    subprocess.run(["bash", str(HELPER), "append", str(f), "B=2"], check=True)
    assert f.read_text() == "A=1\nB=2\n"

    f.write_text("A=1\n")
    subprocess.run(["bash", str(HELPER), "append", str(f), "B=2"], check=True)
    assert f.read_text() == "A=1\nB=2\n"
