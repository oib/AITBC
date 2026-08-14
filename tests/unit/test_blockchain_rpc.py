"""Unit tests for aitbc.marketplace.blockchain_rpc (v0.6.6 §A3).

Covers the BlockchainRPCClient with mocked httpx responses. No real
blockchain node required — all HTTP calls are stubbed with AsyncMock.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx

from aitbc.marketplace.blockchain_rpc import BlockchainRPCClient

RPC_URL = "http://localhost:8202"


def _mock_response(
    status_code: int = 200,
    json_data: dict | list | None = None,
) -> MagicMock:
    """Create a mock httpx.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data if json_data is not None else {}
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error",
            request=MagicMock(),
            response=resp,
        )
    return resp


def _mock_async_client(resp: MagicMock) -> AsyncMock:
    """Create a mock httpx.AsyncClient that returns the given response for all methods."""
    client = AsyncMock()
    client.get = AsyncMock(return_value=resp)
    client.post = AsyncMock(return_value=resp)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    return client


# ---------------------------------------------------------------------------
# rpc_url
# ---------------------------------------------------------------------------


def test_rpc_url_default() -> None:
    client = BlockchainRPCClient()
    assert client.rpc_url == "http://localhost:8202"


def test_rpc_url_custom() -> None:
    client = BlockchainRPCClient(rpc_url="http://node:9000")
    assert client.rpc_url == "http://node:9000"


def test_rpc_url_strips_trailing_slash() -> None:
    client = BlockchainRPCClient(rpc_url="http://localhost:8202/")
    assert client.rpc_url == "http://localhost:8202"


# ---------------------------------------------------------------------------
# query_offers
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# get_offer
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# submit_transaction
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# register_gpu
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# allocate_gpu
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# verify_escrow (v0.10.1 A1: job_id parameter, backward-compat escrow_id)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# package re-export
# ---------------------------------------------------------------------------


def test_package_reexport() -> None:
    from aitbc.marketplace import BlockchainRPCClient as ExportedClient

    assert ExportedClient is BlockchainRPCClient
