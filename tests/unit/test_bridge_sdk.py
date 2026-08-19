"""Unit tests for the aitbc.bridge shared SDK (v0.7.0 §A3).

Covers:
- Bridge types (BridgeStatus, BridgeTransfer, BridgeProof, BridgeConfig)
- BridgeClient init + async context manager + mocked RPC methods
- Proof utilities (build_lock_proof, validate_proof_fields, serialization,
  verify_proposer_signature with mocked recover_signer)

No real blockchain node required — all HTTP calls are stubbed with AsyncMock.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from aitbc.bridge import (
    REQUIRED_PROOF_FIELDS,
    BridgeClient,
    BridgeConfig,
    BridgeProof,
    BridgeStatus,
    BridgeTransfer,
    build_lock_proof,
    dict_to_proof,
    proof_to_dict,
    transfer_from_dict,
    validate_proof_fields,
    verify_proposer_signature,
)
from aitbc.bridge.client import BridgeClient as _BridgeClient  # noqa: F401  (re-export sanity)

RPC_URL = "http://localhost:8202"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


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
    client.aclose = AsyncMock()
    return client


def _sample_transfer(
    *,
    source_chain: str = "ait-hub",
    target_chain: str = "ait-2",
    sender: str = "0xSender",
    recipient: str = "0xRecipient",
    amount: int = 3600,
    status: BridgeStatus = BridgeStatus.LOCKED,
) -> BridgeTransfer:
    return BridgeTransfer(
        transfer_id="tx-1",
        source_chain=source_chain,
        target_chain=target_chain,
        sender=sender,
        recipient=recipient,
        amount=amount,
        asset="native",
        status=status,
        lock_time=datetime(2026, 1, 1, 0, 0, 0),
    )


def _sample_proof(
    *,
    source_chain: str = "ait-hub",
    amount: int = 3600,
    sender: str = "0xSender",
    recipient: str = "0xRecipient",
    block_height: int = 100,
    block_hash: str = "0xabc",
    proposer_signature: str = "0xdeadbeef",
) -> BridgeProof:
    return BridgeProof(
        source_chain=source_chain,
        lock_tx_hash="0xlock",
        amount=amount,
        sender=sender,
        recipient=recipient,
        chain_id="ait-hub",
        block_height=block_height,
        block_hash=block_hash,
        proposer_signature=proposer_signature,
    )


# ---------------------------------------------------------------------------
# BridgeStatus
# ---------------------------------------------------------------------------


def test_bridge_status_values() -> None:
    assert BridgeStatus.PENDING.value == "pending"
    assert BridgeStatus.LOCKED.value == "locked"
    assert BridgeStatus.CONFIRMED.value == "confirmed"
    assert BridgeStatus.COMPLETED.value == "completed"
    assert BridgeStatus.FAILED.value == "failed"
    assert BridgeStatus.REFUNDED.value == "refunded"


def test_bridge_status_is_str_enum() -> None:
    # str enum: members compare equal to their string value
    assert BridgeStatus.PENDING == "pending"
    assert str(BridgeStatus.LOCKED) == "locked"


# ---------------------------------------------------------------------------
# BridgeTransfer
# ---------------------------------------------------------------------------


def test_bridge_transfer_defaults() -> None:
    t = BridgeTransfer(
        transfer_id="t1",
        source_chain="ait-hub",
        target_chain="ait-2",
        sender="0xa",
        recipient="0xb",
        amount=100,
    )
    assert t.asset == "native"
    assert t.status == BridgeStatus.PENDING
    assert t.source_tx_hash is None
    assert t.target_tx_hash is None
    assert t.lock_time is None
    assert t.confirm_time is None
    assert t.fee == 0


# ---------------------------------------------------------------------------
# BridgeProof
# ---------------------------------------------------------------------------


def test_bridge_proof_dataclass() -> None:
    p = _sample_proof()
    assert p.source_chain == "ait-hub"
    assert p.lock_tx_hash == "0xlock"
    assert p.amount == 3600
    assert p.sender == "0xSender"
    assert p.recipient == "0xRecipient"
    assert p.chain_id == "ait-hub"
    assert p.block_height == 100
    assert p.block_hash == "0xabc"
    assert p.proposer_signature == "0xdeadbeef"


def test_required_proof_fields_complete() -> None:
    expected = {
        "source_chain",
        "lock_tx_hash",
        "amount",
        "sender",
        "recipient",
        "chain_id",
        "block_height",
        "block_hash",
        "proposer_signature",
    }
    assert set(REQUIRED_PROOF_FIELDS) == expected
    assert len(REQUIRED_PROOF_FIELDS) == 9


# ---------------------------------------------------------------------------
# BridgeConfig
# ---------------------------------------------------------------------------


def test_bridge_config_defaults() -> None:
    c = BridgeConfig()
    assert c.rpc_url == "http://localhost:8202/rpc"
    assert c.chain_id == "ait-hub"
    assert c.timeout == 30
    assert c.retry_limit == 3
    assert c.fee_basis_points == 10
    assert c.batch_size == 10


# ---------------------------------------------------------------------------
# BridgeClient
# ---------------------------------------------------------------------------


def test_bridge_client_init_default_config() -> None:
    c = BridgeClient()
    assert c.config.rpc_url == "http://localhost:8202/rpc"
    assert c.config.chain_id == "ait-hub"
    assert c._client is None


def test_bridge_client_custom_config() -> None:
    cfg = BridgeConfig(rpc_url="http://node:9000", chain_id="ait-2", timeout=5)
    c = BridgeClient(cfg)
    assert c.config.rpc_url == "http://node:9000"
    assert c.config.chain_id == "ait-2"
    assert c.config.timeout == 5


# ---------------------------------------------------------------------------
# transfer_from_dict
# ---------------------------------------------------------------------------


def test_transfer_from_dict_full() -> None:
    data = {
        "transfer_id": "tx-1",
        "source_chain": "ait-hub",
        "target_chain": "ait-2",
        "sender": "0xa",
        "recipient": "0xb",
        "amount": "3600",  # string should coerce to int
        "asset": "native",
        "status": "LOCKED",  # uppercase should normalize
        "source_tx_hash": "0xsrc",
        "target_tx_hash": "0xtgt",
        "fee": "5",
    }
    t = transfer_from_dict(data)
    assert t.transfer_id == "tx-1"
    assert t.amount == 3600
    assert t.status == BridgeStatus.LOCKED
    assert t.source_tx_hash == "0xsrc"
    assert t.fee == 5


def test_transfer_from_dict_unknown_status_defaults_pending() -> None:
    data = {
        "transfer_id": "tx-1",
        "source_chain": "ait-hub",
        "target_chain": "ait-2",
        "sender": "0xa",
        "recipient": "0xb",
        "amount": 100,
        "status": "weird",
    }
    t = transfer_from_dict(data)
    assert t.status == BridgeStatus.PENDING


def test_transfer_from_dict_missing_optional() -> None:
    data = {
        "transfer_id": "tx-1",
        "source_chain": "ait-hub",
        "target_chain": "ait-2",
        "sender": "0xa",
        "recipient": "0xb",
        "amount": 100,
    }
    t = transfer_from_dict(data)
    assert t.asset == "native"
    assert t.status == BridgeStatus.PENDING
    assert t.source_tx_hash is None
    assert t.fee == 0


# ---------------------------------------------------------------------------
# build_lock_proof
# ---------------------------------------------------------------------------


def test_build_lock_proof() -> None:
    p = build_lock_proof(
        source_chain="ait-hub",
        lock_tx_hash="0xlock",
        amount=3600,
        sender="0xa",
        recipient="0xb",
        chain_id="ait-hub",
        block_height=100,
        block_hash="0xabc",
        proposer_signature="0xdeadbeef",
    )
    assert p.source_chain == "ait-hub"
    assert p.lock_tx_hash == "0xlock"
    assert p.amount == 3600
    assert p.chain_id == "ait-hub"
    assert p.proposer_signature == "0xdeadbeef"


# ---------------------------------------------------------------------------
# validate_proof_fields
# ---------------------------------------------------------------------------


def test_validate_proof_fields_valid() -> None:
    proof = _sample_proof()
    transfer = _sample_transfer()
    assert validate_proof_fields(proof, transfer) == []


def test_validate_proof_fields_source_chain_mismatch() -> None:
    proof = _sample_proof(source_chain="other")
    transfer = _sample_transfer()
    errors = validate_proof_fields(proof, transfer)
    assert any("source_chain mismatch" in e for e in errors)


def test_validate_proof_fields_amount_mismatch() -> None:
    proof = _sample_proof(amount=7200)
    transfer = _sample_transfer(amount=3600)
    errors = validate_proof_fields(proof, transfer)
    assert any("amount mismatch" in e for e in errors)


def test_validate_proof_fields_sender_mismatch() -> None:
    proof = _sample_proof(sender="0xOther")
    transfer = _sample_transfer(sender="0xSender")
    errors = validate_proof_fields(proof, transfer)
    assert any("sender mismatch" in e for e in errors)


def test_validate_proof_fields_recipient_mismatch() -> None:
    proof = _sample_proof(recipient="0xOther")
    transfer = _sample_transfer(recipient="0xRecipient")
    errors = validate_proof_fields(proof, transfer)
    assert any("recipient mismatch" in e for e in errors)


def test_validate_proof_fields_negative_block_height() -> None:
    proof = _sample_proof(block_height=-1)
    transfer = _sample_transfer()
    errors = validate_proof_fields(proof, transfer)
    assert any("block_height must be non-negative" in e for e in errors)


def test_validate_proof_fields_empty_block_hash() -> None:
    proof = _sample_proof(block_hash="")
    transfer = _sample_transfer()
    errors = validate_proof_fields(proof, transfer)
    assert any("block_hash must be non-empty" in e for e in errors)


def test_validate_proof_fields_empty_signature() -> None:
    proof = _sample_proof(proposer_signature="")
    transfer = _sample_transfer()
    errors = validate_proof_fields(proof, transfer)
    assert any("proposer_signature must be non-empty" in e for e in errors)


def test_validate_proof_fields_non_hex_signature() -> None:
    proof = _sample_proof(proposer_signature="deadbeef")  # no 0x prefix
    transfer = _sample_transfer()
    errors = validate_proof_fields(proof, transfer)
    assert any("0x prefix" in e for e in errors)


# ---------------------------------------------------------------------------
# proof serialization
# ---------------------------------------------------------------------------


def test_proof_to_dict() -> None:
    p = _sample_proof()
    d = proof_to_dict(p)
    assert d["source_chain"] == "ait-hub"
    assert d["lock_tx_hash"] == "0xlock"
    assert d["amount"] == 3600
    assert d["proposer_signature"] == "0xdeadbeef"
    assert set(d.keys()) == set(REQUIRED_PROOF_FIELDS)


def test_dict_to_proof() -> None:
    d = {
        "source_chain": "ait-hub",
        "lock_tx_hash": "0xlock",
        "amount": "3600",  # string should coerce
        "sender": "0xa",
        "recipient": "0xb",
        "chain_id": "ait-hub",
        "block_height": "100",  # string should coerce
        "block_hash": "0xabc",
        "proposer_signature": "0xdeadbeef",
    }
    p = dict_to_proof(d)
    assert p.amount == 3600
    assert p.block_height == 100
    assert p.source_chain == "ait-hub"


def test_proof_roundtrip() -> None:
    p = _sample_proof()
    d = proof_to_dict(p)
    p2 = dict_to_proof(d)
    assert p2 == p


# ---------------------------------------------------------------------------
# verify_proposer_signature
# ---------------------------------------------------------------------------


def test_verify_proposer_signature_returns_recovered_address() -> None:
    p = _sample_proof()
    with patch("aitbc.bridge.proof.recover_signer", return_value="0xRecovered") as mocked:
        result = verify_proposer_signature(p)
    assert result == "0xRecovered"
    mocked.assert_called_once()
    sent_data = mocked.call_args.args[0]
    sent_sig = mocked.call_args.args[1]
    assert sent_sig == "0xdeadbeef"
    # message_data must NOT contain the signature key
    assert "signature" not in sent_data
    assert "proposer_signature" not in sent_data
    assert sent_data["source_chain"] == "ait-hub"
    assert sent_data["block_height"] == 100


def test_verify_proposer_signature_returns_none_on_failure() -> None:
    p = _sample_proof()
    with patch("aitbc.bridge.proof.recover_signer", return_value=None):
        result = verify_proposer_signature(p)
    assert result is None


# ---------------------------------------------------------------------------
# package re-exports
# ---------------------------------------------------------------------------


def test_package_reexport() -> None:
    import aitbc.bridge as pkg

    for name in [
        "BridgeClient",
        "BridgeConfig",
        "BridgeProof",
        "BridgeStatus",
        "BridgeTransfer",
        "build_lock_proof",
        "dict_to_proof",
        "proof_to_dict",
        "transfer_from_dict",
        "validate_proof_fields",
        "verify_proposer_signature",
        "REQUIRED_PROOF_FIELDS",
    ]:
        assert hasattr(pkg, name), f"aitbc.bridge missing re-export: {name}"
        assert name in pkg.__all__
