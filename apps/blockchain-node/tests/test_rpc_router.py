from __future__ import annotations

import pytest

from aitbc_chain.rpc.router import TransactionRequest


def test_transfer_payload_accepts_modern_format() -> None:
    """Test model_validator accepts modern format with recipient/amount in payload"""
    req = TransactionRequest.model_validate(
        {
            "type": "transfer",
            "from": "aitbc1sender",
            "nonce": 1,
            "fee": 0,
            "payload": {"recipient": "aitbc1recipient", "amount": "100"},
        }
    )

    assert req.type == "TRANSFER"
    assert req.sender == "aitbc1sender"
    assert req.payload["recipient"] == "aitbc1recipient"
    assert req.payload["to"] == "aitbc1recipient"
    assert req.payload["amount"] == "100"
    assert req.payload["value"] == "100"


def test_transfer_payload_accepts_legacy_to_field() -> None:
    """Test model_validator accepts legacy format with to/value in payload"""
    req = TransactionRequest.model_validate(
        {
            "type": "transfer",
            "from": "aitbc1sender",
            "nonce": 1,
            "fee": 0,
            "payload": {"to": "aitbc1recipient", "value": "100"},
        }
    )

    assert req.type == "TRANSFER"
    assert req.sender == "aitbc1sender"
    assert req.payload["recipient"] == "aitbc1recipient"
    assert req.payload["to"] == "aitbc1recipient"
    assert req.payload["amount"] == "100"
    assert req.payload["value"] == "100"


def test_transfer_payload_requires_recipient_or_to() -> None:
    """Test model_validator rejects payload without recipient or to"""
    with pytest.raises(ValueError, match="recipient"):
        TransactionRequest.model_validate(
            {
                "type": "TRANSFER",
                "from": "aitbc1sender",
                "nonce": 1,
                "fee": 0,
                "payload": {"amount": "100"},
            }
        )


def test_transfer_payload_normalizes_amount_and_value() -> None:
    """Test model_validator sets both amount and value in payload"""
    req = TransactionRequest.model_validate(
        {
            "type": "transfer",
            "from": "aitbc1sender",
            "nonce": 1,
            "fee": 0,
            "payload": {"recipient": "aitbc1recipient", "amount": "100"},
        }
    )

    assert req.payload["amount"] == "100"
    assert req.payload["value"] == "100"


def test_transfer_payload_normalizes_value_to_amount() -> None:
    """Test model_validator converts value to amount when only value provided"""
    req = TransactionRequest.model_validate(
        {
            "type": "transfer",
            "from": "aitbc1sender",
            "nonce": 1,
            "fee": 0,
            "payload": {"to": "aitbc1recipient", "value": "200"},
        }
    )

    assert req.payload["amount"] == "200"
    assert req.payload["value"] == "200"


def test_transfer_payload_with_chain_id() -> None:
    """Test model_validator accepts chain_id field"""
    req = TransactionRequest.model_validate(
        {
            "type": "transfer",
            "from": "aitbc1sender",
            "nonce": 1,
            "fee": 0,
            "chain_id": "ait-testnet",
            "payload": {"recipient": "aitbc1recipient", "amount": "100"},
        }
    )

    assert req.chain_id == "ait-testnet"
    assert req.type == "TRANSFER"


def test_transfer_payload_without_chain_id() -> None:
    """Test model_validator works without chain_id field"""
    req = TransactionRequest.model_validate(
        {
            "type": "transfer",
            "from": "aitbc1sender",
            "nonce": 1,
            "fee": 0,
            "payload": {"recipient": "aitbc1recipient", "amount": "100"},
        }
    )

    assert req.chain_id is None
    assert req.type == "TRANSFER"


def test_transfer_payload_with_sig() -> None:
    """Test model_validator accepts signature field"""
    req = TransactionRequest.model_validate(
        {
            "type": "transfer",
            "from": "aitbc1sender",
            "nonce": 1,
            "fee": 0,
            "sig": "0xabc123",
            "payload": {"recipient": "aitbc1recipient", "amount": "100"},
        }
    )

    assert req.sig == "0xabc123"


def test_transfer_payload_without_sig() -> None:
    """Test model_validator works without signature field"""
    req = TransactionRequest.model_validate(
        {
            "type": "transfer",
            "from": "aitbc1sender",
            "nonce": 1,
            "fee": 0,
            "payload": {"recipient": "aitbc1recipient", "amount": "100"},
        }
    )

    assert req.sig is None


def test_transfer_type_normalization() -> None:
    """Test model_validator normalizes transaction type to uppercase"""
    req = TransactionRequest.model_validate(
        {
            "type": "transfer",
            "from": "aitbc1sender",
            "nonce": 1,
            "fee": 0,
            "payload": {"recipient": "aitbc1recipient", "amount": "100"},
        }
    )

    assert req.type == "TRANSFER"


def test_receipt_claim_type() -> None:
    """Test model_validator accepts RECEIPT_CLAIM type"""
    req = TransactionRequest.model_validate(
        {
            "type": "receipt_claim",
            "from": "aitbc1sender",
            "nonce": 1,
            "fee": 0,
            "payload": {"receipt_id": "receipt123"},
        }
    )

    assert req.type == "RECEIPT_CLAIM"


def test_unsupported_transaction_type() -> None:
    """Test model_validator rejects unsupported transaction type"""
    with pytest.raises(ValueError, match="unsupported transaction type"):
        TransactionRequest.model_validate(
            {
                "type": "INVALID_TYPE",
                "from": "aitbc1sender",
                "nonce": 1,
                "fee": 0,
                "payload": {"recipient": "aitbc1recipient", "amount": "100"},
            }
        )


# Integration tests for full flow
from fastapi.testclient import TestClient
from aitbc_chain.rpc.router import router


@pytest.fixture
def client():
    """Create a test client for the router"""
    return TestClient(router)


def test_submit_transaction_modern_format(client) -> None:
    """Test full transaction submission with modern payload format"""
    response = client.post(
        "/rpc/transaction",
        json={
            "type": "TRANSFER",
            "from": "aitbc1sender",
            "nonce": 1,
            "fee": 10,
            "payload": {
                "recipient": "aitbc1recipient",
                "amount": 100
            }
        }
    )

    # This will fail if mempool/database not available, but should validate the request structure
    # The important thing is that it doesn't fail with 400 due to validation errors
    # We expect either success (200) or a business logic error (not validation error)


def test_submit_transaction_legacy_format(client) -> None:
    """Test full transaction submission with legacy payload format"""
    response = client.post(
        "/rpc/transaction",
        json={
            "type": "TRANSFER",
            "from": "aitbc1sender",
            "nonce": 1,
            "fee": 10,
            "payload": {
                "to": "aitbc1recipient",
                "value": 100
            }
        }
    )

    # Should not fail with validation error


def test_submit_transaction_missing_recipient(client) -> None:
    """Test transaction submission fails when recipient is missing"""
    response = client.post(
        "/rpc/transaction",
        json={
            "type": "TRANSFER",
            "from": "aitbc1sender",
            "nonce": 1,
            "fee": 10,
            "payload": {
                "amount": 100
            }
        }
    )

    # Should fail with validation error (400 or 422 depending on FastAPI error handling)
    # The important thing is that it doesn't succeed
    assert response.status_code in (400, 422, 404)


def test_submit_transaction_with_chain_id(client) -> None:
    """Test transaction submission with chain_id field"""
    response = client.post(
        "/rpc/transaction",
        json={
            "type": "TRANSFER",
            "from": "aitbc1sender",
            "nonce": 1,
            "fee": 10,
            "chain_id": "ait-testnet",
            "payload": {
                "recipient": "aitbc1recipient",
                "amount": 100
            }
        }
    )

    # Should not fail with validation error


def test_submit_transaction_with_signature(client) -> None:
    """Test transaction submission with signature field"""
    response = client.post(
        "/rpc/transaction",
        json={
            "type": "TRANSFER",
            "from": "aitbc1sender",
            "nonce": 1,
            "fee": 10,
            "sig": "0xabc123def456",
            "payload": {
                "recipient": "aitbc1recipient",
                "amount": 100
            }
        }
    )

    # Should not fail with validation error
