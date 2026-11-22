"""#2507: bounty/agent-staking status must page past the newest-N window.

Both commands used to fetch ONE ``limit=200`` newest page per tx type and
match client-side, so an id older than the window read ``found:false`` /
empty. The shared ``scan_transactions_for_payload_id`` helper now walks the
type's history with ``before_id`` until the row budget or history ends, and
reports ``truncated`` so a capped scan is never mistaken for not-found.
"""

import copy
import json

from click.testing import CliRunner

import aitbc_cli.commands.agent_staking as agent_staking_mod
import aitbc_cli.commands.bounty as bounty_mod
from aitbc_cli.utils.tx_history import scan_transactions_for_payload_id
from aitbc_cli.utils.http_client import AITBCHTTPClient
from typing import cast


def _tx(tid, tx_type, payload_id, payload_key):
    return {
        "transaction_id": tid,
        "tx_hash": "0x" + f"{tid:064x}",
        "type": tx_type,
        "payload": {payload_key: payload_id, "amount": 1},
    }


class _StreamClient:
    """Emulates GET /rpc/transactions: newest-first, honours limit+before_id
    and the transaction_type filter (payload filters are client-side)."""

    def __init__(self, rows):
        self.rows = sorted(rows, key=lambda r: r["transaction_id"], reverse=True)
        self.calls = []

    def get_json(self, path, params=None, **kwargs):
        if path == "/rpc/pending":
            return []
        assert path == "/rpc/transactions"
        params = params or {}
        self.calls.append(dict(params))
        tx_type = params.get("transaction_type")
        limit = int(params.get("limit") or 100)
        before = params.get("before_id")
        out = [
            copy.deepcopy(r) for r in self.rows if r["type"] == tx_type and (before is None or r["transaction_id"] < before)
        ]
        return out[:limit]


def _client(rows) -> tuple[AITBCHTTPClient, _StreamClient]:
    stream = _StreamClient(rows)
    return cast(AITBCHTTPClient, stream), stream


def test_helper_finds_id_older_than_first_page():
    """The target id sits below the first page — paging must reach it."""
    rows = [_tx(i, "BOUNTY_LOCK", f"b-{i}", "bounty_id") for i in range(1, 601)]
    rows.append(_tx(0, "BOUNTY_LOCK", "b-ancient", "bounty_id"))  # oldest row, id 0
    client, stream = _client(rows)
    matches, truncated = scan_transactions_for_payload_id(
        client, transaction_type="BOUNTY_LOCK", payload_key="bounty_id", payload_id="b-ancient", limit=5000
    )
    assert [m["transaction_id"] for m in matches] == [0]
    assert truncated is False
    # second call walked before_id
    assert any("before_id" in c for c in stream.calls)


def test_helper_truncated_when_budget_exhausted_on_full_page():
    rows = [_tx(i, "BOUNTY_PAYOUT", f"b-{i}", "bounty_id") for i in range(1, 601)]
    client, _stream = _client(rows)
    matches, truncated = scan_transactions_for_payload_id(
        client,
        transaction_type="BOUNTY_PAYOUT",
        payload_key="bounty_id",
        payload_id="b-0",
        limit=500,  # exactly one page — last page full, history may remain
        page_size=500,
    )
    assert matches == []
    assert truncated is True


def test_helper_not_truncated_on_short_last_page():
    rows = [_tx(i, "BOUNTY_PAYOUT", f"b-{i}", "bounty_id") for i in range(1, 120)]
    client, _stream = _client(rows)
    matches, truncated = scan_transactions_for_payload_id(
        client, transaction_type="BOUNTY_PAYOUT", payload_key="bounty_id", payload_id="b-1", limit=5000
    )
    assert len(matches) == 1 and not truncated


def test_bounty_status_finds_old_id_and_reports_truncated(monkeypatch):
    rows = [_tx(i, "BOUNTY_LOCK", f"b-{i}", "bounty_id") for i in range(1, 601)]
    rows.append(_tx(0, "BOUNTY_LOCK", "b-ancient", "bounty_id"))
    stream = _StreamClient(rows)
    monkeypatch.setattr(bounty_mod, "AITBCHTTPClient", lambda *a, **k: stream)
    runner = CliRunner()
    result = runner.invoke(
        bounty_mod.bounty,
        obj={"output_format": "json"},
        args=["status", "--bounty-id", "b-ancient", "--rpc-url", "http://x", "--json"],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["found"] is True
    assert data["truncated"] is False
    assert data["transactions"]["BOUNTY_LOCK"][0]["transaction_id"] == 0


def test_bounty_status_capped_scan_reports_truncated_not_found(monkeypatch):
    rows = [_tx(i, "BOUNTY_LOCK", f"b-{i}", "bounty_id") for i in range(1, 601)]
    stream = _StreamClient(rows)
    monkeypatch.setattr(bounty_mod, "AITBCHTTPClient", lambda *a, **k: stream)
    runner = CliRunner()
    result = runner.invoke(
        bounty_mod.bounty,
        obj={"output_format": "json"},
        args=["status", "--bounty-id", "b-ancient", "--rpc-url", "http://x", "--json", "--limit", "500"],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["found"] is False
    assert data["truncated"] is True  # capped scan ≠ proven absent


def test_agent_staking_status_finds_old_id(monkeypatch):
    rows = [_tx(i, "STAKE_LOCK", f"s-{i}", "agent_stake_id") for i in range(1, 601)]
    rows.append(_tx(0, "STAKE_LOCK", "s-ancient", "agent_stake_id"))
    rows.append(_tx(700, "STAKE_RELEASE", "s-ancient", "agent_stake_id"))
    stream = _StreamClient(rows)
    monkeypatch.setattr(agent_staking_mod, "AITBCHTTPClient", lambda *a, **k: stream)
    runner = CliRunner()
    result = runner.invoke(
        agent_staking_mod.agent_staking,
        obj={"output_format": "json"},
        args=["status", "--stake-id", "s-ancient", "--json"],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert "STAKE_LOCK" in data["transactions"] and "STAKE_RELEASE" in data["transactions"]
    assert data["transactions"]["STAKE_RELEASE"][0]["kind"] == "release"
    assert data["truncated"] is False
