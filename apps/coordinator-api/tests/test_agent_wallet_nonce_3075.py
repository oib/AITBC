"""Pins for AUDIT-NONCE-FABRICATE-AGENTWALLET-1 (#3075).

``AITBCWalletAdapter._get_nonce`` used to answer ``0`` for every failure
shape — a missing/null/string/bool/float/negative nonce on a 200, or any
probe exception — and ``execute_transaction`` then signed an envelope at
that fabricated nonce inside the spend-session claim window. The #3015
genus, last straggler: only a real non-negative int (explicit ``0``
included) may feed signing; everything else fails closed as a definite
pre-send ``ValueError`` so the caller releases the reservation.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from eth_account import Account
from eth_utils import to_checksum_address

from coordinator_api.agent_identity.wallet_adapter_enhanced import AITBCWalletAdapter


_DEFAULT = object()


def _adapter(account_payload=_DEFAULT, get_side_effect=None):
    adapter = AITBCWalletAdapter("http://rpc.invalid")
    client = MagicMock()
    if get_side_effect is not None:
        client.get.side_effect = get_side_effect
    else:
        client.get.return_value = {"nonce": 7} if account_payload is _DEFAULT else account_payload
    client.post.return_value = {"transaction_hash": "0xtx"}
    adapter._http_client = client
    return adapter, client


# --- _get_nonce: strict-uint contract ----------------------------------------


@pytest.mark.asyncio
async def test_get_nonce_returns_real_nonce():
    adapter, _ = _adapter({"nonce": 42})
    assert await adapter._get_nonce("0x" + "aa" * 20) == 42


@pytest.mark.asyncio
async def test_get_nonce_explicit_zero_is_valid():
    """A fresh account really does sit at nonce 0 — it must not be
    confused with the fabricated-0 failure shape."""
    adapter, _ = _adapter({"nonce": 0})
    assert await adapter._get_nonce("0x" + "aa" * 20) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {},  # missing
        {"nonce": None},
        {"nonce": "7"},
        {"nonce": True},
        {"nonce": 1.5},
        {"nonce": -1},
        "not-a-dict",
        None,
    ],
)
async def test_get_nonce_malformed_never_fabricates_zero(payload):
    adapter, _ = _adapter(payload)
    assert await adapter._get_nonce("0x" + "aa" * 20) is None


@pytest.mark.asyncio
async def test_get_nonce_probe_failure_returns_none():
    adapter, _ = _adapter(get_side_effect=RuntimeError("rpc down"))
    assert await adapter._get_nonce("0x" + "aa" * 20) is None


# --- execute_transaction: fail closed before signing --------------------------


@pytest.mark.asyncio
async def test_execute_transaction_refuses_signing_without_nonce_truth():
    """Every malformed/failure nonce shape must stop the tx BEFORE the
    signature is computed and BEFORE rpc/transaction is posted — the old
    code signed nonce=0 envelopes that could never land."""
    for payload in ({}, {"nonce": "7"}, {"nonce": None}):
        adapter, client = _adapter(payload)
        acct = Account.create()
        with pytest.raises(ValueError, match="nonce unavailable"):
            await adapter.execute_transaction(
                to_checksum_address(acct.address),
                to_checksum_address(Account.create().address),
                Decimal("1"),
                private_key=acct.key.hex(),
            )
        client.post.assert_not_called()


@pytest.mark.asyncio
async def test_execute_transaction_probe_failure_refuses_signing():
    adapter, client = _adapter(get_side_effect=RuntimeError("rpc down"))
    acct = Account.create()
    with pytest.raises(ValueError, match="nonce unavailable"):
        await adapter.execute_transaction(
            to_checksum_address(acct.address),
            to_checksum_address(Account.create().address),
            Decimal("1"),
            private_key=acct.key.hex(),
        )
    client.post.assert_not_called()


@pytest.mark.asyncio
async def test_execute_transaction_signs_with_real_nonce():
    """Control: a valid account response still flows through to a signed,
    posted transaction carrying the chain nonce."""
    adapter, client = _adapter({"nonce": 9})
    acct = Account.create()
    result = await adapter.execute_transaction(
        to_checksum_address(acct.address),
        to_checksum_address(Account.create().address),
        Decimal("1"),
        private_key=acct.key.hex(),
    )
    assert result["transaction_hash"] == "0xtx"
    posted = client.post.call_args.kwargs["json"]
    assert posted["nonce"] == 9
    assert posted["signature"]
