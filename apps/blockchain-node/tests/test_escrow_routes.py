"""Tests for escrow RPC settlement key handling."""

import importlib
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
RELEASE_KEY_ADDRESS = "0x1563915e194D8CfBA1943570603F7606A3115508"
FOREIGN_ADDRESS = "0xAAbbCCDdeEFf00112233445566778899aABBcCDd"
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
    monkeypatch.setenv("ESCROW_RELEASE_ADDRESS", "0x0000000000000000000000000000000000000000")
    monkeypatch.delenv("ESCROW_RELEASE_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("GENESIS_WALLET_PRIVATE_KEY", raising=False)

    escrow_routes = _reload_routes()
    assert escrow_routes._get_settlement_address() is None


def test_settlement_address_derives_from_release_key(release_key, monkeypatch):
    monkeypatch.setenv("ESCROW_RELEASE_PRIVATE_KEY", release_key)
    monkeypatch.delenv("ESCROW_RELEASE_ADDRESS", raising=False)
    monkeypatch.delenv("GENESIS_WALLET_PRIVATE_KEY", raising=False)

    escrow_routes = _reload_routes()
    assert escrow_routes._get_settlement_address() == "0x1563915e194D8CfBA1943570603F7606A3115508"


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

    with (
        patch.object(escrow_routes, "_create_account_if_missing", new_callable=AsyncMock) as mock_create,
        patch.object(escrow_routes, "_find_existing_release", new_callable=AsyncMock, return_value=None),
        patch.object(escrow_routes, "_resolve_chain_account", new_callable=AsyncMock) as mock_resolve,
        patch.object(escrow_routes, "_get_account_nonce", new_callable=AsyncMock) as mock_nonce,
        patch.object(escrow_routes.SharedHttpClient, "post", new_callable=AsyncMock, return_value=mock_response) as mock_post,
    ):
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
    with (
        patch.object(escrow_routes, "_create_account_if_missing", new_callable=AsyncMock) as mock_create,
        patch.object(escrow_routes, "_find_existing_release", new_callable=AsyncMock, return_value=None),
        patch.object(escrow_routes, "_resolve_chain_account", new_callable=AsyncMock) as mock_resolve,
        patch.object(escrow_routes, "_get_account_nonce", new_callable=AsyncMock) as mock_nonce,
        patch.object(escrow_routes.SharedHttpClient, "post", new_callable=AsyncMock, return_value=mock_response) as mock_post,
    ):
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


@pytest.mark.asyncio
async def test_submit_payment_tx_skips_already_settled_job(release_key, monkeypatch):
    """A job that already settled must return the existing hash, not pay again."""
    monkeypatch.setenv("ESCROW_RELEASE_PRIVATE_KEY", release_key)
    monkeypatch.setenv("HUB_RPC_URL", "http://localhost:8202")
    monkeypatch.setenv("CHAIN_ID", "test-chain")

    escrow_routes = _reload_routes()

    with (
        patch.object(escrow_routes, "_find_existing_release", new_callable=AsyncMock, return_value="0xalready") as mock_lookup,
        patch.object(escrow_routes.SharedHttpClient, "post", new_callable=AsyncMock) as mock_post,
    ):
        tx_hash = await escrow_routes._submit_payment_tx(
            buyer="0x4444444444444444444444444444444444444444",
            provider="0x3333333333333333333333333333333333333333",
            amount=Decimal("1.0"),
            job_id="job-123",
            contract_id="contract-123",
        )

    assert tx_hash == "0xalready"
    mock_lookup.assert_awaited_once()
    mock_post.assert_not_awaited(), "a settled job must not be paid a second time"


@pytest.mark.asyncio
async def test_find_existing_release_matches_on_job_id(monkeypatch):
    """The lookup matches the job_id carried in the ESCROW_RELEASE payload."""
    monkeypatch.setenv("HUB_RPC_URL", "http://localhost:8202")
    escrow_routes = _reload_routes()

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {"tx_hash": "0xother", "payload": {"job_id": "job-999"}},
        {"tx_hash": "0xmine", "payload": {"job_id": "job-123"}},
    ]

    with patch.object(escrow_routes.SharedHttpClient, "get", new_callable=AsyncMock, return_value=mock_response):
        assert await escrow_routes._find_existing_release("job-123") == "0xmine"
        assert await escrow_routes._find_existing_release("job-absent") is None


@pytest.mark.asyncio
async def test_find_existing_release_is_quiet_when_the_rpc_is_unreachable(monkeypatch):
    """A lookup failure must not be mistaken for 'already settled'."""
    monkeypatch.setenv("HUB_RPC_URL", "http://localhost:8202")
    escrow_routes = _reload_routes()

    with patch.object(
        escrow_routes.SharedHttpClient, "get", new_callable=AsyncMock, side_effect=RuntimeError("connection refused")
    ):
        assert await escrow_routes._find_existing_release("job-123") is None


@pytest.mark.asyncio
async def test_find_existing_release_filters_server_side(monkeypatch):
    """The lookup must ask the RPC to filter by job_id, not scan and filter locally.

    /transactions returns rows oldest-first and truncates to `limit`, so an unfiltered
    scan silently misses recent settlements -- the ones a retry asks about. Missing one
    means resubmitting at the next nonce and paying the provider twice.
    """
    monkeypatch.setenv("HUB_RPC_URL", "http://localhost:8202")
    escrow_routes = _reload_routes()

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = []

    with patch.object(escrow_routes.SharedHttpClient, "get", new_callable=AsyncMock, return_value=mock_response) as mock_get:
        await escrow_routes._find_existing_release("job-123")

    url = mock_get.call_args.args[0]
    assert "job_id=job-123" in url
    assert "transaction_type=ESCROW_RELEASE" in url


def test_build_lock_tx_rejects_node_wallet_as_provider(monkeypatch):
    """A lock whose provider is the node wallet would pay the operator, not a miner."""
    monkeypatch.setenv("NODE_WALLET_ADDRESS", "0x1111111111111111111111111111111111111111")
    monkeypatch.setenv("CHAIN_ID", "test-chain")

    escrow_routes = _reload_routes()
    with pytest.raises(ValueError, match="provider"):
        escrow_routes._build_lock_tx(
            job_id="job-123",
            buyer="0x2222222222222222222222222222222222222222",
            provider="0x1111111111111111111111111111111111111111",
            amount_dec=Decimal("1.0"),
            nonce=0,
        )


@pytest.mark.asyncio
async def test_submit_payment_tx_refuses_unresolvable_provider(release_key, monkeypatch):
    """A release whose provider cannot be resolved must not fall back to the node wallet."""
    monkeypatch.setenv("ESCROW_RELEASE_PRIVATE_KEY", release_key)
    monkeypatch.setenv("HUB_RPC_URL", "http://localhost:8202")
    monkeypatch.setenv("CHAIN_ID", "test-chain")

    escrow_routes = _reload_routes()

    with (
        patch.object(escrow_routes, "_create_account_if_missing", new_callable=AsyncMock, return_value=True),
        patch.object(escrow_routes, "_find_existing_release", new_callable=AsyncMock, return_value=None),
        patch.object(escrow_routes, "_resolve_chain_account", new_callable=AsyncMock, return_value=None),
        patch.object(escrow_routes.SharedHttpClient, "post", new_callable=AsyncMock) as mock_post,
    ):
        tx_hash = await escrow_routes._submit_payment_tx(
            buyer="0x4444444444444444444444444444444444444444",
            provider="0x3333333333333333333333333333333333333333",
            amount=Decimal("1.0"),
            job_id="job-123",
            contract_id="contract-123",
        )

    assert tx_hash is None
    mock_post.assert_not_awaited()


@pytest.mark.asyncio
async def test_submit_refund_tx_refuses_node_wallet_buyer(release_key, monkeypatch):
    """Refunding the node wallet is a custody bug and must be refused."""
    monkeypatch.setenv("ESCROW_RELEASE_PRIVATE_KEY", release_key)
    monkeypatch.setenv("NODE_WALLET_ADDRESS", "0x1111111111111111111111111111111111111111")
    monkeypatch.setenv("HUB_RPC_URL", "http://localhost:8202")
    monkeypatch.setenv("CHAIN_ID", "test-chain")

    escrow_routes = _reload_routes()

    tx_hash = await escrow_routes._submit_refund_tx(
        buyer="0x1111111111111111111111111111111111111111",
        provider="0x2222222222222222222222222222222222222222",
        amount=Decimal("1.0"),
        job_id="job-123",
        contract_id="contract-123",
    )

    assert tx_hash is None


@pytest.mark.asyncio
async def test_submit_refund_tx_refuses_unresolvable_buyer(release_key, monkeypatch):
    """A refund whose buyer cannot be resolved must not be submitted."""
    monkeypatch.setenv("ESCROW_RELEASE_PRIVATE_KEY", release_key)
    monkeypatch.setenv("NODE_WALLET_ADDRESS", "0x1111111111111111111111111111111111111111")
    monkeypatch.setenv("HUB_RPC_URL", "http://localhost:8202")
    monkeypatch.setenv("CHAIN_ID", "test-chain")

    escrow_routes = _reload_routes()

    with patch.object(escrow_routes, "_resolve_chain_account", new_callable=AsyncMock, return_value=None):
        tx_hash = await escrow_routes._submit_refund_tx(
            buyer="0x3333333333333333333333333333333333333333",
            provider="0x2222222222222222222222222222222222222222",
            amount=Decimal("1.0"),
            job_id="job-123",
            contract_id="contract-123",
        )

    assert tx_hash is None


@pytest.mark.asyncio
async def test_submit_refund_tx_re_raises_on_submission_failure(release_key, monkeypatch):
    """A transport or unexpected failure during refund submission must propagate, not be swallowed."""
    monkeypatch.setenv("ESCROW_RELEASE_PRIVATE_KEY", release_key)
    monkeypatch.setenv("NODE_WALLET_ADDRESS", "0x1111111111111111111111111111111111111111")
    monkeypatch.setenv("HUB_RPC_URL", "http://localhost:8202")
    monkeypatch.setenv("CHAIN_ID", "test-chain")

    escrow_routes = _reload_routes()

    with (
        patch.object(escrow_routes, "_create_account_if_missing", new_callable=AsyncMock, return_value=True),
        patch.object(escrow_routes, "_find_existing_refund", new_callable=AsyncMock, return_value=None),
        patch.object(
            escrow_routes,
            "_resolve_chain_account",
            new_callable=AsyncMock,
            return_value="0x3333333333333333333333333333333333333333",
        ),
        patch.object(escrow_routes, "_get_account_nonce", new_callable=AsyncMock, return_value=5),
        patch.object(escrow_routes.SharedHttpClient, "post", new_callable=AsyncMock, side_effect=RuntimeError("RPC down")),
    ):
        with pytest.raises(RuntimeError, match="RPC down"):
            await escrow_routes._submit_refund_tx(
                buyer="0x3333333333333333333333333333333333333333",
                provider="0x2222222222222222222222222222222222222222",
                amount=Decimal("1.0"),
                job_id="job-123",
                contract_id="contract-123",
            )
