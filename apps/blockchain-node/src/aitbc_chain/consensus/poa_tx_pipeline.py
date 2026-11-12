"""Sequential and parallel transaction-processing paths for ``PoAProposer`` (#1867 pure-move split).

Import ``aitbc_chain.consensus.poa`` first (it wires these
mixins into ``PoAProposer``); this module is not meant to be imported
directly."""

from __future__ import annotations

from typing import Any

from . import poa as _poa
from .poa import (
    _PoaBaseMixin,
    _SeqTxContext,
    _parallel_bridge_authority,
    _parallel_build_graph,
    _parallel_refresh_group_nonces,
    _parallel_tx_data_map,
    _seq_reject,
    _validate_governance_payload,
)

from ..base_models import _to_ait_address
from ..config import settings
from ..models import Account, Transaction
from ..state.authoritative_reads import read_current_account
from ..state.bridge_credit import (
    bridge_refund_lock_hash,
    validate_bridge_refund_lock,
    verify_bridge_credit_signature,
    verify_bridge_lock_signature,
)
from ..state.pure_state_transition import StateDelta
from ..state.state_transition import (
    _bridge_release_authority,
    _refund_lock_record,
    get_block_version_for_height,
    use_account_nonce_override,
)
from ..state.v9_policy import count_v9_would_reject
from datetime import datetime
from sqlmodel import Session, select


class _TxPipelineMixin(_PoaBaseMixin):
    def _process_txs_sequential(
        self,
        session: Session,
        pending_txs: list[Any],
        account_map: dict[str, Account],
        existing_tx_map: dict[str, int],
        next_height: int,
        timestamp: datetime,
        rejected: list[tuple[Any, str]] | None = None,
    ) -> tuple[list[Any], set[str], bool]:
        """Sequential transaction processing — the fallback for the parallel path.

        Same contract as ``_process_txs_parallel``: returns
        ``(processed_txs, changed_addresses, ok)``. On a per-transaction
        exception the session is rolled back and ``ok=False`` is returned so the
        caller can abort the proposal with a clean session.

        ``rejected``, when given, collects ``(tx, reason)`` for every drained
        tx the loop refuses so the caller can persist a terminal status (#669).
        """
        # S-4: the active state-transition version for this block. Every path that
        # calls apply_transaction must use the same version so the state root is
        # deterministic and consistent with the stamped block_metadata.
        ctx = _SeqTxContext(
            session=session,
            account_map=account_map,
            existing_tx_map=existing_tx_map,
            next_height=next_height,
            timestamp=timestamp,
            block_version=get_block_version_for_height(next_height),
            rejected=rejected,
        )
        for tx in pending_txs:
            try:
                self._process_tx_sequential(ctx, tx)
            except Exception as e:
                session.rollback()
                self._logger.warning("Failed to process transaction %s: %s", tx.tx_hash, e)
                _seq_reject(ctx, tx, f"processing exception: {e}")
                return [], set(), False
        # Add transaction records only after all state transitions for
        # this block have succeeded. This keeps them inside the outer
        # transaction so a subsequent PBFT or attestation failure rolls
        # them back together with the account state changes.
        for record in ctx.pending_records:
            session.add(record)
        return ctx.processed_txs, ctx.changed_addresses, True

    def _process_tx_sequential(self, ctx: _SeqTxContext, tx: Any) -> None:
        """Run one drained tx through the sequential apply path.

        Every refusal records ``(tx, reason)`` via ``_seq_reject`` and returns;
        only the caller's per-tx ``except`` turns an exception into ``ok=False``.
        Stage order is the original inline order — first refusal wins."""
        tx_data = tx.content
        sender = _to_ait_address(tx_data.get("from", ""))
        recipient = _to_ait_address(tx_data.get("to", ""))
        value = tx_data.get("amount", 0)
        fee = tx_data.get("fee", 0)
        tx_type = (tx_data.get("type") or "TRANSFER").upper()
        self._logger.info(
            "[PROPOSE] Processing tx %s: from=%s, to=%s, amount=%s, fee=%s",
            tx.tx_hash,
            sender,
            recipient,
            value,
            fee,
        )
        if not sender or not recipient:
            self._logger.warning("[PROPOSE] Skipping tx %s: missing sender or recipient", tx.tx_hash)
            _seq_reject(ctx, tx, "missing sender or recipient")
            return
        # Pre-registered transactions (e.g. bridge releases/refunds) are already
        # applied by the originating RPC call. Record them in the block without
        # re-running the state transition to avoid replay and double-credit.
        existing_tx_record = ctx.session.exec(
            select(Transaction).where(
                Transaction.chain_id == self._config.chain_id,
                Transaction.tx_hash == tx.tx_hash,
            )
        ).first()
        if self._seq_stamp_preregistered(ctx, tx, tx_type, existing_tx_record):
            return
        if self._seq_block_scoped_credit(ctx, tx, tx_type, value, fee):
            return
        state = self._seq_sender_state(ctx, tx, sender)
        if state is None:
            return
        sender_balance, authoritative_nonce = state
        total_cost = value + fee
        if sender_balance < total_cost:
            self._logger.warning(
                "[PROPOSE] Skipping tx %s: insufficient balance (has %s, needs %s)",
                tx.tx_hash,
                sender_balance,
                total_cost,
            )
            _seq_reject(ctx, tx, f"insufficient balance (has {sender_balance}, needs {total_cost})")
            return
        # Resolve canonical tx type and validate governance
        # payloads before mutating state so we can skip invalid
        # transactions without rolling back earlier work.
        tx_type = self._seq_canonical_tx_type(ctx, tx)
        if tx_type is None:
            return
        existing_block_height = ctx.existing_tx_map.get(tx.tx_hash)
        if existing_block_height is not None:
            self._logger.warning(
                "[PROPOSE] Skipping tx %s: already exists in database at block %s",
                tx.tx_hash,
                existing_block_height,
            )
            return
        self._seq_apply_and_record(ctx, tx, sender, recipient, value, fee, tx_type, authoritative_nonce, existing_tx_record)

    def _seq_stamp_preregistered(self, ctx: _SeqTxContext, tx: Any, tx_type: str, existing_tx_record) -> bool:
        """Stamp a pre-registered row into the block, or reject it on an
        authorization failure. Returns True when the tx is consumed."""
        if not (
            existing_tx_record
            and existing_tx_record.status == "confirmed"
            and existing_tx_record.block_height is None
            and tx_type in {"MESSAGE", "BRIDGE_RELEASE", "BRIDGE_REFUND", "BRIDGE_LOCK"}
        ):
            return False
        if self._seq_bridge_lock_gate(ctx, tx, tx_type):
            return True
        skip_reason = self._seq_bridge_credit_gate(ctx, tx, tx_type)
        if skip_reason:
            self._logger.warning(
                "[PROPOSE] Skipping pre-registered %s tx %s: %s",
                tx_type,
                tx.tx_hash,
                skip_reason,
            )
            _seq_reject(ctx, tx, skip_reason)
            return True
        existing_tx_record.block_height = ctx.next_height
        existing_tx_record.timestamp = ctx.timestamp.isoformat()
        ctx.session.add(existing_tx_record)
        if ctx.block_version >= 24:
            # #1314 R2 path (a): no apply/savepoint on this path —
            # the explicit flush is the ONLY thing making the row
            # visible to later same-block reads (e.g. :2759
            # _refund_lock_record on a following BRIDGE_REFUND).
            ctx.session.flush()
        ctx.processed_txs.append(tx)
        ctx.existing_tx_map[tx.tx_hash] = ctx.next_height
        self._logger.info(
            "[PROPOSE] Included pre-registered %s tx %s in block %s",
            tx_type,
            tx.tx_hash,
            ctx.next_height,
        )
        return True

    def _seq_bridge_lock_gate(self, ctx: _SeqTxContext, tx: Any, tx_type: str) -> bool:
        """v9 bridge-lock authorization for a pre-registered BRIDGE_LOCK.
        Returns True only when the tx was rejected."""
        if tx_type != "BRIDGE_LOCK":
            return False
        # v5: a pre-registered credit row bypasses apply_transaction
        # here (it was already applied off-chain), so the bridge
        # authority signature check must run before stamping —
        # otherwise this node seals a credit that followers, who DO
        # validate the block content, reject. Skipping leaves the
        # row un-sealed for retry/next block rather than forking.
        bridge_authority = _bridge_release_authority(ctx.session, self._config.chain_id, ctx.next_height)
        if ctx.block_version >= 9:
            # Followers verify the lock's bridge_signature from
            # the block content (pure path counts below v9,
            # enforces at v9). Stamping an unsigned/invalid lock
            # here would seal a block they reject.
            if not bridge_authority or not verify_bridge_lock_signature(tx.content, tx.tx_hash, bridge_authority):
                self._logger.warning(
                    "[PROPOSE] Skipping pre-registered BRIDGE_LOCK tx %s: failed v9 bridge-lock authorization",
                    tx.tx_hash,
                )
                _seq_reject(ctx, tx, "failed v9 bridge-lock authorization")
                return True
        elif not verify_bridge_lock_signature(tx.content, tx.tx_hash, bridge_authority or ""):
            count_v9_would_reject("bridge_lock_unsigned")
            self._logger.warning("v9 shadow: BRIDGE_LOCK tx %s lacks a valid bridge_signature", tx.tx_hash)
        return False

    def _seq_bridge_credit_gate(self, ctx: _SeqTxContext, tx: Any, tx_type: str) -> str:
        """v5/v6 authorization check for a pre-registered credit row.
        Returns the skip reason, or "" when the tx may be stamped."""
        if tx_type not in {"BRIDGE_RELEASE", "BRIDGE_REFUND"} or ctx.block_version < 5:
            return ""
        expected_sender = "bridge_release" if tx_type == "BRIDGE_RELEASE" else "bridge_refund"
        bridge_authority = _bridge_release_authority(ctx.session, self._config.chain_id, ctx.next_height)
        skip_reason = ""
        if (
            _to_ait_address(tx.content.get("from", "")) != expected_sender
            or not bridge_authority
            or not verify_bridge_credit_signature(tx.content, tx.tx_hash, bridge_authority)
        ):
            skip_reason = "failed v5 bridge-credit authorization"
        elif tx_type == "BRIDGE_REFUND" and ctx.block_version >= 6:
            # v6 refund lock binding — followers run the same
            # check, so stamping an unbound refund would seal a
            # credit they reject.
            lock_hash = bridge_refund_lock_hash(tx.content)
            if not lock_hash:
                skip_reason = "missing payload.lock_tx_hash"
            else:
                reason = validate_bridge_refund_lock(
                    _refund_lock_record(ctx.session, self._config.chain_id, lock_hash, exclude_tx_hash=tx.tx_hash),
                    tx.content,
                )
                if reason:
                    skip_reason = reason
        return skip_reason

    def _seq_block_scoped_credit(self, ctx: _SeqTxContext, tx: Any, tx_type: str, value, fee) -> bool:
        """v0.24.2: apply block-scoped pre-registered credits
        (BRIDGE_RELEASE, BRIDGE_REFUND) now rather than earlier.
        Returns True when the tx is consumed."""
        if not (
            getattr(settings, "block_scoped_preregistered_transactions", True)
            and tx_type in {"BRIDGE_RELEASE", "BRIDGE_REFUND"}
        ):
            return False
        state_transition = _poa.get_state_transition()
        tx_data_for_transition = tx.content.copy()
        tx_data_for_transition["nonce"] = 0
        tx_data_for_transition["value"] = tx_data_for_transition.get("amount", 0)
        success, error_msg = state_transition.apply_transaction_guarded(
            ctx.session,
            self._config.chain_id,
            tx_data_for_transition,
            tx.tx_hash,
            block_version=ctx.block_version,
            block_height=ctx.next_height,
            block_time=ctx.timestamp,
        )
        if not success:
            self._logger.warning("[PROPOSE] Failed to apply credit tx %s: %s", tx.tx_hash, error_msg)
            _seq_reject(ctx, tx, error_msg or "credit apply failed")
            return True
        original_payload = tx.content.get("payload", {})
        transaction = Transaction(
            chain_id=self._config.chain_id,
            tx_hash=tx.tx_hash,
            sender=tx.content.get("from", ""),
            recipient=tx.content.get("to", ""),
            payload=original_payload,
            envelope=dict(tx.content),
            value=value,
            fee=fee,
            nonce=0,
            timestamp=ctx.timestamp.isoformat(),
            block_height=ctx.next_height,
            status="confirmed",
            type=tx_type,
        )
        ctx.pending_records.append(transaction)
        if ctx.block_version >= 24:
            # #1314 R2: match importer visibility — the row must be
            # flushed before the next transaction's apply queries
            # Transaction rows (e.g. refund/lock lookups).
            ctx.session.add(transaction)
            ctx.session.flush()
        ctx.changed_addresses.add(_to_ait_address(tx.content.get("to", "")))
        ctx.existing_tx_map[tx.tx_hash] = ctx.next_height
        ctx.processed_txs.append(tx)
        self._logger.info("[PROPOSE] Successfully applied credit tx %s", tx.tx_hash)
        return True

    def _seq_sender_state(self, ctx: _SeqTxContext, tx: Any, sender: str):
        """Resolve the sender's spendable balance and authoritative nonce.

        Returns ``(sender_balance, authoritative_nonce)``, or None after
        recording a refusal (missing sender account pre-v22)."""
        sender_account = ctx.account_map.get(sender)
        if not sender_account and ctx.block_version >= 22:
            # v22 R1 (CONSENSUS-STATE-001): a sender missing from the
            # pre-block account map reads live state first — an
            # account created earlier in this same block is already
            # flushed — then falls back to virtual (0,0), matching
            # validate_transaction. apply_transaction materializes
            # the row on success, so a valid zero-cost tx from a
            # never-seen address is includable, not skipped (R1a).
            sender_account = ctx.session.get(Account, (self._config.chain_id, sender))
            if sender_account is not None:
                ctx.account_map[sender] = sender_account
        if not sender_account and ctx.block_version < 22:
            self._logger.warning("[PROPOSE] Skipping tx %s: sender account not found for %s", tx.tx_hash, sender)
            _seq_reject(ctx, tx, f"sender account not found for {sender}")
            return None
        if ctx.block_version >= 24:
            # #1314 V5: authoritative scalar read — the account_map /
            # session.get path can serve identity-map-stale balance
            # and nonce. Same session/transaction; creates no Account;
            # virtual (0,0) semantics preserved for missing accounts.
            auth_balance, auth_nonce, auth_exists = read_current_account(ctx.session, self._config.chain_id, sender)
            sender_balance = auth_balance if auth_balance is not None else 0
            authoritative_nonce = auth_nonce if auth_exists else 0
        else:
            sender_balance = sender_account.balance if sender_account else 0
            authoritative_nonce = sender_account.nonce if sender_account and sender_account.nonce is not None else 0
        return sender_balance, authoritative_nonce

    def _seq_canonical_tx_type(self, ctx: _SeqTxContext, tx: Any) -> str | None:
        """Canonical upper tx type for the record, or None when a
        GOVERNANCE_* payload failed validation (reason already recorded)."""
        tx_type = tx.content.get("type", "TRANSFER")
        if tx_type:
            tx_type = tx_type.upper()
        else:
            tx_type = "TRANSFER"
        if tx_type.startswith("GOVERNANCE_"):
            gov_errors = _validate_governance_payload(tx_type, tx.content.get("payload", {}))
            if gov_errors:
                self._logger.warning(
                    "[PROPOSE] Skipping governance tx %s: invalid payload: %s",
                    tx.tx_hash,
                    ", ".join(gov_errors),
                )
                _seq_reject(ctx, tx, f"invalid governance payload: {', '.join(gov_errors)}")
                return None
        return str(tx_type)

    def _seq_apply_and_record(
        self,
        ctx: _SeqTxContext,
        tx: Any,
        sender: str,
        recipient: str,
        value,
        fee,
        tx_type: str,
        authoritative_nonce,
        existing_tx_record,
    ) -> None:
        """Apply the state transition and stage the Transaction record."""
        recipient_account = ctx.account_map.get(recipient)
        if recipient_account:
            self._logger.info("[PROPOSE] Recipient account exists for %s", recipient)
        else:
            self._logger.info("[PROPOSE] Recipient account for %s will be created by the state transition", recipient)
        state_transition = _poa.get_state_transition()
        tx_data_for_transition = tx.content.copy()
        if use_account_nonce_override(tx_data_for_transition, ctx.block_version):
            tx_data_for_transition["nonce"] = authoritative_nonce
        tx_data_for_transition["value"] = tx_data_for_transition.get("amount", 0)
        success, error_msg = state_transition.apply_transaction_guarded(
            ctx.session,
            self._config.chain_id,
            tx_data_for_transition,
            tx.tx_hash,
            block_version=ctx.block_version,
            block_height=ctx.next_height,
            block_time=ctx.timestamp,
        )
        if not success:
            self._logger.warning("[PROPOSE] Failed to apply transaction %s: %s", tx.tx_hash, error_msg)
            _seq_reject(ctx, tx, error_msg or "state transition rejected transaction")
            return
        if recipient_account is None:
            # The state transition created it; pick up the real
            # row so later transactions in this block see it.
            recipient_account = ctx.session.get(Account, (self._config.chain_id, recipient))
            if recipient_account is not None:
                ctx.account_map[recipient] = recipient_account
        original_payload = tx.content.get("payload", {})
        self._seq_write_tx_record(
            ctx, tx, tx_type, value, fee, tx_data_for_transition["nonce"], existing_tx_record, original_payload
        )
        # Track changed addresses for incremental state root computation
        ctx.changed_addresses.add(sender)
        ctx.changed_addresses.add(recipient)
        # Track the newly committed tx hash so subsequent iterations
        # in this loop detect it as a duplicate without another DB query.
        ctx.existing_tx_map[tx.tx_hash] = ctx.next_height
        ctx.processed_txs.append(tx)
        self._logger.info("[PROPOSE] Successfully processed tx %s: updated balances", tx.tx_hash)

    def _seq_write_tx_record(
        self, ctx: _SeqTxContext, tx: Any, tx_type: str, value, fee, nonce, existing_tx_record, original_payload
    ) -> None:
        """Stage the Transaction row: update the pre-registered record when
        one exists, else build the new confirmed row. Records are flushed to
        the session only by the caller after all transitions succeed."""
        if existing_tx_record:
            existing_tx_record.block_height = ctx.next_height
            existing_tx_record.status = "confirmed"
            existing_tx_record.timestamp = ctx.timestamp.isoformat()
            existing_tx_record.nonce = nonce
            if existing_tx_record.envelope is None:
                existing_tx_record.envelope = dict(tx.content)
            ctx.pending_records.append(existing_tx_record)
            if ctx.block_version >= 24:
                ctx.session.add(existing_tx_record)
                ctx.session.flush()
        else:
            transaction = Transaction(
                chain_id=self._config.chain_id,
                tx_hash=tx.tx_hash,
                # Raw, not the canonicalised locals: these are signed (V23-65).
                sender=tx.content.get("from", ""),
                recipient=tx.content.get("to", ""),
                payload=original_payload,
                envelope=dict(tx.content),
                value=value,
                fee=fee,
                nonce=nonce,
                timestamp=ctx.timestamp.isoformat(),
                block_height=ctx.next_height,
                status="confirmed",
                type=tx_type,
            )
            ctx.pending_records.append(transaction)
            if ctx.block_version >= 24:
                ctx.session.add(transaction)
                ctx.session.flush()

    def _process_txs_parallel(
        self,
        session: Session,
        pending_txs: list[Any],
        account_map: dict[str, Account],
        existing_tx_map: dict[str, int],
        next_height: int,
        timestamp: datetime,
        block_version: int,
        escrow_context: dict[str, dict[str, Any]] | None = None,
        bridge_lock_context: dict[str, dict[str, Any]] | None = None,
        rejected: list[tuple[Any, str]] | None = None,
    ) -> tuple[list[Any], set[str], bool]:
        """Process transactions in parallel using dependency analysis.

        Returns (processed_txs, changed_addresses, success).
        Falls back to sequential if conflict rate exceeds threshold.

        ``rejected``, when given, collects ``(tx, reason)`` for every drained
        tx validation refused so the caller can persist a terminal status
        (#669).
        """
        chain_id = self._config.chain_id
        # Build dependency graph from tx read/write sets
        graph, tx_by_hash = _parallel_build_graph(pending_txs)

        # Check conflict rate — fall back to sequential if too many conflicts
        conflict_rate = graph.conflict_rate()
        threshold = getattr(settings, "conflict_threshold", 0.5)
        if conflict_rate > threshold:
            self._logger.info(
                "[PROPOSE-PARALLEL] Conflict rate %.2f exceeds threshold %.2f — falling back to sequential",
                conflict_rate,
                threshold,
            )
            return [], set(), True  # signal: no parallel processing, caller continues sequential

        groups = graph.get_conflict_groups()
        self._logger.info(
            "[PROPOSE-PARALLEL] %d txs → %d groups (conflict_rate=%.2f)",
            len(pending_txs),
            len(groups),
            conflict_rate,
        )

        # Bridge-signed txs (credits v5, locks v9) carry a signature from the
        # bridge release authority — resolve the on-chain parameter once so
        # the pure path applies the same gate as the sequential one. Only
        # queried when a v5+ block actually contains a bridge-signed tx.
        bridge_authority = _parallel_bridge_authority(session, chain_id, next_height, block_version, pending_txs)

        # Prepare tx_data for each tx (with nonce set from account_map)
        tx_data_map = _parallel_tx_data_map(pending_txs, account_map, block_version)

        # Track processed tx hashes for duplicate detection
        processed_tx_hashes: set[str] = set()

        # Execute groups in parallel — within each group, txs are independent
        max_workers = getattr(settings, "parallel_workers", 4)
        executor = _poa.ParallelExecutor(max_workers=max_workers)
        try:
            all_deltas: list[tuple[int, StateDelta, Any]] = []  # (index, delta, tx)
            for group in groups:
                # Update nonces from account_map before processing each group
                # (conflicting txs in later groups need updated nonces from earlier groups)
                _parallel_refresh_group_nonces(group, tx_data_map, account_map, block_version)

                # Build the list of (tx_hash, tx_data) for this group
                group_items = [(tx_hash, tx_data_map[tx_hash]) for tx_hash in group]

                def compute_fn(item: tuple[str, dict[str, Any]]) -> StateDelta:
                    tx_hash, tx_data = item
                    return _poa.compute_state_delta(
                        account_map,
                        tx_data,
                        chain_id,
                        tx_hash,
                        processed_tx_hashes,
                        block_version=block_version,
                        escrow_context=escrow_context,
                        bridge_authority=bridge_authority,
                        bridge_lock_context=bridge_lock_context,
                        block_time=timestamp,
                    )

                results = executor.execute_groups([group_items], compute_fn)
                group_deltas = results[0] if results else []

                # Apply successful deltas to account_map immediately (within group,
                # txs don't conflict, so order within group doesn't matter for state)
                self._parallel_collect_deltas(
                    group_items,
                    group_deltas,
                    tx_by_hash,
                    existing_tx_map,
                    account_map,
                    processed_tx_hashes,
                    all_deltas,
                    rejected,
                    block_version,
                )
        finally:
            executor.close()

        # Sort deltas by original tx index for deterministic ordering
        all_deltas.sort(key=lambda x: x[0])

        # Write all deltas to DB in a single batch — this is the only phase that
        # touches the session, so it is wrapped: a mid-write failure must not
        # escape with flushed state or queued Transaction rows still pending in
        # the caller's session (same incident class as the sequential path's
        # savepoint leak).
        write_result = self._parallel_write_deltas(
            session, all_deltas, tx_data_map, chain_id, block_version, next_height, timestamp, existing_tx_map
        )
        if write_result is None:
            return [], set(), False
        processed_txs, changed_addresses = write_result

        self._logger.info(
            "[PROPOSE-PARALLEL] Processed %d/%d txs in parallel",
            len(processed_txs),
            len(pending_txs),
        )
        return processed_txs, changed_addresses, True

    def _parallel_collect_deltas(
        self,
        group_items: list[tuple[str, dict[str, Any]]],
        group_deltas: list[StateDelta],
        tx_by_hash: dict[str, Any],
        existing_tx_map: dict[str, int],
        account_map: dict[str, Account],
        processed_tx_hashes: set[str],
        all_deltas: list[tuple[int, StateDelta, Any]],
        rejected: list[tuple[Any, str]] | None,
        block_version: int,
    ) -> None:
        """Fold one group's computed deltas into account_map + all_deltas.

        Successful deltas apply immediately (within a group txs don't
        conflict); failures are logged and recorded on ``rejected``."""
        for i, (tx_hash, _) in enumerate(group_items):
            delta = group_deltas[i]
            tx = tx_by_hash[tx_hash]
            if delta.success:
                # Check for duplicate tx in DB
                if existing_tx_map.get(tx_hash) is not None:
                    self._logger.warning(
                        "[PROPOSE-PARALLEL] Skipping tx %s: already exists in database at block %s",
                        tx_hash,
                        existing_tx_map[tx_hash],
                    )
                    continue
                _poa.apply_delta_to_map(account_map, delta, self._config.chain_id, block_version)
                processed_tx_hashes.add(tx_hash)
                all_deltas.append((i, delta, tx))
            else:
                self._logger.warning("[PROPOSE-PARALLEL] Failed to validate tx %s: %s", tx_hash, delta.error)
                if rejected is not None:
                    rejected.append((tx, delta.error or "parallel validation failed"))

    def _parallel_write_deltas(
        self,
        session: Session,
        all_deltas: list[tuple[int, StateDelta, Any]],
        tx_data_map: dict[str, dict[str, Any]],
        chain_id: str,
        block_version: int,
        next_height: int,
        timestamp: datetime,
        existing_tx_map: dict[str, int],
    ):
        """Write all deltas to the session in one batch.

        Returns ``(processed_txs, changed_addresses)``, or None after
        rollback when the write phase fails (caller aborts the proposal)."""
        successful_deltas = [d for _, d, _ in all_deltas]
        try:
            if successful_deltas:
                _poa.apply_deltas_to_db(
                    session,
                    successful_deltas,
                    chain_id,
                    block_version,
                    block_height=next_height,
                    block_time=timestamp,
                )
            prereg_rows = self._parallel_prereg_rows(session, all_deltas, chain_id)
            return self._parallel_write_tx_records(
                session, all_deltas, prereg_rows, tx_data_map, chain_id, next_height, timestamp, existing_tx_map
            )
        except Exception:
            session.rollback()
            self._logger.error("[PROPOSE-PARALLEL] Write phase failed; session rolled back — aborting proposal")
            return None

    def _parallel_prereg_rows(self, session: Session, all_deltas: list[tuple[int, StateDelta, Any]], chain_id: str):
        # Pre-registered rows (bridge credits, MESSAGE) already exist with
        # block_height NULL — stamp the stored row instead of inserting a
        # duplicate (chain_id/tx_hash is unique). Mirrors the sequential
        # path's stamp branch. Only queried when such a tx is present.
        prereg_rows: dict[str, Transaction] = {}
        if any(d.tx_type in {"MESSAGE", "BRIDGE_RELEASE", "BRIDGE_REFUND", "BRIDGE_LOCK"} for _, d, _ in all_deltas):
            prereg_rows = {
                r.tx_hash: r
                for r in session.exec(
                    select(Transaction).where(
                        Transaction.chain_id == chain_id,
                        Transaction.tx_hash.in_([tx.tx_hash for _, _, tx in all_deltas]),  # type: ignore[attr-defined]
                        Transaction.block_height.is_(None),  # type: ignore[union-attr]
                        Transaction.status == "confirmed",
                    )
                ).all()
            }
        return prereg_rows

    def _parallel_write_tx_records(
        self,
        session: Session,
        all_deltas: list[tuple[int, StateDelta, Any]],
        prereg_rows: dict[str, Transaction],
        tx_data_map: dict[str, dict[str, Any]],
        chain_id: str,
        next_height: int,
        timestamp: datetime,
        existing_tx_map: dict[str, int],
    ):
        """Create/stamp Transaction records and collect changed addresses."""
        processed_txs: list[Any] = []
        changed_addresses: set[str] = set()
        for _idx, delta, tx in all_deltas:
            sender = delta.sender
            recipient = delta.recipient
            tx_type = delta.tx_type
            tx_data = tx.content
            existing_record = prereg_rows.get(tx.tx_hash)
            if existing_record is not None and tx_type in {"MESSAGE", "BRIDGE_RELEASE", "BRIDGE_REFUND", "BRIDGE_LOCK"}:
                existing_record.block_height = next_height
                existing_record.timestamp = timestamp.isoformat()
                if existing_record.envelope is None:
                    existing_record.envelope = dict(tx_data)
                session.add(existing_record)
            else:
                value = tx_data.get("amount", 0)
                fee = tx_data.get("fee", 0)
                original_payload = tx_data.get("payload", {})
                transaction = Transaction(
                    chain_id=chain_id,
                    tx_hash=tx.tx_hash,
                    # Raw, not the canonicalised locals: these are signed (V23-65).
                    sender=tx_data.get("from", sender),
                    recipient=tx_data.get("to", recipient),
                    payload=original_payload,
                    envelope=dict(tx_data),
                    value=value,
                    fee=fee,
                    nonce=tx_data_map[tx.tx_hash].get("nonce", 0),
                    timestamp=timestamp.isoformat(),
                    block_height=next_height,
                    status="confirmed",
                    type=tx_type,
                )
                session.add(transaction)
            changed_addresses.add(sender)
            if recipient:
                changed_addresses.add(recipient)
            existing_tx_map[tx.tx_hash] = next_height
            processed_txs.append(tx)
            self._logger.info("[PROPOSE-PARALLEL] Successfully processed tx %s", tx.tx_hash)
        return processed_txs, changed_addresses
