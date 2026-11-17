"""Sequential per-transaction apply helpers for ``BlockImportMixin`` (#1860).

Split out of ``aitbc_chain.sync_block_import`` (#1860): the methods are
byte-identical moves onto a mixin that ``BlockImportMixin`` inherits, so
every ``self._…`` call resolves exactly as before. Import
``aitbc_chain.sync_block_import`` first (it wires these mixins in); this
module is not meant to be imported directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .base_models import Account, _to_ait_address
from .base_models import Transaction as ChainTransaction
from .logger import get_logger
from .state.authoritative_reads import read_current_account
from .state.pure_state_transition import _determine_tx_type
from .state.state_transition import StateTransition, get_state_transition, use_account_nonce_override
from .sync_base import SyncBase

if TYPE_CHECKING:
    from sqlmodel import Session

    from .sync_block_import import _AppendContext


logger = get_logger("aitbc_chain.sync_block_import")


class SequentialApplyMixin(SyncBase):
    """Full StateTransition.apply_transaction path used when the parallel path is off or ineligible."""

    if TYPE_CHECKING:
        # Provided by ``BlockImportMixin`` itself (sync_block_import.py).
        def _upsert_import_tx_row(
            self, session: Session, db_tx: ChainTransaction, tx_only_root: bool
        ) -> ChainTransaction | None: ...

    def _apply_sequential_transactions(
        self,
        ctx: _AppendContext,
        transactions: list[dict[str, Any]],
        state_transition: StateTransition | None,
    ) -> None:
        """Sequential fallback path (parallel_tx_validation off or conflict
        rate exceeds the threshold)."""
        # The loop-carried bindings deliberately mirror the original inline
        # loop's frame locals: they keep the most recently touched ORM objects
        # (sender Account, tx rows) referenced for the next iteration, which
        # preserves the session identity-map lifetime the v<7 nonce override
        # and same-hash tx-row upgrade rely on.
        sender_acct: Account | None = None
        db_tx: ChainTransaction | None = None
        existing_tx: ChainTransaction | None = None
        for tx_data in transactions:
            ctx.check_deadline()
            sender_acct, db_tx, existing_tx = self._apply_sequential_tx(
                ctx, tx_data, state_transition, sender_acct, db_tx, existing_tx
            )

    def _ensure_sequential_sender(self, ctx: _AppendContext, sender_addr: str, raw_from: str) -> Account | None:
        """v22 (CONSENSUS-STATE-001, #1169): no pre-apply sender insert — a tx
        that validate/apply rejects must leave zero mutation, and a phantom
        account row is committed state. apply_transaction creates accounts only
        on its success paths; a same-block-earlier credit is already visible
        via session.get above. Historical v2-v21 blocks still pre-create the
        sender to match their sealed state roots."""
        if raw_from in {"bridge_release", "bridge_refund"}:
            return None
        sender_acct = ctx.session.get(Account, (self._chain_id, sender_addr))
        if sender_acct is None and 2 <= ctx.block_version < 22:
            sender_acct = Account(chain_id=self._chain_id, address=sender_addr, balance=0, nonce=0)
            ctx.session.add(sender_acct)
            ctx.session.flush()
        return sender_acct

    def _sync_sequential_tx_fields(
        self,
        ctx: _AppendContext,
        tx_data: dict[str, Any],
        sender_acct: Account | None,
        sender_addr: str,
        raw_from: str,
    ) -> None:
        """Bump tx_data nonce/value to the live account state before applying,
        mirroring the block producer.  Blocks may contain multiple same-sender
        transactions that share the stored nonce (e.g. parallel-validated
        GPU_MARKET offers); the follower must apply them with the current
        account nonce, not the stored one, or the second transaction fails and
        the state root diverges."""
        if raw_from not in {"bridge_release", "bridge_refund"} and use_account_nonce_override(tx_data, ctx.block_version):
            if ctx.block_version >= 24:
                # #1314 V5 mirror: authoritative scalar read — the
                # identity-mapped sender_acct can be stale after
                # raw-SQL writes earlier in this block.
                _, auth_nonce, auth_exists = read_current_account(ctx.session, self._chain_id, sender_addr)
                if auth_exists:
                    tx_data["nonce"] = auth_nonce
            elif sender_acct is not None:
                tx_data["nonce"] = sender_acct.nonce
        if ctx.block_version >= 20:
            # v20+: value is unsigned — the signed amount always
            # wins, exactly as the proposer does (#1066).
            if "amount" in tx_data:
                tx_data["value"] = tx_data["amount"]
        elif "value" not in tx_data and "amount" in tx_data:
            tx_data["value"] = tx_data["amount"]

    def _sequential_tx_type(self, ctx: _AppendContext, tx_data: dict[str, Any]) -> str:
        """Resolve the stored tx type, including the tx-derived-era
        BRIDGE_LOCK override (#1940 F5: payload-typed locks store their real
        resolved type, matching the producer)."""
        tx_type: str = tx_data.get("type", "TRANSFER")
        if tx_type:
            tx_type = tx_type.upper()
        else:
            tx_type = "TRANSFER"
        if ctx.tx_only_root and _determine_tx_type(tx_data) == "BRIDGE_LOCK":
            tx_type = "BRIDGE_LOCK"
        return tx_type

    def _apply_sequential_tx(
        self,
        ctx: _AppendContext,
        tx_data: dict[str, Any],
        state_transition: StateTransition | None,
        sender_acct: Account | None,
        db_tx: ChainTransaction | None,
        existing_tx: ChainTransaction | None,
    ) -> tuple[Account | None, ChainTransaction | None, ChainTransaction | None]:
        """Apply one transaction through the full StateTransition path and
        persist its sealed Transaction row.

        Returns ``(sender_acct, db_tx, existing_tx)`` so the caller's
        loop-carried bindings keep the same identity-map lifetime the
        original inline loop's frame locals had."""
        sender_addr = _to_ait_address(tx_data.get("from", ""))
        recipient_addr = _to_ait_address(tx_data.get("to", ""))
        int(tx_data.get("amount", 0) or 0)
        int(tx_data.get("fee", 0) or 0)
        tx_hash = tx_data.get("tx_hash", "")
        raw_from = tx_data.get("from", "")
        if raw_from not in {"bridge_release", "bridge_refund"}:
            # Only non-bridge senders rebind sender_acct — a bridge tx leaves
            # the previous iteration's Account referenced, exactly as the
            # original inline loop did (identity-map lifetime matters for the
            # v<24 nonce override below).
            sender_acct = self._ensure_sequential_sender(ctx, sender_addr, raw_from)
        # Do not create the recipient account here, matching the
        # proposer (poa.py): apply_transaction ensures the recipient
        # itself on the paths that credit it. Pre-creating left a
        # phantom row for zero-value types (GPU_MARKET offers carry
        # to=0x0000…0000), so the importer computed a state root the
        # committed header never had — every validator rejected the
        # block (bc-2 fork at height 1462).
        self._sync_sequential_tx_fields(ctx, tx_data, sender_acct, sender_addr, raw_from)
        state_transition = state_transition if state_transition is not None else get_state_transition()
        success, error_msg = state_transition.apply_transaction_guarded(
            ctx.session,
            self._chain_id,
            tx_data,
            tx_hash,
            block_version=ctx.block_version,
            block_height=ctx.block_data["height"],
            # v18: the sealed header timestamp drives the
            # deterministic apply paths — identical to the
            # ``timestamp`` the proposer threaded through.
            block_time=ctx.timestamp,
        )
        if not success:
            logger.warning(ctx.reject_tag + " Failed to apply transaction %s: %s", tx_hash, error_msg)
        if ctx.tx_only_root and tx_hash in ctx.declared_lock_hashes and success:
            # #1940 F5: only an actually-applied lock may be
            # certified by the tx-derived root — below v20 the
            # persisted "confirmed" status proves nothing.
            ctx.successful_lock_hashes.add(tx_hash)
        db_tx = ChainTransaction(
            chain_id=self._chain_id,
            tx_hash=tx_hash,
            block_height=ctx.block_data["height"],
            # Raw, not the canonicalised locals: these are signed (V23-65).
            sender=tx_data.get("from", sender_addr),
            recipient=tx_data.get("to", recipient_addr),
            payload=tx_data.get("payload", {}),
            envelope=dict(tx_data),
            type=self._sequential_tx_type(ctx, tx_data),
            value=tx_data.get("value", tx_data.get("amount", 0)),
            fee=tx_data.get("fee", 0),
            nonce=tx_data.get("nonce", 0),
            status="confirmed" if success or ctx.block_version < 20 else "failed",
        )
        existing_tx = self._upsert_import_tx_row(ctx.session, db_tx, ctx.tx_only_root)
        if ctx.block_version >= 24:
            # #1314 R2 importer mirror: prod sessions run
            # autoflush=False, so without this flush the sealed
            # row stays pending and later same-block applies
            # (escrow-lock/refund Transaction-row reads) cannot
            # see it — diverging from the proposer's in-loop
            # flush schedule.
            ctx.session.flush()
        return sender_acct, db_tx, existing_tx
