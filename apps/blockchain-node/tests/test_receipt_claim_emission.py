"""Tests for RECEIPT_CLAIM emission at the escrow claim/settle step (#687).

The release route emits a settlement-signed RECEIPT_CLAIM whose payload
carries the receipt's issuance record; apply materialises the ``receipt``
row deterministically so the type seals honestly on every node.
"""

import importlib
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlmodel import Session, create_engine, select

from aitbc_chain.metadata import chain_metadata
from aitbc_chain.models import Account, Receipt


def _reload_routes():
    """Reload escrow_routes so module-level env variables are re-read."""
    from aitbc_chain.rpc import escrow_routes

    importlib.reload(escrow_routes)
    return escrow_routes


@pytest.fixture
def release_key():
    # Deterministic, valid secp256k1 test key (same as test_escrow_routes.py).
    return "0x2222222222222222222222222222222222222222222222222222222222222222"


@pytest.fixture
def signed_receipt():
    return {
        "receipt_id": "rcpt-abc123",
        "job_id": "job-1",
        "provider": "0x3333333333333333333333333333333333333333",
        "price": 1.5,
        "signature": {"alg": "Ed25519", "key_id": "k", "sig": "s"},
        "attestations": [{"alg": "Ed25519", "key_id": "a", "sig": "at"}],
    }


@pytest.mark.asyncio
async def test_submit_receipt_claim_posts_signed_claim_with_carried_record(release_key, signed_receipt, monkeypatch):
    monkeypatch.setenv("ESCROW_RELEASE_PRIVATE_KEY", release_key)
    monkeypatch.delenv("ESCROW_RELEASE_ADDRESS", raising=False)
    monkeypatch.setenv("HUB_RPC_URL", "http://localhost:8202")
    monkeypatch.setenv("CHAIN_ID", "test-chain")

    escrow_routes = _reload_routes()
    from aitbc.crypto.crypto import derive_ethereum_address
    from aitbc.crypto.signature_recovery import canonical_address

    settlement_address = canonical_address(derive_ethereum_address(release_key))
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"transaction_hash": "0xclaim"}

    with (
        patch.object(escrow_routes, "_find_existing_receipt_claim", new_callable=AsyncMock, return_value=None),
        patch.object(escrow_routes, "_resolve_chain_account", new_callable=AsyncMock, return_value=signed_receipt["provider"]),
        patch.object(escrow_routes, "_settlement_next_nonce", new_callable=AsyncMock, return_value=6) as mock_nonce,
        patch.object(escrow_routes.SharedHttpClient, "post", new_callable=AsyncMock, return_value=mock_response) as mock_post,
    ):
        tx_hash = await escrow_routes._submit_receipt_claim_tx(
            signed_receipt, job_id="job-1", contract_id="c-1", provider=signed_receipt["provider"]
        )

    assert tx_hash == "0xclaim"
    sent_tx = mock_post.call_args.kwargs["json"]
    assert sent_tx["type"] == "RECEIPT_CLAIM"
    assert sent_tx["from"] == settlement_address
    assert sent_tx["to"] == signed_receipt["provider"]
    assert sent_tx["amount"] == 0
    assert sent_tx["nonce"] == 6
    assert sent_tx["signature"]
    payload = sent_tx["payload"]
    assert payload["receipt_id"] == "rcpt-abc123"
    record = payload["receipt"]
    assert record["receipt_id"] == "rcpt-abc123"
    assert record["job_id"] == "job-1"
    assert record["miner_signature"] == signed_receipt["signature"]
    assert record["coordinator_attestations"] == signed_receipt["attestations"]
    # The signed receipt body is carried minus its signature fields.
    assert record["payload"]["price"] == 1.5
    assert "signature" not in record["payload"]
    assert "attestations" not in record["payload"]
    mock_nonce.assert_awaited_once_with(settlement_address)


@pytest.mark.asyncio
async def test_submit_receipt_claim_skips_unattested_receipt(release_key, signed_receipt, monkeypatch):
    monkeypatch.setenv("ESCROW_RELEASE_PRIVATE_KEY", release_key)
    escrow_routes = _reload_routes()
    signed_receipt.pop("attestations")

    with patch.object(escrow_routes.SharedHttpClient, "post", new_callable=AsyncMock) as mock_post:
        tx_hash = await escrow_routes._submit_receipt_claim_tx(
            signed_receipt, job_id="job-1", contract_id="c-1", provider="0x3"
        )
    assert tx_hash is None
    mock_post.assert_not_awaited()


@pytest.mark.asyncio
async def test_submit_receipt_claim_dedupes_settled_claim(release_key, signed_receipt, monkeypatch):
    monkeypatch.setenv("ESCROW_RELEASE_PRIVATE_KEY", release_key)
    escrow_routes = _reload_routes()

    with (
        patch.object(escrow_routes, "_find_existing_receipt_claim", new_callable=AsyncMock, return_value="0xold"),
        patch.object(escrow_routes.SharedHttpClient, "post", new_callable=AsyncMock) as mock_post,
    ):
        tx_hash = await escrow_routes._submit_receipt_claim_tx(
            signed_receipt, job_id="job-1", contract_id="c-1", provider="0x3"
        )
    assert tx_hash == "0xold"
    mock_post.assert_not_awaited()


@pytest.mark.asyncio
async def test_settlement_next_nonce_queues_behind_pending_release(release_key, monkeypatch):
    monkeypatch.setenv("ESCROW_RELEASE_PRIVATE_KEY", release_key)
    monkeypatch.setenv("HUB_RPC_URL", "http://localhost:8202")
    escrow_routes = _reload_routes()
    from aitbc.crypto.crypto import derive_ethereum_address
    from aitbc.crypto.signature_recovery import canonical_address

    sender = canonical_address(derive_ethereum_address(release_key))
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "transactions": [
            {"from": sender, "nonce": 5},
            {"from": "0x9999999999999999999999999999999999999999", "nonce": 99},
        ]
    }

    with (
        patch.object(escrow_routes, "_get_account_nonce", new_callable=AsyncMock, return_value=5),
        patch.object(escrow_routes.SharedHttpClient, "get", new_callable=AsyncMock, return_value=mock_response),
    ):
        assert await escrow_routes._settlement_next_nonce(sender) == 6


@pytest.mark.asyncio
async def test_settlement_next_nonce_falls_back_to_sealed(release_key, monkeypatch):
    monkeypatch.setenv("ESCROW_RELEASE_PRIVATE_KEY", release_key)
    monkeypatch.setenv("HUB_RPC_URL", "http://localhost:8202")
    escrow_routes = _reload_routes()

    with (
        patch.object(escrow_routes, "_get_account_nonce", new_callable=AsyncMock, return_value=7),
        patch.object(escrow_routes.SharedHttpClient, "get", new_callable=AsyncMock, side_effect=RuntimeError("down")),
    ):
        assert await escrow_routes._settlement_next_nonce("0xabc") == 7


# ---------------------------------------------------------------------------
# Apply-side: a carried-issuance claim materialises the receipt row.
# ---------------------------------------------------------------------------

CHAIN = "test-chain"
CLAIMER_KEY = "0x" + "44" * 32


def _sign_tx(tx: dict, private_key: str) -> dict:
    from eth_utils import keccak

    from aitbc.crypto.crypto import sign_transaction_hash

    signable = {k: v for k, v in tx.items() if k != "signature"}
    if "amount" in signable:
        signable.pop("value", None)
    message = json.dumps(signable, sort_keys=True, separators=(",", ":")).encode()
    tx["signature"] = sign_transaction_hash("0x" + keccak(message).hex(), private_key)
    return tx


def _new_engine(tmp_path, tag="a"):
    engine = create_engine(f"sqlite:///{tmp_path / f'rc-{tag}.db'}")
    chain_metadata.create_all(engine)
    return engine


def _carried_claim_tx(claimer: str) -> dict:
    return _sign_tx(
        {
            "from": claimer,
            "to": claimer,
            "amount": 0,
            "fee": 36,
            "nonce": 0,
            "type": "RECEIPT_CLAIM",
            "chain_id": CHAIN,
            "payload": {
                "action": "receipt_claim",
                "job_id": "job-1",
                "receipt_id": "rcpt-carried-1",
                "receipt": {
                    "receipt_id": "rcpt-carried-1",
                    "job_id": "job-1",
                    "provider": claimer,
                    "payload": {"units": 3, "price": 0.5},
                    "miner_signature": {"alg": "Ed25519", "sig": "s"},
                    "coordinator_attestations": [{"alg": "Ed25519", "sig": "at"}],
                },
            },
        },
        CLAIMER_KEY,
    )


def test_apply_materialises_claimed_receipt_from_carried_record(tmp_path):
    from aitbc.crypto.crypto import derive_ethereum_address

    from aitbc_chain.state.state_transition import StateTransition

    claimer = derive_ethereum_address(CLAIMER_KEY)
    engine = _new_engine(tmp_path)
    with Session(engine) as session:
        session.add(Account(chain_id=CHAIN, address=claimer, balance=10_000, nonce=0))
        session.commit()

        ok, msg = StateTransition().apply_transaction(
            session, CHAIN, _carried_claim_tx(claimer), "0xclaimhash", block_version=18, block_height=50
        )
        assert ok, msg
        session.commit()

        receipt = session.exec(
            select(Receipt).where(Receipt.chain_id == CHAIN, Receipt.receipt_id == "rcpt-carried-1")
        ).first()
        assert receipt is not None
        assert receipt.status == "claimed"
        assert receipt.claimed_by == claimer
        assert receipt.job_id == "job-1"
        assert receipt.block_height == 50
        assert receipt.minted_amount is None
        assert receipt.miner_signature == {"alg": "Ed25519", "sig": "s"}
        assert receipt.coordinator_attestations == [{"alg": "Ed25519", "sig": "at"}]


def test_apply_rejects_claim_without_row_or_record(tmp_path):
    from aitbc.crypto.crypto import derive_ethereum_address

    from aitbc_chain.state.state_transition import StateTransition

    claimer = derive_ethereum_address(CLAIMER_KEY)
    engine = _new_engine(tmp_path)
    with Session(engine) as session:
        session.add(Account(chain_id=CHAIN, address=claimer, balance=10_000, nonce=0))
        session.commit()
        tx = _sign_tx(
            {
                "from": claimer,
                "to": claimer,
                "amount": 0,
                "fee": 36,
                "nonce": 0,
                "type": "RECEIPT_CLAIM",
                "chain_id": CHAIN,
                "payload": {"receipt_id": "rcpt-missing"},
            },
            CLAIMER_KEY,
        )
        ok, msg = StateTransition().apply_transaction(session, CHAIN, tx, "0xh2", block_version=18, block_height=50)
        assert not ok
        assert "Receipt not found" in msg
