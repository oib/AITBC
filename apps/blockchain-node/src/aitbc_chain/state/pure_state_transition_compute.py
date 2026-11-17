"""Compute-pipeline state deltas for the pure state-transition split.

The per-transaction gate chain (precheck, sender/nonce, signature and v9
payload-auth gates, escrow dispatch, generic transfer) plus
``compute_state_delta`` itself. Import
``aitbc_chain.state.pure_state_transition`` first (it re-exports every name
here); this module is not meant to be imported directly.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ..base_models import _to_ait_address
from ..models import Account
from .bridge_credit import (
    bridge_refund_lock_hash,
    validate_bridge_refund_lock,
    verify_bridge_credit_signature,
    verify_bridge_lock_signature,
)
from .pure_state_transition_base import (
    SEQUENTIAL_ONLY_TX_TYPES,
    StateDelta,
    _carried_receipt_record,
    _determine_tx_type,
    _escrow_address,
    _fail_delta,
    logger,
)
from .pure_state_transition_escrow import _escrow_fee_sweep_delta, _escrow_release_refund_delta
from .v9_policy import (
    V17_PAYLOAD_AUTH_TX_TYPES,
    _payload_auth_of,
    count_v9_would_reject,
    v9_signature_verdict,
)


def _escrow_lock_precheck(
    tx_data: dict[str, Any],
    sender: str,
    recipient: str,
    tx_type: str,
    tx_hash: str,
    block_version: int,
) -> tuple[list[str] | None, str, StateDelta | None]:
    """ESCROW_LOCK payload handling that runs before every other gate.

    Returns ``(extra_accounts, recipient, delta)``: ``delta`` is a failure
    StateDelta for a malformed v3 payload (job_id/provider missing), else
    None and the caller continues — possibly with ``recipient`` rewritten to
    the deterministic per-escrow address.
    """
    extra_accounts: list[str] | None = None
    if tx_type != "ESCROW_LOCK":
        return extra_accounts, recipient, None
    # S-4: ESCROW_LOCK always creates the provider account, and v3 also
    # redirects the locked value to a deterministic per-escrow address.
    payload = tx_data.get("payload", {}) or {}
    if isinstance(payload, str):
        try:
            import json

            payload = json.loads(payload)
        except (RecursionError, TypeError, ValueError):  # malformed payload JSON decodes to the empty/default branch
            payload = {}
    provider_addr = _to_ait_address(payload.get("provider", ""))
    extra_accounts = [a for a in [provider_addr] if a]
    if block_version >= 3:
        job_id = payload.get("job_id", "")
        if not job_id:
            return (
                extra_accounts,
                recipient,
                _fail_delta(sender, recipient, "ESCROW_LOCK v3 payload must include job_id", tx_type, tx_hash),
            )
        if not payload.get("provider"):
            return (
                extra_accounts,
                recipient,
                _fail_delta(sender, recipient, "ESCROW_LOCK v3 payload must include provider", tx_type, tx_hash),
            )
        recipient = _escrow_address(job_id)
    return extra_accounts, recipient, None


def _bridge_refund_lock_error(
    tx_data: dict[str, Any],
    bridge_lock_context: dict[str, dict[str, Any]] | None,
) -> str | None:
    """v6 BRIDGE_REFUND lock-binding check; returns the reject reason or None."""
    # v6: the refund must name its sealed BRIDGE_LOCK via
    # payload.lock_tx_hash (sender/amount match, not already refunded).
    # Mirrors validate_transaction — the caller prefetches the record
    # via build_bridge_lock_context; None fails closed.
    lock_hash = bridge_refund_lock_hash(tx_data)
    return validate_bridge_refund_lock(
        (bridge_lock_context or {}).get(lock_hash) if lock_hash else None,
        tx_data,
    )


def _bridge_credit_delta(
    tx_data: dict[str, Any],
    sender: str,
    recipient: str,
    value: int,
    tx_type: str,
    tx_hash: str,
    block_version: int,
    bridge_authority: str | None,
    bridge_lock_context: dict[str, dict[str, Any]] | None,
) -> StateDelta | None:
    """Terminal delta for BRIDGE_RELEASE/BRIDGE_REFUND; None for other types.

    These are pre-registered credits: the sender is the chain-level
    pseudo-address (no account, no nonce, no debit) and only the recipient is
    credited — mirrors StateTransition.apply_transaction.
    """
    if tx_type not in {"BRIDGE_RELEASE", "BRIDGE_REFUND"}:
        return None
    if block_version >= 5:
        # v5: only the bridge's own pseudo-sender shape is legitimate —
        # public intake refuses these types, so any other sender in a block
        # is a forged credit. Mirrors validate_transaction.
        expected_sender = "bridge_release" if tx_type == "BRIDGE_RELEASE" else "bridge_refund"
        if sender != expected_sender:
            return _fail_delta(
                sender,
                recipient,
                f"{tx_type} must carry the internal pseudo-sender {expected_sender}, got {sender}",
                tx_type,
                tx_hash,
            )
        # The pseudo-sender is a name, not a key: the credit must also be
        # signed by the bridge release authority. Mirrors
        # validate_transaction — the caller resolves the on-chain
        # parameter for a known block height and None must fail closed;
        # env fallbacks apply only to mempool pre-checks (block_height
        # is None), never to block validation.
        if not bridge_authority:
            return _fail_delta(
                sender,
                recipient,
                f"{tx_type} requires a bridge release authority: set the bridge_release_authority chain parameter",
                tx_type,
                tx_hash,
            )
        if not verify_bridge_credit_signature(tx_data, tx_hash, bridge_authority):
            return _fail_delta(
                sender,
                recipient,
                f"{tx_type} must carry a valid bridge_signature from the bridge release authority",
                tx_type,
                tx_hash,
            )
        if block_version >= 6 and tx_type == "BRIDGE_REFUND":
            lock_reason = _bridge_refund_lock_error(tx_data, bridge_lock_context)
            if lock_reason:
                return _fail_delta(sender, recipient, lock_reason, tx_type, tx_hash)
    return StateDelta(
        sender=sender,
        recipient=recipient,
        sender_balance_change=0,
        recipient_balance_change=value,
        sender_nonce_change=0,
        success=True,
        tx_type=tx_type,
        tx_hash=tx_hash,
    )


def _pre_sender_delta(
    tx_data: dict[str, Any],
    sender: str,
    recipient: str,
    value: int,
    tx_type: str,
    tx_hash: str,
    chain_id: str,
    existing_tx_hashes: set[str] | None,
    block_version: int,
    bridge_authority: str | None,
    bridge_lock_context: dict[str, dict[str, Any]] | None,
) -> StateDelta | None:
    """Pre-sender-account gates: sequential-only, sender/chain/dup, bridge credits.

    Returns the terminal delta (a reject or a bridge-credit success) or None
    to continue to signature validation.
    """
    # Sequential-only types: side effects the pure delta map cannot model
    # (pools, stakes, gpu rows, chain parameters, bond rows, burn semantics —
    # see SEQUENTIAL_ONLY_TX_TYPES). Force a sequential fallback so
    # StateTransition.apply_transaction handles them; callers additionally
    # pre-filter whole blocks on the same list.
    if tx_type in SEQUENTIAL_ONLY_TX_TYPES:
        return StateDelta(
            sender=sender,
            recipient=recipient,
            sender_balance_change=0,
            recipient_balance_change=0,
            sender_nonce_change=0,
            success=False,
            error=f"{tx_type} must be processed sequentially",
            tx_type=tx_type,
            tx_hash=tx_hash,
            requires_sequential=True,
        )

    # Validate sender exists
    if not sender:
        return _fail_delta("", recipient, "Missing sender", tx_type, tx_hash)

    # Chain isolation check
    tx_chain_id = tx_data.get("chain_id")
    if tx_chain_id and tx_chain_id != chain_id:
        return _fail_delta(
            sender,
            recipient,
            f"Chain isolation violation: transaction chain_id={tx_chain_id} does not match node chain_id={chain_id}",
            tx_type,
            tx_hash,
        )

    # Duplicate tx check (in-memory)
    if existing_tx_hashes is not None and tx_hash in existing_tx_hashes:
        return _fail_delta(sender, recipient, f"Transaction {tx_hash} already processed (replay attack)", tx_type, tx_hash)

    # BRIDGE_RELEASE/BRIDGE_REFUND are pre-registered credits: the sender is the
    # chain-level pseudo-address (no account, no nonce, no debit) and only the
    # recipient is credited — mirrors StateTransition.apply_transaction. Without
    # this branch the generic path fails them with "Sender account not found" and
    # followers never apply a sealed release.
    return _bridge_credit_delta(
        tx_data, sender, recipient, value, tx_type, tx_hash, block_version, bridge_authority, bridge_lock_context
    )


def _sender_signature_gate_delta(
    tx_data: dict[str, Any],
    tx_type: str,
    tx_hash: str,
    sender: str,
    recipient: str,
    block_version: int,
) -> StateDelta | None:
    """v7+ sender-signature check; None when the signature verifies or is absent."""
    # Signature verification — same contract as apply_transaction: verify only
    # when a signature field is present (unsigned internal txs skip), but a
    # present signature must verify. Until the parallel path checked this, a
    # signed tx applied regardless of its signature whenever the caller had
    # rewritten the nonce. Gated to v7+: the v2–v6 parallel era rewrote the
    # nonce before this call, so a signature carried in from that era would be
    # checked against the rewritten nonce and fail a block that applied fine
    # historically. Imported txs arrive without a signature anyway, so the
    # gate only preserves identical behaviour for any path that does carry one.
    signature = tx_data.get("signature")
    # BRIDGE_LOCK is pre-registered like the credits: the sequential path
    # never checks a sender signature or nonce for it — authorization is the
    # v9 bridge_signature gate below. Skip the generic sender-sig check so a
    # lock carrying a decorative/wrong sender signature applies identically
    # on both paths.
    if signature and sender and block_version >= 7 and tx_type != "BRIDGE_LOCK":
        from ..rpc.utils import verify_transaction_signature

        if not verify_transaction_signature(tx_data, signature, sender):
            return _fail_delta(sender, recipient, f"Invalid signature for transaction {tx_hash}", tx_type, tx_hash)
    return None


def _v9_signature_gate_delta(
    tx_data: dict[str, Any],
    tx_type: str,
    tx_hash: str,
    sender: str,
    recipient: str,
    block_version: int,
) -> StateDelta | None:
    """v9 signature verdict: reject at v9+, shadow-count below it."""
    # v9: non-internal txs must carry a signature at all — same rule and
    # same allowlist as the sequential path. While the v9 height is unset
    # this only logs/counts the would-reject (shadow mode).
    v9_reason = v9_signature_verdict(tx_data, tx_type, block_version)
    if v9_reason is not None:
        count_v9_would_reject(v9_reason, tx_type)
        if block_version >= 9:
            return _fail_delta(
                sender, recipient, f"v9 signature rule: {v9_reason} for {tx_type} transaction {tx_hash}", tx_type, tx_hash
            )
        logger.warning(
            "v9 shadow: unsigned %s tx %s would be rejected (%s)",
            tx_type,
            tx_hash,
            v9_reason,
        )
    return None


def _payload_auth_gate_delta(
    tx_data: dict[str, Any],
    tx_type: str,
    tx_hash: str,
    sender: str,
    recipient: str,
) -> StateDelta | None:
    """v17 payload-auth check for the protocol transfer types."""
    # Same payload-auth rule as the sequential path: for the protocol
    # transfer types an ``auth`` that is present must verify and bind —
    # presence alone is not authorization. An absent auth stays allowed
    # here: an unsigned one was already rejected by the v9 verdict above,
    # and pre-auth protocol transfers exist in sealed history.
    if tx_type in V17_PAYLOAD_AUTH_TX_TYPES:
        auth = _payload_auth_of(tx_data)
        if auth is not None:
            from .state_transition import StateTransition

            if not StateTransition._verify_payload_auth(tx_type, auth, tx_data):
                return _fail_delta(
                    sender, recipient, f"Invalid payload auth signature for transaction {tx_hash}", tx_type, tx_hash
                )
    return None


def _auth_gates_delta(
    tx_data: dict[str, Any],
    tx_type: str,
    tx_hash: str,
    sender: str,
    recipient: str,
    block_version: int,
) -> StateDelta | None:
    """Run the sender-signature, v9-verdict and payload-auth gates in order.

    The first failing gate's delta is returned; None means every gate passed.
    Ordering is identical to the sequential checks they mirror.
    """
    delta = _sender_signature_gate_delta(tx_data, tx_type, tx_hash, sender, recipient, block_version)
    if delta is not None:
        return delta
    delta = _v9_signature_gate_delta(tx_data, tx_type, tx_hash, sender, recipient, block_version)
    if delta is not None:
        return delta
    return _payload_auth_gate_delta(tx_data, tx_type, tx_hash, sender, recipient)


def _sender_account_and_nonce_delta(
    account_map: dict[str, Account],
    tx_data: dict[str, Any],
    sender: str,
    recipient: str,
    tx_type: str,
    tx_hash: str,
) -> Account | StateDelta:
    """Return the sender Account, or a failure StateDelta.

    Validates the sender account exists and the nonce matches — real when the
    caller kept the signed envelope nonce (v7+ signed txs); tautological for
    unsigned/legacy overrides.
    """
    sender_account = account_map.get(sender)
    if not sender_account:
        return _fail_delta(sender, recipient, f"Sender account not found: {sender}", tx_type, tx_hash)

    # Nonce validation — real when the caller kept the signed envelope nonce
    # (v7+ signed txs); tautological for unsigned/legacy overrides.
    expected_nonce = sender_account.nonce if sender_account.nonce is not None else 0
    tx_nonce = tx_data.get("nonce", 0)
    # BRIDGE_LOCK: sequential's pre-registered branch does not check the nonce
    # either — the caller-side account-nonce override already substitutes the
    # live value for unsigned locks, and a signed nonce carries no authority.
    if tx_type != "BRIDGE_LOCK" and tx_nonce != expected_nonce:
        return _fail_delta(
            sender, recipient, f"Invalid nonce for {sender}: expected {expected_nonce}, got {tx_nonce}", tx_type, tx_hash
        )
    return sender_account


def _escrow_dispatch_delta(
    account_map: dict[str, Account],
    tx_data: dict[str, Any],
    sender: str,
    recipient: str,
    value: int,
    fee: int,
    tx_type: str,
    tx_hash: str,
    block_version: int,
    escrow_context: dict[str, dict[str, Any]] | None,
) -> StateDelta | None:
    """Dispatch ESCROW_RELEASE/ESCROW_REFUND and v11 ESCROW_FEE_SWEEP."""
    # S-4: ESCROW_RELEASE/ESCROW_REFUND require the matching lock metadata.
    if tx_type in ("ESCROW_RELEASE", "ESCROW_REFUND"):
        return _escrow_release_refund_delta(
            account_map, tx_data, sender, recipient, value, fee, tx_type, tx_hash, block_version, escrow_context
        )

    # v11: ESCROW_FEE_SWEEP pays the governed fee recipient out of the job's
    # custody account. Below the gate the type has no consensus meaning and
    # falls through to the generic transfer path — the same "unknown type"
    # semantics the sequential path keeps for sealed history.
    if tx_type == "ESCROW_FEE_SWEEP" and block_version >= 11:
        return _escrow_fee_sweep_delta(
            account_map, tx_data, sender, recipient, value, fee, tx_type, tx_hash, block_version, escrow_context
        )
    return None


def _ipfs_subscription_field_error(payload: dict[str, Any], value: int) -> str | None:
    """Field validation for an IPFS_SUBSCRIPTION payload; error string or None."""
    if not payload.get("island_id"):
        return "IPFS_SUBSCRIPTION payload must include island_id"
    duration_blocks = payload.get("duration_blocks")
    if not isinstance(duration_blocks, int) or duration_blocks <= 0:
        return "IPFS_SUBSCRIPTION payload must include positive duration_blocks"
    quota_bytes = payload.get("quota_bytes")
    if not isinstance(quota_bytes, int) or quota_bytes < 0:
        return "IPFS_SUBSCRIPTION payload must include non-negative quota_bytes"
    if value <= 0:
        return "IPFS_SUBSCRIPTION requires value > 0"
    return None


def _ipfs_subscription_validate(
    tx_data: dict[str, Any],
    sender: str,
    recipient: str,
    value: int,
    tx_type: str,
    tx_hash: str,
) -> StateDelta | None:
    """Validate the IPFS_SUBSCRIPTION payload; failure delta or None."""
    if tx_type != "IPFS_SUBSCRIPTION":
        return None
    # IPFS_SUBSCRIPTION: payload must contain island subscription terms
    payload = tx_data.get("payload", {}) or {}
    if isinstance(payload, str):
        try:
            import json

            payload = json.loads(payload)
        except (RecursionError, TypeError, ValueError):  # malformed payload JSON decodes to the empty/default branch
            return _fail_delta(sender, recipient, "IPFS_SUBSCRIPTION payload is not valid JSON", tx_type, tx_hash)
    field_error = _ipfs_subscription_field_error(payload, value)
    if field_error is not None:
        return _fail_delta(sender, recipient, field_error, tx_type, tx_hash)
    return None


def _pre_transfer_validation_delta(
    tx_data: dict[str, Any],
    tx_type: str,
    sender: str,
    recipient: str,
    value: int,
    tx_hash: str,
) -> StateDelta | None:
    """Value-zero and IPFS_SUBSCRIPTION payload validation, in order."""
    # Value-zero types: MESSAGE and GPU_MARKET must not move funds.
    # GPU_MARKET has no dedicated apply branch, so a nonzero value would
    # execute as a plain transfer.
    if tx_type in {"MESSAGE", "GPU_MARKET"} and value != 0:
        return _fail_delta(sender, recipient, f"{tx_type} transactions must have value=0, got {value}", tx_type, tx_hash)
    return _ipfs_subscription_validate(tx_data, sender, recipient, value, tx_type, tx_hash)


def _bridge_lock_signature_error(
    tx_data: dict[str, Any],
    tx_hash: str,
    bridge_authority: str | None,
    block_version: int,
) -> str | None:
    """v9 BRIDGE_LOCK bridge-signature gate; error string or None.

    Below v9 an unsigned/invalid lock only counts (shadow mode); at v9+ it
    fails closed.
    """
    # v9: the lock must carry the bridge authority's signature over its
    # semantic fields — mirrors validate_transaction's BRIDGE_LOCK gate.
    # bridge_authority is resolved by the caller (None fails closed at
    # v9); below the height an unsigned lock only counts (shadow).
    if block_version >= 9:
        if not bridge_authority:
            return "BRIDGE_LOCK requires a bridge release authority: set the bridge_release_authority chain parameter"
        if not verify_bridge_lock_signature(tx_data, tx_hash, bridge_authority):
            return "BRIDGE_LOCK must carry a valid bridge_signature from the bridge authority"
    elif not verify_bridge_lock_signature(tx_data, tx_hash, bridge_authority or ""):
        count_v9_would_reject("bridge_lock_unsigned")
        logger.warning("v9 shadow: BRIDGE_LOCK tx %s lacks a valid bridge_signature", tx_hash)
    return None


def _generic_transfer_delta(
    tx_data: dict[str, Any],
    sender_account: Account,
    sender: str,
    recipient: str,
    value: int,
    fee: int,
    tx_type: str,
    tx_hash: str,
    block_version: int,
    bridge_authority: str | None,
    extra_accounts: list[str] | None,
    extra_debits: dict[str, int] | None,
) -> StateDelta:
    """Balance/recipient checks and the generic transfer StateDelta.

    Handles the BRIDGE_LOCK burn (no recipient credit, cleared recipient)
    and the v9 bridge-lock signature gate; every other crediting type
    credits ``value`` to the recipient.
    """
    # Calculate total cost
    if tx_type == "MESSAGE":
        total_cost = fee
    else:
        total_cost = value + fee

    # Balance check
    if sender_account.balance < total_cost:
        return _fail_delta(
            sender,
            recipient,
            f"Insufficient balance for {sender}: {sender_account.balance} < {total_cost}",
            tx_type,
            tx_hash,
        )

    # v0.25.5: recipient accounts are created on first credit, so a missing
    # recipient is not a validation failure.  The in-memory and DB apply paths
    # both create the account when the delta is committed.
    if tx_type not in {"MESSAGE", "RECEIPT_CLAIM"}:
        if not recipient:
            return _fail_delta(sender, "", "Missing recipient", tx_type, tx_hash)

    # Compute delta
    sender_balance_change = -total_cost
    recipient_balance_change = 0
    if tx_type == "BRIDGE_LOCK":
        bridge_error = _bridge_lock_signature_error(tx_data, tx_hash, bridge_authority, block_version)
        if bridge_error is not None:
            return _fail_delta(sender, recipient, bridge_error, tx_type, tx_hash)
        # Burn on the source chain: the locked value is anchored in the
        # CrossChainTransfer record and must NOT be credited to the
        # "bridge_lock" pseudo-recipient — which must not even exist as an
        # account (mirrors StateTransition.apply_transaction). Clearing the
        # delta recipient keeps the apply paths from creating it.
        recipient = ""
    elif tx_type not in {"MESSAGE", "BRIDGE_WITHDRAW"}:
        # BRIDGE_WITHDRAW also burns: sender is debited, the 0x0 recipient is
        # created at zero balance but never credited.
        recipient_balance_change = value

    return StateDelta(
        sender=sender,
        recipient=recipient,
        sender_balance_change=sender_balance_change,
        recipient_balance_change=recipient_balance_change,
        sender_nonce_change=1,
        success=True,
        tx_type=tx_type,
        tx_hash=tx_hash,
        extra_accounts=extra_accounts,
        extra_debits=extra_debits,
    )


def _finalize_delta(delta: StateDelta, tx_data: dict[str, Any]) -> StateDelta:
    """Attach IPFS_SUBSCRIPTION terms / RECEIPT_CLAIM fields to a success delta.

    Returns a failure StateDelta when a RECEIPT_CLAIM lacks receipt_id;
    failure deltas pass through unchanged.
    """
    if not delta.success:
        return delta
    tx_type = delta.tx_type
    tx_hash = delta.tx_hash
    sender = delta.sender
    recipient = delta.recipient

    # IPFS_SUBSCRIPTION: capture subscription terms for apply_deltas_to_db
    if tx_type == "IPFS_SUBSCRIPTION":
        payload = tx_data.get("payload", {}) or {}
        if isinstance(payload, str):
            try:
                import json

                payload = json.loads(payload)
            except (RecursionError, TypeError, ValueError):  # malformed payload JSON decodes to the empty/default branch
                payload = {}
        delta.ipfs_subscription = {
            "island_id": payload.get("island_id"),
            "duration_blocks": payload.get("duration_blocks", 0),
            "quota_bytes": payload.get("quota_bytes", 0),
        }

    # RECEIPT_CLAIM: note the receipt_id for later DB processing
    # (receipt validation requires DB access, so we just record it here)
    if tx_type == "RECEIPT_CLAIM":
        payload = tx_data.get("payload", {})
        receipt_id = payload.get("receipt_id") if isinstance(payload, dict) else None
        if not receipt_id:
            return _fail_delta(
                sender,
                recipient,
                "RECEIPT_CLAIM transactions must include receipt_id in payload",
                tx_type,
                tx_hash,
            )
        delta.receipt_id = receipt_id
        # A claim may carry its own issuance (payload.receipt): keep the record
        # on the delta so apply_deltas_to_db can materialise the row when the
        # local DB does not have it yet (#687).
        delta.receipt_record = _carried_receipt_record(payload, receipt_id)
        # minted_amount will be set during apply_deltas_to_db (requires DB read)

    return delta


def compute_state_delta(
    account_map: dict[str, Account],
    tx_data: dict[str, Any],
    chain_id: str,
    tx_hash: str = "",
    existing_tx_hashes: set[str] | None = None,
    block_version: int = 2,
    escrow_context: dict[str, dict[str, Any]] | None = None,
    bridge_authority: str | None = None,
    bridge_lock_context: dict[str, dict[str, Any]] | None = None,
    block_time: datetime | None = None,
) -> StateDelta:
    """Compute the state delta for a transaction WITHOUT modifying the DB.

    Pure function — reads from account_map (in-memory), returns a StateDelta.
    Does NOT touch the session, does NOT execute SQL, does NOT invalidate cache.

    Args:
        account_map: In-memory account state (pre-fetched from DB).
        tx_data: Transaction data (from, to, amount, fee, type, etc.).
        chain_id: Chain identifier.
        tx_hash: Transaction hash (for duplicate detection).
        existing_tx_hashes: Set of already-processed tx hashes (for duplicate check).
        block_version: State-transition rule version active for the block.
        escrow_context: Per-job metadata needed for ESCROW_RELEASE/ESCROW_REFUND
            (lock_version, expected_beneficiary, escrow_addr) and — from v11 —
            ESCROW_FEE_SWEEP (escrow_addr, settlement_authority, fee_recipient).
            Callers must supply this when enabling parallel processing for
            blocks containing those tx types.
        bridge_authority: Resolved bridge release authority for v5+ credit
            signature checks. Callers with DB access must pass
            ``state_transition._bridge_release_authority(session, chain_id)``
            when a block contains BRIDGE_RELEASE/BRIDGE_REFUND — ``None`` falls
            back to env-only resolution (the same chain the sequential resolver
            uses after its on-chain parameter lookup).
        bridge_lock_context: ``{lock_tx_hash: {exists, sender, amount, refunded}}``
            for v6+ BRIDGE_REFUND lock binding, from
            ``state_transition.build_bridge_lock_context``. ``None`` fails
            closed on any v6 refund.
        block_time: Sealed block-header timestamp. The v18 time-dependent
            types are all in SEQUENTIAL_ONLY_TX_TYPES so the pure path never
            consumes it — it is accepted here so every caller threads the
            same header value the sequential apply sees (attester parity),
            and it stays available if a future version moves a type off the
            sequential-only list.

    Returns:
        StateDelta with balance/nonce changes, or success=False with error.
    """
    sender = _to_ait_address(tx_data.get("from", ""))
    recipient = _to_ait_address(tx_data.get("to", ""))
    tx_type = _determine_tx_type(tx_data)
    value = tx_data.get("value", tx_data.get("amount", 0))
    fee = tx_data.get("fee", 0)

    # S-4: release/refund logic is handled after sender/nonce validation.
    extra_debits: dict[str, int] | None = None

    extra_accounts, recipient, early_delta = _escrow_lock_precheck(tx_data, sender, recipient, tx_type, tx_hash, block_version)
    if early_delta is not None:
        return early_delta

    early_delta = _pre_sender_delta(
        tx_data,
        sender,
        recipient,
        value,
        tx_type,
        tx_hash,
        chain_id,
        existing_tx_hashes,
        block_version,
        bridge_authority,
        bridge_lock_context,
    )
    if early_delta is not None:
        return early_delta

    early_delta = _auth_gates_delta(tx_data, tx_type, tx_hash, sender, recipient, block_version)
    if early_delta is not None:
        return early_delta

    sender_gate = _sender_account_and_nonce_delta(account_map, tx_data, sender, recipient, tx_type, tx_hash)
    if isinstance(sender_gate, StateDelta):
        return sender_gate
    sender_account = sender_gate

    early_delta = _escrow_dispatch_delta(
        account_map, tx_data, sender, recipient, value, fee, tx_type, tx_hash, block_version, escrow_context
    )
    if early_delta is not None:
        return early_delta

    early_delta = _pre_transfer_validation_delta(tx_data, tx_type, sender, recipient, value, tx_hash)
    if early_delta is not None:
        return early_delta

    delta = _generic_transfer_delta(
        tx_data,
        sender_account,
        sender,
        recipient,
        value,
        fee,
        tx_type,
        tx_hash,
        block_version,
        bridge_authority,
        extra_accounts,
        extra_debits,
    )
    return _finalize_delta(delta, tx_data)
