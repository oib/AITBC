"""Block-version, transaction-type, account and nonce primitives for ``StateTransition``.

Pure-move split out of ``state_transition.py``: the state-transition facade
re-exports every name defined here, so ``from aitbc_chain.state.state_transition
import X`` keeps working unchanged for all of them.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from sqlmodel import Session, col, func, select

from ..base_models import _to_ait_address
from ..config import settings
from ..logger import get_logger
from ..metrics import metrics_registry
from ..models import Account, Block, Transaction
from .agent_spend import AGENT_SESSION_TX_TYPES

# Keep the historical logger name: these helpers moved out of
# state_transition.py but their log records must stay identical.
logger = get_logger("aitbc_chain.state.state_transition")


# Transaction types that are forbidden from carrying value at consensus level.
# GPU_MARKET is included because every legitimate action (offer,
# software_offer, software_job, cancel, rating) is a value-zero record; there is
# no dedicated branch for it in apply_transaction, so a nonzero amount would
# execute as a plain transfer.
_ZERO_VALUE_TX_TYPES = frozenset(
    {"MESSAGE", "GOVERNANCE_EXECUTE", "GPU_REGISTER", "GPU_ALLOCATE", "GPU_MARKET", "VALIDATOR_DEACTIVATE"}
)

# v25 (#1566): GPURegistration.price_per_hour is Numeric(20,8) — at most 12
# integer digits. The bound mirrors the coordinator-side
# _validated_price_per_hour (#1389/#1566): finite, >= 0, <= column max.
_GPU_PRICE_PER_HOUR_MAX = Decimal("999999999999.99999999")


def _gpu_price_per_hour_in_range(price: Decimal) -> bool:
    """v25 GPU_REGISTER price bound: finite Decimal in [0, Numeric(20,8) max]."""
    return price.is_finite() and Decimal("0") <= price <= _GPU_PRICE_PER_HOUR_MAX


def _is_zero_value_tx_type(tx_type: str, block_version: int) -> bool:
    """Whether ``tx_type`` may not carry value under the rules of ``block_version``.

    GPU_DEREGISTER joins the set from v10 only: below it the name has no consensus meaning and a block carrying it
    replays as the plain transfer it always was.
    """
    if tx_type in _ZERO_VALUE_TX_TYPES or (block_version >= 10 and tx_type == "GPU_DEREGISTER"):
        return True
    # v21: session lifecycle txs move no value — the owner pays only the fee.
    return block_version >= 21 and tx_type in AGENT_SESSION_TX_TYPES


def _ensure_account(session: Session, chain_id: str, address: str) -> Account:
    ait_addr = _to_ait_address(address)
    account = session.get(Account, (chain_id, ait_addr))
    if not account:
        account = Account(chain_id=chain_id, address=ait_addr, balance=0, nonce=0)
        session.add(account)
        session.flush()
    return account


def _tx_type(tx_data: dict[str, Any], tx_record: Transaction | None = None) -> str:
    """Resolve the canonical transaction type from record or tx data."""
    if tx_record and tx_record.type:
        return tx_record.type.upper()
    tx_type = tx_data.get("type", "TRANSFER")
    if not tx_type or tx_type == "TRANSFER":
        payload = tx_data.get("payload", {})
        if isinstance(payload, dict):
            tx_type = payload.get("type", "TRANSFER")
    # str() coercion: a non-string type (e.g. payload.type=123) must not raise —
    # the pure path resolves the same shape via str().upper(), and an
    # AttributeError here is a proposer-stalling crash, not a rejection.
    return str(tx_type or "TRANSFER").upper()


def get_recorded_block_version(block_data_or_block: dict[str, Any] | object) -> int | None:
    """Return the version stamped in ``block_metadata``, or ``None``.

    ``None`` covers both an absent ``state_transition_version`` key and
    malformed/unparseable metadata.
    """
    metadata: Any = None
    if isinstance(block_data_or_block, dict):
        metadata = block_data_or_block.get("block_metadata")
    else:
        metadata = getattr(block_data_or_block, "block_metadata", None)
    if not metadata:
        return None
    try:
        parsed = metadata if isinstance(metadata, dict) else json.loads(metadata)
        version = parsed.get("state_transition_version")
        if version is not None:
            return int(version)
    except (TypeError, ValueError, AttributeError, json.JSONDecodeError):
        pass
    return None


def _log_advisory_stamp(recorded: int | None, height: int, expected: int) -> None:
    """Audit-log the advisory stamp's relation to the height-derived version.

    An absent stamp is expected above v8 — the proposer stamps late and the VC
    re-seal republishes the pre-stamp body — so it logs at debug and is not
    counted as a mismatch (#2279). A present-but-wrong stamp keeps the
    WARNING + ``block_version_stamp_mismatch_total`` — that disagreement is
    the signal the check exists for.
    """
    if recorded is None:
        logger.debug(
            "Block at height %s carries no state_transition_version stamp; using the height-derived version %s",
            height,
            expected,
        )
    elif recorded != expected:
        metrics_registry.increment("block_version_stamp_mismatch_total")
        logger.warning(
            "Block at height %s records state_transition_version=%s; height requires %s — using the height-derived version",
            height,
            recorded,
            expected,
        )


def get_block_version(block_data_or_block: dict[str, Any] | object, height: int = 0) -> int:
    """Return the state-transition rule version that should be used for a block.

    Below the v8 activation height a recorded ``state_transition_version`` in
    ``block_metadata`` wins, and unversioned blocks fall back to the configured
    activation heights so historical blocks replay under the rules that
    produced them.

    At or above v8 the stamp is advisory only: the height-derived version
    always applies. ``block_metadata`` is covered by neither the block hash
    nor the proposer's signature, so trusting the stamp would let any relay
    pick the rules a block is validated under; ignoring it removes the
    dependency on the unauthenticated field entirely. A recorded version that
    disagrees with the height is logged and counted, never obeyed. An absent
    stamp is expected above v8 — the proposer stamps late and the VC re-seal
    republishes the pre-stamp body — so it logs at debug and is not counted
    as a mismatch (#2279).
    """
    recorded = get_recorded_block_version(block_data_or_block)
    v8_threshold = getattr(settings, "state_transition_v8_height", 0)
    if v8_threshold > 0 and height >= v8_threshold:
        expected = get_block_version_for_height(height)
        _log_advisory_stamp(recorded, height, expected)
        return expected
    if recorded is not None:
        return recorded
    v7_threshold = getattr(settings, "state_transition_v7_height", 0)
    if v7_threshold > 0 and height >= v7_threshold:
        return 7
    v6_threshold = getattr(settings, "state_transition_v6_height", 0)
    if v6_threshold > 0 and height >= v6_threshold:
        return 6
    v5_threshold = getattr(settings, "state_transition_v5_height", 0)
    if v5_threshold > 0 and height >= v5_threshold:
        return 5
    v4_threshold = getattr(settings, "state_transition_v4_height", 0)
    if v4_threshold > 0 and height >= v4_threshold:
        return 4
    v3_threshold = getattr(settings, "state_transition_v3_height", 0)
    if v3_threshold > 0 and height >= v3_threshold:
        return 3
    v2_threshold = getattr(settings, "state_transition_v2_height", 0)
    if v2_threshold > 0 and height >= v2_threshold:
        return 2
    return 1


def get_block_version_for_height(height: int) -> int:
    """Return the state-transition rule version a *new* block at ``height`` should use.

    Unlike ``get_block_version``, this does not inspect an existing block's
    metadata. It is used by the proposer to determine which version to stamp into
    the block it is about to build.
    """
    # v9+ thresholds treat any configured value as active; v3-v8 additionally
    # require a positive threshold (their getattr default is 0). v2 inverts:
    # heights *below* its threshold run v1 rules.
    for version in range(27, 2, -1):
        threshold = getattr(settings, f"state_transition_v{version}_height", None)
        if not threshold:
            continue
        if version >= 9:
            if height >= threshold:
                return version
        elif threshold > 0 and height >= threshold:
            return version
    v2_threshold = getattr(settings, "state_transition_v2_height", 0)
    if v2_threshold > 0 and height < v2_threshold:
        return 1
    return 2


BLOCK_SCOPED_PREREGISTERED_RUNG = 26


def block_scoped_preregistered(block_version: int) -> bool:
    """Whether pre-registered bridge mutations are deferred to block apply.

    ``block_version >= 26`` (#2186) makes the deferral unconditional; below it
    the node-local ``block_scoped_preregistered_transactions`` setting decides,
    exactly as before the rung (default true; env-false refused at startup).
    """
    if block_version >= BLOCK_SCOPED_PREREGISTERED_RUNG:
        return True
    return bool(getattr(settings, "block_scoped_preregistered_transactions", True))


def block_scoped_preregistered_for_next_block(session: Session, chain_id: str) -> bool:
    """RPC-side decision matching what the sealing block will do (#2186).

    Resolves the version of the block at ``head + 1`` so an RPC handler defers
    its mutation exactly when apply will. Dormant rung (v26 unset): returns the
    setting without touching the database, byte-identical to the pre-rung path.
    """
    if not getattr(settings, f"state_transition_v{BLOCK_SCOPED_PREREGISTERED_RUNG}_height", None):
        return block_scoped_preregistered(0)
    head = session.exec(select(func.max(Block.height)).where(col(Block.chain_id) == chain_id)).first()
    return block_scoped_preregistered(get_block_version_for_height((head or 0) + 1))


BRIDGE_SIGNED_NONCE_RUNG = 27


def _is_signed_bridge_lock(tx_data: dict[str, Any]) -> bool:
    """True for a ``BRIDGE_LOCK`` carrying the bridge authority's
    ``bridge_signature`` (flat envelope field or inside ``payload``).

    The lock's signature binds the envelope nonce, so v27+ must verify it
    against that nonce (#2252). The type is checked explicitly (resolved the
    way apply resolves it): a non-lock tx that merely carries the field must
    not take this nonce path.
    """
    if _tx_type(tx_data) != "BRIDGE_LOCK":
        return False
    if tx_data.get("bridge_signature"):
        return True
    payload = tx_data.get("payload")
    return isinstance(payload, dict) and bool(payload.get("bridge_signature"))


def use_account_nonce_override(tx_data: dict[str, Any], block_version: int) -> bool:
    """Whether apply-time code must substitute the account's live nonce for the
    tx's recorded nonce before validation.

    Two cases require the substitution:

    - ``block_version < 7``: the parallel-proposal era could seal same-sender
      tx pairs sharing one stored nonce — the second only applied because the
      producer rewrote the nonce to the live account value. Re-importing those
      blocks needs the same rewrite or historical replay diverges.
    - Unsigned internal transactions (preregistered MESSAGE/bridge rows,
      operator-relayed records) carry no signed nonce to enforce; the check
      must not run on a meaningless stored value.

    From v27 (#2252) a ``BRIDGE_LOCK`` carrying a ``bridge_signature`` also
    keeps its envelope nonce: the authority signature binds it, and rewriting
    it made a lock sharing a nonce with an earlier sealed lock fail
    verification. Other tx types keep the existing rule, whatever fields
    they carry.

    For signed transactions at v7+ the envelope nonce is authoritative: the
    signature covers it, and the nonce check enforces it for real instead of
    being a tautology behind the rewrite.
    """
    if block_version < 7:
        return True
    if block_version >= BRIDGE_SIGNED_NONCE_RUNG and _is_signed_bridge_lock(tx_data):
        return False
    return not (tx_data.get("signature") or tx_data.get("sig"))
