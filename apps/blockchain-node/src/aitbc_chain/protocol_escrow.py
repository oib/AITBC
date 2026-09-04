"""Protocol-owned escrow addresses and the queue helper for protocol transfers.

Staking and bounty balances used to be moved by the RPC handlers themselves:
the handler opened a session, did ``account.balance -= amount`` and committed.
That is the same defect class that froze the fleet on 2026-09-03. The block
header ``state_root`` is a full scan of the ``account`` table
(``state.state_root_utils.compute_state_root_full``), so any balance committed
outside block processing makes the computed root disagree with the parent
header and the proposer refuses to build with "Parent state mismatch".

The fix is the one the bond subsystem already uses: value moves only inside a
block, by an ordinary transfer to or from a protocol escrow address.

* A *lock* is a transfer ``user -> escrow``.
* A *release* is a transfer ``escrow -> user``.

Both are ordinary transfers as far as consensus is concerned, so they need no
new transaction type in the state transition: ``poa`` fills in the sender's
nonce from the account, the state transition creates the recipient on first
credit, and followers replay the identical transfer through
``sync_block_import``. The ``type`` field is descriptive only -- it exists so
the transaction is legible in explorers and logs.

The escrow addresses are derived from a keccak label and therefore have **no
private key**. Nobody can produce a signature that recovers to one, so a
release can never be forged through ``/rpc/transaction`` (which verifies the
signature against the sender before admitting anything to the mempool). Only
this node's own code can originate one. That is the same property that makes
the FAUCET magic sender safe.
"""

from __future__ import annotations

import os
from typing import Any

from eth_utils import keccak

from aitbc.crypto.signature_recovery import canonical_address

from .base_models import _to_ait_address


def _derive(env_var: str, label: bytes) -> str:
    configured = os.getenv(env_var, "")
    if configured:
        return canonical_address(configured)
    return canonical_address("0x" + keccak(label).hex()[:40])


# Consensus staking (/rpc/staking/stake) and the agent-economy stake records
# share one escrow: both hold user principal that is returned on withdrawal.
_STAKE_ESCROW_ADDRESS = _derive("STAKE_ESCROW_ADDRESS", b"aitbc.stake.escrow")
_BOUNTY_ESCROW_ADDRESS = _derive("BOUNTY_ESCROW_ADDRESS", b"aitbc.bounty.escrow")
_HTLC_ESCROW_ADDRESS = _derive("HTLC_ESCROW_ADDRESS", b"aitbc.htlc.escrow")


def stake_escrow_address() -> str:
    """AIT-form address of the staking escrow."""
    return _to_ait_address(_STAKE_ESCROW_ADDRESS)


def bounty_escrow_address() -> str:
    """AIT-form address of the bounty escrow."""
    return _to_ait_address(_BOUNTY_ESCROW_ADDRESS)


def htlc_escrow_address() -> str:
    """AIT-form address of the cross-chain HTLC escrow."""
    return _to_ait_address(_HTLC_ESCROW_ADDRESS)


def is_protocol_escrow(address: str) -> bool:
    """Return True if ``address`` is one of the keyless protocol escrows."""
    try:
        canonical = canonical_address(address)
    except Exception:
        return False
    return canonical in {_STAKE_ESCROW_ADDRESS, _BOUNTY_ESCROW_ADDRESS, _HTLC_ESCROW_ADDRESS}


def queue_protocol_transfer(
    *,
    sender: str,
    recipient: str,
    amount: int,
    chain_id: str,
    tx_type: str,
    payload: dict[str, Any] | None = None,
) -> str:
    """Queue a protocol-initiated transfer and return its transaction hash.

    The balance change happens when the transaction is included in a block --
    never here. Callers must not touch the ``account`` table themselves.

    The transaction carries no signature. That is deliberate and safe: the
    state transition only verifies a signature when one is present, and the
    public submit endpoint rejects anything whose signature does not recover to
    the sender, so an unsigned transfer cannot be injected from outside. The
    fee is 0 because these are protocol-internal movements of the user's own
    principal, matching BOND_RELEASE and BOND_SLASH.
    """
    if amount <= 0:
        raise ValueError(f"Protocol transfer amount must be positive, got {amount}")

    from .mempool import get_mempool

    tx_data: dict[str, Any] = {
        "from": _to_ait_address(sender),
        "to": _to_ait_address(recipient),
        "amount": int(amount),
        "fee": 0,
        # Overwritten by the proposer with the sender account's current nonce.
        "nonce": 0,
        "type": tx_type,
        "payload": payload or {},
        "chain_id": chain_id,
    }
    return get_mempool().add(tx_data, chain_id=chain_id)


def protocol_transfer_confirmed(
    session: Any,
    chain_id: str,
    tx_type: str,
    payload_key: str,
    payload_value: Any,
) -> bool:
    """Return True once the identified lock transaction is in a block.

    A release must never be queued against a lock that has not landed. The
    domain rows (``stake``, ``agent_stake``, ``bounty_contract``) are written by
    the RPC handler as soon as the lock is queued, because they are not part of
    the state root and so cannot desynchronise it -- but that means a row can
    exist while its funds are still in the mempool, or while the lock has been
    dropped outright (the proposer skips a transfer whose sender has since spent
    the balance). Releasing on the strength of the row alone would pay out of
    the shared escrow, taking principal that belongs to other stakers.

    Matching is by payload key rather than a stored hash so that no column has
    to be added to tables the migration chain cannot rebuild.
    """
    from sqlmodel import select

    from .models import Transaction

    candidates = session.exec(
        select(Transaction).where(
            Transaction.chain_id == chain_id,
            Transaction.type == tx_type,
            Transaction.block_height.is_not(None),  # type: ignore[union-attr]
        )
    ).all()
    for tx in candidates:
        payload = tx.payload or {}
        if str(payload.get(payload_key, "")) == str(payload_value):
            return True
    return False


def confirmed_lock_total(
    session: Any,
    chain_id: str,
    tx_type: str,
    payload_key: str,
    payload_value: Any,
) -> int:
    """Total value of the confirmed lock transfers tagged with this key.

    A stake can be topped up, so a single boolean is not enough to authorise a
    release: the escrow must actually hold the full principal being returned.
    Callers compare this against the record amount before queueing a release.
    """
    from sqlmodel import select

    from .models import Transaction

    total = 0
    candidates = session.exec(
        select(Transaction).where(
            Transaction.chain_id == chain_id,
            Transaction.type == tx_type,
            Transaction.block_height.is_not(None),  # type: ignore[union-attr]
        )
    ).all()
    for tx in candidates:
        payload = tx.payload or {}
        if str(payload.get(payload_key, "")) == str(payload_value):
            total += int(tx.value or 0)
    return total
