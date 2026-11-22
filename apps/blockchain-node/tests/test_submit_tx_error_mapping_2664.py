"""AUDIT-BN-SUBMIT-TX-ECHOES-INTERNAL-ERRORS-AS-400-1 (#2664): the submit
routes must answer admission refusals (ValueError) with 400 but map any other
exception — database failures included — to a generic 5xx. Echoing ``str(e)``
into a 400 leaked SQL statements, bound parameters and backend connection
text to unauthenticated callers and told clients a node fault was their fault.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import OperationalError

from aitbc_chain.rpc import transactions
from aitbc_chain.rpc.transactions import TransactionRequest


def _tx_request() -> TransactionRequest:
    return TransactionRequest.model_validate(
        {
            "from": "0xsender",
            "to": "0xrecipient",
            "amount": 1,
            "fee": 0,
            "nonce": 0,
            "type": "TRANSFER",
            "payload": {},
            "signature": "0xsig",
        }
    )


def _admission_patches(error: BaseException):
    return (
        patch("aitbc_chain.mempool.get_mempool", return_value=MagicMock()),
        patch.object(transactions, "verify_transaction_signature", return_value=True),
        patch.object(transactions, "normalize_transaction_data", side_effect=lambda d, c: d),
        patch.object(transactions, "_validate_transaction_admission", side_effect=error),
    )


def test_submit_transaction_db_error_is_generic_500() -> None:
    db_error = OperationalError(
        "SELECT account.balance FROM account WHERE account.chain_id = ?",
        {"chain_id": "c"},
        Exception("database is locked"),
    )
    p1, p2, p3, p4 = _admission_patches(db_error)
    with p1, p2, p3, p4:
        with pytest.raises(HTTPException) as exc_info:
            transactions.submit_transaction(MagicMock(), _tx_request())

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Internal server error"
    assert "SELECT" not in str(exc_info.value.detail)
    assert "parameters" not in str(exc_info.value.detail)


def test_submit_transaction_admission_refusal_stays_400() -> None:
    p1, p2, p3, p4 = _admission_patches(ValueError("sender account not found"))
    with p1, p2, p3, p4:
        with pytest.raises(HTTPException) as exc_info:
            transactions.submit_transaction(MagicMock(), _tx_request())

    assert exc_info.value.status_code == 400
    assert "sender account not found" in exc_info.value.detail


def _market_patches(error: BaseException):
    return (
        patch("aitbc_chain.mempool.get_mempool", return_value=MagicMock()),
        patch.object(transactions, "_enforce_market_offer_rules", return_value=None),
        patch.object(transactions, "_verify_market_signature", side_effect=lambda tx, sig, sender: tx),
        patch.object(transactions, "normalize_transaction_data", side_effect=lambda d, c: d),
        patch.object(transactions, "_admit_market_transaction", side_effect=error),
    )


def _market_tx() -> dict:
    return {
        "chain_id": "",
        "from": "0xsender",
        "to": "0xrecipient",
        "amount": 1,
        "fee": 0,
        "nonce": 0,
        "type": "TRANSFER",
        "payload": {},
        "signature": "0xsig",
    }


def test_submit_market_transaction_db_error_is_generic_500() -> None:
    db_error = OperationalError(
        "SELECT gpu.id FROM gpu WHERE gpu.chain_id = ?",
        {"chain_id": "c"},
        Exception("database is locked"),
    )
    patches = _market_patches(db_error)
    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        with pytest.raises(HTTPException) as exc_info:
            transactions.submit_market_transaction(MagicMock(), _market_tx())

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Internal server error"


def test_submit_market_transaction_admission_refusal_stays_400() -> None:
    patches = _market_patches(ValueError("bond below minimum"))
    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        with pytest.raises(HTTPException) as exc_info:
            transactions.submit_market_transaction(MagicMock(), _market_tx())

    assert exc_info.value.status_code == 400
    assert "bond below minimum" in exc_info.value.detail
