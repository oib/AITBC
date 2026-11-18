"""Pins for GENESIS-VERIFY-1 (#2200).

``genesis verify`` printed wrong block fields (positional ``SELECT *``
indices vs the real schema), rendered ``genesis_hash``/``proposer`` empty
because the canonical genesis document has no ``block`` key, and exited 1
on follower nodes that legitimately have no treasury wallet.
"""

import json
import sqlite3
from pathlib import Path

import pytest
from click.testing import CliRunner

from aitbc_cli.commands.genesis import genesis


@pytest.fixture
def data_dir(tmp_path):
    """Scratch data dir with a canonical-shape genesis.json + chain.db."""
    chain = "t-chain"
    cdir = tmp_path / chain
    cdir.mkdir(parents=True)

    genesis_json = {
        "chain_id": chain,
        "genesis_hash": "0x" + "ab" * 32,
        "allocations": [{"address": "0x" + "11" * 20, "balance": 1, "nonce": 0}],
        "parameters": {},
        "state_root": "0x" + "00" * 32,
        "timestamp": "2026-11-18T00:00:00Z",
    }
    (cdir / "genesis.json").write_text(json.dumps(genesis_json))

    conn = sqlite3.connect(cdir / "chain.db")
    conn.execute(
        "CREATE TABLE block (id INTEGER PRIMARY KEY, chain_id VARCHAR, height INTEGER, "
        "hash VARCHAR, parent_hash VARCHAR, proposer VARCHAR, timestamp DATETIME, "
        "tx_count INTEGER, state_root VARCHAR, bridge_state_root VARCHAR, "
        "aux_state_root VARCHAR, block_metadata VARCHAR, signature VARCHAR)"
    )
    conn.execute(
        "INSERT INTO block (chain_id, height, hash, parent_hash, proposer, timestamp, tx_count, signature) "
        "VALUES (?, 0, ?, '0x00', 'genesis', '2026-11-18', 0, '0xsig')",
        (chain, "0x" + "cd" * 32),
    )
    conn.execute("CREATE TABLE account (chain_id VARCHAR, address VARCHAR, balance INTEGER, nonce INTEGER)")
    conn.execute("INSERT INTO account VALUES (?, '0x' + '11' * 20, 1, 0)", (chain,))
    conn.commit()
    conn.close()
    return tmp_path


def _verify(data_dir, chain="t-chain"):
    return CliRunner().invoke(
        genesis,
        ["verify", "--chain-id", chain, "--data-dir", str(data_dir)],
        obj={"output_format": "table"},
    )


def test_verify_block_table_shows_real_fields(data_dir):
    """height/hash/proposer must be the DB values, not shifted columns."""
    result = _verify(data_dir)
    assert result.exit_code == 0, result.output
    # table output: 'bc-2'-style chain_id must not appear as a height
    assert "t-chain" not in result.output.split("Genesis block found")[1].split("\n")[2]
    assert "0x" + "cd" * 32 in result.output  # real block hash
    assert "genesis" in result.output


def test_verify_genesis_hash_from_top_level_key(data_dir):
    """genesis_hash renders from the document's top-level key (#2200)."""
    result = _verify(data_dir)
    assert result.exit_code == 0, result.output
    assert "0x" + "ab" * 32 in result.output


def test_verify_missing_treasury_wallet_is_warning_not_failure(data_dir):
    """No /var/lib/aitbc/keystore/genesis.json on a follower -> exit 0."""
    result = _verify(data_dir)
    assert result.exit_code == 0, result.output
    assert "Treasury (genesis) wallet not found" in result.output


def test_verify_missing_db_fails(data_dir):
    """Absent chain.db still fails the verify."""
    (data_dir / "t-chain" / "chain.db").unlink()
    result = _verify(data_dir)
    assert result.exit_code != 0


def test_verify_missing_genesis_json_fails(tmp_path):
    result = CliRunner().invoke(
        genesis,
        ["verify", "--chain-id", "nope", "--data-dir", str(tmp_path)],
        obj={"output_format": "table"},
    )
    assert result.exit_code != 0
    assert "Genesis config not found" in result.output


def test_verify_json_output_shape(data_dir):
    result = CliRunner().invoke(
        genesis,
        ["verify", "--chain-id", "t-chain", "--data-dir", str(data_dir)],
        obj={"output_format": "json"},
    )
    assert result.exit_code == 0, result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
