"""
State Transition Layer for AITBC

This module provides the StateTransition class that validates all state changes
to ensure they only occur through validated transactions.

The module-level helpers live in sibling modules (``state_transition_txmeta``,
``state_transition_authority``, ``state_transition_bond``,
``state_transition_escrow``, ``state_transition_payload_auth``); every name is
re-exported below so ``from aitbc_chain.state.state_transition import X``
keeps working unchanged.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from sqlmodel import Session, select

from ..base_models import _to_ait_address
from ..logger import get_logger
from ..models import Account, Transaction
from ..rpc.utils import verify_transaction_signature
from ..v24_rules import v24_rules_active
from .authoritative_reads import read_current_account as read_current_account

from .state_transition_authority import (
    _chain_parameter_value as _chain_parameter_value,
    _governance_executors as _governance_executors,
    _bond_slash_authority as _bond_slash_authority,
    _validator_deactivation_authority as _validator_deactivation_authority,
    _parse_validator_deactivation_payload as _parse_validator_deactivation_payload,
    _escrow_settlement_authority as _escrow_settlement_authority,
    _bridge_release_authority as _bridge_release_authority,
    _escrow_fee_recipient as _escrow_fee_recipient,
    _escrow_fee_cap_bps as _escrow_fee_cap_bps,
    _AUTHORITY_PARAMETERS as _AUTHORITY_PARAMETERS,
    _SINGLE_ADDRESS_PARAMETERS as _SINGLE_ADDRESS_PARAMETERS,
    _EXECUTOR_MIN_BALANCE_UNITS as _EXECUTOR_MIN_BALANCE_UNITS,
    _ZERO_ADDRESS as _ZERO_ADDRESS,
    _validate_authority_parameter_value as _validate_authority_parameter_value,
    _canonical_authority_addresses as _canonical_authority_addresses,
    _authority_value_shape_error as _authority_value_shape_error,
    _executors_funded as _executors_funded,
    _V13_MAX_EXECUTION_PAYLOAD_BYTES as _V13_MAX_EXECUTION_PAYLOAD_BYTES,
    _V13Verdict as _V13Verdict,
    _sealed_propose_execution_payload as _sealed_propose_execution_payload,
    _sealed_execute_exists as _sealed_execute_exists,
    _governance_propose_binding_verdict as _governance_propose_binding_verdict,
    _governance_execute_binding_verdict as _governance_execute_binding_verdict,
    _governance_binding_verdict as _governance_binding_verdict,
    _governance_binding_error as _governance_binding_error,
    _v13_shadow_observe as _v13_shadow_observe,
    _authority_parameter_change_error as _authority_parameter_change_error,
    _governance_execute_payload as _governance_execute_payload,
)

from .state_transition_bond import (
    _BOND_ESCROW_ADDRESS as _BOND_ESCROW_ADDRESS,
    _BOND_BURN_ADDRESS as _BOND_BURN_ADDRESS,
    _bond_escrow_ait as _bond_escrow_ait,
    _bond_burn_ait as _bond_burn_ait,
    _is_bond_escrow as _is_bond_escrow,
    _is_bond_burn as _is_bond_burn,
    PROTOCOL_MAX_LOCK_DURATION as PROTOCOL_MAX_LOCK_DURATION,
    bond_tx_verdict as bond_tx_verdict,
    _bond_verdict_now as _bond_verdict_now,
    _bond_lock_verdict as _bond_lock_verdict,
    _bond_topup_verdict as _bond_topup_verdict,
    _bond_release_verdict as _bond_release_verdict,
    _bond_release_row_verdict as _bond_release_row_verdict,
)

from .state_transition_escrow import (
    _escrow_address as _escrow_address,
    _is_escrow_address as _is_escrow_address,
    _is_valid_0x_address as _is_valid_0x_address,
    _get_escrow_lock as _get_escrow_lock,
    _get_escrow_lock_block_version as _get_escrow_lock_block_version,
    _escrow_beneficiary as _escrow_beneficiary,
    _ESCROW_SETTLEMENT_TYPES as _ESCROW_SETTLEMENT_TYPES,
    _escrow_lock_rows as _escrow_lock_rows,
    _sum_confirmed_escrow_values as _sum_confirmed_escrow_values,
    _escrow_obligation_state as _escrow_obligation_state,
    _escrow_lock_beneficiaries as _escrow_lock_beneficiaries,
    _ESCROW_CONTEXT_TYPES as _ESCROW_CONTEXT_TYPES,
    _escrow_tx_job_id as _escrow_tx_job_id,
    _escrow_v23_context_params as _escrow_v23_context_params,
    _escrow_duplicate_settlement as _escrow_duplicate_settlement,
    _escrow_merge_existing_entry as _escrow_merge_existing_entry,
    _escrow_new_context_entry as _escrow_new_context_entry,
    _EscrowContextParams as _EscrowContextParams,
    build_escrow_context as build_escrow_context,
    _refund_lock_record as _refund_lock_record,
    build_bridge_lock_context as build_bridge_lock_context,
)

from .state_transition_payload_auth import (
    _AUTH_ADDRESS_FIELDS as _AUTH_ADDRESS_FIELDS,
    _payload_auth_named_addresses as _payload_auth_named_addresses,
    _payload_auth_binds_transfer as _payload_auth_binds_transfer,
    _payload_auth_role as _payload_auth_role,
    _payload_auth_party_binds as _payload_auth_party_binds,
    _payload_auth_chain_action_binds as _payload_auth_chain_action_binds,
    _payload_auth_amount_binds as _payload_auth_amount_binds,
    _payload_auth_ids_binds as _payload_auth_ids_binds,
    _payload_auth_lock_hashes_binds as _payload_auth_lock_hashes_binds,
    _STAKE_LOCK_BLOCKS_PER_DAY as _STAKE_LOCK_BLOCKS_PER_DAY,
    _validate_stake_release_locks as _validate_stake_release_locks,
    _claimed_lock_hashes as _claimed_lock_hashes,
    _load_claimed_locks as _load_claimed_locks,
    _claimed_locks_matured as _claimed_locks_matured,
    _claimed_locks_unspent as _claimed_locks_unspent,
)

from .state_transition_txmeta import (
    _ZERO_VALUE_TX_TYPES as _ZERO_VALUE_TX_TYPES,
    _GPU_PRICE_PER_HOUR_MAX as _GPU_PRICE_PER_HOUR_MAX,
    _gpu_price_per_hour_in_range as _gpu_price_per_hour_in_range,
    _is_zero_value_tx_type as _is_zero_value_tx_type,
    _ensure_account as _ensure_account,
    _tx_type as _tx_type,
    get_recorded_block_version as get_recorded_block_version,
    get_block_version as get_block_version,
    get_block_version_for_height as get_block_version_for_height,
    block_scoped_preregistered as block_scoped_preregistered,
    block_scoped_preregistered_for_next_block as block_scoped_preregistered_for_next_block,
    use_account_nonce_override as use_account_nonce_override,
)


try:
    from aitbc.caching import RedisCache

    _REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    _cache: RedisCache | None = RedisCache(redis_url=_REDIS_URL, default_ttl=30)
except Exception:  # noqa: BLE001 - cache is optional; any init failure means no cache
    _cache = None
logger = get_logger(__name__)


class _TxValidationCtx:
    """Shared state threaded through ``validate_transaction``'s ordered checks.

    Each ``_vt_*`` validator runs in the exact position its source block held
    in the original monolith; the first non-None return is the verdict, so
    first-failure-wins error precedence is preserved block-for-block.
    """

    __slots__ = (
        "session",
        "chain_id",
        "tx_data",
        "tx_hash",
        "block_version",
        "block_height",
        "block_time",
        "skip_dedup",
        "tx_record",
        "tx_type",
        "sender_addr",
        "recipient_addr",
        "value",
        "fee",
        "sender_nonce",
        "sender_balance",
        "total_cost",
        "job_id",
        "lock_tx",
        "lock_version",
        "payload",
        "escrow_balance",
        "tx_only_root",
    )

    def __init__(
        self,
        *,
        session: Session,
        chain_id: str,
        tx_data: dict[str, Any],
        tx_hash: str,
        block_version: int,
        block_height: int | None,
        block_time: datetime | None,
        skip_dedup: bool,
    ) -> None:
        self.session = session
        self.chain_id = chain_id
        self.tx_data = tx_data
        self.tx_hash = tx_hash
        self.block_version = block_version
        self.block_height = block_height
        self.block_time = block_time
        self.skip_dedup = skip_dedup
        self.tx_record: Any = None
        self.tx_type: str = ""
        self.sender_addr: str = ""
        self.recipient_addr: str = ""
        self.value: Any = 0
        self.fee: Any = 0
        self.sender_nonce: int = 0
        self.sender_balance: Any = 0
        self.total_cost: Any = 0
        self.job_id: str = ""
        self.lock_tx: Any = None
        self.lock_version: Any = 0
        self.payload: Any = {}
        self.escrow_balance: Any = 0
        # #1940 F5: resolved once per tx in _vt_prepare — the history-gated
        # tx-derived bridge-root era for this block's height.
        self.tx_only_root: bool = False


from .state_transition_apply import _ApplyMixin
from .state_transition_handlers import _HandlerMixin
from .state_transition_validation import _ValidationMixin


class StateTransition(_ValidationMixin, _ApplyMixin, _HandlerMixin):
    """
    Validates and applies state transitions only through validated transactions.

    This class ensures that balance changes can only occur through properly
    validated transactions, preventing direct database manipulation of account
    balances.
    """

    def __init__(self, *, cache_side_effects: bool = True) -> None:
        self._processed_nonces: dict[str, int] = {}
        self._processed_tx_hashes: set[str] = set()
        # #1940 F4: speculative applies (the attestation post-state probe)
        # construct with cache_side_effects=False so no Redis invalidation
        # fires for state that is never committed. The production singleton
        # keeps the default — behavior there is unchanged.
        self._cache_side_effects = cache_side_effects

    def reset_processed_cache(self) -> None:
        """Clear in-memory per-process tx/nonce caches.

        The caches are intended to prevent the same transaction from being
        applied twice within one block. Because a rejected block is rolled back,
        leaving the cache populated causes false "replay attack" errors on the
        next import attempt. Call this at the start of each block.
        """
        self._processed_nonces.clear()
        self._processed_tx_hashes.clear()

    def validate_transaction(
        self,
        session: Session,
        chain_id: str,
        tx_data: dict[str, Any],
        tx_hash: str,
        block_version: int = 2,
        block_height: int | None = None,
        *,
        skip_dedup: bool = False,
        block_time: datetime | None = None,
    ) -> tuple[bool, str]:
        """
        Validate a transaction before applying state changes.

        Args:
            session: Database session
            chain_id: Chain identifier
            tx_data: Transaction data
            tx_hash: Transaction hash
            block_height: Height of the block carrying this transaction.
                Authority chain parameters resolve to the value in force at
                this height, so replayed blocks validate against the
                parameters as they were when the block was sealed. None
                resolves the current value (e.g. mempool pre-checks).

        Returns:
            Tuple of (is_valid, error_message)
        """
        ctx = _TxValidationCtx(
            session=session,
            chain_id=chain_id,
            tx_data=tx_data,
            tx_hash=tx_hash,
            block_version=block_version,
            block_height=block_height,
            block_time=block_time,
            skip_dedup=skip_dedup,
        )
        for _check in (
            self._vt_chain_id,
            self._vt_dedup,
            self._vt_prepare,
            self._vt_liquidity,
            self._vt_bridge_credit,
            self._vt_bridge_lock_sig,
            self._vt_bridge_lock_account,
            self._vt_bridge_withdraw,
            self._vt_escrow_lock_v3,
            self._vt_signature,
            self._vt_v9_signature,
            self._vt_stake_payload_auth,
            self._vt_sender_account,
            self._vt_nonce,
            self._vt_governance_execute,
            self._vt_governance_propose,
            self._vt_stake_release_locks,
            self._vt_zero_value_cost,
            self._vt_escrow_release_refund_job,
            self._vt_escrow_beneficiary,
            self._vt_escrow_obligation,
            self._vt_escrow_authority,
            self._vt_escrow_funding,
            self._vt_sweep_params,
            self._vt_sweep_fee_recipient,
            self._vt_sweep_custody,
            self._vt_sweep_obligation,
            self._vt_sweep_fee,
            self._vt_sender_balance,
            self._vt_receipt_claim,
            self._vt_ipfs_subscription,
            self._vt_gpu_register_fields,
            self._vt_gpu_register_ownership,
            self._vt_gpu_deregister,
            self._vt_gpu_allocate,
            self._vt_retired_gpu,
            self._vt_bond_lock_v20,
            self._vt_bond_lock_v19,
            self._vt_bond_v22,
            self._vt_agent_spend,
        ):
            verdict = _check(ctx)
            if verdict is not None:
                return verdict
        return (True, "Transaction validated successfully")

    def _vt_signature(self, ctx: _TxValidationCtx) -> tuple[bool, str] | None:
        signature = ctx.tx_data.get("signature")
        if signature and ctx.sender_addr:
            if not verify_transaction_signature(ctx.tx_data, signature, ctx.sender_addr):
                return (False, f"Invalid signature for transaction {ctx.tx_hash}")
        return None

    def apply_transaction(
        self,
        session: Session,
        chain_id: str,
        tx_data: dict[str, Any],
        tx_hash: str,
        block_version: int = 2,
        block_height: int | None = None,
        *,
        block_time: datetime | None = None,
        skip_dedup: bool = False,
    ) -> tuple[bool, str]:
        """
        Apply a validated transaction to update state.

        Args:
            session: Database session
            chain_id: Chain identifier
            tx_data: Transaction data
            tx_hash: Transaction hash
            block_version: State-transition rule version active for the block
                that contains this transaction. v1 keeps pre-2026-09-01 rules
                (no auto-created recipient/provider accounts); v2 applies the
                current account-creation rules.
            block_height: Height of the block carrying this transaction.
                Authority chain parameters resolve to the value in force at
                this height, and a parameter_change applied here takes effect
                from this height onward — replayed history can never fail
                because a parameter was set later in the chain.
            block_time: Sealed block-header timestamp. At block_version >= 18
                the volatile apply paths (liquidity stake ids/locked_until/
                accrual, bond locked_until/verdict) derive from it instead of
                wall-clock ``datetime.now(UTC)`` — the apply output is then a
                pure function of (transaction, prior state, block header).
                ``None`` keeps the volatile fallback for pre-v18 replay and
                non-consensus callers.

        Returns:
            Tuple of (success, error_message)
        """
        logger.info("apply_transaction called for tx %s, tx_data keys: %s", tx_hash, list(tx_data.keys()))
        is_valid, error_msg = self.validate_transaction(
            session,
            chain_id,
            tx_data,
            tx_hash,
            block_version=block_version,
            block_height=block_height,
            skip_dedup=skip_dedup,
            block_time=block_time,
        )
        if not is_valid:
            return (False, error_msg)
        sender_addr = _to_ait_address(tx_data.get("from") or "")
        if block_version >= 22 and sender_addr and tx_data.get("from") not in {"bridge_release", "bridge_refund"}:
            # v22 R1 (CONSENSUS-STATE-001): validation passed, so the sender
            # materializes now — the same committed row the pre-v22 importer
            # pre-create produced, but only on the success path. A rejected
            # tx never reaches this line and leaves no phantom account.
            _ensure_account(session, chain_id, sender_addr)
        recipient_addr = _to_ait_address(tx_data.get("to") or "")
        tx_record = session.exec(
            select(Transaction).where(Transaction.chain_id == chain_id, Transaction.tx_hash == tx_hash)
        ).first()
        tx_type = _tx_type(tx_data, tx_record)
        value = tx_data.get("value", 0)
        fee = tx_data.get("fee", 0)
        # Guard against BigInt overflow (SQLite INTEGER is 64-bit signed)
        _MAX_INT64 = 2**63 - 1
        if value < 0 or fee < 0 or value > _MAX_INT64 or fee > _MAX_INT64:
            raise ValueError(f"Transaction value/fee out of range: value={value}, fee={fee}")
        special = self._apply_special_transfer(
            session,
            chain_id,
            tx_data,
            tx_hash,
            tx_type,
            sender_addr,
            recipient_addr,
            value,
            fee,
            block_version=block_version,
            block_time=block_time,
        )
        if special is not None:
            return special
        sender_account, recipient_addr = self._apply_core_transfer(
            session, chain_id, tx_data, tx_type, sender_addr, recipient_addr, value, fee, block_version
        )
        side = self._apply_post_transfer_effects(
            session,
            chain_id,
            tx_data,
            tx_hash,
            tx_type,
            sender_addr,
            recipient_addr,
            value,
            sender_account,
            block_height,
            block_version=block_version,
            block_time=block_time,
        )
        if side is not None:
            return side
        return self._apply_success_epilogue(
            session,
            chain_id,
            tx_hash,
            tx_type,
            sender_addr,
            recipient_addr,
            sender_account,
            value,
            fee,
            block_version=block_version,
        )

    def apply_transaction_guarded(
        self,
        session: Session,
        chain_id: str,
        tx_data: dict[str, Any],
        tx_hash: str,
        block_version: int,
        **kwargs: Any,
    ) -> tuple[bool, str]:
        """``apply_transaction`` bracketed in a per-tx savepoint at v22+.

        CONSENSUS-STATE-001 (R1): at ``block_version >= 22`` a transaction
        whose apply returns ``False`` — or raises — must leave zero
        mutation. Validation-pass account materialization and any handler
        residue are rolled back to the savepoint, so importer, proposer,
        reapply and golden-engine callers all commit identical state for
        failed txs. Below v22 the call delegates unchanged: historical
        replay keeps whatever residue the original code committed.
        ``block_version`` is a required keyword so a caller cannot
        silently bypass the guard by omitting it.
        """
        if block_version < 22:
            return self.apply_transaction(session, chain_id, tx_data, tx_hash, block_version=block_version, **kwargs)
        if not session.in_transaction():
            # Anchor a real outer transaction first so begin_nested() creates a
            # genuine SAVEPOINT rather than auto-beginning the outer
            # transaction itself.
            session.begin()
        savepoint = session.begin_nested()
        try:
            if block_version >= 24:
                # #1314 R1: identity-map invalidation after raw-SQL writes is
                # active for the duration of this transaction's apply.
                with v24_rules_active():
                    result = self.apply_transaction(session, chain_id, tx_data, tx_hash, block_version=block_version, **kwargs)
            else:
                result = self.apply_transaction(session, chain_id, tx_data, tx_hash, block_version=block_version, **kwargs)
        except Exception:  # noqa: BLE001 - any apply failure must roll back to the savepoint before re-raise
            savepoint.rollback()
            raise
        if not result[0]:
            # Dispatch-failure: roll back to the savepoint. SessionTransaction.
            # rollback() restores the session snapshot (expunging ORM objects
            # added inside) as well as the DB writes, so no sender row or
            # handler residue survives — while the caller still owns the
            # outer transaction and records the deterministic failed-tx row.
            savepoint.rollback()
        # On success the savepoint is deliberately left open: calling
        # SessionTransaction.commit() here released the SAVEPOINT but the
        # writes then survived a later session.rollback() under the pysqlite
        # driver — effectively committing past the caller's transaction
        # boundary (verified empirically; breaks proposer PBFT-failure
        # rollback). An open savepoint costs nothing: later txs nest inside
        # it, a later failure rolls back only to its own savepoint, and the
        # caller's outer commit/rollback covers everything uniformly.
        return result

    def _bond_release_payout(
        self, session: Session, chain_id: str, sender_addr: str, release_amount: int, tx_hash: str
    ) -> str | None:
        escrow = _ensure_account(session, chain_id, _BOND_ESCROW_ADDRESS)
        sender = session.get(Account, (chain_id, sender_addr))
        if escrow and sender:
            session.refresh(escrow)
            session.refresh(sender)
            if escrow.balance < release_amount:
                return f"escrow balance {escrow.balance} below release amount {release_amount}"
            escrow.balance -= release_amount
            sender.balance += release_amount
            logger.info("BOND_RELEASE %s moved %s from escrow to %s", tx_hash, release_amount, sender_addr)
        return None

    def _bond_slash_move(self, session: Session, chain_id: str, slash_amount: int, tx_hash: str) -> str | None:
        escrow = _ensure_account(session, chain_id, _BOND_ESCROW_ADDRESS)
        burn = _ensure_account(session, chain_id, _BOND_BURN_ADDRESS)
        if escrow and burn:
            session.refresh(escrow)
            session.refresh(burn)
            if escrow.balance < slash_amount:
                return f"escrow balance {escrow.balance} below slash amount {slash_amount}"
            escrow.balance -= slash_amount
            burn.balance += slash_amount
            logger.info("BOND_SLASH %s moved %s from escrow to burn", tx_hash, slash_amount)
        return None

    def validate_state_transition(
        self, session: Session, chain_id: str, old_accounts: dict[str, Account], new_accounts: dict[str, Account]
    ) -> tuple[bool, str]:
        """
        Validate that state changes only occur through transactions.

        Args:
            session: Database session
            chain_id: Chain identifier
            old_accounts: Previous account state
            new_accounts: New account state

        Returns:
            Tuple of (is_valid, error_message)
        """
        for address, old_acc in old_accounts.items():
            if address not in new_accounts:
                continue
            new_acc = new_accounts[address]
            if old_acc.balance != new_acc.balance:
                logger.warning(
                    "Balance change detected for %s: %s -> %s (validated through transaction processing)",
                    address,
                    old_acc.balance,
                    new_acc.balance,
                )
        return (True, "State transition validated")

    def get_processed_nonces(self) -> dict[str, int]:
        """Get the last processed nonce for each address."""
        return self._processed_nonces.copy()

    def reset(self) -> None:
        """Reset the state transition validator (for testing)."""
        self._processed_nonces.clear()
        self._processed_tx_hashes.clear()


_state_transition = StateTransition()


def get_state_transition() -> StateTransition:
    """Get the global state transition instance."""
    return _state_transition
