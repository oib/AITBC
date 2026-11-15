"""v9 unsigned-tx attestation policy checks (#1950 pure-move split)."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

from sqlalchemy import text
from sqlmodel import select


from ..config import settings
from ..metrics import metrics_registry
from ..models import Block
from ..state.v9_policy import V9_UNSIGNED_ALLOWED_TX_TYPES
from .remote_attestation_crypto import (
    V9_CHECK_ATTEMPTS,
    V9_CHECK_RETRY_DELAY_S,
    _is_transient_db_lock,
)
from . import remote_attestation as _ra

if TYPE_CHECKING:
    import logging

    logger: logging.Logger
else:
    logger = _ra.logger

from .remote_attestation import _ListenerMixin


def _int_header_height(header: dict[str, Any]) -> int:
    """Int-convertible header height for gate decisions (#1940 F4).

    Malformed numeric representations resolve -1 (gate inactive); the v9
    check itself still reports ``bad_header`` for them, and once the gate is
    armed the probe enforces the strict-int contract so a string height
    cannot bypass verification.
    """
    try:
        return int(header.get("height", 0))
    except (TypeError, ValueError, OverflowError):
        return -1


class _V9Mixin(_ListenerMixin):
    def _parent_lag_gap(self, header: dict[str, Any]) -> int | None:
        """#1295: how many blocks the local tip is behind the request's parent.

        Returns ``(height - 1) - tip_height`` — positive means the validator
        is still importing blocks the attestation needs; zero/negative means
        the tip is at or past the parent height (the not_at_parent verdict
        is then a real rival/ahead refusal, not lag). None when the height
        is unreadable or no session factory is configured.
        """
        try:
            height = int(header.get("height", 0))
        except (TypeError, ValueError):
            return None
        if self._session_factory is None or height <= 0:
            return None
        session_ctx = self._session_factory()
        try:
            with session_ctx as session:
                from ..database import ensure_chain_db_healthy

                db_ok, _ = ensure_chain_db_healthy(self._chain_id, session=session)
                if not db_ok:
                    return None
                tip_row = session.exec(
                    select(Block.height).where(Block.chain_id == self._chain_id).order_by(text("height DESC")).limit(1)
                ).first()
        except Exception:  # noqa: BLE001 - a probe failure must not mask the real verdict
            return None
        if tip_row is None:
            return None
        return (height - 1) - int(tip_row)

    async def _run_v9_check(
        self,
        header: dict[str, Any],
        txs: list[Any],
        *,
        proposer_signature: str | None = None,
    ) -> str | None:
        """#1310: run the v9 tx check, timed; optionally off the event loop.

        With ``attest_v9_check_offload_enabled`` — or
        ``attest_lag_wait_enabled``, whose bounded parent-import wait also
        sleeps — the (read-only, idempotent) check runs in a worker thread --
        ecrecover, sqlite reads and the retry/lag sleeps no longer freeze the
        loop. The handler still awaits the verdict before any signing
        decision, so serial ordering is unchanged.
        ``attest_v9_check_seconds`` records the cost either way.

        #1295 ATTEST-LAG-WAIT-1: a ``not_at_parent`` verdict while the tip
        is 1..``attest_lag_wait_max_blocks`` behind the request's parent is
        retried until ``attest_lag_wait_seconds`` elapses — transient import
        stalls get absorbed instead of instant refusal. The wait lives here,
        outside the check's session, so each poll opens and closes its own
        session (no connection pile-up) and fork protection is untouched:
        rival/ahead tips produce gap <= 0 and refuse on the first verdict.
        """
        start = _ra.time.monotonic()
        lag_wait = bool(getattr(settings, "attest_lag_wait_enabled", False))
        from .attestation_state_probe import post_state_probe_active

        # #1940 F4: an armed post-state gate always offloads — the probe must
        # never run on the event loop.
        probe_gate = post_state_probe_active(_int_header_height(header))
        offload = bool(getattr(settings, "attest_v9_check_offload_enabled", False)) or lag_wait or probe_gate
        deadline: float | None = None
        try:
            while True:
                if probe_gate:
                    verdict = await self._run_post_state_probe(header, txs, proposer_signature)
                elif offload:
                    verdict = await asyncio.to_thread(self._v9_check_transactions, header, txs)
                else:
                    verdict = self._v9_check_transactions(header, txs)
                if verdict != "not_at_parent" or not lag_wait:
                    return verdict
                gap = await asyncio.to_thread(self._parent_lag_gap, header)
                max_blocks = int(getattr(settings, "attest_lag_wait_max_blocks", 2))
                if gap is None or gap < 1 or gap > max_blocks:
                    return verdict
                now = _ra.time.monotonic()
                if deadline is None:
                    deadline = now + float(getattr(settings, "attest_lag_wait_seconds", 10.0))
                remaining = deadline - now
                if remaining <= 0:
                    return verdict
                await asyncio.sleep(min(V9_CHECK_RETRY_DELAY_S, remaining))
        finally:
            metrics_registry.observe("attest_v9_check_seconds", _ra.time.monotonic() - start)

    async def _run_post_state_probe(
        self,
        header: dict[str, Any],
        txs: list[Any],
        proposer_signature: str | None,
    ) -> str | None:
        """#1940 F4: one bounded post-state probe per service at a time.

        The worker owns the permit until it actually finishes — an async
        timeout stops awaiting but cannot release the permit early or let
        workers pile up; the worker's absolute monotonic deadline aborts the
        snapshot copy and scratch SQL, while bounded pure-Python trie work
        simply completes. Expiry refuses; it is never a consensus verdict.
        """
        timeout = float(getattr(settings, "attestation_post_state_timeout_seconds", 10.0))
        deadline = _ra.time.monotonic() + timeout
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._v9_post_state_worker, header, txs, proposer_signature, deadline),
                timeout=timeout,
            )
        except TimeoutError:
            return "post_state_timeout"
        except Exception as e:  # noqa: BLE001 - worker failure refuses; cancellation still propagates
            logger.warning("ATTEST-PROBE worker errored: %s", type(e).__name__)
            return "post_state_error"

    def _v9_post_state_worker(
        self,
        header: dict[str, Any],
        txs: list[Any],
        proposer_signature: str | None,
        deadline: float,
    ) -> str | None:
        """Worker-thread body: at most one post-state probe per service."""
        lock = self._attest_probe_lock
        if not lock.acquire(blocking=False):
            return "post_state_busy"
        try:
            return self._v9_check_transactions(
                header,
                txs,
                proposer_signature=proposer_signature,
                _probe_deadline=deadline,
            )
        finally:
            lock.release()

    def _v9_tx_root_structural_check(
        self,
        session: Any,
        header: dict[str, Any],
        txs: list[Any],
        height: int,
    ) -> str | None:
        """#1940 F5: new-era structural/type/derived-root check for a request.

        Every delivered tx must resolve unambiguously against its stored row
        type; every effective BRIDGE_LOCK must satisfy the canonical signed
        contract with signed amount == effective outer debit; and the shared
        tx-derived trie over the delivered bodies must equal the claimed
        ``bridge_state_root``. Returns a refusal reason or None.
        """
        from ..base_models import Transaction
        from ..cross_chain.bridge_tx_root import (
            assert_lock_debit,
            build_tx_bridge_trie,
            canonical_lock_fields,
            effective_lock_debit,
            resolve_lock_type,
        )

        hashes = [str(tx.get("tx_hash") or "") for tx in txs if isinstance(tx, dict)]
        stored_types: dict[str, str] = {}
        if hashes:
            for tx_hash, tx_type in session.exec(
                select(Transaction.tx_hash, Transaction.type).where(
                    Transaction.chain_id == self._chain_id,
                    Transaction.tx_hash.in_(hashes),  # type: ignore[attr-defined]
                )
            ).all():
                stored_types[tx_hash] = tx_type
        bodies: list[dict[str, Any]] = []
        for tx in txs:
            if not isinstance(tx, dict):
                return "malformed_tx"
            tx_hash = str(tx.get("tx_hash") or "")
            try:
                if resolve_lock_type(tx, stored_types.get(tx_hash)) == "BRIDGE_LOCK":
                    fields = canonical_lock_fields({**tx, "tx_hash": tx_hash}, tx_hash, self._chain_id, height)
                    assert_lock_debit(fields, effective_lock_debit(tx))
            except (TypeError, ValueError) as e:
                return f"bridge_lock_contract: {e}"
            body = dict(tx)
            body["tx_hash"] = tx_hash
            bodies.append(body)
        try:
            trie = build_tx_bridge_trie(bodies, self._chain_id, height)
        except (TypeError, ValueError) as e:
            return f"bridge_root_contract: {e}"
        computed = "0x" + trie.get_root().hex()
        claimed = str(header.get("bridge_state_root") or "")
        if not claimed:
            return "missing_bridge_state_root"
        if claimed != computed:
            return "bridge_state_root_mismatch"
        return None

    def _v9_check_transactions(
        self,
        header: dict[str, Any],
        txs: list[Any],
        _attempt: int = 1,
        *,
        proposer_signature: str | None = None,
        _probe_deadline: float | None = None,
    ) -> str | None:
        """Verify attestation-request transactions against local parent state.

        Returns a refusal reason, or None when the request is attestable.
        Checks are deliberately shallow — signature presence/validity and
        same-block nonce order; full re-execution is deferred until a
        scratch-overlay exists.

        Two binds before any tx check:

        - the declared ``tx_hashes``/``tx_count``/``timestamp`` must
          recompute to the signed block hash, proving the request's tx list
          is the set the block commits to (not a clean subset covering a
          forged one);
        - this validator must sit at the block's parent — a tip behind,
          ahead, or on a rival hash makes the nonce check meaningless, so it
          refuses rather than attest from stale state.
        """
        header_hash = str(header.get("hash", ""))
        try:
            height = int(header.get("height", 0))
        except (TypeError, ValueError):
            return "bad_header"
        from .attestation_state_probe import post_state_probe_active, probe_post_state

        # #1940 F4: the gate decided on the int-convertible height above so a
        # malformed numeric representation cannot skip the check; the probe
        # itself then enforces the strict-int contract.
        probe_active = post_state_probe_active(height)
        parent_hash = str(header.get("parent_hash", ""))
        proposer = str(header.get("proposer", ""))
        tx_hashes = header.get("tx_hashes")
        tx_count = header.get("tx_count")
        timestamp = header.get("timestamp")
        if not isinstance(tx_hashes, list) or tx_count is None or not timestamp:
            return "unbound_tx_set"
        try:
            if int(tx_count) != len(txs):
                return "tx_count_mismatch"
        except (TypeError, ValueError):
            return "tx_count_mismatch"

        from .block_hash import compute_block_hash

        recomputed = compute_block_hash(
            str(header.get("chain_id") or self._chain_id),
            height,
            parent_hash,
            str(timestamp),
            [str(h) for h in tx_hashes],
            proposer,
            str(header.get("state_root") or ""),
            str(header.get("bridge_state_root") or ""),
            str(header.get("aux_state_root") or ""),
        )
        if recomputed != header_hash:
            return "tx_set_mismatch"
        declared_hashes = {str(h) for h in tx_hashes}

        if self._session_factory is None:
            return "no_state_access"
        try:
            session_ctx = self._session_factory()
            with session_ctx as session:
                from ..database import ensure_chain_db_healthy

                db_ok, _ = ensure_chain_db_healthy(self._chain_id, session=session)
                if not db_ok:
                    return "db_corrupt"
                # Column-only select: loading the Block ORM entity would
                # eager-load its selectin relationships (transactions and
                # receipts) and cost seconds per request on a slow host.
                tip_row = session.exec(
                    select(Block.height, Block.hash)
                    .where(Block.chain_id == self._chain_id)
                    .order_by(text("height DESC"))
                    .limit(1)
                ).first()
                if tip_row is None:
                    return "not_at_parent"
                tip_height, tip_hash = tip_row
                self._tip_height_hint = int(tip_height)
                if tip_hash != parent_hash:
                    # Late request for the block this validator already
                    # imported: the request's hash IS the local head at that
                    # height. The parent-binding/nonce checks below cannot
                    # run (the tip moved past the parent) and need not —
                    # import already validated this exact block, so signing
                    # it is idempotent rather than a would-reject.
                    # A RIVAL at the same height still refuses: tip.height
                    # matches but tip.hash != header hash falls through to
                    # not_at_parent, which is the fork protection working.
                    if tip_height == height and tip_hash == header_hash:
                        if probe_active:
                            return probe_post_state(
                                session,
                                self._chain_id,
                                header,
                                txs,
                                deadline=_probe_deadline,
                                proposer_signature=proposer_signature,
                            )
                        return None
                    return "not_at_parent"

                # #1940 F5: tx-derived bridge-root era — structural lock
                # contract plus derived-root equality, gated by the
                # parent-history rule at this block's height (NOT the F4
                # post-state gate). Shallow by design: canonical signed
                # fields, debit equality, duplicate/malformed rejection and
                # the shared trie root vs the claimed bridge_state_root.
                # Full apply verification remains the post-state probe's
                # job; failed-state roots are not claimed here.
                from ..cross_chain.bridge_tx_root import tx_only_root_active

                if tx_only_root_active(session, self._chain_id, height):
                    refusal = self._v9_tx_root_structural_check(session, header, txs, height)
                    if refusal:
                        return refusal

                from ..base_models import _to_ait_address
                from ..models import Account
                from ..rpc.utils import verify_transaction_signature

                expected_nonce: dict[str, int] = {}
                for tx in txs:
                    if not isinstance(tx, dict):
                        return "malformed_tx"
                    payload = tx.get("payload") or {}
                    tx_type = str(
                        tx.get("type") or (payload.get("type") if isinstance(payload, dict) else "") or "TRANSFER"
                    ).upper()
                    sender = _to_ait_address(str(tx.get("from") or tx.get("sender") or ""))
                    signature = tx.get("signature") or tx.get("sig")
                    # Every delivered envelope must be one of the tx hashes
                    # the block hash commits to. User txs recompute from the
                    # body; allowlisted internals carry arbitrary ids (e.g.
                    # bridge transfer_id) so membership is the check there.
                    declared_hash = str(tx.get("tx_hash") or "")
                    if tx_type in V9_UNSIGNED_ALLOWED_TX_TYPES:
                        if declared_hash not in declared_hashes:
                            return "tx_not_in_block"
                    else:
                        from ..mempool import compute_tx_hash

                        recomputed_tx = compute_tx_hash({k: v for k, v in tx.items() if k != "tx_hash"})
                        if recomputed_tx != declared_hash or recomputed_tx not in declared_hashes:
                            return "tx_not_in_block"
                    if signature:
                        # A present signature must verify for every type —
                        # apply enforces that even for allowlisted internals.
                        if not sender or not verify_transaction_signature(tx, signature, sender):
                            return "invalid_signature"
                    elif tx_type not in V9_UNSIGNED_ALLOWED_TX_TYPES:
                        # v17: protocol transfers may authorize via
                        # payload.auth instead of a sender signature. Attest
                        # only when apply would accept the same tx: version
                        # armed, auth well-formed, and verifiably bound.
                        from ..state.state_transition import (
                            StateTransition,
                            get_block_version_for_height,
                        )
                        from ..state.v9_policy import (
                            V17_PAYLOAD_AUTH_TX_TYPES,
                            _payload_auth_of,
                            payload_auth_shape,
                        )

                        auth = _payload_auth_of(tx)
                        if not (
                            get_block_version_for_height(height) >= 17
                            and tx_type in V17_PAYLOAD_AUTH_TX_TYPES
                            and payload_auth_shape(auth)
                        ):
                            if not sender:
                                return "missing_sender"
                            return "missing_signature"
                        if not StateTransition._verify_payload_auth(tx_type, auth, tx):
                            return "invalid_payload_auth"
                    # Bridge-issued internals are exempt from the *sender*
                    # signature only because the bridge authority's signature
                    # replaces it — attest to neither exemption without it.
                    if tx_type in {"BRIDGE_LOCK", "BRIDGE_RELEASE", "BRIDGE_REFUND"}:
                        from ..state.bridge_credit import (
                            bridge_credit_signature,
                            verify_bridge_credit_signature,
                            verify_bridge_lock_signature,
                        )
                        from ..state.state_transition import _bridge_release_authority

                        authority = _bridge_release_authority(session, self._chain_id, height)
                        if not authority:
                            return "bridge_authority_unset"
                        if not bridge_credit_signature(tx):
                            return "bridge_signature_missing"
                        verify = verify_bridge_lock_signature if tx_type == "BRIDGE_LOCK" else verify_bridge_credit_signature
                        if not verify(tx, declared_hash, authority):
                            return "bridge_signature_invalid"
                    # Nonce ordering: signed txs must arrive in account-nonce
                    # order. Unsigned internal txs carry a placeholder nonce
                    # rewritten at seal time, but they still increment the
                    # sender nonce at apply (BRIDGE_LOCK) — the
                    # counter must advance past them or a same-sender signed
                    # tx later in the block would read as out of order.
                    if sender:
                        if sender not in expected_nonce:
                            account = session.get(Account, (self._chain_id, sender))
                            expected_nonce[sender] = account.nonce if account and account.nonce is not None else 0
                        if signature:
                            try:
                                tx_nonce = int(tx.get("nonce") or 0)
                            except (TypeError, ValueError):
                                return "bad_nonce"
                            if tx_nonce != expected_nonce[sender]:
                                return "nonce_order"
                        expected_nonce[sender] += 1
                if probe_active:
                    return probe_post_state(
                        session,
                        self._chain_id,
                        header,
                        txs,
                        deadline=_probe_deadline,
                        proposer_signature=proposer_signature,
                    )
        except Exception as e:  # noqa: BLE001 - any check failure verdicts check_error: refuse, never attest unverified
            if _attempt < V9_CHECK_ATTEMPTS and _is_transient_db_lock(e):
                logger.info(
                    "v9 attestation tx check hit a locked database for height %s (attempt %s of %s), retrying: %s",
                    height,
                    _attempt,
                    V9_CHECK_ATTEMPTS,
                    e,
                )
                time.sleep(V9_CHECK_RETRY_DELAY_S)
                return self._v9_check_transactions(
                    header,
                    txs,
                    _attempt + 1,
                    proposer_signature=proposer_signature,
                    _probe_deadline=_probe_deadline,
                )
            logger.warning("v9 attestation tx check failed to run for height %s: %s", height, e)
            return "check_error"
        return None
