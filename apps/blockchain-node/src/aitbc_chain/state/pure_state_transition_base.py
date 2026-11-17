"""Shared primitives for the pure state-transition split.

``StateDelta``, the sequential-only type list, the tx-type/payload helpers,
the escrow address and authority env lookups and the carried-receipt record
live here so the domain siblings (``pure_state_transition_escrow``,
``pure_state_transition_compute``, ``pure_state_transition_rwsets``) and the
``pure_state_transition`` facade can all import them without cycles. Import
the facade; this module is not meant to be imported directly.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, cast

from ..base_models import _to_ait_address
from ..config import settings
from ..logger import get_logger

# Same logger name as the facade: logging.getLogger returns the identical
# logger object, so record identity is unchanged.
logger = get_logger("aitbc_chain.state.pure_state_transition")


def _escrow_address(job_id: str) -> str:
    from aitbc.crypto.signature_recovery import canonical_address
    from eth_utils import keccak

    return canonical_address("0x" + keccak(f"aitbc.escrow.{job_id}".encode()).hex()[:40])


def _escrow_settlement_authority() -> str | None:
    """Return the canonical settlement authority for v3 escrow releases/refunds."""
    addr = settings.escrow_settlement_authority or os.getenv("ESCROW_RELEASE_ADDRESS", "")
    if not addr:
        return None
    return _to_ait_address(addr)


def _escrow_fee_recipient() -> str | None:
    """Return the canonical fee recipient for v11 ESCROW_FEE_SWEEP txs.

    Env-only fallback — the DB-capable context builder resolves the on-chain
    ``escrow_fee_recipient`` parameter at the block's height and carries it in
    the context entry, so this path is for context-free callers only.
    """
    addr = settings.escrow_fee_recipient or os.getenv("ESCROW_FEE_RECIPIENT", "")
    if not addr:
        return None
    return _to_ait_address(addr)


def _decode_payload(payload: Any) -> dict[str, Any]:
    """Return payload as a dict, decoding JSON string if necessary."""
    if isinstance(payload, str):
        try:
            import json

            return cast(dict[str, Any], json.loads(payload))
        except (RecursionError, TypeError, ValueError):  # malformed payload JSON decodes to the empty/default branch
            return {}
    if not payload:
        return {}
    return cast(dict[str, Any], payload)


@dataclass
class StateDelta:
    """State change resulting from a transaction.

    Captures the balance/nonce changes without touching the DB.
    The delta can be applied to account_map (in-memory) or to the DB (batch).
    """

    sender: str
    recipient: str
    sender_balance_change: int  # negative (debit)
    recipient_balance_change: int  # positive (credit)
    sender_nonce_change: int  # +1
    success: bool
    error: str = ""
    tx_type: str = "TRANSFER"
    tx_hash: str = ""
    # For RECEIPT_CLAIM: the receipt_id and minted_amount (if claimed)
    receipt_id: str | None = None
    minted_amount: int | None = None
    # For RECEIPT_CLAIM: the issuance record carried in payload.receipt — lets
    # apply_deltas_to_db materialise the receipt row when the DB lacks it (#687).
    receipt_record: dict[str, Any] | None = None
    # For IPFS_SUBSCRIPTION: subscription record to be written to the DB
    ipfs_subscription: dict[str, Any] | None = None
    # For ESCROW_LOCK v2/v3: additional accounts (e.g. provider) that the
    # sequential path would ensure exist. They carry zero balance change but
    # must be present in account state for matching state roots.
    extra_accounts: list[str] | None = None
    # For ESCROW_RELEASE/ESCROW_REFUND v3: per-account balance debits beyond
    # sender and recipient (e.g. the per-escrow address that loses value).
    extra_debits: dict[str, int] | None = None
    # For side-effect transactions that the pure delta map cannot model.
    # Set by compute_state_delta when the tx type must be processed
    # sequentially by StateTransition.apply_transaction.
    requires_sequential: bool = False


# Transaction types whose block application the pure delta map cannot model —
# they must always run through the full sequential
# ``StateTransition.apply_transaction``. One canonical list, shared by
# ``sync_block_import`` and ``consensus.poa``: a block containing any of them
# never takes the parallel path.
#
# - ``LIQUIDITY_*``/``GPU_REGISTER``/``GPU_ALLOCATE``/``GPU_DEREGISTER`` write non-account state
#   (pools, stakes, distributions, gpu_registration, gpu_allocation). Below v10 GPU_DEREGISTER has no
#   consensus meaning and both paths treat it as the plain transfer it always was.
# - ``GOVERNANCE_EXECUTE`` writes chain_parameter (governance_executors et
#   al.) at apply — the pure delta computes account changes only, so the
#   parameter write would silently never land on parallel-applied blocks
#   (GAP-57).
# - ``STAKE_RELEASE`` v4 lock-window rules (maturity, payee ownership,
#   claim-set overlap) live in validate_transaction — only the sequential
#   apply path runs them (GAP-42).
# - ``BOND_*`` write/mutate the ``bond`` row, and BOND_RELEASE/BOND_SLASH
#   move the bonded value escrow->provider / escrow->burn inside
#   ``_handle_bond_transaction`` — movements outside the generic sender/
#   recipient debit the pure delta would produce (v0.25.8).
# - ``BRIDGE_WITHDRAW`` burns: its payload validation (eth_address, value>0)
#   lives only in the sequential validator, and apply deliberately never
#   creates or credits the pseudo-recipient account — the generic delta
#   would do both (v0.25.8).
SEQUENTIAL_ONLY_TX_TYPES = frozenset(
    {
        "LIQUIDITY_DEPOSIT",
        "LIQUIDITY_WITHDRAW",
        "LIQUIDITY_CLAIM",
        "GPU_REGISTER",
        "GPU_ALLOCATE",
        "GPU_DEREGISTER",
        "GOVERNANCE_EXECUTE",
        "STAKE_RELEASE",
        "BOND_LOCK",
        "BOND_RELEASE",
        "BOND_SLASH",
        # #1198: writes the validator_deactivation marker row — a side-table
        # write the pure delta cannot model; same class as BOND_*.
        "VALIDATOR_DEACTIVATE",
        "BRIDGE_WITHDRAW",
        # v21 (AGENT-SPEND-B-1, #1142): session lifecycle txs write
        # agent_spend_session, and session-bound TRANSFER/ESCROW_LOCK spends
        # charge agent_spend_ledger — side-table writes the delta map cannot
        # model. The block-level parallel paths are already bounded to
        # v2-v8, so no v21 block reaches here; these entries keep direct
        # per-tx callers on the sequential fallback too.
        "AGENT_SESSION_GRANT",
        "AGENT_SESSION_REVOKE",
    }
)


def _determine_tx_type(tx_data: dict[str, Any]) -> str:
    """Determine the transaction type from tx_data.

    Mirrors the logic in state_transition.py:150-161 but without DB access.
    """
    tx_type = tx_data.get("type", "TRANSFER")
    if not tx_type or tx_type == "TRANSFER":
        payload = tx_data.get("payload", {})
        if isinstance(payload, dict):
            tx_type = payload.get("type", "TRANSFER")
    if tx_type:
        return str(tx_type).upper()
    return "TRANSFER"


def _fail_delta(sender: str, recipient: str, error: str, tx_type: str, tx_hash: str) -> StateDelta:
    """Return the standard failure StateDelta shared by every reject path."""
    return StateDelta(
        sender=sender,
        recipient=recipient,
        sender_balance_change=0,
        recipient_balance_change=0,
        sender_nonce_change=0,
        success=False,
        error=error,
        tx_type=tx_type,
        tx_hash=tx_hash,
    )


def _carried_receipt_record(payload: Any, receipt_id: str) -> dict[str, Any] | None:
    """Return the issuance record a RECEIPT_CLAIM carries in ``payload.receipt``, or None.

    A well-formed record lets apply materialise the ``receipt`` row
    deterministically on every node, so a claim seals identically whether or
    not the node ever served the RPC that issued the receipt (previously the
    row had to pre-exist in the local DB, which no live path ever wrote —
    the type was admissible but unsealable, #687). The record never sets
    ``minted_amount``: carried issuance is claim-only — it marks the receipt
    claimed but mints nothing.
    """
    if not isinstance(payload, dict):
        return None
    record = payload.get("receipt")
    if not isinstance(record, dict):
        return None
    if record.get("receipt_id") != receipt_id:
        return None
    miner_signature = record.get("miner_signature")
    if not isinstance(miner_signature, dict) or not miner_signature:
        return None
    attestations = record.get("coordinator_attestations")
    if not isinstance(attestations, list) or not attestations:
        return None
    return record
