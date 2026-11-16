"""Cross-chain bridge transfer — Lock admission gates and ``initiate_transfer`` (mempool + pre-registered lock)."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any


from aitbc.utils.env import is_production

from ..config import settings
from ..logger import get_logger
from ..models import Account, CrossChainTransfer, Transaction
from ..state.bridge_credit import (
    BRIDGE_SIGNATURE_FIELD,
    bridge_credit_private_key,
    sign_bridge_credit,
    sign_bridge_lock,
)
from .bridge_base import BridgeBase
from .bridge_types import BRIDGE_LOCKS_PAUSED_DETAIL, BridgeLocksPausedError, BridgeStatus, BridgeTransfer

logger = get_logger(__name__)


class BridgeTransferIntakeMixin(BridgeBase):
    """Lock admission gates and ``initiate_transfer``."""

    # Protocol base declares the attributes the concrete CrossChainBridge sets.

    BRIDGE_FEE_BASIS_POINTS = 10

    def _enforce_lock_cap(self, amount: int) -> None:
        """Per-lock cap gate for ``initiate_transfer``.

        Fail-closed (BR-3): when locks are enabled and
        ``bridge_max_lock_amount`` is unset or 0 on a production node
        (``ENVIRONMENT``/``APP_ENV``/``NODE_ENV``), the lock is refused with
        an explicit error and a clear log line — an uncapped production node
        can never lock by accident. Development and test environments keep
        the historical "0 = unlimited" behaviour. With a positive cap the
        over-cap lock is refused in every environment.
        """
        max_amount = getattr(settings, "bridge_max_lock_amount", 0)
        if not max_amount:
            if is_production():
                logger.error(
                    "bridge lock refused: BRIDGE_MAX_LOCK_AMOUNT is unset or 0 "
                    "while locks are enabled in production (fail-closed)"
                )
                raise ValueError(
                    "Bridge locks refused: BRIDGE_MAX_LOCK_AMOUNT is unset or 0; "
                    "production nodes must set an explicit per-lock cap"
                )
            return
        if amount > max_amount:
            raise ValueError(f"Amount {amount} exceeds bridge max lock amount {max_amount}")

    def _enforce_signing_key(self, source_chain: str) -> None:
        """BRIDGE-INTAKE-KEY-1 (#675): admission gate on the release-signing key.

        A lock admitted on a host whose process cannot sign emits a
        signature-less ``BRIDGE_LOCK`` that drains-and-skips at apply
        (v9+) and can never sign the ``BRIDGE_RELEASE`` credit
        (v5+) — the Lock-A/Lock-B incidents: the intake looks accepted
        and the transfer silently stalls at release time. Check the key
        *before* any funds move: warn loudly everywhere, refuse the lock
        outright in production (same fail-closed posture as
        ``_enforce_lock_cap`` — a misdirected production intake must fail
        fast instead of vanishing). Development/test environments keep
        the warn-and-proceed behaviour so key-less single-node setups
        still work below the signature heights.

        When an authority is configured (``bridge_release_authority`` /
        ``BRIDGE_RELEASE_AUTHORITY``, falling back to the escrow
        settlement address), the configured key must also derive to that
        address — a wrong key fails validation identically to a missing
        one.
        """
        key = bridge_credit_private_key()
        if key:
            from aitbc.crypto.signature_recovery import canonical_address

            from ..state.bridge_credit import bridge_release_authority_env

            authority = bridge_release_authority_env()
            if authority:
                try:
                    from aitbc.crypto.crypto import derive_ethereum_address

                    derived = canonical_address(derive_ethereum_address(key))
                except (ImportError, ValueError, TypeError, AttributeError) as e:
                    logger.warning(
                        "bridge lock on %s: could not derive address from the configured release signing key (%s); "
                        "the BRIDGE_LOCK/BRIDGE_RELEASE signatures may fail validation",
                        source_chain,
                        e,
                    )
                    return
                if derived != authority:
                    msg = (
                        f"bridge lock refused on {source_chain}: the configured release signing key derives to "
                        f"{derived}, not the bridge release authority {authority} "
                        "(BRIDGE_RELEASE_PRIVATE_KEY/ESCROW_RELEASE_PRIVATE_KEY mismatch); "
                        "locks admitted here would fail signature validation downstream"
                    )
                    if is_production():
                        logger.error(msg)
                        raise ValueError(msg)
                    logger.warning("%s — proceeding anyway (non-production)", msg)
            return
        msg = (
            f"bridge lock on {source_chain}: this process holds no bridge release signing key "
            "(BRIDGE_RELEASE_PRIVATE_KEY/ESCROW_RELEASE_PRIVATE_KEY); the BRIDGE_LOCK is emitted "
            "unsigned and the release credit can never be signed — the transfer will drain-and-skip "
            "at apply and stall at release time"
        )
        if is_production():
            logger.error("%s — refusing the lock (fail-closed)", msg)
            raise ValueError(
                "Bridge locks refused: no release signing key configured "
                "(BRIDGE_RELEASE_PRIVATE_KEY/ESCROW_RELEASE_PRIVATE_KEY); "
                "this node cannot sign the release for admitted locks"
            )
        logger.warning("%s — proceeding anyway (non-production)", msg)

    def _sign_bridge_credit(
        self,
        credit: dict[str, Any],
        tx_hash: str,
        payload: dict[str, Any] | None = None,
        target_chain: str | None = None,
    ) -> None:
        """Attach the bridge authority signature to an issued credit (in place).

        Pre-registered ``Transaction`` rows keep it inside ``payload`` (the row
        has no signature column); flat mempool dicts carry it at top level.
        Consensus verifies it against the ``bridge_release_authority`` chain
        parameter from v5 — a credit issued with no signing key configured
        still records, but will be rejected once v5 is active.
        """
        key = bridge_credit_private_key(target_chain)
        if not key:
            logger.warning(
                "bridge credit issued without a signing key (BRIDGE_RELEASE_PRIVATE_KEY/ESCROW_RELEASE_PRIVATE_KEY); "
                "it will fail v5+ validation"
            )
            return
        signature = sign_bridge_credit(credit, tx_hash, key)
        if payload is not None:
            payload[BRIDGE_SIGNATURE_FIELD] = signature
        else:
            credit[BRIDGE_SIGNATURE_FIELD] = signature

    def _maybe_debit_lock_account(
        self, session: Any, sender_account: Account, total_deduction: int, block_scoped: bool
    ) -> None:
        """Debit the sender for amount+fee on the pre-block-scoped path."""
        if not block_scoped:
            sender_account.balance -= total_deduction
            sender_account.nonce += 1
            session.add(sender_account)

    def _maybe_preregister_lock_tx(
        self,
        session: Any,
        *,
        source_chain: str,
        transfer_id: str,
        sender: str,
        recipient: str,
        target_chain: str,
        amount: int,
        fee: int,
        asset: str,
        lock_nonce: int,
        timestamp: datetime,
        lock_body: dict[str, Any],
        block_scoped: bool,
    ) -> None:
        """Pre-register the confirmed BRIDGE_LOCK row on the non-block-scoped path."""
        if block_scoped:
            return
        lock_tx = Transaction(
            chain_id=source_chain,
            tx_hash=transfer_id,
            sender=sender,
            recipient="bridge_lock",
            payload={
                "type": "BRIDGE_LOCK",
                "transfer_id": transfer_id,
                "target_chain": target_chain,
                "target_recipient": recipient,
                "amount": amount,
                "fee": fee,
                "asset": asset,
                **({BRIDGE_SIGNATURE_FIELD: lock_body[BRIDGE_SIGNATURE_FIELD]} if BRIDGE_SIGNATURE_FIELD in lock_body else {}),
            },
            value=amount,
            fee=fee,
            nonce=lock_nonce,
            timestamp=timestamp,
            block_height=None,
            status="confirmed",
            type="BRIDGE_LOCK",
        )
        session.add(lock_tx)

    def initiate_transfer(
        self,
        source_chain: str,
        target_chain: str,
        sender: str,
        recipient: str,
        amount: int,
        asset: str = "native",
        release_amount: int | None = None,
    ) -> BridgeTransfer:
        """
        Initiate a cross-chain transfer.

        Step 1: Lock funds on source chain

        ``release_amount`` optionally overrides the amount credited on the
        target chain (GAP-47 cross-chain swaps quote a converted amount).
        ``None`` releases the locked amount — the plain bridge behavior.
        """
        # Pause gate — the single chokepoint every lock request funnels
        # through (/bridge/lock, /swap, /cross-chain/bridge). Raising here
        # rather than only in the routes
        # covers internal callers too: while paused no new BRIDGE_LOCK
        # envelope is signed, so no valid lock can reach the mempool —
        # nothing downstream needs to refuse it for the pause to hold.
        if getattr(settings, "bridge_locks_paused", False):
            raise BridgeLocksPausedError(BRIDGE_LOCKS_PAUSED_DETAIL)
        if source_chain == target_chain:
            raise ValueError("Source and target chain must be different")
        if release_amount is not None and release_amount < 0:
            raise ValueError("release_amount must be non-negative")

        self._enforce_lock_cap(amount)

        # BRIDGE-INTAKE-KEY-1 (#675): refuse/warn before any funds move when
        # this process cannot sign the lock (v9) or the release credit (v5).
        self._enforce_signing_key(source_chain)

        # v0.24.1: bridge locks must be initiated on the node that produces
        # the source chain. Initiating a lock on a follower would update the
        # local follower DB, which is then overwritten by the next state sync
        # from the producer, producing state-root mismatches and unlocked
        # source funds.  Single-node tests do not set a default peer, so the
        # guard is skipped when there is no upstream RPC to follow.
        has_peer = bool(getattr(settings, "default_peer_rpc_url", None))
        if has_peer:
            local_chains = [
                c.strip() for c in (getattr(settings, "block_production_chains", "") or "").split(",") if c.strip()
            ]
            if source_chain not in local_chains:
                raise ValueError(
                    f"Source chain {source_chain} is not produced by this node; initiate the lock on the source chain producer"
                )

        transfer_id = self._generate_transfer_id(source_chain, target_chain, sender, recipient, amount, int(time.time()))
        with self._session_for(source_chain) as session:
            sender_account = session.get(Account, (source_chain, sender))
            if not sender_account:
                raise ValueError(f"Sender account not found: {sender}")
            fee = amount * self.BRIDGE_FEE_BASIS_POINTS // 10000
            total_deduction = amount + fee
            if sender_account.balance < total_deduction:
                raise ValueError(f"Insufficient balance: {sender_account.balance} < {total_deduction}")
            lock_nonce = sender_account.nonce
            block_scoped = getattr(settings, "block_scoped_preregistered_transactions", True)
            self._maybe_debit_lock_account(session, sender_account, total_deduction, block_scoped)

            # v0.7.3: put the bridge lock in the mempool so the next block
            # produced by this node will include it and anchor the event in a
            # real block header.
            from ..mempool import get_mempool

            timestamp = datetime.now(UTC)
            # v9: the lock carries the bridge authority's signature over its
            # semantic fields (state/bridge_credit.py) — a forged lock was a
            # theft of the target-chain credit. `chain_id` travels inside the
            # body because the signed message binds source_chain from it; the
            # pre-registered row's chain_id column produces the same field.
            lock_body = {
                "from": sender,
                "to": "bridge_lock",
                "amount": amount,
                "fee": fee,
                "type": "BRIDGE_LOCK",
                "transfer_id": transfer_id,
                "target_chain": target_chain,
                "target_recipient": recipient,
                "asset": asset,
                "nonce": lock_nonce,
                "chain_id": source_chain,
                "timestamp": timestamp.isoformat(),
            }
            lock_key = bridge_credit_private_key()
            if lock_key:
                lock_body[BRIDGE_SIGNATURE_FIELD] = sign_bridge_lock(lock_body, transfer_id, lock_key)
            else:
                logger.warning(
                    "BRIDGE_LOCK issued without a signing key (BRIDGE_RELEASE_PRIVATE_KEY/ESCROW_RELEASE_PRIVATE_KEY); "
                    "it will fail v9+ validation"
                )
            mempool = get_mempool()
            mempool.add(
                lock_body,
                chain_id=source_chain,
                tx_hash=transfer_id,
            )

            self._maybe_preregister_lock_tx(
                session,
                source_chain=source_chain,
                transfer_id=transfer_id,
                sender=sender,
                recipient=recipient,
                target_chain=target_chain,
                amount=amount,
                fee=fee,
                asset=asset,
                lock_nonce=lock_nonce,
                timestamp=timestamp,
                lock_body=lock_body,
                block_scoped=block_scoped,
            )
            transfer_record = CrossChainTransfer(
                transfer_id=transfer_id,
                source_chain=source_chain,
                target_chain=target_chain,
                sender=sender,
                recipient=recipient,
                amount=amount,
                asset=asset,
                status="pending",
                source_tx_hash=transfer_id,
                lock_time=datetime.now(UTC),
                release_amount=release_amount,
            )
            session.add(transfer_record)
            session.commit()
            # #696: write-through register with the shared ledger service —
            # fire-and-log; a ledger outage never fails the lock and the
            # local row remains the fallback cache.
            self._ledger_register(transfer_record)
            transfer = BridgeTransfer(
                transfer_id=transfer_id,
                source_chain=source_chain,
                target_chain=target_chain,
                sender=sender,
                recipient=recipient,
                amount=amount,
                asset=asset,
                status=BridgeStatus.locked,
                source_tx_hash=transfer_id,
                target_tx_hash=None,
                lock_time=datetime.now(UTC),
                confirm_time=None,
                proof=None,
            )
            self._pending_transfers[transfer_id] = transfer
            logger.info(
                "Bridge transfer initiated: %s... %s from %s to %s", transfer_id[:16], amount, source_chain, target_chain
            )
            return transfer
