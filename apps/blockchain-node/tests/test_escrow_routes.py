"""Tests for escrow RPC settlement key handling."""

import importlib
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


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
        patch.object(escrow_routes, "_find_existing_release", new_callable=AsyncMock, return_value=None),
        patch.object(escrow_routes, "_resolve_chain_account", new_callable=AsyncMock) as mock_resolve,
        patch.object(escrow_routes, "_get_account_nonce", new_callable=AsyncMock) as mock_nonce,
        patch.object(escrow_routes.SharedHttpClient, "post", new_callable=AsyncMock, return_value=mock_response) as mock_post,
    ):
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
        patch.object(escrow_routes, "_find_existing_release", new_callable=AsyncMock, return_value=None),
        patch.object(escrow_routes, "_resolve_chain_account", new_callable=AsyncMock) as mock_resolve,
        patch.object(escrow_routes, "_get_account_nonce", new_callable=AsyncMock) as mock_nonce,
        patch.object(escrow_routes.SharedHttpClient, "post", new_callable=AsyncMock, return_value=mock_response) as mock_post,
    ):
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


# --- v11: ESCROW_FEE_SWEEP post-settlement leg --------------------------------

# Obviously synthetic recipient — the real treasury address is designated at
# deploy time and must never appear in the repo. The wire form is the EIP-55
# canonicalisation of this literal.
from aitbc.crypto.signature_recovery import canonical_address as _canonical

FEE_SWEEP_RECIPIENT_RAW = "0x" + "ee" * 20
FEE_SWEEP_RECIPIENT = _canonical(FEE_SWEEP_RECIPIENT_RAW)


def _enable_fee_sweep(monkeypatch, release_key):
    monkeypatch.setenv("ESCROW_FEE_SWEEP_ENABLED", "1")
    monkeypatch.setenv("ESCROW_FEE_RECIPIENT", FEE_SWEEP_RECIPIENT_RAW)
    monkeypatch.setenv("ESCROW_RELEASE_PRIVATE_KEY", release_key)
    monkeypatch.delenv("ESCROW_RELEASE_ADDRESS", raising=False)
    monkeypatch.delenv("GENESIS_WALLET_PRIVATE_KEY", raising=False)
    monkeypatch.setenv("HUB_RPC_URL", "http://localhost:8202")
    monkeypatch.setenv("CHAIN_ID", "test-chain")
    return _reload_routes()


@pytest.mark.asyncio
async def test_fee_sweep_disabled_by_default(release_key, monkeypatch):
    """The probe's failing half: with the flag unset the sweep must not be
    submitted even when every other input is configured."""
    monkeypatch.delenv("ESCROW_FEE_SWEEP_ENABLED", raising=False)
    monkeypatch.setenv("ESCROW_FEE_RECIPIENT", FEE_SWEEP_RECIPIENT)
    monkeypatch.setenv("ESCROW_RELEASE_PRIVATE_KEY", release_key)
    monkeypatch.setenv("HUB_RPC_URL", "http://localhost:8202")
    escrow_routes = _reload_routes()

    with patch.object(escrow_routes.SharedHttpClient, "post", new_callable=AsyncMock) as mock_post:
        result = await escrow_routes._retry_sweep_released_escrow("job-123", _released_record(), None)

    assert result is None
    mock_post.assert_not_awaited()


@pytest.mark.asyncio
async def test_fee_sweep_submits_residue_to_configured_recipient(release_key, monkeypatch):
    """The passing half: flag on, recipient configured — the sweep drains the
    given residue to the fee recipient, authority-signed."""
    escrow_routes = _enable_fee_sweep(monkeypatch, release_key)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"transaction_hash": "0xsweep"}

    with (
        patch.object(escrow_routes, "_find_existing_fee_sweep", new_callable=AsyncMock, return_value=None),
        patch.object(escrow_routes, "_get_account_nonce", new_callable=AsyncMock, return_value=7),
        patch.object(escrow_routes.SharedHttpClient, "post", new_callable=AsyncMock, return_value=mock_response) as mock_post,
    ):
        tx_hash = await escrow_routes._submit_fee_sweep_tx("job-123", "contract-123", 20_000)

    assert tx_hash == "0xsweep"
    sent_tx = mock_post.call_args.kwargs["json"]
    assert sent_tx["type"] == "ESCROW_FEE_SWEEP"
    assert sent_tx["to"] == FEE_SWEEP_RECIPIENT
    assert sent_tx["amount"] == 20_000
    assert sent_tx["nonce"] == 7
    assert sent_tx["payload"]["job_id"] == "job-123"
    assert sent_tx["from"] == RELEASE_KEY_ADDRESS
    assert sent_tx["signature"]


@pytest.mark.asyncio
async def test_fee_sweep_skips_when_no_residue(release_key, monkeypatch):
    """A settlement whose legs claim the whole lock has nothing to sweep."""
    escrow_routes = _enable_fee_sweep(monkeypatch, release_key)

    with patch.object(escrow_routes.SharedHttpClient, "post", new_callable=AsyncMock) as mock_post:
        result = await escrow_routes._submit_fee_sweep_tx("job-123", "contract-123", 0)

    assert result is None
    mock_post.assert_not_awaited()


@pytest.mark.asyncio
async def test_fee_sweep_failure_never_raises(release_key, monkeypatch):
    """The release is authoritative: a rejected or crashed sweep submission is
    logged, counted in the metric, and returns None — never raised."""
    escrow_routes = _enable_fee_sweep(monkeypatch, release_key)

    from aitbc_chain.metrics import escrow_fee_sweep_total

    rejected = MagicMock()
    rejected.status_code = 400
    rejected.text = "admission refused"
    baseline_rejected = escrow_fee_sweep_total.labels(result="rejected")._value.get()
    baseline_error = escrow_fee_sweep_total.labels(result="error")._value.get()

    with (
        patch.object(escrow_routes, "_find_existing_fee_sweep", new_callable=AsyncMock, return_value=None),
        patch.object(escrow_routes, "_get_account_nonce", new_callable=AsyncMock, return_value=7),
        patch.object(escrow_routes.SharedHttpClient, "post", new_callable=AsyncMock, return_value=rejected),
    ):
        assert await escrow_routes._submit_fee_sweep_tx("job-1", "contract-1", 5_000) is None

    with (
        patch.object(escrow_routes, "_find_existing_fee_sweep", new_callable=AsyncMock, return_value=None),
        patch.object(escrow_routes, "_get_account_nonce", new_callable=AsyncMock, return_value=7),
        patch.object(escrow_routes.SharedHttpClient, "post", new_callable=AsyncMock, side_effect=RuntimeError("down")),
    ):
        assert await escrow_routes._submit_fee_sweep_tx("job-1", "contract-1", 5_000) is None

    assert escrow_fee_sweep_total.labels(result="rejected")._value.get() == baseline_rejected + 1
    assert escrow_fee_sweep_total.labels(result="error")._value.get() == baseline_error + 1


@pytest.mark.asyncio
async def test_fee_sweep_skips_when_recipient_unset(release_key, monkeypatch):
    """Fail closed at the signer too: with no ESCROW_FEE_RECIPIENT the tx is
    never built — consensus would refuse it anyway."""
    monkeypatch.setenv("ESCROW_FEE_SWEEP_ENABLED", "1")
    monkeypatch.delenv("ESCROW_FEE_RECIPIENT", raising=False)
    monkeypatch.setenv("ESCROW_RELEASE_PRIVATE_KEY", release_key)
    monkeypatch.setenv("HUB_RPC_URL", "http://localhost:8202")
    escrow_routes = _reload_routes()

    with (
        patch.object(escrow_routes, "_find_existing_fee_sweep", new_callable=AsyncMock, return_value=None),
        patch.object(escrow_routes.SharedHttpClient, "post", new_callable=AsyncMock) as mock_post,
    ):
        assert await escrow_routes._submit_fee_sweep_tx("job-1", "contract-1", 5_000) is None

    mock_post.assert_not_awaited()


@pytest.mark.asyncio
async def test_fee_sweep_dedupes_settled_jobs(release_key, monkeypatch):
    """A job whose sweep already sealed returns the existing hash — the retry
    surface can offer the leg on every call without double-sweeping."""
    escrow_routes = _enable_fee_sweep(monkeypatch, release_key)

    with (
        patch.object(escrow_routes, "_find_existing_fee_sweep", new_callable=AsyncMock, return_value="0xswept"),
        patch.object(escrow_routes.SharedHttpClient, "post", new_callable=AsyncMock) as mock_post,
    ):
        tx_hash = await escrow_routes._submit_fee_sweep_tx("job-1", "contract-1", 5_000)

    assert tx_hash == "0xswept"
    mock_post.assert_not_awaited()


def _released_record(**overrides):
    from aitbc_chain.models import Escrow

    record = Escrow(
        job_id="job-1",
        chain_id="test-chain",
        buyer="0x" + "66" * 20,
        provider="0x" + "77" * 20,
        amount=1_000_000,
        released_amount=920_000,
        refunded_amount=75_000,
    )
    for key, value in overrides.items():
        setattr(record, key, value)
    return record


@pytest.mark.asyncio
async def test_retry_path_sweeps_only_the_proven_residue(release_key, monkeypatch):
    """Retry: custody balance must equal lock − sealed releases − sealed
    refunds exactly — the design's equality check. A balance above it means
    an owed leg is still pending; the job is skipped, never guessed."""
    escrow_routes = _enable_fee_sweep(monkeypatch, release_key)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"transaction_hash": "0xsweep"}

    # bps=800: release 920_000 = billed 1_000_000·0.92 → withheld bound 80_000
    record = _released_record(
        energy_fee_basis_points=800,
        billed_legs=[{"tx_hash": "0xrel", "billed": 1_000_000}],
    )  # residue = 1_000_000 − 920_000 − 75_000 = 5_000
    legs = {
        "locked_amount": 1_000_000,
        "released_amount": 920_000,
        "refunded_amount": 75_000,
        "release_values": [920_000],
        "release_legs": [{"tx_hash": "0xrel", "value": 920_000}],
        "min_settlement_height": 36000,
    }

    # Legs fully sealed: custody holds exactly the residue.
    with (
        patch("aitbc_chain.contracts.escrow.settlement_legs_from_chain", return_value=legs),
        patch.object(escrow_routes, "_escrow_custody_balance", new_callable=AsyncMock, return_value=5_000),
        patch.object(escrow_routes, "_find_existing_fee_sweep", new_callable=AsyncMock, return_value=None),
        patch.object(escrow_routes, "_get_account_nonce", new_callable=AsyncMock, return_value=9),
        patch.object(escrow_routes.SharedHttpClient, "post", new_callable=AsyncMock, return_value=mock_response) as mock_post,
    ):
        assert await escrow_routes._retry_sweep_released_escrow("job-1", record, None) == "0xsweep"
    assert mock_post.call_args.kwargs["json"]["amount"] == 5_000

    # An owed leg still pending: custody holds residue + unbilled change.
    with (
        patch("aitbc_chain.contracts.escrow.settlement_legs_from_chain", return_value=legs),
        patch.object(escrow_routes, "_escrow_custody_balance", new_callable=AsyncMock, return_value=85_000),
        patch.object(escrow_routes.SharedHttpClient, "post", new_callable=AsyncMock) as mock_post,
    ):
        assert await escrow_routes._retry_sweep_released_escrow("job-1", record, None) is None
    mock_post.assert_not_awaited()

    # Custody unprovable: skipped.
    with (
        patch("aitbc_chain.contracts.escrow.settlement_legs_from_chain", return_value=legs),
        patch.object(escrow_routes, "_escrow_custody_balance", new_callable=AsyncMock, return_value=None),
        patch.object(escrow_routes.SharedHttpClient, "post", new_callable=AsyncMock) as mock_post,
    ):
        assert await escrow_routes._retry_sweep_released_escrow("job-1", record, None) is None
    mock_post.assert_not_awaited()


@pytest.mark.asyncio
async def test_retry_skips_when_chain_shows_no_sealed_legs(release_key, monkeypatch):
    """No sealed settlement legs → nothing to derive a residue from; the
    sweep defers regardless of what the row claims."""
    escrow_routes = _enable_fee_sweep(monkeypatch, release_key)
    record = _released_record()

    with (
        patch("aitbc_chain.contracts.escrow.settlement_legs_from_chain", return_value=None),
        patch.object(escrow_routes.SharedHttpClient, "post", new_callable=AsyncMock) as mock_post,
    ):
        assert await escrow_routes._retry_sweep_released_escrow("job-1", record, None) is None
    mock_post.assert_not_awaited()


@pytest.mark.asyncio
async def test_retry_unpoisoned_by_unsealed_row_refund(release_key, monkeypatch):
    """F2 companion: a refund the row claims but that never sealed cannot
    inflate or veto the residue — the sealed legs are the only evidence."""
    escrow_routes = _enable_fee_sweep(monkeypatch, release_key)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"transaction_hash": "0xsweep"}
    # Row claims a refund that never sealed; the chain shows only the release.
    record = _released_record(
        refunded_amount=75_000,
        refund_tx_hash="0xphantom",
        energy_fee_basis_points=800,
        billed_legs=[{"tx_hash": "0xrel", "billed": 1_000_000}],
    )
    legs = {
        "locked_amount": 1_000_000,
        "released_amount": 920_000,
        "refunded_amount": 0,
        "release_values": [920_000],
        "release_legs": [{"tx_hash": "0xrel", "value": 920_000}],
        "min_settlement_height": 36000,
    }

    with (
        patch("aitbc_chain.contracts.escrow.settlement_legs_from_chain", return_value=legs),
        patch.object(escrow_routes, "_escrow_custody_balance", new_callable=AsyncMock, return_value=80_000),
        patch.object(escrow_routes, "_find_existing_fee_sweep", new_callable=AsyncMock, return_value=None),
        patch.object(escrow_routes.SharedHttpClient, "post", new_callable=AsyncMock, return_value=mock_response) as mock_post,
    ):
        assert await escrow_routes._retry_sweep_released_escrow("job-1", record, None) == "0xsweep"
    assert mock_post.call_args.kwargs["json"]["amount"] == 80_000


@pytest.mark.asyncio
async def test_submit_refund_tx_re_raises_on_submission_failure(release_key, monkeypatch):
    """A transport or unexpected failure during refund submission must propagate, not be swallowed."""
    monkeypatch.setenv("ESCROW_RELEASE_PRIVATE_KEY", release_key)
    monkeypatch.setenv("NODE_WALLET_ADDRESS", "0x1111111111111111111111111111111111111111")
    monkeypatch.setenv("HUB_RPC_URL", "http://localhost:8202")
    monkeypatch.setenv("CHAIN_ID", "test-chain")

    escrow_routes = _reload_routes()

    with (
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


# ---------------------------------------------------------------------------
# Task C2 desired-behavior contracts — xfail(strict): these FAIL on current
# main (that is the point of the review) and flip when the multi-leg nonce
# fix lands. Design: TOPOLOGY/2026-10-05-multileg-nonce-design.md.
# ---------------------------------------------------------------------------


def _locked_contract(released: str = "0.6", locked: str = "1.0"):
    """Minimal EscrowContract stand-in for release_escrow(): milestones,
    parties, and the released_amount the manager stamps."""
    from types import SimpleNamespace

    return SimpleNamespace(
        milestones=[{"amount": locked}],
        state=None,
        released_amount=Decimal(released),
        client_address="0x" + "66" * 20,
        agent_address="0x" + "77" * 20,
        fee_rate=Decimal("0.025"),
    )


def _release_drive_mocks(escrow_routes, *, unsealed=True, expose: dict | None = None):
    """Patch the module surface release_escrow() touches so a partial
    settle (release + change refund owed) can be driven without a DB or
    network. ``unsealed=True`` means the release's sealed lookup never
    returns — the multi-leg fix must not let later legs sign while the
    release is still pending."""
    import contextlib
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock, patch

    mgr = MagicMock()
    contract = _locked_contract()
    mgr.escrow_contracts = {"c1": contract}
    mgr.snapshot_release_state = MagicMock(return_value={})
    mgr.release_payment = AsyncMock(return_value=(True, "ok"))
    mgr.restore_after_failed_settlement = MagicMock()

    @contextlib.asynccontextmanager
    async def _lock(_contract_id):
        yield

    mgr.release_lock = _lock

    record = SimpleNamespace(
        job_id="job-1",
        contract_id="c1",
        status="locked",
        protected=False,
        released_at=None,
        refunded_at=None,
        released_amount=None,
        refunded_amount=None,
        amount=1_000_000,
        release_tx_hash=None,
        refund_tx_hash=None,
        job_tx_hash=None,
        energy_settlement_asset=None,
        energy_settlement_unit_scale=None,
        energy_fee_basis_points=None,
        energy_provider_credit_units=None,
        energy_net_floor_units=None,
        billed_legs=None,
    )
    session = MagicMock()
    session.get = MagicMock(return_value=record)
    if expose is not None:
        expose["record"] = record
        expose["contract"] = contract
        expose["session"] = session

    @contextlib.contextmanager
    def _session_scope():
        yield session

    return (
        patch.object(escrow_routes, "get_escrow_manager", return_value=mgr),
        patch.object(escrow_routes, "_get_settlement_key", return_value="0xkey"),
        patch.object(escrow_routes, "_get_settlement_address", return_value="0xaddr"),
        patch.object(escrow_routes, "session_scope", _session_scope),
        patch.object(escrow_routes, "backfill_settlement_legs", MagicMock(return_value=False)),
        patch.object(escrow_routes, "_find_contract_id", new_callable=AsyncMock, return_value="c1"),
        patch.object(escrow_routes, "_ensure_lock_sealed", new_callable=AsyncMock),
        patch.object(escrow_routes, "_refuse_v2_lock", new_callable=AsyncMock),
        patch.object(escrow_routes, "_submit_payment_tx", new_callable=AsyncMock, return_value="0xrel"),
        patch.object(
            escrow_routes,
            "_find_existing_release",
            new_callable=AsyncMock,
            return_value=None if unsealed else "0xrel",
        ),
    )


@pytest.mark.asyncio
async def test_release_leaves_change_leg_to_sweeper(release_key, monkeypatch):
    """A6/F1b: a partial settle never signs the change leg in-request — the
    route submits only the release, returns fast, and reports the owed change
    explicitly for the settlement sweeper's change pass."""
    monkeypatch.setenv("ESCROW_RELEASE_PRIVATE_KEY", release_key)
    monkeypatch.setenv("HUB_RPC_URL", "http://localhost:8202")
    monkeypatch.setenv("CHAIN_ID", "test-chain")
    escrow_routes = _reload_routes()
    mocks = _release_drive_mocks(escrow_routes, unsealed=True)
    refund_spy = AsyncMock(return_value="0xref")

    import contextlib

    with (
        contextlib.ExitStack() as stack,
        patch.object(escrow_routes, "_submit_refund_tx", refund_spy),
    ):
        for m in mocks:
            stack.enter_context(m)
        result = await escrow_routes.release_escrow("job-1", {"amount": "0.6"})

    refund_spy.assert_not_awaited()
    assert result["change_owed_amount"] == "0.4"
    assert result["refunded_amount"] == "0"
    assert result["refund_tx_hash"] is None
    assert result["tx_hash"] == "0xrel"


@pytest.mark.asyncio
async def test_release_quantizes_sub_unit_amount(release_key, monkeypatch):
    """A7d: sub-compute-unit precision is what the real CLI sends
    (``str(Decimal(tokens)/1000 * price)`` — e.g. 1234 tokens at 0.0073
    AIT/1k = 0.0090082 AIT = 324295.2 units). The route quantizes to whole
    units ROUND_HALF_UP and signs the integer-derived leg, so the sealed
    value and the recorded billed prove under recompute — no 422, no wedge.
    """
    from aitbc_chain.contracts.escrow import recompute_release_proofs
    from aitbc.utils.units import ait_to_units

    monkeypatch.setenv("ESCROW_RELEASE_PRIVATE_KEY", release_key)
    monkeypatch.setenv("HUB_RPC_URL", "http://localhost:8202")
    monkeypatch.setenv("CHAIN_ID", "test-chain")
    escrow_routes = _reload_routes()
    expose: dict = {}
    mocks = _release_drive_mocks(escrow_routes, unsealed=True, expose=expose)
    submit_spy = AsyncMock(return_value="0xrel")

    import contextlib

    with contextlib.ExitStack() as stack:
        for m in mocks:
            stack.enter_context(m)
        # Entered last so this spy (not the helper's patch) captures the amount.
        stack.enter_context(patch.object(escrow_routes, "_submit_payment_tx", submit_spy))
        # The CLI's real shape: Decimal("1234")/1000 * Decimal("0.0073")
        result = await escrow_routes.release_escrow("job-1", {"amount": "0.0090082"})

    assert result["tx_hash"] == "0xrel"
    # ROUND_HALF_UP(324295.2) = 324295 billed units, recorded under the leg's hash.
    assert expose["record"].billed_legs == [{"tx_hash": "0xrel", "billed": 324295}]
    # The sealed leg: ait_to_units(units_to_ait(E)) round-trips to E exactly.
    sealed_ait = submit_spy.await_args.args[2]
    sealed_units = ait_to_units(sealed_ait)
    # round_half_up(324295 * 0.975) = round_half_up(316187.625) = 316188.
    assert sealed_units == 316188
    # End-to-end: the sealed leg + recorded billed prove under recompute.
    proof = recompute_release_proofs(
        [{"tx_hash": "0xrel", "value": sealed_units}],
        expose["record"].billed_legs,
        fee_bps=250,
        protected=False,
        credit_units=None,
        net_floor_units=None,
        lock_units=1_000_000,
    )
    # proof = (billed_total, withheld_total): the sealed leg pays billed−fee.
    assert proof == (324295, 324295 - sealed_units)


def test_sealed_release_units_match_recompute_sweep():
    """A7d sweep: for every billed N in the boundary window — including every
    exact .5 rounding tie (N·(10000−bps) ≡ 5000 mod 10000) — the value the
    route signs (``ait_to_units(units_to_ait(E))``) equals what
    ``recompute_release_proofs`` derives, for protected and unprotected rows."""
    from aitbc_chain.contracts.escrow import expected_release_units, recompute_release_proofs
    from aitbc.utils.units import ait_to_units, units_to_ait

    tie_hits = 0
    for bps in (0, 1, 250, 9999):
        for billed in range(1, 40001):
            for protected, credit in ((False, None), (True, None), (True, billed)):
                expected = expected_release_units(billed, fee_bps=bps, protected=protected, credit_units=credit)
                # What the route signs: quantized AIT -> tx amount units.
                sealed = max(ait_to_units(units_to_ait(expected)), 1)
                proof = recompute_release_proofs(
                    [{"tx_hash": "0xrel", "value": sealed}],
                    [{"tx_hash": "0xrel", "billed": billed}],
                    fee_bps=bps,
                    protected=protected,
                    credit_units=credit,
                    net_floor_units=None,
                    lock_units=billed + 1_000_000,
                )
                assert proof is not None, (bps, billed, protected, credit, sealed)
                assert proof == (billed, billed - sealed)
            if billed * (10000 - bps) % 10000 == 5000:
                tie_hits += 1
    # The sweep actually exercised exact .5 ties — the boundary the Decimal
    # AIT path could cross in the wrong direction.
    assert tie_hits > 0


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["NaN", "sNaN", "Infinity", "-Infinity"])
async def test_release_rejects_non_finite_amount(release_key, monkeypatch, bad):
    """A7e: non-finite decimals must never reach a comparison or the unit
    conversion — NaN <= 0 raises InvalidOperation and Infinity raises in
    ait_to_units, so they were (or became) 500s. Refuse with 400 up front."""
    monkeypatch.setenv("ESCROW_RELEASE_PRIVATE_KEY", release_key)
    monkeypatch.setenv("HUB_RPC_URL", "http://localhost:8202")
    monkeypatch.setenv("CHAIN_ID", "test-chain")
    escrow_routes = _reload_routes()

    import contextlib

    with contextlib.ExitStack() as stack:
        for m in _release_drive_mocks(escrow_routes, unsealed=True):
            stack.enter_context(m)
        with pytest.raises(HTTPException) as exc:
            await escrow_routes.release_escrow("job-1", {"amount": bad})
        assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_release_refuses_protected_contract_without_row(release_key, monkeypatch):
    """A7e/L3: a cached protected contract whose escrow row cannot be read
    must not sign — the leg would drop the credit bump and wedge the row
    unproven while underpaying the signed credit."""
    monkeypatch.setenv("ESCROW_RELEASE_PRIVATE_KEY", release_key)
    monkeypatch.setenv("HUB_RPC_URL", "http://localhost:8202")
    monkeypatch.setenv("CHAIN_ID", "test-chain")
    escrow_routes = _reload_routes()
    expose: dict = {}
    mocks = _release_drive_mocks(escrow_routes, unsealed=True, expose=expose)

    import contextlib

    with contextlib.ExitStack() as stack:
        for m in mocks:
            stack.enter_context(m)
        # Contract is cached and protected; the row read fails.
        expose["contract"].protected = True
        expose["session"].get = MagicMock(return_value=None)
        with pytest.raises(HTTPException) as exc:
            await escrow_routes.release_escrow("job-1", {"amount": "0.6"})
        assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_unprotected_row_ignores_stale_fee_basis_points(release_key, monkeypatch):
    """A7e/L2: the contract only honors energy_fee_basis_points on protected
    rows — an unprotected row carrying bps=0 must still bill the default
    250, and the signed leg must match."""
    from aitbc.utils.units import ait_to_units

    monkeypatch.setenv("ESCROW_RELEASE_PRIVATE_KEY", release_key)
    monkeypatch.setenv("HUB_RPC_URL", "http://localhost:8202")
    monkeypatch.setenv("CHAIN_ID", "test-chain")
    escrow_routes = _reload_routes()
    expose: dict = {}
    mocks = _release_drive_mocks(escrow_routes, unsealed=True, expose=expose)
    submit_spy = AsyncMock(return_value="0xrel")

    import contextlib

    with contextlib.ExitStack() as stack:
        for m in mocks:
            stack.enter_context(m)
        stack.enter_context(patch.object(escrow_routes, "_submit_payment_tx", submit_spy))
        expose["record"].protected = False
        expose["record"].energy_fee_basis_points = 0
        result = await escrow_routes.release_escrow("job-1", {"amount": "0.6"})

    assert result["tx_hash"] == "0xrel"
    sealed_units = ait_to_units(submit_spy.await_args.args[2])
    # billed 21600000 at default 250bps -> round_half_up(21060000.0)
    assert sealed_units == 21060000


@pytest.mark.asyncio
async def test_release_records_billed_gross_per_submission(release_key, monkeypatch):
    """A7: the route persists the billed gross it consumed, keyed by the
    release leg's hash — the settlement passes prove the sealed leg by
    recomputing the route's own fee rule from it, never by inversion."""
    from aitbc.utils.units import ait_to_units

    monkeypatch.setenv("ESCROW_RELEASE_PRIVATE_KEY", release_key)
    monkeypatch.setenv("HUB_RPC_URL", "http://localhost:8202")
    monkeypatch.setenv("CHAIN_ID", "test-chain")
    escrow_routes = _reload_routes()
    expose: dict = {}
    mocks = _release_drive_mocks(escrow_routes, unsealed=True, expose=expose)

    import contextlib

    with contextlib.ExitStack() as stack:
        for m in mocks:
            stack.enter_context(m)
        result = await escrow_routes.release_escrow("job-1", {"amount": "0.6"})

    assert result["tx_hash"] == "0xrel"
    # billed_gross = min(requested 0.6, locked 1.0) — recorded in units under
    # the submission's own hash; a same-hash dedup retry must not duplicate.
    assert expose["record"].billed_legs == [{"tx_hash": "0xrel", "billed": ait_to_units("0.6")}]


@pytest.mark.asyncio
async def test_release_never_signs_change_leg_even_when_release_sealed(release_key, monkeypatch):
    """A6/F1b companion: the route defers the change leg unconditionally —
    a sealed release changes nothing in-request; the change pass owns it."""
    monkeypatch.setenv("ESCROW_RELEASE_PRIVATE_KEY", release_key)
    monkeypatch.setenv("HUB_RPC_URL", "http://localhost:8202")
    monkeypatch.setenv("CHAIN_ID", "test-chain")
    escrow_routes = _reload_routes()
    mocks = _release_drive_mocks(escrow_routes, unsealed=False)
    refund_spy = AsyncMock(return_value="0xref")

    import contextlib

    with (
        contextlib.ExitStack() as stack,
        patch.object(escrow_routes, "_submit_refund_tx", refund_spy),
    ):
        for m in mocks:
            stack.enter_context(m)
        result = await escrow_routes.release_escrow("job-1", {"amount": "0.6"})

    refund_spy.assert_not_awaited()
    assert result["change_owed_amount"] == "0.4"
    assert result["refund_tx_hash"] is None


@pytest.mark.asyncio
async def test_release_retry_at_lock_cannot_reenter_submission(release_key, monkeypatch):
    """A6 re-entry proof: a caller retry that read the row before the first
    request committed proceeds to the per-contract lock, then sees the
    already-released contract — release_payment refuses and the handler dies
    BEFORE _submit_payment_tx or any restore. A restore can therefore only
    ever fire on the calling handler's own snapshot inside the lock."""
    monkeypatch.setenv("ESCROW_RELEASE_PRIVATE_KEY", release_key)
    monkeypatch.setenv("HUB_RPC_URL", "http://localhost:8202")
    monkeypatch.setenv("CHAIN_ID", "test-chain")
    escrow_routes = _reload_routes()

    import contextlib

    with contextlib.ExitStack() as stack:
        for m in _release_drive_mocks(escrow_routes, unsealed=True):
            stack.enter_context(m)
        mgr = escrow_routes.get_escrow_manager()
        # Post-lock state a retry sees: the first handler's release_payment
        # already ran, so the manager refuses a second release for the same
        # contract — before any submission or restore can happen.
        mgr.release_payment = AsyncMock(return_value=(False, "Cannot release payment in released state"))
        with pytest.raises(HTTPException) as exc:
            await escrow_routes.release_escrow("job-1", {"amount": "0.6"})
        assert exc.value.status_code == 400
        escrow_routes._submit_payment_tx.assert_not_awaited()
        mgr.restore_after_failed_settlement.assert_not_called()


@pytest.mark.asyncio
async def test_release_defers_sweep_until_settlement_legs_seal(release_key, monkeypatch):
    """F1 fixed: the settle-time sweep attempt is gone — the release route
    never signs a sweep while its own legs are still pending. Residue is
    swept by the periodic pass / retry surface instead."""
    monkeypatch.setenv("ESCROW_RELEASE_PRIVATE_KEY", release_key)
    monkeypatch.setenv("ESCROW_FEE_SWEEP_ENABLED", "1")
    monkeypatch.setenv("ESCROW_FEE_RECIPIENT", "0x" + "fe" * 20)
    monkeypatch.setenv("HUB_RPC_URL", "http://localhost:8202")
    monkeypatch.setenv("CHAIN_ID", "test-chain")
    escrow_routes = _reload_routes()
    mocks = _release_drive_mocks(escrow_routes, unsealed=True)
    sweep_spy = AsyncMock(return_value="0xsweep")

    import asyncio
    import contextlib

    with (
        contextlib.ExitStack() as stack,
        patch.object(escrow_routes, "_submit_refund_tx", new_callable=AsyncMock, return_value="0xref"),
        patch.object(escrow_routes, "_submit_fee_sweep_tx", sweep_spy),
    ):
        for m in mocks:
            stack.enter_context(m)
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(escrow_routes.release_escrow("job-1", {"amount": "0.6"}), timeout=5)

    sweep_spy.assert_not_awaited()


@pytest.mark.asyncio
async def test_retry_sweeps_zero_change_row_from_chain_legs(release_key, monkeypatch):
    """F2 fixed: a released escrow that owed no change has refunded_amount
    NULL — the chain still proves the residue (lock − released − 0 sealed
    refunds) and the retry offers the sweep instead of skipping on NULL."""
    escrow_routes = _enable_fee_sweep(monkeypatch, release_key)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"transaction_hash": "0xsweep"}
    record = _released_record(
        refunded_amount=None,
        energy_fee_basis_points=800,
        billed_legs=[{"tx_hash": "0xrel", "billed": 1_000_000}],
    )  # residue = 1_000_000 − 920_000 = 80_000
    legs = {
        "locked_amount": 1_000_000,
        "released_amount": 920_000,
        "refunded_amount": 0,
        "release_values": [920_000],
        "release_legs": [{"tx_hash": "0xrel", "value": 920_000}],
        "min_settlement_height": 36000,
        "release_tx_hash": "0xrel",
        "refund_tx_hash": None,
        "status": "released",
        "released_at": None,
    }

    with (
        patch("aitbc_chain.contracts.escrow.settlement_legs_from_chain", return_value=legs),
        patch.object(escrow_routes, "_escrow_custody_balance", new_callable=AsyncMock, return_value=80_000),
        patch.object(escrow_routes, "_find_existing_fee_sweep", new_callable=AsyncMock, return_value=None),
        patch.object(escrow_routes, "_get_account_nonce", new_callable=AsyncMock, return_value=9),
        patch.object(escrow_routes.SharedHttpClient, "post", new_callable=AsyncMock, return_value=mock_response) as mock_post,
    ):
        assert await escrow_routes._retry_sweep_released_escrow("job-1", record, None) == "0xsweep"
    assert mock_post.call_args.kwargs["json"]["amount"] == 80_000


@pytest.mark.asyncio
async def test_retry_refuses_residue_beyond_fee_bound(release_key, monkeypatch):
    """D11: the retry applies the same fee-only proof as the pass — a
    released-marked row whose change refund never sealed leaves custody
    holding fee+owed change; custody equality alone cannot tell them apart,
    so the bound refuses. The pre-bound code swept exactly this shape."""
    escrow_routes = _enable_fee_sweep(monkeypatch, release_key)
    # bps=800: release 460_000 → billed 500_000, withheld fee 40_000. The owed
    # 500_000 change never sealed, so custody holds 540_000 = fee + change.
    record = _released_record(
        energy_fee_basis_points=800,
        billed_legs=[{"tx_hash": "0xrel", "billed": 500_000}],
    )
    legs = {
        "locked_amount": 1_000_000,
        "released_amount": 460_000,
        "refunded_amount": 0,
        "release_values": [460_000],
        "release_legs": [{"tx_hash": "0xrel", "value": 460_000}],
        "min_settlement_height": 36000,
    }

    with (
        patch("aitbc_chain.contracts.escrow.settlement_legs_from_chain", return_value=legs),
        patch.object(escrow_routes, "_escrow_custody_balance", new_callable=AsyncMock, return_value=540_000),
        patch.object(escrow_routes.SharedHttpClient, "post", new_callable=AsyncMock) as mock_post,
    ):
        assert await escrow_routes._retry_sweep_released_escrow("job-1", record, None) is None
    mock_post.assert_not_awaited()


@pytest.mark.asyncio
async def test_retry_refuses_protected_recompute_mismatch(release_key, monkeypatch):
    """D11 companion (A7): a protected row whose sealed value matches neither
    the net nor the credit bump fails the recompute — deferred."""
    escrow_routes = _enable_fee_sweep(monkeypatch, release_key)
    record = _released_record(
        protected=True,
        energy_fee_basis_points=800,
        energy_provider_credit_units=950_000,  # bump expected → 950_000 ≠ 920_000
        billed_legs=[{"tx_hash": "0xrel", "billed": 1_000_000}],
    )
    legs = {
        "locked_amount": 1_000_000,
        "released_amount": 920_000,
        "refunded_amount": 0,
        "release_values": [920_000],
        "release_legs": [{"tx_hash": "0xrel", "value": 920_000}],
        "min_settlement_height": 36000,
    }

    with (
        patch("aitbc_chain.contracts.escrow.settlement_legs_from_chain", return_value=legs),
        patch.object(escrow_routes, "_escrow_custody_balance", new_callable=AsyncMock, return_value=80_000),
        patch.object(escrow_routes.SharedHttpClient, "post", new_callable=AsyncMock) as mock_post,
    ):
        assert await escrow_routes._retry_sweep_released_escrow("job-1", record, None) is None
    mock_post.assert_not_awaited()


@pytest.mark.asyncio
async def test_retry_refuses_reused_id_with_prefork_leg(release_key, monkeypatch):
    """A4d: the retry refuses when ANY settlement leg sits below the v11
    floor — even when the residue is provably all-fee. Two eras of a reused
    job id, each leaving the same provable 900-unit fee residue: the floor
    is a policy gate (pre-fork custody is the operator's census decision),
    so the bound cannot rescue it."""
    escrow_routes = _enable_fee_sweep(monkeypatch, release_key)
    record = _released_record()  # default 250 bps: 35100 → billed 36000, fee 900/era
    legs = {
        "locked_amount": 72_000,  # old-era lock 36_000 + new-era lock 36_000
        "released_amount": 70_200,  # old-era release 35_100 + new-era 35_100
        "refunded_amount": 0,
        "release_values": [35_100, 35_100],
        "min_settlement_height": 33593,  # a real reused id's old-era leg height
    }

    with (
        patch("aitbc_chain.contracts.escrow.settlement_legs_from_chain", return_value=legs),
        patch.object(escrow_routes, "_escrow_custody_balance", new_callable=AsyncMock, return_value=1_800),
        patch.object(escrow_routes.SharedHttpClient, "post", new_callable=AsyncMock) as mock_post,
    ):
        assert await escrow_routes._retry_sweep_released_escrow("job-1", record, None) is None
    mock_post.assert_not_awaited()


@pytest.mark.asyncio
async def test_retry_refuses_leg_with_null_height(release_key, monkeypatch):
    """A4d fail-closed: a settlement leg whose block_height is NULL cannot be
    proven post-floor — refuse, don't guess. Provable residue and matching
    custody cannot rescue it."""
    escrow_routes = _enable_fee_sweep(monkeypatch, release_key)
    record = _released_record()
    legs = {
        "locked_amount": 36_000,
        "released_amount": 35_100,
        "refunded_amount": 0,
        "release_values": [35_100],
        "min_settlement_height": None,
        "null_settlement_height": True,
    }

    with (
        patch("aitbc_chain.contracts.escrow.settlement_legs_from_chain", return_value=legs),
        patch.object(escrow_routes, "_escrow_custody_balance", new_callable=AsyncMock, return_value=900),
        patch.object(escrow_routes.SharedHttpClient, "post", new_callable=AsyncMock) as mock_post,
    ):
        assert await escrow_routes._retry_sweep_released_escrow("job-1", record, None) is None
    mock_post.assert_not_awaited()
