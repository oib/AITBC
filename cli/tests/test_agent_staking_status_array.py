"""STRESS-CLI-3 (#746): `agent-staking status` must accept the array shape
/rpc/transactions returns.

The command scanned the endpoint with ``client.get`` which asserts an
object body and raises TypeError on a JSON array — the endpoint has
always answered a bare list, so status failed on every host.
"""

import json

from click.testing import CliRunner

from aitbc_cli.commands import agent_staking as agent_staking_mod


class _ArrayClient:
    """Stand-in for AITBCHTTPClient answering the real array shape."""

    def __init__(self, base_url=None, timeout=None):
        pass

    def get_json(self, path, params=None):
        assert path == "/rpc/transactions"
        tx_type = (params or {}).get("transaction_type")
        rows = [
            {
                "tx_hash": "0x" + "ab" * 32,
                "type": tx_type,
                "block_height": 100,
                "payload": {"agent_stake_id": "stake-other", "amount": 360},
            },
        ]
        if tx_type == "STAKE_LOCK":
            rows.append(
                {
                    "tx_hash": "0x" + "cd" * 32,
                    "type": tx_type,
                    "block_height": 99,
                    "payload": {"agent_stake_id": "stake-hit", "amount": 1},
                }
            )
        return rows


def _invoke(runner, monkeypatch, args):
    monkeypatch.setattr(agent_staking_mod, "AITBCHTTPClient", _ArrayClient)
    return runner.invoke(
        agent_staking_mod.agent_staking,
        obj={"output_format": "json"},
        args=args,
    )


def test_status_accepts_array_response(monkeypatch):
    runner = CliRunner()
    result = _invoke(
        runner,
        monkeypatch,
        ["status", "--stake-id", "stake-hit", "--json"],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    txs = data["transactions"]
    assert "STAKE_LOCK" in txs
    assert all((tx.get("payload") or {}).get("agent_stake_id") == "stake-hit" for tx in txs["STAKE_LOCK"])
    assert "STAKE_RELEASE" not in txs


def test_status_reports_no_match(monkeypatch):
    runner = CliRunner()
    result = _invoke(
        runner,
        monkeypatch,
        ["status", "--stake-id", "stake-missing", "--json"],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["transactions"] == {}
