"""PROTOCOL-LANE-SEAL-1 (#2457): ``bounty status``/``agent-staking status``
scanned sealed ``/rpc/transactions`` only, so a submitted-but-unsealed
protocol transfer read as absent. They now also read ``/rpc/pending`` and
report ``state: pending|sealed`` plus the pooled rows.
"""

import json

from click.testing import CliRunner

from aitbc_cli.commands import agent_staking as stake_mod
from aitbc_cli.commands import bounty as bounty_mod


class _Client:
    """Answers /rpc/transactions (sealed) and /rpc/pending (mempool)."""

    def __init__(self, sealed=None, pending=None, pending_exc=None, base_url=None, timeout=None):
        self._sealed = sealed or {}
        self._pending = pending or []
        self._pending_exc = pending_exc

    def get_json(self, path, params=None, **kwargs):
        if path == "/rpc/pending":
            if self._pending_exc is not None:
                raise self._pending_exc
            return {"success": True, "transactions": self._pending, "count": len(self._pending)}
        assert path == "/rpc/transactions"
        tx_type = (params or {}).get("transaction_type")
        return list(self._sealed.get(tx_type, []))


def _run_bounty(monkeypatch, client, bounty_id="b-1"):
    monkeypatch.setattr(bounty_mod, "AITBCHTTPClient", lambda *a, **k: client)
    return CliRunner().invoke(
        bounty_mod.bounty,
        ["status", "--bounty-id", bounty_id, "--rpc-url", "http://x", "--json"],
        obj={"output_format": "json"},
    )


def _run_stake(monkeypatch, client, stake_id="s-1"):
    monkeypatch.setattr(stake_mod, "AITBCHTTPClient", lambda *a, **k: client)
    return CliRunner().invoke(
        stake_mod.agent_staking,
        ["status", "--stake-id", stake_id, "--rpc-url", "http://x", "--json"],
        obj={"output_format": "json"},
    )


def _pending_row(tx_type, payload):
    return {"type": tx_type, "payload": payload, "state": "pending", "tx_hash": "0x" + "00" * 32}


def test_bounty_status_pending_only_reports_state_pending(monkeypatch):
    client = _Client(
        pending=[_pending_row("BOUNTY_LOCK", {"bounty_id": "b-1", "amount": 5})],
    )
    result = _run_bounty(monkeypatch, client)
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["state"] == "pending"
    assert data["found"] is False
    assert "BOUNTY_LOCK" in data["pending_transactions"]
    assert data["pending_transactions"]["BOUNTY_LOCK"][0]["payload"]["bounty_id"] == "b-1"


def test_bounty_status_sealed_reports_state_sealed(monkeypatch):
    client = _Client(
        sealed={"BOUNTY_LOCK": [{"type": "BOUNTY_LOCK", "payload": {"bounty_id": "b-1"}}]},
    )
    result = _run_bounty(monkeypatch, client)
    data = json.loads(result.output)
    assert data["state"] == "sealed"
    assert data["pending_transactions"] == {}


def test_bounty_status_unrelated_pending_ignored(monkeypatch):
    client = _Client(
        pending=[
            _pending_row("BOUNTY_LOCK", {"bounty_id": "other"}),
            _pending_row("TRANSFER", {"bounty_id": "b-1"}),  # TRANSFER resolves payload.type only
        ],
    )
    result = _run_bounty(monkeypatch, client)
    data = json.loads(result.output)
    assert data["state"] is None
    assert data["pending_transactions"] == {}


def test_agent_staking_status_pending_lock(monkeypatch):
    client = _Client(
        pending=[_pending_row("STAKE_LOCK", {"agent_stake_id": "s-1", "amount": 3})],
    )
    result = _run_stake(monkeypatch, client)
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["state"] == "pending"
    assert data["pending_transactions"]["STAKE_LOCK"][0]["kind"] == "lock"


def test_agent_staking_status_sealed_wins_over_pending(monkeypatch):
    client = _Client(
        sealed={"STAKE_LOCK": [{"type": "STAKE_LOCK", "payload": {"agent_stake_id": "s-1"}}]},
        pending=[_pending_row("STAKE_RELEASE", {"agent_stake_id": "s-1"})],
    )
    result = _run_stake(monkeypatch, client)
    data = json.loads(result.output)
    assert data["state"] == "sealed"
    assert "STAKE_RELEASE" in data["pending_transactions"]


def test_pending_lookup_failure_is_flagged_not_fatal(monkeypatch):
    from aitbc.exceptions import NetworkError

    client = _Client(pending_exc=NetworkError("refused"))
    result = _run_bounty(monkeypatch, client)
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["pending_lookup_failed"] is True
    assert data["state"] is None
