"""Remote block-header attestation over the gossip broker.

v0.7.6: minimal second-node validator PoC. Proposers publish a block header
over the ``consensus.attest_request.<chain_id>`` gossip topic. Other validators
sign the canonical header and publish responses on
``consensus.attest_response.<chain_id>``. The proposer collects responses and
includes them in ``block_metadata``.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlmodel import select

from aitbc.aitbc_logging import get_logger
from aitbc.async_tasks import create_task_with_logging
from aitbc.crypto.consensus_signing import sign_consensus_message, verify_block_signature
from aitbc.crypto.signature_recovery import canonical_address

from ..config import settings
from ..gossip import gossip_broker
from ..metrics import metrics_registry
from ..models import Block
from ..state.v9_policy import V9_UNSIGNED_ALLOWED_TX_TYPES, count_v9_would_reject

logger = get_logger(__name__)

# The v9 attestation check opens its own database session. A validator that
# cannot read its own state must not attest, but SQLite lock contention (a long
# writer on the same file) says nothing about the block: the whole check is
# retried once before it fails closed. The proposer waits
# ``multi_validator_attestation_timeout_seconds`` plus 0.5 s per missing
# attestation for answers, so one extra attempt still lands inside that window.
V9_CHECK_ATTEMPTS = 2
V9_CHECK_RETRY_DELAY_S = 0.5


def _is_transient_db_lock(exc: BaseException) -> bool:
    """True for SQLite's transient "database is locked" / "database is busy" errors."""
    if not isinstance(exc, (OperationalError, sqlite3.OperationalError)):
        return False
    message = str(exc).lower()
    return "database is locked" in message or "database is busy" in message


def _same_address(a: str, b: str) -> bool:
    """Compare two 0x EVM addresses (case-insensitive)."""
    return canonical_address(a) == canonical_address(b)


class RemoteAttestationService:
    """Collect and serve remote block-header attestations over gossip."""

    def __init__(
        self,
        chain_id: str,
        validator_keys: dict[str, str],
        session_factory: Any | None = None,
    ) -> None:
        self._chain_id = chain_id
        self._validator_keys = validator_keys
        # Needed for the v9 attestation checks: signature and nonce-order
        # verification run against this validator's own account state at the
        # block's parent. Without a session factory the checks cannot run —
        # requests stay attestable while v9 is inactive (shadow mode only)
        # and are refused once it is.
        self._session_factory = session_factory
        self._request_topic = f"consensus.attest_request.{chain_id}"
        self._response_topic = f"consensus.attest_response.{chain_id}"
        self._listener_task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        # Attester locks: height -> (block_hash, proposer, signed_at).
        # A validator that signs block X at height h must not propose — or
        # re-attest — a different block at h for one proposer round. Without
        # this a validator can attest a block it never receives and then
        # build a rival at the same height — the asymmetric-partition fork
        # mechanism seen live 2026-09-27.
        self._attested: dict[int, tuple[str, str, float]] = {}

    async def start(self) -> None:
        if self._listener_task is not None:
            return
        self._stop_event.clear()
        self._listener_task = create_task_with_logging(
            self._listen(),
            name=f"remote_attestation_listener_{self._chain_id}",
        )

    async def stop(self) -> None:
        self._stop_event.set()
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
            self._listener_task = None

    async def _listen(self) -> None:
        try:
            sub = await gossip_broker.subscribe(self._request_topic, max_queue_size=1000)
        except Exception as e:
            logger.warning("Failed to subscribe to attestation requests: %s", e)
            return

        logger.info("Subscribed to remote attestation requests on %s", self._request_topic)
        try:
            async for request in sub:
                if self._stop_event.is_set():
                    break
                try:
                    await self._handle_request(request)
                except Exception as e:
                    logger.warning("Error handling attestation request: %s", e)
        finally:
            sub.close()

    async def _handle_request(self, request: Any) -> None:
        if not isinstance(request, dict):
            return
        header = request.get("header")
        if not isinstance(header, dict):
            return

        proposer = header.get("proposer", "")
        if not proposer:
            return

        try:
            height_int = int(header.get("height", 0))
        except (TypeError, ValueError):
            return
        header_hash = str(header.get("hash", ""))
        if not header_hash:
            return

        # Attestation lock: having signed one header at this height, refuse a
        # rival hash for one round window. Double-signing two blocks at h is
        # the equivocation that lets an asymmetric partition become a fork.
        window = float(getattr(settings, "consensus_proposer_round_seconds", 60))
        if getattr(settings, "attestation_lock_enabled", True):
            existing = self.attestation_lock(height_int, window)
            if existing is not None and existing[0] != header_hash:
                logger.info(
                    "Attestation lock: refusing to sign rival %s at height %s — already attested %s",
                    header_hash[:18],
                    height_int,
                    existing[0][:18],
                )
                return

        # Only sign for blocks produced by a known validator in our set.
        validator_set = self._load_validator_set()
        if validator_set and canonical_address(proposer) not in {canonical_address(v) for v in validator_set}:
            return

        # v9: before signing, verify every transaction in the request —
        # sender signature (except the shared internal allowlist) and nonce
        # order against this validator's own state at the block's parent.
        # Full re-execution is deferred; an attestation then means "these
        # transactions are authorized", not just "the header came from a
        # validator". While the v9 height is unset a failed check only logs
        # and counts — the attestation still goes out (shadow mode).
        txs = request.get("transactions")
        from ..state.state_transition import get_block_version_for_height

        refusal: str | None
        if not isinstance(txs, list):
            refusal = "transactions_absent"
        elif len(json.dumps(request).encode()) > int(getattr(settings, "gossip_max_message_size", 1_048_576)):
            refusal = "request_too_large"
        else:
            refusal = self._v9_check_transactions(header, txs)
        if refusal is not None:
            count_v9_would_reject(f"attest_{refusal}")
            if get_block_version_for_height(height_int) >= 9:
                logger.warning(
                    "v9: refusing attestation for block %s at height %s — %s",
                    header_hash[:18],
                    height_int,
                    refusal,
                )
                return
            logger.warning(
                "v9 shadow: would refuse attestation for block %s at height %s — %s",
                header_hash[:18],
                height_int,
                refusal,
            )

        for address, private_key in self._validator_keys.items():
            # Do not sign our own block.
            if _same_address(address, proposer):
                continue
            # Only sign with keys that are part of the configured validator set.
            if validator_set and canonical_address(address) not in {canonical_address(v) for v in validator_set}:
                continue

            message = {
                "chain_id": header.get("chain_id", self._chain_id),
                "height": header.get("height", 0),
                "hash": header.get("hash", ""),
                "parent_hash": header.get("parent_hash", ""),
                "proposer": proposer,
                "state_root": header.get("state_root", ""),
                "bridge_state_root": header.get("bridge_state_root", ""),
            }
            try:
                signature = sign_consensus_message(message, private_key)
            except Exception as e:
                logger.warning("Failed to sign attestation: %s", e)
                continue
            self._record_attestation_lock(height_int, header_hash, proposer)

            response = {
                "chain_id": self._chain_id,
                "height": message["height"],
                "hash": message["hash"],
                "validator": address,
                "signature": signature,
            }
            try:
                await gossip_broker.publish(self._response_topic, response)
            except Exception as e:
                logger.warning("Failed to publish attestation response: %s", e)
                continue
            # request_age_ms is this node's clock minus the proposer's request
            # timestamp: request transit, queueing and the v9 checks, plus any
            # clock offset between the two hosts. It is what separates a validator
            # that answers late from one that never answers (V-9).
            request_ts = request.get("timestamp")
            request_age_ms = (
                int((time.time() - float(request_ts)) * 1000) if isinstance(request_ts, (int, float)) else "unknown"
            )
            logger.info(
                "Attestation response published: height=%s validator=%s proposer=%s request_age_ms=%s",
                message["height"],
                address,
                proposer,
                request_age_ms,
            )
            return

    def _v9_check_transactions(
        self,
        header: dict[str, Any],
        txs: list[Any],
        _attempt: int = 1,
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
        )
        if recomputed != header_hash:
            return "tx_set_mismatch"
        declared_hashes = {str(h) for h in tx_hashes}

        if self._session_factory is None:
            return "no_state_access"
        try:
            session_ctx = self._session_factory()
            with session_ctx as session:
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
                        return None
                    return "not_at_parent"

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
                        if not sender:
                            return "missing_sender"
                        return "missing_signature"
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
        except Exception as e:
            if _attempt < V9_CHECK_ATTEMPTS and _is_transient_db_lock(e):
                logger.info(
                    "v9 attestation tx check hit a locked database for height %s (attempt %s of %s), retrying: %s",
                    height,
                    _attempt,
                    V9_CHECK_ATTEMPTS,
                    e,
                )
                time.sleep(V9_CHECK_RETRY_DELAY_S)
                return self._v9_check_transactions(header, txs, _attempt + 1)
            logger.warning("v9 attestation tx check failed to run for height %s: %s", height, e)
            return "check_error"
        return None

    def _record_attestation_lock(self, height: int, block_hash: str, proposer: str) -> None:
        """Record that this node's validator key(s) signed block `block_hash`
        at `height`. Locks expire by wall clock in `attestation_lock`."""
        now = time.monotonic()
        window = float(getattr(settings, "consensus_proposer_round_seconds", 60))
        self._attested = {h: e for h, e in self._attested.items() if now - e[2] < 2 * window}
        self._attested[height] = (block_hash, proposer, now)

    def attestation_lock(self, height: int, window_seconds: float) -> tuple[str, str] | None:
        """Return ``(block_hash, proposer)`` this validator attested at
        ``height`` if the lock is still live, else None. Expired entries are
        dropped lazily."""
        entry = self._attested.get(height)
        if entry is None:
            return None
        block_hash, proposer, signed_at = entry
        if time.monotonic() - signed_at >= window_seconds:
            del self._attested[height]
            return None
        return block_hash, proposer

    def _load_validator_set(self) -> set[str]:
        validator_set_str = getattr(settings, "validator_set", "")
        if not validator_set_str:
            return set()
        try:
            data = json.loads(validator_set_str)
            return {v.get("address", "") for v in data if v.get("address")}
        except Exception:
            return set()

    async def collect_attestations(
        self,
        block: Block,
        min_count: int,
        timeout: float | None = None,
        transactions: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, str]]:
        """Publish a header and collect at least min_count remote attestations.

        ``transactions`` carries the block's signed transaction envelopes —
        at v9 attesters verify them (signature + nonce order against their
        own parent state) before signing, so the request must always
        include them, empty list included.
        """
        if not self._validator_keys:
            return []

        effective_timeout = float(
            timeout if timeout is not None else getattr(settings, "multi_validator_attestation_timeout_seconds", 1.0)
        )

        header = {
            "chain_id": self._chain_id,
            "height": block.height,
            "hash": block.hash,
            "parent_hash": block.parent_hash or "",
            "proposer": block.proposer,
            "state_root": block.state_root or "",
            "bridge_state_root": block.bridge_state_root or "",
        }
        request: dict[str, Any] = {"header": header, "timestamp": time.time()}
        if transactions is not None:
            # Bind the tx set to the signed header: the attester recomputes
            # the block hash from these fields plus the declared tx-hash set,
            # so a request carrying a truncated/substituted tx list fails the
            # digest check instead of attesting a different block.
            header["timestamp"] = block.timestamp.isoformat() if block.timestamp else ""
            header["tx_count"] = len(transactions)
            header["tx_hashes"] = sorted(str(tx.get("tx_hash") or "") for tx in transactions if isinstance(tx, dict))
            request["transactions"] = transactions
            request_size = len(json.dumps(request).encode())
            max_size = int(getattr(settings, "gossip_max_message_size", 1_048_576))
            if request_size > max_size:
                # The broker drops oversized payloads, so remote attestations
                # will never arrive — fail loud here rather than stall a full
                # timeout cycle wondering why.
                metrics_registry.increment("v9_attestation_request_oversized_total")
                logger.warning(
                    "Attestation request for height %s is %s bytes, over gossip_max_message_size %s — remote attestations unlikely",
                    block.height,
                    request_size,
                    max_size,
                )

        # Subscribe first to avoid missing a fast response.
        try:
            sub = await gossip_broker.subscribe(self._response_topic, max_queue_size=1000)
        except Exception as e:
            logger.warning("Failed to subscribe to attestation responses: %s", e)
            return []

        try:
            await gossip_broker.publish(self._request_topic, request)
        except Exception as e:
            logger.warning("Failed to publish attestation request: %s", e)
            sub.close()
            return []

        attestations: list[dict[str, str]] = []
        start = time.monotonic()

        # Post-quorum linger (V-9 follow-up): once min_count valid attestations
        # are in, keep collecting for up to linger seconds so slower validators
        # still land in the block instead of losing the first-to-quorum race
        # every round. 0 preserves the old seal-as-soon-as-quorum behaviour;
        # the effective_timeout above still bounds the whole collection.
        linger = float(getattr(settings, "attestation_post_quorum_linger_seconds", 0.0) or 0.0)
        expected_remote = {canonical_address(v) for v in self._load_validator_set()} - {canonical_address(str(block.proposer))}
        answered: set[str] = set()
        counted: set[str] = set()
        quorum_at: float | None = None
        try:
            while time.monotonic() - start < effective_timeout:
                remaining = effective_timeout - (time.monotonic() - start)
                if quorum_at is not None:
                    remaining = min(remaining, linger - (time.monotonic() - quorum_at))
                if remaining <= 0:
                    break
                try:
                    response = await asyncio.wait_for(sub.get(), timeout=remaining)
                except asyncio.TimeoutError:
                    break
                if not isinstance(response, dict):
                    continue
                if response.get("chain_id") != self._chain_id:
                    continue
                # One INFO line per response that reaches the collector, with its
                # arrival time, so the order and the delay in which validators
                # answer can be read from the journal (V-9: one validator attests
                # in ~3% of blocks, and the proposer keeps only the first answers).
                # The loop stops at min_count, so a response that comes later than
                # the kept ones is never read here; one for an earlier block that
                # lands in this window is logged as stale.
                arrived_ms = int((time.monotonic() - start) * 1000)
                validator = response.get("validator", "")
                if response.get("hash") != block.hash:
                    logger.info(
                        "Attestation arrival: height=%s validator=%s arrived_ms=%d outcome=stale response_height=%s",
                        block.height,
                        validator,
                        arrived_ms,
                        response.get("height"),
                    )
                    continue
                signature = response.get("signature", "")
                if not validator or not signature:
                    continue
                try:
                    vcanon = canonical_address(validator)
                except Exception:
                    vcanon = ""
                if vcanon and vcanon in expected_remote:
                    answered.add(vcanon)
                outcome = "invalid_signature"
                try:
                    if verify_block_signature(header, signature, validator):
                        dedup_key = vcanon or validator
                        if dedup_key in counted:
                            outcome = "duplicate"
                        else:
                            counted.add(dedup_key)
                            attestations.append({"validator": validator, "signature": signature})
                            outcome = f"valid rank={len(attestations)}"
                except Exception as e:
                    logger.warning("Failed to verify attestation from %s: %s", validator, e)
                    outcome = "verify_error"
                logger.info(
                    "Attestation arrival: height=%s validator=%s arrived_ms=%d outcome=%s",
                    block.height,
                    validator,
                    arrived_ms,
                    outcome,
                )
                if expected_remote and len(answered) >= len(expected_remote):
                    break
                if len(attestations) >= min_count:
                    if linger <= 0 or min_count <= 0:
                        break
                    if quorum_at is None:
                        quorum_at = time.monotonic()
                    elif time.monotonic() - quorum_at >= linger:
                        break
        finally:
            sub.close()

        return attestations
