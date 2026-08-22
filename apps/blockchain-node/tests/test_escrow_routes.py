"""Tests for escrow RPC settlement key handling."""

import importlib
import os
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _reload_routes():
    """Reload escrow_routes so module-level env variables are re-read."""
    from aitbc_chain.rpc import escrow_routes

    importlib.reload(escrow_routes)
    return escrow_routes


@pytest.fixture
def release_key():
    # Deterministic, valid secp256k1 test key.
    return "0x2222222222222222222222222222222222222222222222222222222222222222"


def test_settlement_key_prefers_escrow_release_private_key(release_key, monkeypatch):
    monkeypatch.setenv("ESCROW_RELEASE_PRIVATE_KEY", release_key)
    monkeypatch.setenv("GENESIS_WALLET_PRIVATE_KEY", "0x1111111111111111111111111111111111111111111111111111111111111111")

    escrow_routes = _reload_routes()
    assert escrow_routes._get_settlement_key() == release_key


def test_settlement_key_falls_back_to_genesis(monkeypatch):
    genesis_key = "0x1111111111111111111111111111111111111111111111111111111111111111"
    monkeypatch.delenv("ESCROW_RELEASE_PRIVATE_KEY", raising=False)
    monkeypatch.setenv("GENESIS_WALLET_PRIVATE_KEY", genesis_key)

    escrow_routes = _reload_routes()
    assert escrow_routes._get_settlement_key() == genesis_key


# The address the deterministic ``release_key`` fixture actually controls.
RELEASE_KEY_ADDRESS = "0x1563915e194d8cfba1943570603f7606a3115508"
FOREIGN_ADDRESS = "0xaabbccddeeff00112233445566778899aabbccdd"
GENESIS_KEY = "0x1111111111111111111111111111111111111111111111111111111111111111"


def test_settlement_address_accepts_matching_explicit_address(release_key, monkeypatch):
    """An explicit address is honoured (and canonicalised) when the key matches it."""
    monkeypatch.setenv("ESCROW_RELEASE_PRIVATE_KEY", release_key)
    monkeypatch.setenv("ESCROW_RELEASE_ADDRESS", RELEASE_KEY_ADDRESS.upper().replace("0X", "0x"))
    monkeypatch.delenv("GENESIS_WALLET_PRIVATE_KEY", raising=False)

    escrow_routes = _reload_routes()
    assert escrow_routes._get_settlement_address() == RELEASE_KEY_ADDRESS


def test_settlement_address_rejects_mismatched_explicit_address(release_key, monkeypatch):
    """A from-address the signing key does not control would be rejected by the RPC (403)."""
    monkeypatch.setenv("ESCROW_RELEASE_PRIVATE_KEY", release_key)
    monkeypatch.setenv("ESCROW_RELEASE_ADDRESS", FOREIGN_ADDRESS)
    monkeypatch.delenv("GENESIS_WALLET_PRIVATE_KEY", raising=False)

    escrow_routes = _reload_routes()
    assert escrow_routes._get_settlement_address() is None


def test_settlement_address_rejects_address_without_matching_key(monkeypatch):
    """Half-configured node: address set, release key missing, so genesis would sign for it."""
    monkeypatch.delenv("ESCROW_RELEASE_PRIVATE_KEY", raising=False)
    monkeypatch.setenv("GENESIS_WALLET_PRIVATE_KEY", GENESIS_KEY)
    monkeypatch.setenv("ESCROW_RELEASE_ADDRESS", FOREIGN_ADDRESS)

    escrow_routes = _reload_routes()
    assert escrow_routes._get_settlement_address() is None


def test_settlement_address_none_without_any_key(monkeypatch):
    """Without a signing key there is nothing to settle with, address or not."""
    monkeypatch.setenv("ESCROW_RELEASE_ADDRESS", "ait1aabbccddeeff00112233445566778899aabbccdd")
    monkeypatch.delenv("ESCROW_RELEASE_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("GENESIS_WALLET_PRIVATE_KEY", raising=False)

    escrow_routes = _reload_routes()
    assert escrow_routes._get_settlement_address() is None


def test_settlement_address_derives_from_release_key(release_key, monkeypatch):
    monkeypatch.setenv("ESCROW_RELEASE_PRIVATE_KEY", release_key)
    monkeypatch.delenv("ESCROW_RELEASE_ADDRESS", raising=False)
    monkeypatch.delenv("GENESIS_WALLET_PRIVATE_KEY", raising=False)

    escrow_routes = _reload_routes()
    assert escrow_routes._get_settlement_address() == "0x1563915e194d8cfba1943570603f7606a3115508"


@pytest.mark.asyncio
async def test_submit_payment_tx_signs_with_settlement_key(release_key, monkeypatch):
    monkeypatch.setenv("ESCROW_RELEASE_PRIVATE_KEY", release_key)
    monkeypatch.setenv("GENESIS_WALLET_PRIVATE_KEY", "0x1111111111111111111111111111111111111111111111111111111111111111")
    monkeypatch.setenv("HUB_RPC_URL", "http://localhost:8202")
    monkeypatch.setenv("CHAIN_ID", "test-chain")

    escrow_routes = _reload_routes()
    from aitbc.crypto.crypto import derive_ethereum_address
    from aitbc.crypto.signature_recovery import canonical_address

    settlement_address = canonical_address(derive_ethereum_address(release_key))
    provider = "0x3333333333333333333333333333333333333333"
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"transaction_hash": "0xabc"}

    with patch.object(escrow_routes, "_create_account_if_missing", new_callable=AsyncMock) as mock_create, \
         patch.object(escrow_routes, "_resolve_chain_account", new_callable=AsyncMock) as mock_resolve, \
         patch.object(escrow_routes, "_get_account_nonce", new_callable=AsyncMock) as mock_nonce, \
         patch.object(escrow_routes.SharedHttpClient, "post", new_callable=AsyncMock, return_value=mock_response) as mock_post:

        mock_create.return_value = True
        mock_resolve.return_value = provider
        mock_nonce.return_value = 5

        tx_hash = await escrow_routes._submit_payment_tx(
            buyer="0x4444444444444444444444444444444444444444",
            provider=provider,
            amount=Decimal("1.0"),
            job_id="job-123",
            contract_id="contract-123",
        )

        assert tx_hash == "0xabc"
        sent_tx = mock_post.call_args.kwargs["json"]
        assert sent_tx["from"] == settlement_address
        assert sent_tx["type"] == "ESCROW_RELEASE"
        assert sent_tx["payload"]["buyer_escrow_addr"] == "0x4444444444444444444444444444444444444444"


@pytest.mark.asyncio
async def test_retried_release_builds_an_identical_transaction(release_key, monkeypatch):
    """A retry at the same nonce must hash identically so the mempool deduplicates it.

    Admission validates the nonce against the account, which has not advanced while a
    first attempt is still pending. Two non-identical transactions sharing that nonce
    would both be admitted and the provider paid twice.
    """
    monkeypatch.setenv("ESCROW_RELEASE_PRIVATE_KEY", release_key)
    monkeypatch.setenv("HUB_RPC_URL", "http://localhost:8202")
    monkeypatch.setenv("CHAIN_ID", "test-chain")

    escrow_routes = _reload_routes()
    provider = "0x3333333333333333333333333333333333333333"
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"transaction_hash": "0xabc"}

    sent = []
    with patch.object(escrow_routes, "_create_account_if_missing", new_callable=AsyncMock) as mock_create, \
         patch.object(escrow_routes, "_resolve_chain_account", new_callable=AsyncMock) as mock_resolve, \
         patch.object(escrow_routes, "_get_account_nonce", new_callable=AsyncMock) as mock_nonce, \
         patch.object(escrow_routes.SharedHttpClient, "post", new_callable=AsyncMock, return_value=mock_response) as mock_post:

        mock_create.return_value = True
        mock_resolve.return_value = provider
        mock_nonce.return_value = 5

        for _ in range(2):
            await escrow_routes._submit_payment_tx(
                buyer="0x4444444444444444444444444444444444444444",
                provider=provider,
                amount=Decimal("1.0"),
                job_id="job-123",
                contract_id="contract-123",
            )
            sent.append(mock_post.call_args.kwargs["json"])

    first, second = sent
    assert first == second, "retry produced a different transaction; the mempool cannot deduplicate it"
    assert first["signature"] == second["signature"]
    assert escrow_routes._compute_tx_signing_hash(first) == escrow_routes._compute_tx_signing_hash(second)
    assert "released_at" not in first["payload"]
