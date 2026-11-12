"""State-delta apply helpers for ``StateTransition.apply_transaction`` (#1867 pure-move split).

Import ``aitbc_chain.state.state_transition`` first (it wires these
mixins into ``StateTransition``); this module is not meant to be imported
directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from . import state_transition as _st

from ..base_models import _to_ait_address
from ..models import Account, Receipt
from .agent_spend import AGENT_SESSION_TX_TYPES, apply_agent_session_tx, charge_agent_spend
from .liquidity_transition import apply_liquidity_claim, apply_liquidity_deposit, apply_liquidity_withdraw
from .pure_state_transition import _carried_receipt_record
from datetime import UTC, datetime
from sqlalchemy import text
from sqlmodel import Session, select
from typing import Any
from .state_transition import (
    _cache,
    _ensure_account,
    _escrow_address,
    _get_escrow_lock_block_version,
    _is_zero_value_tx_type,
    logger,
)


class _ApplyMixin:
    if TYPE_CHECKING:
        _processed_nonces: dict[str, int]
        _processed_tx_hashes: set[str]

        def _handle_bond_transaction(
            self,
            session: Session,
            chain_id: str,
            tx_data: dict[str, Any],
            tx_hash: str,
            tx_type: str,
            sender_addr: str,
            recipient_addr: str,
            value: int,
            block_height: int | None = None,
            *,
            block_version: int | None = None,
            block_time: datetime | None = None,
        ) -> str | None: ...
        def _handle_governance_execute(
            self,
            session: Session,
            chain_id: str,
            tx_data: dict[str, Any],
            tx_hash: str,
            block_height: int | None = None,
            block_version: int = 2,
        ) -> None: ...
        def _handle_ipfs_subscription(
            self, session: Session, chain_id: str, tx_data: dict[str, Any], tx_hash: str, sender_addr: str
        ) -> None: ...
        def _handle_validator_deactivation(
            self,
            session: Session,
            chain_id: str,
            tx_data: dict[str, Any],
            tx_hash: str,
            sender_addr: str,
            value: int,
            block_height: int | None = None,
            block_time: datetime | None = None,
        ) -> str | None: ...
        def handle_gpu_allocation(
            self, session: Session, chain_id: str, allocation_data: dict[str, Any]
        ) -> tuple[bool, str]: ...
        def handle_gpu_deregistration(self, session: Session, chain_id: str, gpu_data: dict[str, Any]) -> tuple[bool, str]: ...
        def handle_gpu_registration(
            self, session: Session, chain_id: str, gpu_data: dict[str, Any], block_version: int = 1
        ) -> tuple[bool, str]: ...

    def _apply_special_transfer(
        self,
        session: Session,
        chain_id: str,
        tx_data: dict[str, Any],
        tx_hash: str,
        tx_type: str,
        sender_addr: str,
        recipient_addr: str,
        value: int,
        fee: int,
        *,
        block_version: int,
        block_time: datetime | None,
    ) -> tuple[bool, str] | None:
        """Early-return transfer types that bypass the generic debit/credit:
        the three liquidity legs and the pre-registered bridge flows."""
        liquidity_fn = {
            "LIQUIDITY_DEPOSIT": apply_liquidity_deposit,
            "LIQUIDITY_CLAIM": apply_liquidity_claim,
            "LIQUIDITY_WITHDRAW": apply_liquidity_withdraw,
        }.get(tx_type)
        if liquidity_fn is not None:
            ok, msg = liquidity_fn(
                session, chain_id, tx_data, tx_hash, _cache, block_version=block_version, block_time=block_time
            )
            if ok:
                self._processed_tx_hashes.add(tx_hash)
            return (ok, msg)
        if tx_type in {"BRIDGE_RELEASE", "BRIDGE_REFUND"}:
            return self._apply_bridge_credit_tx(session, chain_id, tx_hash, tx_type, sender_addr, recipient_addr, value, fee)
        if tx_type in {"BRIDGE_LOCK", "BRIDGE_WITHDRAW"}:
            return self._apply_bridge_debit_tx(session, chain_id, tx_data, tx_hash, tx_type, sender_addr, value, fee)
        return None

    def _apply_bridge_credit_tx(
        self,
        session: Session,
        chain_id: str,
        tx_hash: str,
        tx_type: str,
        sender_addr: str,
        recipient_addr: str,
        value: int,
        fee: int,
    ) -> tuple[bool, str]:
        # Pre-registered credit transactions: the sender is a magic string
        # (bridge_release/bridge_refund) and does not have an account.
        # Only the recipient is credited.
        # Pre-registered credit transactions: the sender is a magic string
        # (bridge_release/bridge_refund) and does not have an account.
        # Only the recipient is credited.
        _ensure_account(session, chain_id, recipient_addr)
        logger.info("Updating recipient balance: %s += %s", recipient_addr, value)
        session.execute(
            text("UPDATE account SET balance = balance + :value WHERE chain_id = :chain_id AND address = :recipient_addr"),
            {"value": value, "chain_id": chain_id, "recipient_addr": recipient_addr},
        )
        self._processed_tx_hashes.add(tx_hash)
        if _cache and _cache.is_available():
            _cache.delete(f"account_balance:{chain_id}:{recipient_addr.lower()}")
            _cache.delete(f"account_details:{chain_id}:{recipient_addr.lower()}")
        logger.info(
            "Applied %s transaction %s: %s -> %s, value=%s, fee=%s",
            tx_type,
            tx_hash,
            sender_addr,
            recipient_addr,
            value,
            fee,
        )
        return (True, "Transaction applied successfully")

    def _apply_bridge_debit_tx(
        self,
        session: Session,
        chain_id: str,
        tx_data: dict[str, Any],
        tx_hash: str,
        tx_type: str,
        sender_addr: str,
        value: int,
        fee: int,
    ) -> tuple[bool, str]:
        if tx_type == "BRIDGE_LOCK":
            # Pre-registered bridge lock: debit the sender and increment the nonce.
            # The locked value is not credited to any account; it is recorded in the
            # CrossChainTransfer table. No bridge_lock account is created.
            verb = "lock"
        else:
            # Burn AIT from the sender and increase the nonce. The off-chain
            # bridge monitor is responsible for releasing ETH to payload.eth_address.
            verb = "withdraw"
        _ensure_account(session, chain_id, sender_addr)
        total_cost = value + fee
        logger.info("Bridge %s: %s -= %s, nonce += 1", verb, sender_addr, total_cost)
        session.execute(
            text(
                "UPDATE account SET balance = balance - :total_cost, nonce = nonce + 1 WHERE chain_id = :chain_id AND address = :sender_addr"
            ),
            {"total_cost": total_cost, "chain_id": chain_id, "sender_addr": sender_addr},
        )
        self._processed_tx_hashes.add(tx_hash)
        if _cache and _cache.is_available():
            _cache.delete(f"account_balance:{chain_id}:{sender_addr.lower()}")
            _cache.delete(f"account_details:{chain_id}:{sender_addr.lower()}")
        if tx_type == "BRIDGE_WITHDRAW":
            logger.info(
                "Applied %s transaction %s: %s, value=%s, fee=%s, eth_address=%s",
                tx_type,
                tx_hash,
                sender_addr,
                value,
                fee,
                (tx_data.get("payload") or {}).get("eth_address"),
            )
        else:
            logger.info(
                "Applied %s transaction %s: %s, value=%s, fee=%s",
                tx_type,
                tx_hash,
                sender_addr,
                value,
                fee,
            )
        return (True, "Transaction applied successfully")

    def _escrow_lock_redirect(
        self,
        session: Session,
        chain_id: str,
        tx_data: dict[str, Any],
        tx_type: str,
        recipient_addr: str,
        block_version: int,
    ) -> str:
        """ESCROW_LOCK (v2+) account pre-creation and the v3 per-escrow
        recipient redirect. Returns the recipient the balance update should
        credit — the escrow custody address for v3+ job locks."""
        if tx_type != "ESCROW_LOCK" or block_version < 2:
            return recipient_addr
        # v0.25.5: the Escrow DB record references the provider address, so
        # ensure the provider account exists even though the lock itself only
        # transfers from buyer to the node wallet. Older v1 blocks (pre this
        # fix) do not create the provider account, so replaying them must
        # keep the original state-root behavior.
        provider_addr = _to_ait_address((tx_data.get("payload") or {}).get("provider", ""))
        if provider_addr:
            _ensure_account(session, chain_id, provider_addr)
        # S-4 (v3): redirect the locked value to a deterministic per-escrow
        # address so the node wallet's spendable balance never includes
        # escrowed funds. The escrow address has no known key — funds can
        # only leave via ESCROW_RELEASE or ESCROW_REFUND.
        if block_version >= 3:
            job_id = (tx_data.get("payload") or {}).get("job_id", "")
            if job_id:
                escrow_addr = _escrow_address(job_id)
                _ensure_account(session, chain_id, escrow_addr)
                # Override the recipient for the balance update below.
                return escrow_addr
        return recipient_addr

    def _apply_core_transfer(
        self,
        session: Session,
        chain_id: str,
        tx_data: dict[str, Any],
        tx_type: str,
        sender_addr: str,
        recipient_addr: str,
        value: int,
        fee: int,
        block_version: int,
    ) -> tuple[Account | None, str]:
        """Generic debit/credit: sender pays value+fee (fee only for zero-value
        types), recipient is credited unless MESSAGE. Returns the sender ORM
        row (pre-raw-SQL snapshot, as before) and the possibly escrow-redirected
        recipient."""
        recipient_addr = self._escrow_lock_redirect(session, chain_id, tx_data, tx_type, recipient_addr, block_version)
        sender_account = session.get(Account, (chain_id, sender_addr))
        _MAX_INT64 = 2**63 - 1

        if _is_zero_value_tx_type(tx_type, block_version):
            total_cost = fee
        else:
            total_cost = value + fee
            if total_cost > _MAX_INT64:
                raise ValueError(f"Transaction total_cost overflow: {total_cost}")
            # v0.25.5: auto-create the recipient account on first credit so
            # release/refund/transfer to a new address is deterministic across
            # validators and does not require a direct RPC write. This only
            # applies to v2 blocks; v1 blocks keep the original account set.
            if block_version >= 2:
                _ensure_account(session, chain_id, recipient_addr)
        logger.info("Updating sender balance: %s -= %s", sender_addr, total_cost)
        session.execute(
            text(
                "UPDATE account SET balance = balance - :total_cost, nonce = nonce + 1 WHERE chain_id = :chain_id AND address = :sender_addr"
            ),
            {"total_cost": total_cost, "chain_id": chain_id, "sender_addr": sender_addr},
        )
        if tx_type != "MESSAGE":
            logger.info("Updating recipient balance: %s += %s", recipient_addr, value)
            session.execute(
                text("UPDATE account SET balance = balance + :value WHERE chain_id = :chain_id AND address = :recipient_addr"),
                {"value": value, "chain_id": chain_id, "recipient_addr": recipient_addr},
            )
        session.flush()
        return sender_account, recipient_addr

    def _apply_escrow_custody_effects(
        self,
        session: Session,
        chain_id: str,
        tx_data: dict[str, Any],
        tx_type: str,
        value: int,
        sender_addr: str,
        recipient_addr: str,
        block_version: int,
    ) -> None:
        """S-4/v11 custody fix-ups that run after the generic debit/credit:
        release/refund pays from the per-escrow address for v3+ locks, and the
        v11+ fee sweep always pays from custody."""
        if tx_type in ("ESCROW_RELEASE", "ESCROW_REFUND"):
            # S-4: move funds FROM the per-escrow address only when the lock was
            # itself a v3 per-escrow lock. Legacy v2 locks keep the value in the
            # node wallet, so the generic debit/credit above is already correct.
            job_id = (tx_data.get("payload") or {}).get("job_id", "")
            if job_id:
                lock_version = _get_escrow_lock_block_version(session, chain_id, job_id)
                if lock_version is None:
                    lock_version = 2 if block_version < 3 else 3
                if lock_version >= 3:
                    self._escrow_custody_payout(
                        session, chain_id, tx_type, job_id, value, sender_addr, recipient_addr, block_version, swept=False
                    )
        if tx_type == "ESCROW_FEE_SWEEP" and block_version >= 11:
            # v11: same custody fix-up as the v3 release/refund branch above,
            # but unconditional — no lock lookup (a sweep is bookkeeping over
            # the custody account alone, and a v2-era job has no custody
            # account, so its balance check already refused at validate).
            job_id = (tx_data.get("payload") or {}).get("job_id", "")
            if job_id:
                self._escrow_custody_payout(
                    session, chain_id, tx_type, job_id, value, sender_addr, recipient_addr, block_version, swept=True
                )

    def _escrow_custody_payout(
        self,
        session: Session,
        chain_id: str,
        tx_type: str,
        job_id: str,
        value: int,
        sender_addr: str,
        recipient_addr: str,
        block_version: int,
        *,
        swept: bool,
    ) -> None:
        """Pay ``value`` to the recipient from the per-escrow custody account.

        The generic path above debited the sender for value+fee and credited
        the recipient for value. Undo both — the sender keeps only the fee
        debit — then pay the recipient from custody.
        """
        escrow_addr = _escrow_address(job_id)
        session.execute(
            text("UPDATE account SET balance = balance - :value WHERE chain_id = :chain_id AND address = :recipient_addr"),
            {"value": value, "chain_id": chain_id, "recipient_addr": recipient_addr},
        )
        session.execute(
            text("UPDATE account SET balance = balance + :value WHERE chain_id = :chain_id AND address = :sender_addr"),
            {"value": value, "chain_id": chain_id, "sender_addr": sender_addr},
        )
        if block_version >= 24:
            _ebal, _enonce, escrow_exists = _st.read_current_account(session, chain_id, escrow_addr)
            escrow_balance = _ebal if _ebal is not None else 0
            if not escrow_exists or escrow_balance < value:
                raise ValueError(f"Escrow {job_id} has insufficient balance for {tx_type}")
        else:
            escrow_account = session.get(Account, (chain_id, escrow_addr))
            if escrow_account is None or escrow_account.balance < value:
                raise ValueError(f"Escrow {job_id} has insufficient balance for {tx_type}")
        session.execute(
            text("UPDATE account SET balance = balance - :value WHERE chain_id = :chain_id AND address = :escrow_addr"),
            {"value": value, "chain_id": chain_id, "escrow_addr": escrow_addr},
        )
        session.execute(
            text("UPDATE account SET balance = balance + :value WHERE chain_id = :chain_id AND address = :recipient_addr"),
            {"value": value, "chain_id": chain_id, "recipient_addr": recipient_addr},
        )
        session.flush()
        if swept:
            logger.info("v11: %s swept %s from escrow %s to fee recipient %s", tx_type, value, escrow_addr, recipient_addr)
        else:
            logger.info("S-4: %s moved %s from escrow %s to %s", tx_type, value, escrow_addr, recipient_addr)

    def _apply_bond_deactivation_effects(
        self,
        session: Session,
        chain_id: str,
        tx_data: dict[str, Any],
        tx_hash: str,
        tx_type: str,
        sender_addr: str,
        recipient_addr: str,
        value: int,
        block_height: int | None,
        *,
        block_version: int,
        block_time: datetime | None,
    ) -> None:
        if tx_type in ("BOND_LOCK", "BOND_RELEASE", "BOND_SLASH"):
            skip_reason = self._handle_bond_transaction(
                session,
                chain_id,
                tx_data,
                tx_hash,
                tx_type,
                sender_addr,
                recipient_addr,
                value,
                block_height,
                block_version=block_version,
                block_time=block_time,
            )
            if skip_reason:
                # Fee and nonce still applied — name it, or the "Applied
                # transaction" INFO below reads as a fully-applied slash
                # (the 1-2 Sep forensics trap).
                logger.warning(
                    "%s %s applied fee/nonce but bond effect skipped: %s",
                    tx_type,
                    tx_hash,
                    skip_reason,
                )
        if tx_type == "VALIDATOR_DEACTIVATE":
            skip_reason = self._handle_validator_deactivation(
                session, chain_id, tx_data, tx_hash, sender_addr, value, block_height, block_time
            )
            if skip_reason:
                # Same contract as the bond handlers: fee/nonce still apply,
                # the marker does not — named so the apply log cannot read
                # as a landed deactivation.
                logger.warning(
                    "%s %s applied fee/nonce but deactivation skipped: %s",
                    tx_type,
                    tx_hash,
                    skip_reason,
                )

    def _apply_receipt_claim(
        self,
        session: Session,
        chain_id: str,
        tx_data: dict[str, Any],
        sender_addr: str,
        sender_account: Account | None,
        block_height: int | None,
        *,
        block_version: int,
        block_time: datetime | None,
    ) -> None:
        payload = tx_data.get("payload", {}) or {}
        receipt_id = str(payload.get("receipt_id") or "")
        receipt = session.exec(select(Receipt).where(Receipt.chain_id == chain_id, Receipt.receipt_id == receipt_id)).first()
        if receipt is None:
            # Carried issuance (#687): materialise the receipt row from the
            # claim payload — every node builds the same claimed record, so
            # the claim seals identically with or without a service-written
            # row. minted_amount stays NULL: carried issuance never mints.
            record = _carried_receipt_record(payload, receipt_id)
            if record is not None:
                receipt = Receipt(
                    chain_id=chain_id,
                    job_id=str(record.get("job_id") or payload.get("job_id") or ""),
                    receipt_id=receipt_id,
                    block_height=block_height,
                    payload=record.get("payload") if isinstance(record.get("payload"), dict) else {},
                    miner_signature=record["miner_signature"],
                    coordinator_attestations=record["coordinator_attestations"],
                    minted_amount=None,
                    status="claimed",
                    claimed_at=(
                        block_time
                        if (block_version is not None and block_version >= 18 and block_time is not None)
                        else datetime.now(UTC)
                    ),
                    claimed_by=sender_addr,
                )
                session.add(receipt)
                logger.info(
                    "Materialised claimed receipt %s from carried issuance (job=%s claimed_by=%s)",
                    receipt_id,
                    receipt.job_id,
                    sender_addr,
                )
        elif receipt.status == "pending" and not receipt.minted_amount:
            # A service-recorded pending row claimed with no mint attached:
            # settle it so the row surface converges with the
            # materialised-claimed shape other nodes build (#687).
            receipt.status = "claimed"
            receipt.claimed_at = (
                block_time
                if (block_version is not None and block_version >= 18 and block_time is not None)
                else datetime.now(UTC)
            )
            receipt.claimed_by = sender_addr
            logger.info("Claimed receipt %s (no mint): claimed_by=%s", receipt_id, sender_addr)
        if receipt and receipt.minted_amount:
            # The raw-SQL fee debit above already landed in the row, but
            # the ORM snapshot of sender_account still holds the
            # pre-debit balance — writing stale+minted would silently
            # undo the fee. Refresh before mutating so the stored value
            # is balance-fee+minted, identical to the parallel path's
            # two raw UPDATEs (v0.25.8 parity fix).
            session.refresh(sender_account)
            sender_account.balance += receipt.minted_amount  # type: ignore[union-attr]
            receipt.status = "claimed"
            receipt.claimed_at = (
                block_time
                if (block_version is not None and block_version >= 18 and block_time is not None)
                else datetime.now(UTC)
            )
            receipt.claimed_by = sender_addr
            logger.info("Claimed receipt %s: minted_amount=%s, claimed_by=%s", receipt_id, receipt.minted_amount, sender_addr)

    def _apply_gpu_effects(
        self,
        session: Session,
        chain_id: str,
        tx_data: dict[str, Any],
        tx_type: str,
        sender_addr: str,
        block_version: int,
    ) -> tuple[bool, str] | None:
        if tx_type == "GPU_REGISTER":
            payload = tx_data.get("payload") or {}
            gpu_data = {**(payload if isinstance(payload, dict) else {}), "registered_by": sender_addr}
            ok, msg = self.handle_gpu_registration(session, chain_id, gpu_data, block_version=block_version)
            if not ok:
                return (False, msg)
        if tx_type == "GPU_DEREGISTER" and block_version >= 10:
            payload = tx_data.get("payload") or {}
            ok, msg = self.handle_gpu_deregistration(session, chain_id, payload if isinstance(payload, dict) else {})
            if not ok:
                return (False, msg)
        if tx_type == "GPU_ALLOCATE":
            payload = tx_data.get("payload") or {}
            allocation_data = {**(payload if isinstance(payload, dict) else {}), "allocated_by": sender_addr}
            ok, msg = self.handle_gpu_allocation(session, chain_id, allocation_data)
            if not ok:
                return (False, msg)
        return None

    def _apply_post_transfer_effects(
        self,
        session: Session,
        chain_id: str,
        tx_data: dict[str, Any],
        tx_hash: str,
        tx_type: str,
        sender_addr: str,
        recipient_addr: str,
        value: int,
        sender_account: Account | None,
        block_height: int | None,
        *,
        block_version: int,
        block_time: datetime | None,
    ) -> tuple[bool, str] | None:
        """Side effects that run after the generic debit/credit lands:
        escrow custody fix-ups, bond/deactivation markers, governance,
        receipt claims, IPFS subscriptions, GPU lifecycle, and the v21
        agent-session/spend ledger. Returns ``(False, msg)`` only where the
        original apply path aborted the transaction."""
        self._apply_escrow_custody_effects(
            session, chain_id, tx_data, tx_type, value, sender_addr, recipient_addr, block_version
        )
        self._apply_bond_deactivation_effects(
            session,
            chain_id,
            tx_data,
            tx_hash,
            tx_type,
            sender_addr,
            recipient_addr,
            value,
            block_height,
            block_version=block_version,
            block_time=block_time,
        )
        if tx_type == "GOVERNANCE_EXECUTE":
            self._handle_governance_execute(session, chain_id, tx_data, tx_hash, block_height, block_version=block_version)
        if tx_type == "RECEIPT_CLAIM":
            self._apply_receipt_claim(
                session,
                chain_id,
                tx_data,
                sender_addr,
                sender_account,
                block_height,
                block_version=block_version,
                block_time=block_time,
            )
        if tx_type == "IPFS_SUBSCRIPTION":
            self._handle_ipfs_subscription(session, chain_id, tx_data, tx_hash, sender_addr)
        gpu_result = self._apply_gpu_effects(session, chain_id, tx_data, tx_type, sender_addr, block_version)
        if gpu_result is not None:
            return gpu_result
        if block_version >= 21:
            # v21 (AGENT-SPEND-B-1, #1142): apply the validated session effects
            # — grant/revoke writes the session row, a gated spend charges the
            # day's ledger. Both land in this same apply transaction as the
            # balance debit above, so the daily cap is atomic with the spend.
            if tx_type in AGENT_SESSION_TX_TYPES:
                apply_agent_session_tx(session, chain_id, tx_type, tx_data.get("payload") or {}, sender_addr, block_height)
            charge_agent_spend(session, chain_id, tx_type, tx_data.get("payload"), value, block_height)
        return None

    def _apply_success_epilogue(
        self,
        session: Session,
        chain_id: str,
        tx_hash: str,
        tx_type: str,
        sender_addr: str,
        recipient_addr: str,
        sender_account: Account | None,
        value: int,
        fee: int,
        *,
        block_version: int,
    ) -> tuple[bool, str]:
        if block_version >= 23 and sender_addr is not None and sender_account is not None:
            # v23: the raw-SQL debit/nonce update bypassed the ORM object —
            # flush pending writes, then reload so the retained object (and
            # the diagnostic cache entry) carry the authoritative next
            # expected nonce for the caller's still-uncommitted block
            # transaction. This runs BEFORE the cache writes below: a
            # failure here must not leave a processed-hash entry for a tx
            # the guarded savepoint is about to roll back.
            # _processed_nonces is per-block diagnostic only: callers run
            # reset_processed_cache at each block boundary and on discarded
            # attempts; it is not a consensus input.
            session.flush()
            session.refresh(sender_account)
        self._processed_tx_hashes.add(tx_hash)
        if sender_addr is not None:
            self._processed_nonces[sender_addr] = sender_account.nonce  # type: ignore[union-attr]
        if _cache and _cache.is_available():
            for addr in [sender_addr, recipient_addr]:
                if addr:
                    _cache.delete(f"account_balance:{chain_id}:{addr.lower()}")
                    _cache.delete(f"account_details:{chain_id}:{addr.lower()}")
        logger.info(
            "Applied transaction %s: %s -> %s, value=%s, fee=%s, type=%s",
            tx_hash,
            sender_addr,
            recipient_addr,
            value,
            fee,
            tx_type,
        )
        return (True, "Transaction applied successfully")
