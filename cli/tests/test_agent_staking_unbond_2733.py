"""AGENT-STAKE-STATUS-UNBOND-BLIND (#2733): ``agent-staking status`` scanned
only STAKE_LOCK/STAKE_RELEASE, so a sealed (or pooled) STAKE_UNBOND marker —
the whole unbonding window — was invisible and the stake read as still
locked. STAKE_UNBOND rows are now scanned and tagged ``kind: unbond``.
"""

import json

from click.testing import CliRunner

from aitbc_cli.commands import agent_staking as stake_mod


class _Client:
    """Answers /rpc/transactions (sealed) and /rpc/pending (mempool)."""

    def __init__(self, sealed=None, pending=None):
        self._sealed = sealed or {}
        self._pending = pending or []

    def get_json(self, path, params=None, **kwargs):
        if path == "/rpc/pending":
            return {"success": True, "transactions": self._pending, "count": len(self._pending)}
        assert path == "/rpc/transactions"
        return list(self._sealed.get((params or {}).get("transaction_type"), []))


def _run(monkeypatch, client, stake_id="s-1"):
    monkeypatch.setattr(stake_mod, "AITBCHTTPClient", lambda *a, **k: client)
    return CliRunner().invoke(
        stake_mod.agent_staking,
        ["status", "--stake-id", stake_id, "--rpc-url", "http://x", "--json"],
        obj={"output_format": "json"},
    )


def _row(tx_type, stake_id="s-1"):
    return {"type": tx_type, "payload": {"agent_stake_id": stake_id}, "tx_hash": "0x" + "ab" * 32}


def test_sealed_unbond_is_reported_with_kind_unbond(monkeypatch):
    """The unbonding window must be visible between lock and release (#2733)."""
    client = _Client(
        sealed={
            "STAKE_LOCK": [_row("STAKE_LOCK")],
            "STAKE_UNBOND": [_row("STAKE_UNBOND")],
        }
    )
    result = _run(monkeypatch, client)
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["state"] == "sealed"
    unbonds = data["transactions"]["STAKE_UNBOND"]
    assert len(unbonds) == 1
    assert unbonds[0]["kind"] == "unbond"
    assert data["transactions"]["STAKE_LOCK"][0]["kind"] == "lock"


def test_pending_unbond_is_reported(monkeypatch):
    """A queued-but-unsealed STAKE_UNBOND also surfaces from the mempool."""
    client = _Client(pending=[_row("STAKE_UNBOND")])
    result = _run(monkeypatch, client)
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["state"] == "pending"
    assert data["pending_transactions"]["STAKE_UNBOND"][0]["kind"] == "unbond"


def test_unrelated_unbond_for_other_stake_ignored(monkeypatch):
    client = _Client(sealed={"STAKE_UNBOND": [_row("STAKE_UNBOND", stake_id="other")]})
    result = _run(monkeypatch, client)
    data = json.loads(result.output)
    assert "STAKE_UNBOND" not in data["transactions"]
    assert data["state"] is None
