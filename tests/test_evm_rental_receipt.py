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


def test_accepts_unprefixed_agreement_started_topic() -> None:
    """HexBytes.hex() omits 0x; decoder must still match AgreementStarted."""
    contract = "0xAbC0000000000000000000000000000000000D"
    agreement_id = 42
    topic1_hex = agreement_id.to_bytes(32, "big").hex()
    logs = [
        {
            "address": contract,
            "topics": [AGREEMENT_STARTED_TOPIC0[2:], "0x" + topic1_hex],
            "data": "0x",
        }
    ]
    assert agreement_id_from_receipt_logs(logs, contract) == 42


class _HexBytesNoPrefix:
    """Mimic web3 HexBytes.hex() (no 0x prefix)."""

    def __init__(self, body: str) -> None:
        self._body = body.removeprefix("0x")

    def hex(self) -> str:
        return self._body


class _ReceiptLogStub:
    def __init__(self, address: str, topics: list[_HexBytesNoPrefix], data: _HexBytesNoPrefix) -> None:
        self.address = address
        self.topics = topics
        self.data = data


def test_serializer_output_decodes_agreement_id() -> None:
    """Integration: EthereumRPCClient log JSON → agreement_id_from_receipt_logs."""
    from aitbc.ethereum_rpc import EthereumRPCClient

    contract = "0xAbC0000000000000000000000000000000000D"
    agreement_id = 9001
    topic0 = _HexBytesNoPrefix(AGREEMENT_STARTED_TOPIC0)
    topic1 = _HexBytesNoPrefix("0x" + agreement_id.to_bytes(32, "big").hex())
    stub = _ReceiptLogStub(contract, [topic0, topic1], _HexBytesNoPrefix(""))
    entry = EthereumRPCClient._serialize_receipt_log(stub)
    assert entry["topics"][0].startswith("0x")
    assert agreement_id_from_receipt_logs([entry], contract) == agreement_id
