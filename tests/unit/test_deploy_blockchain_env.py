"""#888: node scripts write the env the node actually reads.

The legacy writers emitted a working-directory `.env` (never in the
settings env list) carrying a clock-derived PROPOSER_KEY placeholder and
no PROPOSER_ID — a guaranteed crash loop under enable_block_production.
Now they call deploy-env.sh's write_blockchain_env, which writes
AITBC_CHAIN_ENV_FILE (default /etc/aitbc/blockchain.env), requires real
proposer identity when production is enabled, and no placeholder exists.
"""

import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEPLOY = REPO / "scripts" / "deployment" / "deploy"

WRITERS = [
    "deploy-blockchain-remote.sh",
    "deploy-in-container.sh",
    "deploy-blockchain-and-explorer.sh",
]


def _write_env(tmp_path, extra_env=None, script_args=""):
    env = dict(os.environ)
    env.pop("AITBC_PROPOSER_ID", None)
    env.pop("AITBC_PROPOSER_KEY", None)
    env["AITBC_CHAIN_ENV_FILE"] = str(tmp_path / "blockchain.env")
    env.update(extra_env or {})
    return subprocess.run(
        ["bash", "-c", f'source "{DEPLOY}/deploy-env.sh" && write_blockchain_env {script_args}'],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_writers_use_the_helper_and_have_no_placeholder_key():
    for name in WRITERS:
        src = (DEPLOY / name).read_text()
        assert "write_blockchain_env" in src, f"{name} still writes its own env"
        assert "proposer_key_$(date" not in src, f"{name} still emits the clock placeholder"


def test_helper_writes_the_file_the_node_reads(tmp_path):
    """Default path is /etc/aitbc/blockchain.env — the test overrides it via
    AITBC_CHAIN_ENV_FILE, the same var settings consults."""
    result = _write_env(tmp_path, script_args='"./data/chain.db" "0.0.0.0" 8202 "0.0.0.0" 7070 memory')
    assert result.returncode == 0, result.stderr
    text = (tmp_path / "blockchain.env").read_text()
    assert "CHAIN_ID=" in text and "DB_PATH=./data/chain.db" in text
    assert "PROPOSER_KEY=proposer_key_" not in text
    assert "PROPOSER_ID" not in text  # unset when production is off
    assert (tmp_path / "blockchain.env").stat().st_mode & 0o777 == 0o600


def test_production_requires_real_proposer_identity(tmp_path):
    """AITBC_ENABLE_BLOCK_PRODUCTION=true without PROPOSER_ID/KEY refuses,
    instead of emitting a placeholder that crashes on start."""
    result = _write_env(
        tmp_path,
        {"AITBC_ENABLE_BLOCK_PRODUCTION": "true"},
        script_args='"./data/chain.db" "0.0.0.0" 8202 "0.0.0.0" 7070 memory',
    )
    assert result.returncode != 0
    assert "AITBC_PROPOSER_ID" in result.stderr


def test_production_writes_both_proposer_vars(tmp_path):
    result = _write_env(
        tmp_path,
        {
            "AITBC_ENABLE_BLOCK_PRODUCTION": "true",
            "AITBC_PROPOSER_ID": "0x" + "ab" * 20,
            "AITBC_PROPOSER_KEY": "de" * 32,
        },
        script_args='"./data/chain.db" "0.0.0.0" 8202 "0.0.0.0" 7070 memory',
    )
    assert result.returncode == 0, result.stderr
    text = (tmp_path / "blockchain.env").read_text()
    assert "PROPOSER_ID=0x" in text and "PROPOSER_KEY=" in text
