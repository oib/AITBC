"""Read/write-set extraction for the pure state-transition split.

``extract_read_write_sets`` and its per-type dependency helpers, used by the
parallel executor's conflict analysis. Import
``aitbc_chain.state.pure_state_transition`` first (it re-exports every name
here); this module is not meant to be imported directly.
"""

from __future__ import annotations

from typing import Any

from ..base_models import _to_ait_address
from .pure_state_transition_base import _decode_payload, _determine_tx_type, _escrow_address


def _add_receipt_rw_set(tx_data: dict[str, Any], read_set: set[str]) -> None:
    """Add the receipt dependency for RECEIPT_CLAIM transactions."""
    receipt_id = tx_data.get("payload", {}).get("receipt_id")
    if receipt_id:
        read_set.add(f"receipt:{receipt_id}")


def _add_ipfs_rw_set(tx_data: dict[str, Any], sender: str, read_set: set[str], write_set: set[str]) -> None:
    """Add island subscription read/write dependencies for IPFS_SUBSCRIPTION."""
    payload = _decode_payload(tx_data.get("payload", {}) or {})
    island_id = payload.get("island_id")
    if island_id:
        read_set.add(f"ipfs_subscription:{island_id}:{sender}")
        write_set.add(f"ipfs_subscription:{island_id}:{sender}")


def _add_escrow_rw_set(tx_data: dict[str, Any], read_set: set[str], write_set: set[str]) -> None:
    """Add per-escrow read/write dependencies for ESCROW_RELEASE/ESCROW_REFUND/ESCROW_FEE_SWEEP."""
    payload = _decode_payload(tx_data.get("payload", {}) or {})
    job_id = payload.get("job_id", "")
    if job_id:
        escrow_addr = _escrow_address(job_id)
        read_set.add(escrow_addr)
        write_set.add(escrow_addr)


def extract_read_write_sets(tx_data: dict[str, Any]) -> tuple[frozenset[str], frozenset[str]]:
    """Extract read/write sets from transaction data for dependency analysis.

    Args:
        tx_data: Transaction data (from, to, amount, fee, type, etc.).

    Returns:
        Tuple of (read_set, write_set) — sets of account addresses.
    """
    sender = _to_ait_address(tx_data.get("from", ""))
    recipient = _to_ait_address(tx_data.get("to", ""))
    tx_type = _determine_tx_type(tx_data)

    read_set: set[str] = set()
    write_set: set[str] = set()

    if sender:
        read_set.add(sender)
        write_set.add(sender)

    if tx_type != "MESSAGE" and recipient:
        read_set.add(recipient)
        write_set.add(recipient)

    if tx_type == "RECEIPT_CLAIM":
        _add_receipt_rw_set(tx_data, read_set)

    if tx_type == "IPFS_SUBSCRIPTION":
        _add_ipfs_rw_set(tx_data, sender, read_set, write_set)

    if tx_type in ("ESCROW_RELEASE", "ESCROW_REFUND", "ESCROW_FEE_SWEEP"):
        _add_escrow_rw_set(tx_data, read_set, write_set)

    return frozenset(read_set), frozenset(write_set)
