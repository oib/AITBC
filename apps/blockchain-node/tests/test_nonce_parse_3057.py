"""Pins for AUDIT-NONCE-FABRICATE-SETTLEMENT-1 / issue #3057.

``_get_account_nonce`` and ``_get_account_nonce_strict`` in
``escrow_routes_helpers`` used to answer ``0`` for a 200 account response
without a valid ``nonce`` field (``int(r.json().get("nonce", 0))``) — and
``_get_account_nonce`` also degraded to 0 on ANY probe failure. Both feed
settlement signing (``_settlement_signing_nonce`` /
``_settlement_next_nonce`` → ``_submit_market_signed``): a fabricated 0
signs a doomed ESCROW_RELEASE/REFUND/SWEEP/RECEIPT_CLAIM envelope.

Contract (same as #3015/#3041/#3044): only a real non-negative int counts —
explicit ``0`` included. Missing, null, string, bool, float or negative
nonce, a non-dict payload, and any probe failure are all "no source" →
``None`` → the submitter skips signing and reports a truthful failure.
"""

from __future__ import annotations

import importlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _reload_routes():
    """Reload escrow_routes so module-level env variables are re-read."""
    from aitbc_chain.rpc import escrow_routes

    importlib.reload(escrow_routes)
    return escrow_routes


@pytest.fixture
def routes(monkeypatch):
    monkeypatch.setenv("HUB_RPC_URL", "http://localhost:8202")
    monkeypatch.setenv("CHAIN_ID", "test-chain")
    return _reload_routes()


def _account_response(payload, status_code: int = 200) -> MagicMock:
    r = MagicMock()
    r.status_code = status_code
    r.json.return_value = payload
    return r


# ---------------------------------------------------------------------------
# _parse_account_nonce — the shared strict contract
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [{}, {"nonce": None}, {"nonce": "5"}, {"nonce": True}, {"nonce": -1}, {"nonce": 2.5}, "junk", None, [1, 2]],
)
def test_parse_account_nonce_rejects_malformed(routes, payload):
    from aitbc_chain.rpc import escrow_routes_helpers

    assert escrow_routes_helpers._parse_account_nonce(payload) is None


@pytest.mark.parametrize("nonce", [0, 1, 42])
def test_parse_account_nonce_accepts_real_ints(routes, nonce):
    from aitbc_chain.rpc import escrow_routes_helpers

    assert escrow_routes_helpers._parse_account_nonce({"nonce": nonce, "balance": 7}) == nonce


# ---------------------------------------------------------------------------
# _get_account_nonce — sealed read used by _settlement_next_nonce
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [{}, {"nonce": None}, {"nonce": "5"}, {"nonce": True}, {"nonce": False}, {"nonce": -1}, {"nonce": 2.5}, "junk"],
)
async def test_get_account_nonce_malformed_is_none_not_zero(routes, payload):
    """A 200 without a real nonce is 'no source' — never a fabricated 0."""
    with patch.object(routes.SharedHttpClient, "get", new_callable=AsyncMock, return_value=_account_response(payload)):
        assert await routes._get_account_nonce("0xabc") is None


@pytest.mark.asyncio
async def test_get_account_nonce_explicit_zero_valid(routes):
    with patch.object(routes.SharedHttpClient, "get", new_callable=AsyncMock, return_value=_account_response({"nonce": 0})):
        assert await routes._get_account_nonce("0xabc") == 0


@pytest.mark.asyncio
async def test_get_account_nonce_probe_failure_is_none(routes):
    with patch.object(routes.SharedHttpClient, "get", new_callable=AsyncMock, side_effect=RuntimeError("down")):
        assert await routes._get_account_nonce("0xabc") is None


@pytest.mark.asyncio
async def test_get_account_nonce_non_200_is_none(routes):
    with patch.object(
        routes.SharedHttpClient, "get", new_callable=AsyncMock, return_value=_account_response({"nonce": 3}, 500)
    ):
        assert await routes._get_account_nonce("0xabc") is None


# ---------------------------------------------------------------------------
# _get_account_nonce_strict — feeds _settlement_signing_nonce (release/refund/
# sweep/receipt-claim signing). A malformed 200 must be None, not 0.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [{}, {"nonce": None}, {"nonce": "5"}, {"nonce": True}, {"nonce": -1}, {"nonce": 2.5}, "junk"],
)
async def test_get_account_nonce_strict_malformed_is_none(routes, payload):
    with patch.object(routes.SharedHttpClient, "get", new_callable=AsyncMock, return_value=_account_response(payload)):
        assert await routes._get_account_nonce_strict("0xabc") is None


@pytest.mark.asyncio
async def test_get_account_nonce_strict_explicit_zero_valid(routes):
    with patch.object(routes.SharedHttpClient, "get", new_callable=AsyncMock, return_value=_account_response({"nonce": 0})):
        assert await routes._get_account_nonce_strict("0xabc") == 0


@pytest.mark.asyncio
async def test_get_account_nonce_strict_probe_failure_is_none(routes):
    with patch.object(routes.SharedHttpClient, "get", new_callable=AsyncMock, side_effect=RuntimeError("down")):
        assert await routes._get_account_nonce_strict("0xabc") is None


# ---------------------------------------------------------------------------
# Signing-path propagation: no nonce truth → no signed envelope
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_settlement_signing_nonce_none_on_malformed_account(routes):
    """End-to-end-ish: a malformed account response propagates None through
    _settlement_signing_nonce so _submit_market_signed skips signing."""
    calls = []

    async def get_side_effect(url, *args, **kwargs):
        calls.append(url)
        return _account_response({"nonce": "not-an-int"})

    with patch.object(routes.SharedHttpClient, "get", new_callable=AsyncMock, side_effect=get_side_effect):
        assert await routes._settlement_signing_nonce("0xabc") is None
    # The sealed read failed → the mempool lookahead is never consulted.
    assert all("/accounts/" in c for c in calls)


@pytest.mark.asyncio
async def test_settlement_next_nonce_none_on_probe_failure(routes):
    """_settlement_next_nonce degrades to None — the same fail-closed contract
    as _settlement_signing_nonce — instead of fabricating nonce 0."""
    with patch.object(routes.SharedHttpClient, "get", new_callable=AsyncMock, side_effect=RuntimeError("down")):
        assert await routes._settlement_next_nonce("0xabc") is None
