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
        result = await escrow_routes._retry_sweep_released_escrow("job-123", _released_record())

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
    """Retry: custody balance must equal locked − released − refunded exactly —
    the design's equality check. A balance above it means an owed leg is still
    pending; the job is skipped, never guessed."""
    escrow_routes = _enable_fee_sweep(monkeypatch, release_key)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"transaction_hash": "0xsweep"}

    record = _released_record()  # residue = 1_000_000 − 920_000 − 75_000 = 5_000

    # Legs fully sealed: custody holds exactly the residue.
    with (
        patch.object(escrow_routes, "_escrow_custody_balance", new_callable=AsyncMock, return_value=5_000),
        patch.object(escrow_routes, "_find_existing_fee_sweep", new_callable=AsyncMock, return_value=None),
        patch.object(escrow_routes, "_get_account_nonce", new_callable=AsyncMock, return_value=9),
        patch.object(escrow_routes.SharedHttpClient, "post", new_callable=AsyncMock, return_value=mock_response) as mock_post,
    ):
        assert await escrow_routes._retry_sweep_released_escrow("job-1", record) == "0xsweep"
    assert mock_post.call_args.kwargs["json"]["amount"] == 5_000

    # An owed leg still pending: custody holds residue + unbilled change.
    with (
        patch.object(escrow_routes, "_escrow_custody_balance", new_callable=AsyncMock, return_value=85_000),
        patch.object(escrow_routes.SharedHttpClient, "post", new_callable=AsyncMock) as mock_post,
    ):
        assert await escrow_routes._retry_sweep_released_escrow("job-1", record) is None
    mock_post.assert_not_awaited()

    # Custody unprovable: skipped.
    with (
        patch.object(escrow_routes, "_escrow_custody_balance", new_callable=AsyncMock, return_value=None),
        patch.object(escrow_routes.SharedHttpClient, "post", new_callable=AsyncMock) as mock_post,
    ):
        assert await escrow_routes._retry_sweep_released_escrow("job-1", record) is None
    mock_post.assert_not_awaited()


@pytest.mark.asyncio
async def test_retry_path_skips_rows_without_recorded_refund(release_key, monkeypatch):
    """A released row with no recorded refund leg is ambiguous — the change
    may never have been owed or its submission may have failed before the
    mark — so the sweep leaves it for the operator's census instead of
    guessing."""
    escrow_routes = _enable_fee_sweep(monkeypatch, release_key)
    record = _released_record(refunded_amount=None)

    with (
        patch.object(escrow_routes, "_escrow_custody_balance", new_callable=AsyncMock, return_value=80_000),
        patch.object(escrow_routes.SharedHttpClient, "post", new_callable=AsyncMock) as mock_post,
    ):
        assert await escrow_routes._retry_sweep_released_escrow("job-1", record) is None
    mock_post.assert_not_awaited()


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


def _release_drive_mocks(escrow_routes, *, unsealed=True):
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
    )

    session = MagicMock()
    session.get = MagicMock(return_value=record)

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
@pytest.mark.xfail(
    strict=True,
    reason="C2 desired: the change leg must wait for the release seal or defer to retry — today it signs the same sealed nonce and collides on the (authority, N) mempool slot (F1b)",
)
async def test_release_defers_change_leg_until_release_seals(release_key, monkeypatch):
    """Partial settle whose release is accepted but never seals within the
    call: the refund leg must not be submitted while the release is still
    pending. On current main `_submit_refund_tx` fires immediately with the
    same sealed nonce — losing the slot, or evicting the release."""
    monkeypatch.setenv("ESCROW_RELEASE_PRIVATE_KEY", release_key)
    monkeypatch.setenv("HUB_RPC_URL", "http://localhost:8202")
    monkeypatch.setenv("CHAIN_ID", "test-chain")
    escrow_routes = _reload_routes()
    mocks = _release_drive_mocks(escrow_routes, unsealed=True)
    refund_spy = AsyncMock(return_value="0xref")

    import asyncio
    import contextlib

    with (
        contextlib.ExitStack() as stack,
        patch.object(escrow_routes, "_submit_refund_tx", refund_spy),
    ):
        for m in mocks:
            stack.enter_context(m)
        # Bound the wait: under the fix a seal-wait may legitimately block;
        # the contract under test is that no later leg is signed while the
        # sealed lookup keeps answering None.
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(escrow_routes.release_escrow("job-1", {"amount": "0.6"}), timeout=5)

    refund_spy.assert_not_awaited()


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
@pytest.mark.xfail(
    strict=True,
    reason="C2 desired: the retry derives residue from sealed chain legs — a NULL refunded_amount row means 'no refund sealed', provable on-chain, not 'ambiguous, skip' (F2)",
)
async def test_retry_sweeps_zero_change_row_from_chain_legs(release_key, monkeypatch):
    """A released escrow that owed no change has refunded_amount NULL — the
    chain still proves the residue (lock − released − 0 sealed refunds).
    The retry must offer the sweep; today it returns early on the NULL."""
    escrow_routes = _enable_fee_sweep(monkeypatch, release_key)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"transaction_hash": "0xsweep"}
    record = _released_record(refunded_amount=None)  # residue = 1_000_000 − 920_000 = 80_000
    legs = {
        "released_amount": 920_000,
        "refunded_amount": 0,
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
        assert await escrow_routes._retry_sweep_released_escrow("job-1", record) == "0xsweep"
    assert mock_post.call_args.kwargs["json"]["amount"] == 80_000
