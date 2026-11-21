"""`transactions status` pending probe spans every known mempool (#2361).

Round-5 finding: a tx fanned out to the proposer can sit in the hub's
mempool while the queried node's `/rpc/pending` misses it (evicted locally
or never received). The status command then aborted "not found (not sealed
and not in the mempool)" for a tx that sealed minutes later. The pending
probe now tries the resolved RPC plus the configured local RPC and hub RPC.
"""

from unittest.mock import MagicMock, patch

import pytest
import requests
from click.testing import CliRunner

import aitbc_cli.commands.transactions as tx_cmd

LOCAL_RPC = "http://node0.local:8202"
HUB_RPC = "http://hub.local:8202"


class _HTTP:
    """Per-base-URL fake: sealed lookup 404s; pending lists are per node."""

    pending_by_url: dict[str, list] = {}

    def __init__(self, base_url="", **kw):
        self.base_url = base_url

    def get(self, endpoint, **kw):
        if endpoint.startswith("/rpc/transaction/"):
            response = MagicMock()
            response.status_code = 404
            http_err = requests.HTTPError("404 Client Error")
            http_err.response = response
            raise tx_cmd.NetworkError("not found") from http_err
        if endpoint.startswith("/rpc/pending") or endpoint.startswith("/rpc/mempool"):
            return {"success": True, "transactions": _HTTP.pending_by_url.get(self.base_url, [])}
        raise AssertionError(f"unexpected GET {endpoint}")


def _config():
    return MagicMock(
        blockchain_rpc_url=LOCAL_RPC,
        hub_blockchain_rpc_url=HUB_RPC,
        hub_discovery_url="hub.local",
    )


def _pending_entry() -> dict:
    """A mempool entry; ``/rpc/pending`` entries carry no hash on the wire —
    the CLI recomputes it, so tests derive the queried hash the same way."""
    return {"type": "TRANSFER", "nonce": 7, "amount": 100}


def _tx_hash_for(entry: dict) -> str:
    return tx_cmd._pending_tx_hash(entry)


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture(autouse=True)
def _reset():
    _HTTP.pending_by_url = {}
    yield
    _HTTP.pending_by_url = {}


def test_probe_urls_include_local_and_hub_when_resolved_is_local():
    with patch.object(tx_cmd, "get_config", return_value=_config()):
        urls = tx_cmd._pending_probe_urls(LOCAL_RPC)
    assert urls[0] == LOCAL_RPC
    assert any("hub.local" in u for u in urls)
    assert len(urls) == len(set(u.rstrip("/") for u in urls))


def test_probe_urls_dedup_when_resolved_is_hub():
    with patch.object(tx_cmd, "get_config", return_value=_config()):
        urls = tx_cmd._pending_probe_urls(HUB_RPC)
    assert urls[0] == HUB_RPC
    assert LOCAL_RPC in urls


def test_find_pending_tx_anywhere_finds_tx_on_second_node():
    entry = _pending_entry()
    tx_hash = _tx_hash_for(entry)
    _HTTP.pending_by_url[HUB_RPC] = [entry]
    with patch.object(tx_cmd, "AITBCHTTPClient", _HTTP):
        found = tx_cmd._find_pending_tx_anywhere(tx_hash, [LOCAL_RPC, HUB_RPC])
    assert found is not None
    assert found["status"] == "pending"
    assert found["tx_hash"] == tx_hash


def test_find_pending_tx_anywhere_returns_none_when_all_miss():
    with patch.object(tx_cmd, "AITBCHTTPClient", _HTTP):
        assert tx_cmd._find_pending_tx_anywhere("0x" + "00" * 32, [LOCAL_RPC, HUB_RPC]) is None


def test_status_reports_pending_found_on_peer_mempool(runner):
    """The round-5 case: local 404 + local pending miss, hub pending hit."""
    entry = _pending_entry()
    tx_hash = _tx_hash_for(entry)
    _HTTP.pending_by_url[HUB_RPC] = [entry]
    with (
        patch.object(tx_cmd, "get_config", return_value=_config()),
        patch.object(tx_cmd, "AITBCHTTPClient", _HTTP),
    ):
        result = runner.invoke(tx_cmd.status, ["--tx-hash", tx_hash, "--rpc-url", LOCAL_RPC])
    assert result.exit_code == 0, result.output
    assert "pending" in result.output
    assert tx_hash in result.output


def test_status_aborts_only_when_no_node_knows_the_tx(runner):
    with (
        patch.object(tx_cmd, "get_config", return_value=_config()),
        patch.object(tx_cmd, "AITBCHTTPClient", _HTTP),
    ):
        result = runner.invoke(tx_cmd.status, ["--tx-hash", "0x" + "00" * 32, "--rpc-url", LOCAL_RPC])
    assert result.exit_code != 0
    assert "not pending on any reachable node" in result.output
