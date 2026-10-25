"""CLI-POLISH-1: brand plugin errors as one line, genesis info fills block 0."""

import json
import sqlite3
from pathlib import Path

from click.testing import CliRunner

from aitbc_cli.commands.brand import brand
from aitbc_cli.commands.genesis import genesis


def test_brand_show_missing_plugin_clean_error(monkeypatch, tmp_path):
    monkeypatch.setenv("AITBC_PLUGINS_DIR", str(tmp_path))
    monkeypatch.setenv("AITBC_ACTIVE_PLUGIN", "mybrand")
    result = CliRunner().invoke(brand, args=["show"], obj={"output_format": "table"})
    assert result.exit_code != 0
    assert "mybrand" in result.output
    assert "aitbc plugin create mybrand" in result.output
    assert "Traceback" not in result.output
    assert "FileNotFoundError" not in result.output


def _mk_genesis(d: Path):
    d.mkdir(parents=True)
    (d / "genesis.json").write_text(
        json.dumps(
            {
                "chain_id": "test-chain",
                "allocations": [{"address": "0x" + "1" * 40, "balance": 5, "nonce": 0}],
            }
        )
    )


def _mk_chain_db(d: Path):
    db = d / "chain.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE block (id INTEGER, chain_id VARCHAR, height INTEGER, hash VARCHAR, "
        "parent_hash VARCHAR, proposer VARCHAR, timestamp DATETIME, tx_count INTEGER, "
        "state_root VARCHAR, bridge_state_root VARCHAR, aux_state_root VARCHAR, block_metadata VARCHAR)"
    )
    conn.execute(
        "INSERT INTO block VALUES (1,'test-chain',0,'0xGEN','0x0','0xPROP','2026-01-01 00:00:00',3,'0xS',NULL,NULL,NULL)"
    )
    conn.commit()
    conn.close()


def test_genesis_info_fills_block0(tmp_path, monkeypatch):
    data_dir = tmp_path / "data" / "test-chain"
    _mk_genesis(data_dir)
    _mk_chain_db(data_dir)
    result = CliRunner().invoke(
        genesis,
        args=["info", "--chain-id", "test-chain", "--data-dir", str(tmp_path / "data")],
        obj={"output_format": "json"},
    )
    assert result.exit_code == 0, result.output
    assert "0xGEN" in result.output
    assert "0xPROP" in result.output


def test_genesis_info_no_db_prints_note(tmp_path):
    data_dir = tmp_path / "data" / "test-chain"
    _mk_genesis(data_dir)
    result = CliRunner().invoke(
        genesis,
        args=["info", "--chain-id", "test-chain", "--data-dir", str(tmp_path / "data")],
        obj={"output_format": "json"},
    )
    assert result.exit_code == 0, result.output
    assert "not sealed" in result.output
