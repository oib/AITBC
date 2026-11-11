"""Decode AIPowerRental funding receipts (startRental → AgreementStarted)."""

from __future__ import annotations

from typing import Any

from eth_utils import keccak

# AIPowerRental.startRental emits AgreementStarted (audit docs may say "RentalStarted").
_AGREEMENT_STARTED_SIG = "AgreementStarted(uint256,uint256,uint256)"
AGREEMENT_STARTED_TOPIC0 = "0x" + keccak(text=_AGREEMENT_STARTED_SIG).hex()


def _normalize_address(addr: str | None) -> str:
    if not addr:
        return ""
    return addr.lower()


def _normalize_topic_hex(topic: str) -> str:
    """Lowercase hex body without 0x (web3 HexBytes.hex() omits the prefix)."""
    raw = (topic or "").strip().lower()
    if raw.startswith("0x"):
        raw = raw[2:]
    return raw


def _topic_to_uint256(topic: str) -> int:
    raw = _normalize_topic_hex(topic)
    return int(raw, 16)


def agreement_id_from_receipt_logs(
    log_entries: list[dict[str, Any]],
    rental_contract: str,
) -> int | None:
    """Return agreementId from the first AgreementStarted log on the rental contract."""
    want = _normalize_address(rental_contract)
    if not want:
        return None
    for entry in log_entries:
        if _normalize_address(entry.get("address")) != want:
            continue
        topics: list[str] = entry.get("topics") or []
        if not topics:
            continue
        if _normalize_topic_hex(topics[0]) != _normalize_topic_hex(AGREEMENT_STARTED_TOPIC0):
            continue
        if len(topics) < 2:
            continue
        return _topic_to_uint256(topics[1])
    return None
