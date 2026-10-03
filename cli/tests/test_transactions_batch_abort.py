"""Batch aborts with a partial summary when a lookup fails mid-run.

``transactions batch`` submits entries in order; when a chain-id/nonce lookup
raises CLIError the loop must report which entries already went out (hashes)
and which entry failed, then exit non-zero — the hashes are the only receipt.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

import aitbc_cli.utils.chain_id as chain_id_mod


@pytest.fixture
def runner():
    return CliRunner()


def _serving_chain_lookup(chain_id):
    def _fake(rpc_url, override=None, timeout=5, *, strict=False):
        return override or chain_id

    return _fake


def _write_named_wallet(directory: Path, name: str, address: str) -> None:
    (directory / f"{name}.json").write_text(
        json.dumps({"address": address, "private_key": "0x" + "11" * 32, "encrypted": False})
    )


def test_batch_prints_partial_summary_when_entry_lookup_fails(runner, tmp_path, monkeypatch):
    """Abort on entry 3 of 4: the summary names the submitted hashes and entry."""
    from aitbc_cli.commands import transactions as tx_mod

    wallet_dir = tmp_path / "wallets"
    wallet_dir.mkdir()
    addrs = {
        "w1": "0x1111111111111111111111111111111111111111",
        "w2": "0x2222222222222222222222222222222222222222",
        "w3": "0x3333333333333333333333333333333333333333",
        "w4": "0x4444444444444444444444444444444444444444",
    }
    for name, addr in addrs.items():
        _write_named_wallet(wallet_dir, name, addr)

    batch_file = tmp_path / "txs.json"
    batch_file.write_text(
        json.dumps(
            [
                {"from_wallet": n, "to_address": "0x02B8F2C61DB19B04aB68cfb43d0605E63dE74c5B", "amount": "1"}
                for n in ("w1", "w2", "w3", "w4")
            ]
        )
    )

    post_counter = {"n": 0}

    class _C:
        def __init__(self, base_url="", **kw):
            self.base_url = base_url

        def get(self, endpoint, **kw):
            if addrs["w3"] in endpoint or addrs["w4"] in endpoint:
                raise RuntimeError("connection refused")
            return {"nonce": 1}

        def post(self, endpoint, json=None, **kw):
            post_counter["n"] += 1
            return {"transaction_hash": f"0xhash{post_counter['n']}"}

    monkeypatch.delenv("CHAIN_ID", raising=False)
    with (
        patch.object(chain_id_mod, "get_chain_id", side_effect=_serving_chain_lookup("ait-test")),
        patch("aitbc_cli.commands.transactions.AITBCHTTPClient", _C),
        patch("aitbc_cli.commands.transactions.wallet_dir", return_value=wallet_dir),
    ):
        result = runner.invoke(
            tx_mod.transactions,
            ["batch", "--transactions-file", str(batch_file), "--password", "x", "--rpc-url", "http://node:1"],
            obj={},
        )
    assert result.exit_code != 0
    assert "0xhash1" in result.output and "0xhash2" in result.output
    assert "entry 3/4" in result.output and "w3" in result.output
    assert "Batch completed" not in result.output
    assert post_counter["n"] == 2
