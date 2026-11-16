"""Payload-auth binding checks and stake-release lock validation.

Pure-move split out of ``state_transition.py``: the state-transition facade
re-exports every name defined here, so ``from aitbc_chain.state.state_transition
import X`` keeps working unchanged for all of them.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func
from sqlmodel import Session, select

from ..base_models import Block, _to_ait_address
from ..models import Transaction


# Address fields the staking RPCs put the authorized party under: consensus
# staking signs {"address": ...}; agent staking is operator-signed with the
# user under "user_address" (or "staker_address").
_AUTH_ADDRESS_FIELDS = ("address", "user_address", "staker_address", "creator_address")


def _payload_auth_named_addresses(message: dict[str, Any]) -> set[str]:
    """Return the normalized addresses the signed message names."""
    named: set[str] = set()
    for field in _AUTH_ADDRESS_FIELDS:
        raw = message.get(field)
        if not raw:
            continue
        try:
            named.add(_to_ait_address(str(raw)))
        except (TypeError, ValueError):
            continue
    return named


def _payload_auth_binds_transfer(tx_type: str, message: dict[str, Any], tx_data: dict[str, Any]) -> bool:
    """Check that a verified auth message names the transfer it authorizes.

    All deterministic context binding lives here so a captured signature
    cannot be re-attached to a different transfer:

    - party: the message must name the account a ``STAKE_LOCK`` debits or the
      account a ``STAKE_RELEASE`` credits (the release sender is the keyless
      escrow, so the payee is the authorized party).
    - chain: a message carrying ``chain_id`` must match the tx's chain.
    - action: a message carrying ``action`` must match the transfer type, so
      a "stake" signature cannot ride a release.
    - amount: a lock's message amount must equal the transferred value.
    - stake: a release's message ``stake_id`` must equal the payload's
      ``stake_id``/``agent_stake_id``; for locks the field is optional (the
      consensus-staking row id is assigned after signing) but must match
      when both sides carry it.
    - bounty: ``BOUNTY_LOCK`` binds the creator and ``reward_amount``;
      ``BOUNTY_REFUND`` binds the refunded payee; ``BOUNTY_PAYOUT`` is
      operator-signed and the payee is resolved server-side, so it binds
      ``submission_id`` instead. ``bounty_id`` must match whenever the
      signed message carries it.
    """
    role = _payload_auth_role(tx_type)
    if role is None:
        return False
    party, expected_action = role
    if not _payload_auth_party_binds(party, message, tx_data):
        return False
    if not _payload_auth_chain_action_binds(message, tx_data, expected_action):
        return False
    if not _payload_auth_amount_binds(tx_type, message, tx_data):
        return False
    return _payload_auth_ids_binds(tx_type, message, tx_data.get("payload") or {})


def _payload_auth_role(tx_type: str) -> tuple[str | None, str] | None:
    """(party field, expected action) for the transfer type, or None."""
    if tx_type in ("STAKE_LOCK", "BOUNTY_LOCK"):
        return ("from", "stake")
    if tx_type in ("STAKE_RELEASE", "BOUNTY_REFUND"):
        return ("to", "unstake")
    if tx_type == "BOUNTY_PAYOUT":
        # operator-signed; the payee is resolved server-side
        return (None, "")
    return None


def _payload_auth_party_binds(party_field: str | None, message: dict[str, Any], tx_data: dict[str, Any]) -> bool:
    """The message must name the account the transfer debits/credits."""
    if party_field is None:
        return True
    party = tx_data.get(party_field)
    if not party:
        return True  # absent party field skips the binding, as before
    try:
        bound_party = _to_ait_address(str(party))
    except (TypeError, ValueError):
        return False
    return bound_party in _payload_auth_named_addresses(message)


def _payload_auth_chain_action_binds(message: dict[str, Any], tx_data: dict[str, Any], expected_action: str) -> bool:
    """A message's chain_id/action, when present, must match the transfer."""
    if message.get("chain_id") is not None and str(message.get("chain_id")) != str(tx_data.get("chain_id")):
        return False
    return "action" not in message or message.get("action") == expected_action


def _payload_auth_amount_binds(tx_type: str, message: dict[str, Any], tx_data: dict[str, Any]) -> bool:
    """A lock's signed amount must equal the transferred value."""
    if tx_type not in ("STAKE_LOCK", "BOUNTY_LOCK"):
        return True
    amount = message.get("amount", message.get("additional_amount", message.get("reward_amount")))
    value = tx_data.get("value", tx_data.get("amount", 0))
    try:
        return amount is not None and int(amount) == int(value)
    except (TypeError, ValueError):
        return False


def _payload_auth_ids_binds(tx_type: str, message: dict[str, Any], payload: dict[str, Any]) -> bool:
    """stake_id / bounty_id / submission_id / lock_tx_hashes cross-checks."""
    msg_stake = message.get("stake_id")
    tx_stake = payload.get("stake_id") or payload.get("agent_stake_id")
    if tx_type == "STAKE_RELEASE":
        if msg_stake is None or tx_stake is None or str(msg_stake) != str(tx_stake):
            return False
    elif msg_stake is not None and tx_stake is not None and str(msg_stake) != str(tx_stake):
        return False
    msg_bounty = message.get("bounty_id")
    tx_bounty = payload.get("bounty_id")
    if tx_type == "BOUNTY_LOCK":
        if msg_bounty is None or tx_bounty is None or str(msg_bounty) != str(tx_bounty):
            return False
    elif msg_bounty is not None and tx_bounty is not None and str(msg_bounty) != str(tx_bounty):
        return False
    if tx_type == "BOUNTY_PAYOUT":
        msg_sub = message.get("submission_id")
        tx_sub = payload.get("submission_id")
        if msg_sub is None or tx_sub is None or str(msg_sub) != str(tx_sub):
            return False
    return _payload_auth_lock_hashes_binds(message, payload)


def _payload_auth_lock_hashes_binds(message: dict[str, Any], payload: dict[str, Any]) -> bool:
    """lock_tx_hashes bind only when the signed message names them — the
    user-staking route signs them, operator-signed agent releases predate the
    field and must not break."""
    msg_locks = message.get("lock_tx_hashes")
    tx_locks = payload.get("lock_tx_hashes")
    if msg_locks is not None and tx_locks is not None:
        if sorted(str(h) for h in msg_locks) != sorted(str(h) for h in tx_locks):
            return False
    return True


# Blocks per day at the chain's fixed 60s cadence — deterministic across nodes,
# unlike wall-clock timestamps which the proposer controls.
_STAKE_LOCK_BLOCKS_PER_DAY = 1440


def _validate_stake_release_locks(
    session: Session,
    chain_id: str,
    tx_data: dict[str, Any],
    tx_hash: str,
    value: int,
    recipient_addr: str,
) -> tuple[bool, str]:
    """v4 consensus check: a STAKE_RELEASE must fully reference matured locks.

    ``payload.lock_tx_hashes`` names the confirmed STAKE_LOCK transactions this
    release spends. Every lock must exist, belong to the payee, and — when it
    declares ``lock_days`` — have been sealed for at least that many days at the
    fixed 60s block cadence. Locks with no ``lock_days`` (legacy, agent stakes,
    auto-stake top-ups) are treated as matured. The claimed lock set must not
    overlap any already-sealed release, and the summed principal must cover the
    release value.
    """
    claimed = _claimed_lock_hashes(tx_data, tx_hash)
    if isinstance(claimed, str):
        return (False, claimed)

    locks = _load_claimed_locks(session, chain_id, claimed, recipient_addr, tx_hash, value)
    if isinstance(locks, str):
        return (False, locks)

    matured = _claimed_locks_matured(session, chain_id, locks, value, tx_hash)
    if isinstance(matured, str):
        return (False, matured)

    return _claimed_locks_unspent(session, chain_id, claimed, tx_hash)


def _claimed_lock_hashes(tx_data: dict[str, Any], tx_hash: str) -> set[str] | str:
    """Normalize + validate ``payload.lock_tx_hashes``; error string on failure."""
    payload = tx_data.get("payload") or {}
    raw_hashes = payload.get("lock_tx_hashes")
    if not isinstance(raw_hashes, list) or not raw_hashes or not all(isinstance(h, str) and h for h in raw_hashes):
        return f"STAKE_RELEASE {tx_hash} payload must carry a non-empty lock_tx_hashes list"
    claimed = {h.lower() for h in raw_hashes}
    if len(claimed) != len(raw_hashes):
        return f"STAKE_RELEASE {tx_hash} lock_tx_hashes contains duplicates"
    return claimed


def _load_claimed_locks(
    session: Session,
    chain_id: str,
    claimed: set[str],
    recipient_addr: str,
    tx_hash: str,
    value: int,
) -> list[Transaction] | str:
    """Fetch each claimed lock; verify existence, payee, and principal coverage."""
    locks: list[Transaction] = []
    for h in claimed:
        lock = session.exec(
            select(Transaction).where(
                Transaction.chain_id == chain_id,
                func.lower(Transaction.tx_hash) == h,
                Transaction.type == "STAKE_LOCK",
                Transaction.block_height.is_not(None),  # type: ignore[union-attr]
            )
        ).first()
        if lock is None:
            return f"STAKE_RELEASE {tx_hash} references unknown or unconfirmed lock {h}"
        if _to_ait_address(lock.sender or "") != recipient_addr:
            return f"STAKE_RELEASE {tx_hash} lock {h} belongs to {lock.sender}, not payee {recipient_addr}"
        locks.append(lock)

    locked_total = sum(int(lock.value or 0) for lock in locks)
    if locked_total < value:
        return f"STAKE_RELEASE {tx_hash} value {value} exceeds locked principal {locked_total}"
    return locks


def _claimed_locks_matured(
    session: Session,
    chain_id: str,
    locks: list[Transaction],
    value: int,
    tx_hash: str,
) -> str | None:
    """Verify every ``lock_days`` window has elapsed at the next block height."""
    parent_height = session.exec(select(func.max(Block.height)).where(Block.chain_id == chain_id)).one()
    next_height = (parent_height or 0) + 1
    for lock in locks:
        lock_payload = lock.payload or {}
        lock_days = lock_payload.get("lock_days")
        if lock_days in (None, 0):
            continue  # legacy / agent / auto-stake locks carry no window
        try:
            unlock_height = int(lock.block_height or 0) + int(str(lock_days)) * _STAKE_LOCK_BLOCKS_PER_DAY
        except (TypeError, ValueError):
            return f"STAKE_RELEASE {tx_hash} lock {lock.tx_hash} has invalid lock_days"
        if next_height < unlock_height:
            return f"STAKE_RELEASE {tx_hash} lock {lock.tx_hash} matures at height {unlock_height}, current {next_height}"
    return None


def _claimed_locks_unspent(
    session: Session,
    chain_id: str,
    claimed: set[str],
    tx_hash: str,
) -> tuple[bool, str]:
    """A lock may be spent only once: no sealed release may name any claimed hash."""
    # Pending same-block duplicates are a mempool-policy concern (mempool drops
    # them); only confirmed history is consensus state.
    for prior in session.exec(
        select(Transaction).where(
            Transaction.chain_id == chain_id,
            Transaction.type == "STAKE_RELEASE",
            Transaction.block_height.is_not(None),  # type: ignore[union-attr]
            Transaction.tx_hash != tx_hash,
        )
    ).all():
        prior_hashes = (prior.payload or {}).get("lock_tx_hashes") or []
        if claimed & {str(h).lower() for h in prior_hashes}:
            return (False, f"STAKE_RELEASE {tx_hash} lock already released by {prior.tx_hash}")
    return (True, "")
