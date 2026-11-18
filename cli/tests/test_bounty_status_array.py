"""#2241: `bounty status` must accept the array shape /rpc/transactions returns.

The command scanned the endpoint with ``client.get`` which asserts an
object body and raises TypeError on a JSON array — the endpoint answers a
bare list, so `bounty status` failed for every bounty id.
"""

import json

from click.testing import CliRunner

from aitbc_cli.commands import bounty as bounty_mod


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
                "payload": {"bounty_id": "bounty-other"},
            },
        ]
        if tx_type == "BOUNTY_LOCK":
            rows.append(
                {
                    "tx_hash": "0x" + "cd" * 32,
                    "type": tx_type,
                    "block_height": 99,
                    "payload": {"bounty_id": "bounty-hit"},
                }
            )
        return rows

    def get(self, path, params=None):
        raise AssertionError("client.get must not be used on array-shaped endpoints")


def _invoke(runner, monkeypatch, args):
    monkeypatch.setattr(bounty_mod, "AITBCHTTPClient", _ArrayClient)
    return runner.invoke(
        bounty_mod.bounty,
        obj={"output_format": "json"},
        args=args,
    )


def test_status_accepts_array_response(monkeypatch):
    runner = CliRunner()
    result = _invoke(
        runner,
        monkeypatch,
        ["status", "--bounty-id", "bounty-hit", "--rpc-url", "http://127.0.0.1:8202", "--json"],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    txs = data["transactions"]
    assert "BOUNTY_LOCK" in txs
    assert all((tx.get("payload") or {}).get("bounty_id") == "bounty-hit" for tx in txs["BOUNTY_LOCK"])
    assert "BOUNTY_PAYOUT" not in txs


def test_status_reports_no_match(monkeypatch):
    runner = CliRunner()
    result = _invoke(
        runner,
        monkeypatch,
        ["status", "--bounty-id", "bounty-missing", "--rpc-url", "http://127.0.0.1:8202", "--json"],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["transactions"] == {}


def test_status_accepts_envelope_shape(monkeypatch):
    """A peer answering {"transactions": [...]} must not crash the lookup."""

    class _EnvelopeClient(_ArrayClient):
        def get_json(self, path, params=None):
            return {"transactions": super().get_json(path, params=params)}

    runner = CliRunner()
    monkeypatch.setattr(bounty_mod, "AITBCHTTPClient", _EnvelopeClient)
    result = runner.invoke(
        bounty_mod.bounty,
        obj={"output_format": "json"},
        args=["status", "--bounty-id", "bounty-hit", "--rpc-url", "http://127.0.0.1:8202", "--json"],
    )
    assert result.exit_code == 0, result.output
    assert "BOUNTY_LOCK" in json.loads(result.output)["transactions"]
