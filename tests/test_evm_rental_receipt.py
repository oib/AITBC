"""Unit tests for AIPowerRental receipt log decoding (#1785)."""

from __future__ import annotations

from aitbc.market.evm_rental_receipt import AGREEMENT_STARTED_TOPIC0, agreement_id_from_receipt_logs


def _agreement_started_log(agreement_id: int, contract: str) -> dict:
    topic1 = "0x" + agreement_id.to_bytes(32, "big").hex()
    return {
        "address": contract,
        "topics": [AGREEMENT_STARTED_TOPIC0, topic1],
        "data": "0x",
    }


def test_extracts_matching_agreement_id() -> None:
    contract = "0xAbC0000000000000000000000000000000000D"
    logs = [_agreement_started_log(42, contract)]
    assert agreement_id_from_receipt_logs(logs, contract) == 42


def test_ignores_other_contracts() -> None:
    contract = "0xAbC0000000000000000000000000000000000D"
    other = "0x1111111111111111111111111111111111111111"
    logs = [_agreement_started_log(7, other)]
    assert agreement_id_from_receipt_logs(logs, contract) is None


def test_missing_event_returns_none() -> None:
    contract = "0xAbC0000000000000000000000000000000000D"
    logs = [
        {
            "address": contract,
            "topics": ["0xdeadbeef" + "0" * 56],
            "data": "0x",
        }
    ]
    assert agreement_id_from_receipt_logs(logs, contract) is None
