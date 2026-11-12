"""Ordered ``_vt_*`` validation gates for ``StateTransition.validate_transaction`` (#1867 pure-move split).

Import ``aitbc_chain.state.state_transition`` first (it wires these
mixins into ``StateTransition``); this module is not meant to be imported
directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from . import state_transition as _st

import json
from ..base_models import Bond, _to_ait_address
from ..chain_isolation_metrics import (
    record_chain_id_validation_failure,
    record_chain_isolation_violation,
    record_cross_chain_transaction_attempt,
)
from ..config import settings
from ..cross_chain.bridge_lock_guard import lock_derivation_source
from ..models import Account, Receipt, Transaction
from ..rpc.utils import verify_request_signature
from .agent_spend import agent_spend_verdict
from .bridge_credit import (
    bridge_refund_lock_hash,
    validate_bridge_refund_lock,
    verify_bridge_credit_signature,
    verify_bridge_lock_signature,
)
from .gpu_resources import (
    GPURegistration,
    gpu_allocate_admission_error,
    gpu_allocate_deactivated_error,
    gpu_deregister_error,
    retired_gpu_error,
)
from .pure_state_transition import _carried_receipt_record, escrow_sweep_ceiling
from .v9_policy import count_v9_would_reject, v9_signature_verdict
from aitbc.crypto.signature_recovery import canonical_address
from decimal import Decimal
from sqlmodel import select
from typing import Any
from .state_transition import (
    _TxValidationCtx,
    _authority_parameter_change_error,
    _bridge_release_authority,
    _ensure_account,
    _escrow_address,
    _escrow_beneficiary,
    _escrow_fee_cap_bps,
    _escrow_fee_recipient,
    _escrow_lock_beneficiaries,
    _escrow_obligation_state,
    _escrow_settlement_authority,
    _get_escrow_lock,
    _get_escrow_lock_block_version,
    _governance_executors,
    _gpu_price_per_hour_in_range,
    _is_valid_0x_address,
    _is_zero_value_tx_type,
    _payload_auth_binds_transfer,
    _refund_lock_record,
    _tx_type,
    _v13_shadow_observe,
    _validate_stake_release_locks,
    bond_tx_verdict,
    logger,
)


class _ValidationMixin:
    if TYPE_CHECKING:
        _processed_tx_hashes: set[str]

    @staticmethod
    def _verify_payload_auth(tx_type: str, auth: Any, tx_data: dict[str, Any]) -> bool:
        """Verify the authorization evidence carried in a protocol transfer payload.

        Protocol transfers (``STAKE_LOCK``/``STAKE_RELEASE``) are queued
        unsigned — the keyless escrow cannot sign a release — so the RPC layer
        embeds ``payload.auth = {"signer", "message", "signature"}``, where
        ``message`` is the exact request dict the authorizer signed. This
        re-verifies it at state-transition time so a malformed auth is
        rejected rather than recorded in the ledger.

        Beyond self-consistency, the signed message must bind the transfer it
        authorizes: the party a ``STAKE_LOCK`` debits or a ``STAKE_RELEASE``
        credits, the locked amount, the stake being moved, and the chain.
        Without the binding a captured signature is re-attachable to any
        same-amount transfer — a nonceless signed message is otherwise a
        permanent bearer token. The signer itself stays unbound by design:
        agent staking is operator-signed on the user's behalf and the
        operator set is node-local env config, not consensus state.

        An absent ``auth`` is allowed — pre-auth protocol transfers exist in
        sealed history (e.g. the STAKE_LOCK in block 7306) and must keep
        replaying identically. No sealed transaction on the live chain
        carries ``payload.auth``, so tightening the present-auth rules cannot
        diverge replay.
        """
        if not isinstance(auth, dict):
            return False
        signature = auth.get("signature")
        message = auth.get("message")
        signer = auth.get("signer")
        if not signature or not isinstance(message, dict) or not signer:
            return False
        if not verify_request_signature(str(signer), str(signature), message):
            return False
        return _payload_auth_binds_transfer(tx_type, message, tx_data)

    def _vt_chain_id(self, ctx: _TxValidationCtx) -> tuple[bool, str] | None:
        tx_chain_id = ctx.tx_data.get("chain_id")
        if tx_chain_id and tx_chain_id != ctx.chain_id:
            record_cross_chain_transaction_attempt(source_chain=tx_chain_id, target_chain=ctx.chain_id, node=ctx.chain_id)
            record_chain_id_validation_failure(expected_chain=ctx.chain_id, actual_chain=tx_chain_id, node=ctx.chain_id)
            record_chain_isolation_violation("cross_chain_tx_rejected", node=ctx.chain_id)
            logger.warning(
                "Chain isolation violation: Transaction %s has chain_id=%s but node is configured for chain_id=%s. Rejecting cross-chain transaction.",
                ctx.tx_hash,
                tx_chain_id,
                ctx.chain_id,
            )
            return (
                False,
                f"Chain isolation violation: transaction chain_id={tx_chain_id} does not match node chain_id={ctx.chain_id}",
            )
        return None

    def _vt_dedup(self, ctx: _TxValidationCtx) -> tuple[bool, str] | None:
        # Replay protection exists to refuse a sealed tx pushed back through
        # admission. The parent-repair path (poa.py _reapply_parent_block)
        # re-executes exactly the rows it loaded from the transaction table —
        # dedup would reject the very txs it is asked to re-apply, so it opts
        # out via skip_dedup. That call site is the only one allowed to.
        if ctx.skip_dedup:
            return None
        # One row lookup drives both checks. A ``status=rejected``
        # writeback is a verdict, not a processed transaction — the
        # in-memory set is not status-aware, so a hash it holds from an
        # earlier rejected apply must fall through to re-application
        # rather than firing replay (Refs #712 follow-up; same family
        # as #704's DB-side fix).
        persisted_row = ctx.session.exec(
            select(Transaction.tx_hash, Transaction.status).where(
                Transaction.chain_id == ctx.chain_id,
                Transaction.tx_hash == ctx.tx_hash,
            )
        ).first()
        persisted_status = persisted_row[1] if persisted_row is not None else None
        if persisted_status == "rejected":
            self._processed_tx_hashes.discard(ctx.tx_hash)
        if ctx.tx_hash in self._processed_tx_hashes and persisted_status != "rejected":
            logger.warning("Replay attack detected: Transaction %s already processed", ctx.tx_hash)
            return (False, f"Transaction {ctx.tx_hash} already processed (replay attack)")
        # Persistent replay protection: the in-memory set above is lost on
        # restart; the DB unique constraint on (chain_id, tx_hash) is not.
        if persisted_row is not None and persisted_status != "rejected":
            logger.warning("Replay attack detected: Transaction %s already persisted", ctx.tx_hash)
            return (False, f"Transaction {ctx.tx_hash} already processed (replay attack)")
        return None

    def _vt_prepare(self, ctx: _TxValidationCtx) -> tuple[bool, str] | None:
        ctx.sender_addr = _to_ait_address(ctx.tx_data.get("from") or "")
        ctx.recipient_addr = _to_ait_address(ctx.tx_data.get("to") or "")
        ctx.value = ctx.tx_data.get("value", 0)
        ctx.fee = ctx.tx_data.get("fee", 0)
        # v20+: ``value`` is unsigned (the signature covers ``amount``) — a
        # divergent value is a forgery, reject rather than pick one (#1066).
        if ctx.block_version >= 20 and "amount" in ctx.tx_data:
            try:
                if "value" in ctx.tx_data and int(ctx.value) != int(ctx.tx_data["amount"]):
                    return (False, "transaction value must equal signed amount")
            except (TypeError, ValueError):
                return (False, "transaction value/amount must be integers")
        ctx.tx_record = ctx.session.exec(
            select(Transaction).where(Transaction.chain_id == ctx.chain_id, Transaction.tx_hash == ctx.tx_hash)
        ).first()
        ctx.tx_type = _tx_type(ctx.tx_data, ctx.tx_record)
        return None

    def _vt_liquidity(self, ctx: _TxValidationCtx) -> tuple[bool, str] | None:
        if ctx.tx_type not in {"LIQUIDITY_DEPOSIT", "LIQUIDITY_WITHDRAW", "LIQUIDITY_CLAIM"}:
            return None
        # Validate the payload before touching state: _ensure_account below
        # writes account rows, and a validator that returns False after
        # writing them leaves the proposer with accounts no other node has.
        ctx.payload = ctx.tx_data.get("payload") or {}
        if ctx.tx_type == "LIQUIDITY_DEPOSIT":
            if not ctx.payload.get("pool_id"):
                return (False, "LIQUIDITY_DEPOSIT payload must include pool_id")
            if "lock_days" not in ctx.payload:
                return (False, "LIQUIDITY_DEPOSIT payload must include lock_days")
        if ctx.tx_type in {"LIQUIDITY_WITHDRAW", "LIQUIDITY_CLAIM"}:
            if not ctx.payload.get("stake_id"):
                return (False, f"{ctx.tx_type} payload must include stake_id")
        # Ensure the pool reserve/treasury/emission accounts and the sender
        # and recipient accounts exist before the generic recipient check.
        # v22 (CONSENSUS-STATE-001, #1169): validation is read-only — a
        # rejected tx must not leave account rows behind; apply creates
        # them on its success paths instead.
        if ctx.block_version < 22:
            _ensure_account(ctx.session, ctx.chain_id, ctx.sender_addr)
            _ensure_account(ctx.session, ctx.chain_id, _to_ait_address(ctx.tx_data.get("to") or ""))
        return None

    def _vt_bridge_credit(self, ctx: _TxValidationCtx) -> tuple[bool, str] | None:
        if ctx.tx_type not in {"BRIDGE_RELEASE", "BRIDGE_REFUND"}:
            return None
        # Pre-registered credit transactions do not require a sender account or
        # nonce. The state update is applied off-chain by the RPC call that
        # created the transaction; the block just anchors the record.  Replay is
        # prevented by the persistent tx hash check above.
        if ctx.block_version >= 5:
            # Only the bridge's own pseudo-sender shape is legitimate: public
            # intake refuses these types, so a block carrying any other sender
            # is a forged credit. (A Byzantine proposer can still mint — the
            # pseudo-sender carries no key; the gate fails closed on wrong
            # shapes so leaked or hand-injected copies cannot apply.)
            expected_sender = "bridge_release" if ctx.tx_type == "BRIDGE_RELEASE" else "bridge_refund"
            if ctx.sender_addr != expected_sender:
                return (
                    False,
                    f"{ctx.tx_type} must carry the internal pseudo-sender {expected_sender}, got {ctx.sender_addr}",
                )
            # The pseudo-sender is a name, not a key: without a signature a
            # Byzantine proposer can still self-issue a credit under it.
            # v5 therefore additionally requires the bridge authority's
            # secp256k1 signature over the credit's semantic fields
            # (state/bridge_credit.py). Pre-v5 history had no signatures
            # and stays lenient for replay.
            authority = _bridge_release_authority(ctx.session, ctx.chain_id, ctx.block_height)
            if not authority:
                return (
                    False,
                    f"{ctx.tx_type} requires a bridge release authority: set the bridge_release_authority chain parameter",
                )
            if not verify_bridge_credit_signature(ctx.tx_data, ctx.tx_hash, authority):
                return (
                    False,
                    f"{ctx.tx_type} must carry a valid bridge_signature from the bridge release authority",
                )
            # v6: a refund must name the sealed BRIDGE_LOCK it repays on
            # this chain (payload.lock_tx_hash), with matching sender and
            # amount, and the lock must not already be refunded. Even the
            # authority key can then only ever anchor a refund for a real
            # lock. Pre-v6 history had no lock binding and stays lenient.
            if ctx.block_version >= 6 and ctx.tx_type == "BRIDGE_REFUND":
                lock_hash = bridge_refund_lock_hash(ctx.tx_data)
                if not lock_hash:
                    return (
                        False,
                        "BRIDGE_REFUND must carry payload.lock_tx_hash naming its BRIDGE_LOCK",
                    )
                reason = validate_bridge_refund_lock(
                    _refund_lock_record(ctx.session, ctx.chain_id, lock_hash, exclude_tx_hash=ctx.tx_hash),
                    ctx.tx_data,
                )
                if reason:
                    return (False, reason)
        return (True, "Pre-registered credit transaction validated")

    def _vt_bridge_lock_sig(self, ctx: _TxValidationCtx) -> tuple[bool, str] | None:
        if ctx.tx_type != "BRIDGE_LOCK":
            return None
        # Pre-registered bridge lock: the sender was already debited when the
        # lock was created. The block only anchors the record. Do not validate
        # the tx nonce or require a bridge_lock recipient account.
        # v9: the lock must carry the bridge authority's signature over its
        # semantic fields — an unsigned lock lets any proposer forge a debit
        # whose target_recipient is credited on the target chain. Pre-v9
        # blocks contain unsigned locks, so below the height the same check
        # only counts (shadow) and replay stays green.
        if ctx.block_version >= 9:
            authority = _bridge_release_authority(ctx.session, ctx.chain_id, ctx.block_height)
            if not authority:
                return (
                    False,
                    "BRIDGE_LOCK requires a bridge release authority: set the bridge_release_authority chain parameter",
                )
            if not verify_bridge_lock_signature(ctx.tx_data, ctx.tx_hash, authority):
                return (
                    False,
                    "BRIDGE_LOCK must carry a valid bridge_signature from the bridge authority",
                )
        elif not verify_bridge_lock_signature(
            ctx.tx_data, ctx.tx_hash, _bridge_release_authority(ctx.session, ctx.chain_id, ctx.block_height) or ""
        ):
            count_v9_would_reject("bridge_lock_unsigned")
            logger.warning(
                "v9 shadow: BRIDGE_LOCK tx %s lacks a valid bridge_signature",
                ctx.tx_hash,
            )
        # v14 (shared ACT-1 activation, V-4): the lock must carry data the
        # bridge event trie can derive a leaf from — payload fields first,
        # then the signed envelope's top level (transfer_id, amount,
        # target_chain). Below v14 the same condition is only counted by
        # the flag-gated dry-run guard: historical underivable locks stay
        # grandfathered and replayable.
        if ctx.block_version >= 14:
            ctx.payload = ctx.tx_data.get("payload")
            if lock_derivation_source(ctx.payload if isinstance(ctx.payload, dict) else {}, ctx.tx_data) == "unreadable":
                return (
                    False,
                    "BRIDGE_LOCK carries no derivable leaf data for the bridge event trie",
                )
        return None

    def _vt_bridge_lock_account(self, ctx: _TxValidationCtx) -> tuple[bool, str] | None:
        if ctx.tx_type != "BRIDGE_LOCK":
            return None
        sender_account = ctx.session.get(Account, (ctx.chain_id, ctx.sender_addr))
        if not sender_account:
            return (False, f"Sender account not found: {ctx.sender_addr}")
        if ctx.block_version >= 24:
            # #1314 V4: scalar authoritative balance read — supersedes the
            # v23 session.refresh pattern (same freshness guarantee
            # without touching the identity-mapped object).
            _sbal, _snonce, _sexists = _st.read_current_account(ctx.session, ctx.chain_id, ctx.sender_addr)
            ctx.sender_balance = _sbal if _sbal is not None else 0
        elif ctx.block_version >= 23:
            # v23: earlier txs in this block updated the row with raw
            # SQL, leaving this retained ORM object stale — reload it
            # so the balance check sees post-tx state.
            ctx.session.refresh(sender_account)
            ctx.sender_balance = sender_account.balance
        else:
            ctx.sender_balance = sender_account.balance
        ctx.total_cost = ctx.value + ctx.fee
        if ctx.sender_balance < ctx.total_cost:
            return (False, f"Insufficient balance for {ctx.sender_addr}: {ctx.sender_balance} < {ctx.total_cost}")
        return (True, "Pre-registered bridge lock validated")

    def _vt_bridge_withdraw(self, ctx: _TxValidationCtx) -> tuple[bool, str] | None:
        if ctx.tx_type != "BRIDGE_WITHDRAW":
            return None
        # User-signed burn of AIT in exchange for an off-chain ETH release.
        # The payload must contain a valid Ethereum destination address.
        ctx.payload = ctx.tx_data.get("payload") or {}
        eth_address = ctx.payload.get("eth_address", "")
        if not eth_address or not _is_valid_0x_address(eth_address):
            return (False, "BRIDGE_WITHDRAW payload must contain a valid 0x eth_address")
        if ctx.value <= 0:
            return (False, "BRIDGE_WITHDRAW must have a positive value")
        return None

    def _vt_escrow_lock_v3(self, ctx: _TxValidationCtx) -> tuple[bool, str] | None:
        if ctx.tx_type != "ESCROW_LOCK" or ctx.block_version < 3:
            return None
        # S-4: v3 per-escrow locks require a job_id and a provider so the
        # escrow is deterministic and future release/refund can bind the
        # beneficiary and settlement authority.
        ctx.payload = ctx.tx_data.get("payload") or {}
        if not ctx.payload.get("job_id"):
            return (False, "ESCROW_LOCK v3 payload must include job_id")
        if not ctx.payload.get("provider"):
            return (False, "ESCROW_LOCK v3 payload must include provider")
        return None

    def _vt_v9_signature(self, ctx: _TxValidationCtx) -> tuple[bool, str] | None:
        v9_reason = v9_signature_verdict(ctx.tx_data, ctx.tx_type, ctx.block_version)
        if v9_reason is not None:
            count_v9_would_reject(v9_reason, ctx.tx_type)
            if ctx.block_version >= 9:
                return (
                    False,
                    f"v9 signature rule: {v9_reason} for {ctx.tx_type} transaction {ctx.tx_hash}",
                )
            logger.warning(
                "v9 shadow: unsigned %s tx %s would be rejected (%s)",
                ctx.tx_type,
                ctx.tx_hash,
                v9_reason,
            )
        return None

    def _vt_stake_payload_auth(self, ctx: _TxValidationCtx) -> tuple[bool, str] | None:
        if ctx.tx_type not in ("STAKE_LOCK", "STAKE_RELEASE", "BOUNTY_LOCK", "BOUNTY_PAYOUT", "BOUNTY_REFUND"):
            return None
        auth = (ctx.tx_data.get("payload") or {}).get("auth")
        if auth is not None and not self._verify_payload_auth(ctx.tx_type, auth, ctx.tx_data):
            return (False, f"Invalid payload auth signature for transaction {ctx.tx_hash}")
        return None

    def _vt_sender_account(self, ctx: _TxValidationCtx) -> tuple[bool, str] | None:
        sender_account = ctx.session.get(Account, (ctx.chain_id, ctx.sender_addr))
        if ctx.block_version >= 24:
            # #1314 V4: scalar authoritative nonce/balance — covers both the
            # exists and missing-sender cases without an identity-map read.
            _sbal, _snonce, _sexists = _st.read_current_account(ctx.session, ctx.chain_id, ctx.sender_addr)
            if not _sexists:
                # v22+ virtual (balance=0, nonce=0) semantics preserved.
                ctx.sender_nonce = 0
                ctx.sender_balance = 0
            else:
                ctx.sender_nonce = _snonce
                ctx.sender_balance = _sbal if _sbal is not None else 0
        elif not sender_account:
            if ctx.block_version < 22:
                return (False, f"Sender account not found: {ctx.sender_addr}")
            # v22 R1 (CONSENSUS-STATE-001): a missing sender reads as a
            # virtual (balance=0, nonce=0) account — the same values the
            # pre-v22 importer pre-create produced. Validation stays
            # read-only; apply_transaction materializes the row only on
            # the success path.
            ctx.sender_nonce = 0
            ctx.sender_balance = 0
        else:
            if ctx.block_version >= 23:
                # v23: same retained-object reload as the BRIDGE_LOCK site
                # above — the nonce/balance reads below must see the raw
                # SQL updates earlier txs in this block already wrote.
                ctx.session.refresh(sender_account)
            ctx.sender_nonce = sender_account.nonce if sender_account.nonce is not None else 0
            ctx.sender_balance = sender_account.balance
        return None

    def _vt_nonce(self, ctx: _TxValidationCtx) -> tuple[bool, str] | None:
        expected_nonce = ctx.sender_nonce
        tx_nonce = ctx.tx_data.get("nonce", 0)
        if tx_nonce != expected_nonce:
            return (False, f"Invalid nonce for {ctx.sender_addr}: expected {expected_nonce}, got {tx_nonce}")
        return None

    def _vt_governance_execute(self, ctx: _TxValidationCtx) -> tuple[bool, str] | None:
        if ctx.tx_type != "GOVERNANCE_EXECUTE":
            return None
        executors = _governance_executors(ctx.session, ctx.chain_id, ctx.block_height)
        if executors is None:
            # v5 fails closed: apply writes the parameter_change without
            # verifying the proposal passed, so an unset allowlist lets any
            # funded sender rewrite chain parameters — including this list,
            # bond_slash_authority and escrow_settlement_authority. Below v5
            # the lenient rule stays: sealed history contains executes mined
            # before the parameter existed.
            if ctx.block_version >= 5:
                return (
                    False,
                    "GOVERNANCE_EXECUTE rejected: governance_executors chain parameter is not set",
                )
        elif ctx.sender_addr not in executors:
            return (
                False,
                f"GOVERNANCE_EXECUTE sender {ctx.sender_addr} is not an authorized executor",
            )
        # `set_governance_address` is a named-but-unimplemented execution action — the
        # apply side logs and continues, so without this check a passed proposal would
        # "execute" a membership change that never happens. Reject it explicitly.
        # Missing/unknown actions stay lenient: sealed history contains GOVERNANCE_EXECUTE
        # txs with no execution_payload (e.g. blocks 8153/8165 on ait-hub), and unknown
        # actions are the forward-compat escape hatch.
        gov_payload = ctx.tx_data.get("payload") or {}
        if isinstance(gov_payload, str):
            try:
                gov_payload = json.loads(gov_payload)
            except Exception:
                gov_payload = {}
        gov_action = (gov_payload.get("execution_payload") or {}).get("action")
        if gov_action == "set_governance_address":
            return (
                False,
                "GOVERNANCE_EXECUTE action 'set_governance_address' is reserved and not implemented",
            )
        # v12: the five authority parameters get deterministic value checks.
        # Below the height — and for other parameters/actions — behaviour is
        # unchanged. Mempool admission runs the same helper so the door
        # refuses exactly what apply would refuse.
        authority_value_error = _authority_parameter_change_error(
            ctx.session, ctx.chain_id, gov_payload, ctx.fee, block_version=ctx.block_version
        )
        if authority_value_error:
            return (False, authority_value_error)
        # v13 (inert until the operator arms state_transition_v13_height):
        # the execute's payload must equal the sealed PROPOSE's. Below the
        # sentinel the same check only counts v13_would_reject_* (shadow).
        binding_error = _v13_shadow_observe(
            ctx.session,
            ctx.chain_id,
            "GOVERNANCE_EXECUTE",
            gov_payload,
            block_version=ctx.block_version,
            block_height=ctx.block_height,
            tx_hash=ctx.tx_hash,
        )
        if binding_error:
            return (False, binding_error)
        return None

    def _vt_governance_propose(self, ctx: _TxValidationCtx) -> tuple[bool, str] | None:
        if ctx.tx_type != "GOVERNANCE_PROPOSE":
            return None
        # v13: the propose must carry the execution_payload it commits to;
        # shadow-only below the sentinel.
        propose_error = _v13_shadow_observe(
            ctx.session,
            ctx.chain_id,
            "GOVERNANCE_PROPOSE",
            ctx.tx_data.get("payload"),
            block_version=ctx.block_version,
            block_height=ctx.block_height,
            tx_hash=ctx.tx_hash,
        )
        if propose_error:
            return (False, propose_error)
        return None

    def _vt_stake_release_locks(self, ctx: _TxValidationCtx) -> tuple[bool, str] | None:
        if ctx.tx_type != "STAKE_RELEASE" or ctx.block_version < 4:
            return None
        ok, why = _validate_stake_release_locks(
            ctx.session, ctx.chain_id, ctx.tx_data, ctx.tx_hash, ctx.value, ctx.recipient_addr
        )
        if not ok:
            return (False, why)
        return None

    def _vt_zero_value_cost(self, ctx: _TxValidationCtx) -> tuple[bool, str] | None:
        if _is_zero_value_tx_type(ctx.tx_type, ctx.block_version) and ctx.value != 0:
            return (False, f"{ctx.tx_type} transactions must have value=0, got {ctx.value}")
        if _is_zero_value_tx_type(ctx.tx_type, ctx.block_version):
            ctx.total_cost = ctx.fee
        else:
            ctx.total_cost = ctx.value + ctx.fee
        return None

    def _vt_escrow_release_refund_job(self, ctx: _TxValidationCtx) -> tuple[bool, str] | None:
        # S-4 (v3): ESCROW_RELEASE/ESCROW_REFUND funds come from the per-escrow
        # address, not the sender (node wallet). We validate against the version
        # the lock was mined under so a v3 activation does not strand v2 locks.
        if ctx.tx_type not in ("ESCROW_RELEASE", "ESCROW_REFUND"):
            return None
        ctx.job_id = (ctx.tx_data.get("payload") or {}).get("job_id", "")
        if not ctx.job_id:
            return (False, f"{ctx.tx_type} payload must include job_id")
        ctx.lock_tx = _get_escrow_lock(ctx.session, ctx.chain_id, ctx.job_id)
        if not ctx.lock_tx:
            return (False, f"No ESCROW_LOCK found for {ctx.job_id}")
        ctx.lock_version = _get_escrow_lock_block_version(ctx.session, ctx.chain_id, ctx.job_id)
        if ctx.lock_version is None:
            ctx.lock_version = 2 if ctx.block_version < 3 else 3
        return None

    def _vt_escrow_beneficiary(self, ctx: _TxValidationCtx) -> tuple[bool, str] | None:
        if ctx.tx_type not in ("ESCROW_RELEASE", "ESCROW_REFUND"):
            return None
        if ctx.block_version >= 23:
            # v23: the beneficiary is resolved across ALL sealed locks —
            # multiple locks with distinct payees (or an unresolvable one)
            # are ambiguous and refuse rather than guess.
            expected_beneficiary, beneficiary_ambiguous = _escrow_lock_beneficiaries(
                ctx.session, ctx.chain_id, ctx.job_id, ctx.tx_type
            )
            if beneficiary_ambiguous:
                return (
                    False,
                    f"{ctx.tx_type} for {ctx.job_id} has an ambiguous beneficiary across its locks — refusing to guess",
                )
        else:
            expected_beneficiary = _escrow_beneficiary(ctx.lock_tx, ctx.tx_type)
        if expected_beneficiary and _to_ait_address(ctx.recipient_addr) != expected_beneficiary:
            return (False, f"{ctx.tx_type} for {ctx.job_id} must pay {expected_beneficiary}, got {ctx.recipient_addr}")
        return None

    def _vt_escrow_obligation(self, ctx: _TxValidationCtx) -> tuple[bool, str] | None:
        if ctx.tx_type not in ("ESCROW_RELEASE", "ESCROW_REFUND"):
            return None
        if ctx.block_version >= 23:
            # v23 obligation bound: value may not exceed the job's
            # remaining obligation (Σ locks − Σ prior settlements).
            # Custody balance is NOT the bound — third-party transfers
            # into the escrow address must not raise entitlement.
            obligation = _escrow_obligation_state(ctx.session, ctx.chain_id, ctx.job_id, exclude_tx_hash=ctx.tx_hash)
            if obligation["remaining"] is None:
                return (
                    False,
                    f"{ctx.tx_type} for {ctx.job_id} has an unbounded obligation (unparseable lock/settlement value) — refusing",
                )
            if ctx.value > obligation["remaining"]:
                return (
                    False,
                    f"{ctx.tx_type} for {ctx.job_id} exceeds remaining obligation {obligation['remaining']} "
                    f"(locked {obligation['obligation']}, settled {obligation['settled']})",
                )
        return None

    def _vt_escrow_authority(self, ctx: _TxValidationCtx) -> tuple[bool, str] | None:
        if ctx.tx_type not in ("ESCROW_RELEASE", "ESCROW_REFUND"):
            return None
        if ctx.block_version >= 3:
            authority = _escrow_settlement_authority(ctx.session, ctx.chain_id, ctx.block_height)
            if authority is None:
                # v5 fails closed: with no authority configured any funded
                # signer may trigger the release/refund — paying the locked
                # beneficiary early (e.g. a provider paying itself before
                # doing the work). Below v5 the lenient rule stays so
                # sealed history mined without an authority still replays.
                if ctx.block_version >= 5:
                    return (
                        False,
                        f"{ctx.tx_type} requires a settlement authority: set the escrow_settlement_authority chain parameter",
                    )
            elif _to_ait_address(ctx.sender_addr) != authority:
                return (False, f"{ctx.tx_type} must be signed by settlement authority {authority}, got {ctx.sender_addr}")
        return None

    def _vt_escrow_funding(self, ctx: _TxValidationCtx) -> tuple[bool, str] | None:
        if ctx.tx_type not in ("ESCROW_RELEASE", "ESCROW_REFUND"):
            return None
        if ctx.lock_version >= 3:
            # Funds are in the per-escrow address.
            escrow_addr = _escrow_address(ctx.job_id)
            if ctx.block_version >= 24:
                # #1314 V1: authoritative scalar custody read — bypasses
                # identity-map staleness after raw-SQL writes.
                _ebal, _enonce, escrow_exists = _st.read_current_account(ctx.session, ctx.chain_id, escrow_addr)
                ctx.escrow_balance = _ebal if _ebal is not None else 0
            else:
                escrow_account = ctx.session.get(Account, (ctx.chain_id, escrow_addr))
                escrow_exists = escrow_account is not None
                ctx.escrow_balance = escrow_account.balance if escrow_account else 0
            if not escrow_exists or ctx.escrow_balance < ctx.value:
                return (False, f"Escrow {ctx.job_id} has insufficient balance: {ctx.escrow_balance} < {ctx.value}")
            # The settlement authority pays only the fee, not the value.
            if ctx.sender_balance < ctx.fee:
                return (False, f"Insufficient balance for fee: {ctx.sender_balance} < {ctx.fee}")
        elif ctx.sender_balance < ctx.total_cost:
            return (False, f"Insufficient balance for {ctx.sender_addr}: {ctx.sender_balance} < {ctx.total_cost}")
        return None

    def _vt_sweep_params(self, ctx: _TxValidationCtx) -> tuple[bool, str] | None:
        if ctx.tx_type != "ESCROW_FEE_SWEEP" or ctx.block_version < 11:
            return None
        # v11: the settlement authority sweeps a settled escrow's custody
        # residue to the governed fee recipient. No lock lookup — the
        # custody account is derived from the job_id, and a v2-era job has
        # none (a zero balance fails the balance check naturally). Order
        # matches state/admission_authority.py so the door mirrors apply.
        ctx.job_id = (ctx.tx_data.get("payload") or {}).get("job_id", "")
        if not ctx.job_id:
            return (False, "ESCROW_FEE_SWEEP payload must include job_id")
        authority = _escrow_settlement_authority(ctx.session, ctx.chain_id, ctx.block_height)
        # v11 postdates v5, so the fail-closed era check never applies:
        # an unset authority is always a refusal here.
        if authority is None:
            return (
                False,
                "ESCROW_FEE_SWEEP requires a settlement authority: set the escrow_settlement_authority chain parameter",
            )
        if _to_ait_address(ctx.sender_addr) != authority:
            return (
                False,
                f"ESCROW_FEE_SWEEP must be signed by settlement authority {authority}, got {ctx.sender_addr}",
            )
        return None

    def _vt_sweep_fee_recipient(self, ctx: _TxValidationCtx) -> tuple[bool, str] | None:
        if ctx.tx_type != "ESCROW_FEE_SWEEP" or ctx.block_version < 11:
            return None
        fee_recipient = _escrow_fee_recipient(ctx.session, ctx.chain_id, ctx.block_height)
        if fee_recipient is None:
            return (
                False,
                "ESCROW_FEE_SWEEP requires a fee recipient: set the escrow_fee_recipient chain parameter",
            )
        if _to_ait_address(ctx.recipient_addr) != fee_recipient:
            return (False, f"ESCROW_FEE_SWEEP must pay {fee_recipient}, got {ctx.recipient_addr}")
        return None

    def _vt_sweep_custody(self, ctx: _TxValidationCtx) -> tuple[bool, str] | None:
        if ctx.tx_type != "ESCROW_FEE_SWEEP" or ctx.block_version < 11:
            return None
        escrow_addr = _escrow_address(ctx.job_id)
        if ctx.block_version >= 24:
            _ebal, _enonce, escrow_exists = _st.read_current_account(ctx.session, ctx.chain_id, escrow_addr)
            ctx.escrow_balance = _ebal if _ebal is not None else 0
        else:
            escrow_account = ctx.session.get(Account, (ctx.chain_id, escrow_addr))
            escrow_exists = escrow_account is not None
            ctx.escrow_balance = escrow_account.balance if escrow_account else 0
        if not escrow_exists or ctx.escrow_balance < ctx.value:
            return (False, f"Escrow {ctx.job_id} has insufficient balance: {ctx.escrow_balance} < {ctx.value}")
        return None

    def _vt_sweep_obligation(self, ctx: _TxValidationCtx) -> tuple[bool, str] | None:
        if ctx.tx_type != "ESCROW_FEE_SWEEP" or ctx.block_version < 11:
            return None
        if ctx.block_version >= 23:
            # v23: a sweep may take custody residue plus the governed fee
            # allowance (#1261) — never more of the job's outstanding
            # obligation than that.
            obligation = _escrow_obligation_state(
                ctx.session,
                ctx.chain_id,
                ctx.job_id,
                exclude_tx_hash=ctx.tx_hash,
                fee_cap_bps=_escrow_fee_cap_bps(ctx.session, ctx.chain_id, ctx.block_height),
            )
            if obligation["remaining"] is None:
                return (
                    False,
                    f"ESCROW_FEE_SWEEP for {ctx.job_id} has an unbounded obligation — refusing",
                )
            custody = ctx.escrow_balance
            sweepable = escrow_sweep_ceiling(custody, obligation["remaining"], obligation["fee_allowance"])
            if ctx.value > sweepable:
                return (
                    False,
                    f"ESCROW_FEE_SWEEP for {ctx.job_id} exceeds sweepable {sweepable} "
                    f"(custody {custody}, remaining obligation {obligation['remaining']}, "
                    f"fee allowance {obligation['fee_allowance']})",
                )
        return None

    def _vt_sweep_fee(self, ctx: _TxValidationCtx) -> tuple[bool, str] | None:
        if ctx.tx_type != "ESCROW_FEE_SWEEP" or ctx.block_version < 11:
            return None
        # The settlement authority pays only the fee, not the value.
        if ctx.sender_balance < ctx.fee:
            return (False, f"Insufficient balance for fee: {ctx.sender_balance} < {ctx.fee}")
        return None

    def _vt_sender_balance(self, ctx: _TxValidationCtx) -> tuple[bool, str] | None:
        if ctx.tx_type in ("ESCROW_RELEASE", "ESCROW_REFUND"):
            return None
        if ctx.tx_type == "ESCROW_FEE_SWEEP" and ctx.block_version >= 11:
            return None
        if ctx.sender_balance < ctx.total_cost:
            return (False, f"Insufficient balance for {ctx.sender_addr}: {ctx.sender_balance} < {ctx.total_cost}")
        return None

    def _vt_receipt_claim(self, ctx: _TxValidationCtx) -> tuple[bool, str] | None:
        # v0.25.5: recipient accounts are created on first credit during
        # block execution, so a release/refund/transfer to a never-before-seen
        # address is valid and becomes deterministic after mining.
        if ctx.tx_type != "RECEIPT_CLAIM":
            return None
        ctx.payload = ctx.tx_data.get("payload", {}) or {}
        receipt_id = ctx.payload.get("receipt_id")
        if not receipt_id:
            return (False, "RECEIPT_CLAIM transactions must include receipt_id in payload")
        receipt = ctx.session.exec(
            select(Receipt).where(Receipt.chain_id == ctx.chain_id, Receipt.receipt_id == receipt_id)
        ).first()
        if not receipt:
            # A claim may carry its own issuance: payload.receipt holds the
            # signed record and apply materialises the row deterministically,
            # so nodes that never served the issuing RPC reach the same
            # verdict (#687 — before this, nothing ever wrote the row, so the
            # type was admissible but nothing could honestly emit it).
            if _carried_receipt_record(ctx.payload, receipt_id) is None:
                return (False, f"Receipt not found: {receipt_id}")
        else:
            if receipt.status != "pending":
                return (False, f"Receipt already claimed or invalid: {receipt.status}")
            if not receipt.miner_signature or not isinstance(receipt.miner_signature, dict):
                return (False, f"Receipt {receipt_id} has invalid miner signature")
            if not receipt.coordinator_attestations or not isinstance(receipt.coordinator_attestations, list):
                return (False, f"Receipt {receipt_id} has invalid coordinator attestations")
        return None

    def _vt_ipfs_subscription(self, ctx: _TxValidationCtx) -> tuple[bool, str] | None:
        if ctx.tx_type != "IPFS_SUBSCRIPTION":
            return None
        ctx.payload = ctx.tx_data.get("payload", {}) or {}
        if isinstance(ctx.payload, str):
            try:
                ctx.payload = json.loads(ctx.payload)
            except Exception:
                return (False, "IPFS_SUBSCRIPTION payload is not valid JSON")
        if not ctx.payload.get("island_id"):
            return (False, "IPFS_SUBSCRIPTION payload must include island_id")
        duration_blocks = ctx.payload.get("duration_blocks")
        if not isinstance(duration_blocks, int) or duration_blocks <= 0:
            return (False, "IPFS_SUBSCRIPTION payload must include positive duration_blocks")
        quota_bytes = ctx.payload.get("quota_bytes")
        if not isinstance(quota_bytes, int) or quota_bytes < 0:
            return (False, "IPFS_SUBSCRIPTION payload must include non-negative quota_bytes")
        if ctx.value <= 0:
            return (False, "IPFS_SUBSCRIPTION requires value > 0")
        # Ensure recipient (island treasury) exists so the payment can be credited.
        # v22 (CONSENSUS-STATE-001, #1169): read-only validation — apply
        # ensures the recipient on its success path.
        if ctx.block_version < 22:
            _ensure_account(ctx.session, ctx.chain_id, ctx.recipient_addr)
        return None

    def _vt_gpu_register_fields(self, ctx: _TxValidationCtx) -> tuple[bool, str] | None:
        if ctx.tx_type != "GPU_REGISTER":
            return None
        ctx.payload = ctx.tx_data.get("payload") or {}
        if not ctx.payload.get("gpu_id"):
            return (False, "GPU_REGISTER payload must include gpu_id")
        if not ctx.payload.get("miner_id"):
            return (False, "GPU_REGISTER payload must include miner_id")
        if not ctx.payload.get("model"):
            return (False, "GPU_REGISTER payload must include model")
        if not isinstance(ctx.payload.get("memory_gb"), int):
            return (False, "GPU_REGISTER payload must include integer memory_gb")
        try:
            gpu_price = Decimal(str(ctx.payload.get("price_per_hour", 0)))
        except Exception:
            return (False, "GPU_REGISTER payload must include a valid price_per_hour")
        if ctx.block_version >= 25 and not _gpu_price_per_hour_in_range(gpu_price):
            # v25 (#1566): negative/NaN/Infinity/oversized prices were
            # storable pre-gate; bound them now that the column is
            # Numeric(20,8). Below v25 the parse-only rule replays history.
            return (False, "GPU_REGISTER price_per_hour out of range")
        if ctx.value != 0:
            return (False, "GPU_REGISTER must have value=0")
        return None

    def _vt_gpu_register_ownership(self, ctx: _TxValidationCtx) -> tuple[bool, str] | None:
        if ctx.tx_type != "GPU_REGISTER":
            return None
        if ctx.block_version >= 7:
            # Ownership gate: only the recorded registrant may update an
            # existing gpu_id. registered_by is the first registrant's tx
            # sender and cannot be rewritten from the payload, so a
            # foreign signed GPU_REGISTER can't reprice, re-spec, or
            # reactivate someone else's GPU. Fails closed if the row
            # carries no registrant.
            gpu_id = str(ctx.payload.get("gpu_id"))
            existing = ctx.session.exec(
                select(GPURegistration).where(GPURegistration.chain_id == ctx.chain_id, GPURegistration.gpu_id == gpu_id)
            ).first()
            if existing is not None:
                if not existing.registered_by:
                    return (False, f"GPU {gpu_id} has no registrant on record; updates are not permitted")
                if canonical_address(existing.registered_by) != canonical_address(ctx.sender_addr):
                    return (
                        False,
                        f"GPU_REGISTER for {gpu_id} must come from its registrant {existing.registered_by}, got {ctx.sender_addr}",
                    )
        return None

    def _vt_gpu_deregister(self, ctx: _TxValidationCtx) -> tuple[bool, str] | None:
        if ctx.tx_type != "GPU_DEREGISTER" or ctx.block_version < 10:
            return None
        # v10: the registrant takes its own GPU out of service. The row stays (status ``deactivated``) so
        # ``registered_by`` keeps guarding the id and the registrant can reactivate it by re-registering.
        # The rule lives in state/gpu_resources.py::gpu_deregister_error, shared with mempool admission
        # (rpc/transactions.py) so a transaction the proposer would drop is refused at the door too.
        error = gpu_deregister_error(ctx.session, ctx.chain_id, ctx.tx_data.get("payload"), ctx.sender_addr)
        if error:
            return (False, error)
        return None

    def _vt_gpu_allocate(self, ctx: _TxValidationCtx) -> tuple[bool, str] | None:
        if ctx.tx_type != "GPU_ALLOCATE":
            return None
        ctx.payload = ctx.tx_data.get("payload") or {}
        if not ctx.payload.get("gpu_id"):
            return (False, "GPU_ALLOCATE payload must include gpu_id")
        if ctx.block_version >= 10:
            # v10: a deactivated GPU takes no new allocations. Checked here, before apply mutates anything.
            # The rule lives in state/gpu_resources.py::gpu_allocate_deactivated_error, shared with mempool
            # admission (rpc/transactions.py) so a transaction the proposer would drop is refused at the door too.
            deactivated_error = gpu_allocate_deactivated_error(ctx.session, ctx.chain_id, ctx.payload)
            if deactivated_error:
                return (False, deactivated_error)
        if ctx.block_version >= 16:
            # v16 (GPU-ADMISSION-1 #384): allocation_id is mandatory and gpu_id must
            # resolve — apply can no longer be the first place that checks, and it can
            # no longer mint a nondeterministic alloc_<uuid4> for a sealed tx.
            admission_error = gpu_allocate_admission_error(ctx.session, ctx.chain_id, ctx.payload)
            if admission_error:
                return (False, admission_error)
        if not ctx.payload.get("client_id"):
            return (False, "GPU_ALLOCATE payload must include client_id")
        try:
            float(ctx.payload.get("duration_hours", 0))
            Decimal(str(ctx.payload.get("total_cost", 0)))
        except Exception:
            return (False, "GPU_ALLOCATE payload must include valid duration_hours and total_cost")
        if ctx.value != 0:
            return (False, "GPU_ALLOCATE must have value=0")
        return None

    def _vt_retired_gpu(self, ctx: _TxValidationCtx) -> tuple[bool, str] | None:
        if ctx.block_version < 10:
            return None
        # v10: the retired-id door (GPU_RETIRED_IDS) is consensus, not just admission — a
        # proposer that skipped admission cannot re-register or allocate a retired gpu_id
        # via a crafted block. Below v10 this never fires, so replay is unchanged. The env
        # list MUST be identical on every node once v10 is live; fleet-config-check.sh
        # compares it across hosts.
        retired_error = retired_gpu_error(ctx.tx_type, ctx.tx_data.get("payload"), settings.gpu_retired_id_set())
        if retired_error:
            return (False, retired_error)
        return None

    def _vt_bond_lock_v20(self, ctx: _TxValidationCtx) -> tuple[bool, str] | None:
        if ctx.tx_type != "BOND_LOCK" or ctx.block_version < 20:
            return None
        # v20 (#1067): the provider in the payload must be the signer —
        # any account could previously top up a bond with a huge lock_days
        # and push the victim's locked_until a century out, or open a bond
        # in someone else's name. lock_days is bounded here so a giant
        # value cannot raise OverflowError inside apply after the debit.
        _v20_payload = ctx.tx_data.get("payload") or {}
        _v20_sender = _to_ait_address(ctx.tx_data.get("from") or "")
        if _v20_sender != _to_ait_address(_v20_payload.get("provider") or ""):
            return (False, "BOND_LOCK refused: signer is not the bond provider")
        try:
            _v20_days = int(_v20_payload.get("lock_days", 30))
        except (TypeError, ValueError, OverflowError):
            return (False, "BOND_LOCK refused: invalid lock_days")
        if not 1 <= _v20_days <= 3650:
            return (False, "BOND_LOCK refused: lock_days out of range (1-3650)")
        return None

    def _vt_bond_lock_v19(self, ctx: _TxValidationCtx) -> tuple[bool, str] | None:
        if ctx.tx_type != "BOND_LOCK" or ctx.block_version < 19:
            return None
        # v19 (BOND-LOCK-TOPUP-SLASHED-1, #782): a top-up on a bond row that
        # is not status=active used to raise ``amount`` while the row kept
        # its terminal status — the added funds could never be released or
        # slashed again (both lookups require ``active``). Refuse at
        # validate and admission; below v19 replay keeps the old behavior.
        bond_id = (ctx.tx_data.get("payload") or {}).get("bond_id")
        if bond_id:
            existing_bond = ctx.session.exec(
                select(Bond).where(Bond.chain_id == ctx.chain_id, Bond.bond_id == bond_id)
            ).first()
            if existing_bond is not None and existing_bond.status != "active":
                return (
                    False,
                    f"BOND_LOCK top-up refused: bond {bond_id} is {existing_bond.status}, not active",
                )
        return None

    def _vt_bond_v22(self, ctx: _TxValidationCtx) -> tuple[bool, str] | None:
        if ctx.tx_type not in ("BOND_LOCK", "BOND_RELEASE") or ctx.block_version < 22:
            return None
        # v22 (BOND-RELEASE-001, BOND-LOCK-TOPUP-PROVIDER-MISMATCH,
        # #1166/#1167): persisted-provider ownership, mandatory
        # payload.provider binding, absolute lock ceiling, NULL
        # fail-closed. Hard reject — validate False means zero
        # mutation (no fee, no nonce). Read-only verdict; placed with
        # the other BOND checks, before any account-ensuring branch
        # that could apply to these types (none exist).
        bond_error = bond_tx_verdict(
            ctx.session,
            ctx.chain_id,
            ctx.tx_type,
            ctx.tx_data.get("payload"),
            ctx.sender_addr,
            ctx.recipient_addr,
            ctx.value,
            block_version=ctx.block_version,
            block_time=ctx.block_time,
            block_height=ctx.block_height,
        )
        if bond_error:
            return (False, bond_error)
        return None

    def _vt_agent_spend(self, ctx: _TxValidationCtx) -> tuple[bool, str] | None:
        if ctx.block_version < 21:
            return None
        # v21 (AGENT-SPEND-B-1, #1142): on-chain agent spend sessions.
        # Grant/revoke lifecycle checks plus session-bound TRANSFER and
        # ESCROW_LOCK enforcement (live session, op allowed, daily cap
        # fits). Read-only — the ledger charge lives in apply. Runs last
        # like the other door checks: signature and nonce are already
        # verified, so ``sender`` here is the authenticated signer.
        spend_error = agent_spend_verdict(
            ctx.session,
            ctx.chain_id,
            ctx.sender_addr,
            ctx.tx_type,
            ctx.tx_data.get("payload"),
            ctx.value,
            ctx.block_height,
        )
        if spend_error:
            return (False, spend_error)
        return None
