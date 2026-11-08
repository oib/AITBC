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
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlmodel import select

from aitbc.aitbc_logging import get_logger
from aitbc.async_tasks import create_task_with_logging
from aitbc.constants import DATA_DIR
from aitbc.crypto.consensus_signing import (
    sign_consensus_message,
    verify_block_signature,
    verify_consensus_message,
)
from aitbc.crypto.signature_recovery import canonical_address

from ..config import settings
from ..gossip import gossip_broker
from ..metrics import metrics_registry
from ..models import Block
from ..state.v9_policy import V9_UNSIGNED_ALLOWED_TX_TYPES, count_v9_would_reject
from .vote_fetch import contention_hold, kick_pull, locate_voted_block
from .vote_journal import KIND_ATTEST, VoteJournalError, get_vote_journal, valve_open, vote_journal_enabled

logger = get_logger(__name__)

# The v9 attestation check opens its own database session. A validator that
# cannot read its own state must not attest, but SQLite lock contention (a long
# writer on the same file) says nothing about the block: the whole check is
# retried once before it fails closed. The proposer waits
# ``multi_validator_attestation_timeout_seconds`` plus 0.5 s per missing
# attestation for answers, so one extra attempt still lands inside that window.
# #1245: heights of "already signed" memory kept when the tip cannot be read.
SIGNED_ONCE_MAX_HEIGHTS = 256
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


class _RoundLockEntry:
    """One signed (height, round) -> block_hash record (#1242).

    ``signed_at``/``request_seen_at`` are monotonic for live entries; records
    restored from disk carry wall-clock-derived equivalents so the same U1/U2
    math applies after a restart.
    """

    __slots__ = ("block_hash", "proposer", "signed_at", "signed_wall", "request_seen_at", "request_seen_wall")

    def __init__(
        self,
        block_hash: str,
        proposer: str,
        signed_at: float,
        signed_wall: float,
        request_seen_at: float | None,
        request_seen_wall: float | None,
    ) -> None:
        self.block_hash = block_hash
        self.proposer = proposer
        self.signed_at = signed_at
        self.signed_wall = signed_wall
        self.request_seen_at = request_seen_at
        self.request_seen_wall = request_seen_wall


class _RoundLockVerdict:
    """Outcome of the shared (height, round) lock transition check."""

    __slots__ = ("permitted", "reason", "block_hash", "proposer")

    def __init__(self, permitted: bool, reason: str | None, block_hash: str = "", proposer: str = "") -> None:
        self.permitted = permitted
        self.reason = reason
        self.block_hash = block_hash
        self.proposer = proposer


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
        # #1242 round-keyed lock state — used only when
        # ``attestation_round_lock_enabled`` is set; the legacy ``_attested``
        # path above is untouched when it is not.
        #   _round_locks: (height, round) -> _RoundLockEntry
        #   _requests_seen: height -> {round: first_seen_mono} — U2 evidence
        self._round_locks: dict[tuple[int, int], _RoundLockEntry] = {}
        self._requests_seen: dict[int, dict[int, float]] = {}
        self._round_locks_loaded = False
        self._round_locks_path = DATA_DIR / "data" / chain_id / "attestation_round_locks.json"
        # #1245: hashes this node has already signed, per height. The lock
        # above is renewed by nothing: the first signing of (height, hash)
        # starts the window and a duplicate request neither renews nor
        # restarts it. A duplicate inside the window is re-published (the
        # proposer may have lost the first response); a duplicate after the
        # window is refused -- the lock has lapsed on purpose and a replay
        # must not re-arm it. Pruned by height as the tip advances, not by
        # wall clock, so waiting out a timer does not forget a signing.
        # Restart clears it, same as the lock; the header freshness bound
        # covers that gap.
        self._signed_once: dict[int, set[str]] = {}
        # #1263: signature-bearing attestation records for equivocation
        # evidence — "height:block_hash:signer" -> the exact fields the
        # signature covers plus the signature itself, so a later rival-hash
        # signing at the same height can cite BOTH attestations on-chain.
        # Persisted next to the round locks so a restart cannot lose the
        # prior signature an equivocation record needs.
        self._signed_attestations: dict[str, dict[str, Any]] = {}
        self._signed_attestations_loaded = False
        self._signed_attestations_path = DATA_DIR / "data" / chain_id / "attestation_signed.json"
        # Highest local tip the v9 check has read; lets pruning avoid its own DB access.
        self._tip_height_hint: int | None = None
        # #1268: ``(chain_id, peer_base_url) -> Any`` the proposer wires to the
        # sync manager so a fetch-before-unlock hit can pull the voted block.
        self.pull_hook: Any | None = None

    async def _journal_refuses(
        self,
        height: int,
        header_hash: str,
        address: str,
        proposer: str,
        request_round: int | None,
    ) -> bool:
        """#1268 vote-journal gate for one signer. True = do not sign.

        A live journal vote for a DIFFERENT hash at this height refuses the
        rival, with no wall-clock expiry and across restarts. Before the
        refusal is allowed to lapse (liveness valve) the voted block is looked
        up on the mesh: if a peer serves it, a pull is kicked so the tip
        passes this height and the rival then fails the parent check. The
        valve opens only when the vote is older than
        ``vote_journal_unlock_seconds`` AND no peer serves the voted block.
        On a clean pass the new vote is made durable BEFORE any signature
        exists; a persistence failure refuses the vote.
        """
        journal = get_vote_journal(self._chain_id)
        journal.prune_below(self._tip_height_hint)
        conflicts = journal.conflicting(height, address, header_hash)
        if conflicts:
            voted_hashes = {r.block_hash for r in conflicts}
            base = await locate_voted_block(self._chain_id, height, voted_hashes)
            if base is not None:
                kick_pull(self.pull_hook, self._chain_id, base)
                metrics_registry.increment("vote_journal_refused_rival_total")
                logger.info(
                    "Vote journal: refusing rival %s at height %s — %s already voted %s; pulling it from %s",
                    header_hash[:18],
                    height,
                    canonical_address(address)[:18],
                    sorted(voted_hashes)[0][:18],
                    base,
                )
                return True
            unlock = float(getattr(settings, "vote_journal_unlock_seconds", 300.0))
            if not all(valve_open(r, unlock) for r in conflicts):
                metrics_registry.increment("vote_journal_refused_rival_total")
                logger.info(
                    "Vote journal: refusing rival %s at height %s — %s already voted %s and no peer serves it yet",
                    header_hash[:18],
                    height,
                    canonical_address(address)[:18],
                    sorted(voted_hashes)[0][:18],
                )
                return True
            # #1280: the valve would open, but a peer serving a DIFFERENT block
            # at this height is positive contention evidence — delay-only
            # suppression while the sighting is fresh and under the fixed cap.
            hold = contention_hold(self._chain_id, height)
            if hold is not None:
                if hold.sealed and hold.base and getattr(settings, "vote_journal_sealed_rival_pull", False):
                    kick_pull(self.pull_hook, self._chain_id, hold.base)
                    metrics_registry.increment("vote_journal_sealed_rival_pull_total")
                metrics_registry.increment("vote_journal_contention_hold_total")
                logger.warning(
                    "Vote journal contention hold at height %s: peer serves rival %s (sealed=%s) — "
                    "refusing %s despite valve age",
                    height,
                    hold.rival_hash[:18],
                    hold.sealed,
                    header_hash[:18],
                )
                return True
            metrics_registry.increment("vote_journal_valve_opened_total")
            logger.warning(
                "Vote journal valve opened at height %s: %s voted %s over %.0fs ago and no peer serves it — "
                "allowing rival %s (recorded as equivocation evidence)",
                height,
                canonical_address(address)[:18],
                sorted(voted_hashes)[0][:18],
                unlock,
                header_hash[:18],
            )
        try:
            journal.record(height, address, header_hash, KIND_ATTEST, request_round, proposer)
        except VoteJournalError as exc:
            logger.error("Vote journal refuses attestation at height %s: %s", height, exc)
            return True
        return False

    def _now_epoch(self) -> float:
        """Wall clock for header freshness; tests override it."""
        return time.time()

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

        # #1245: a stale or far-future header is refused before it can touch
        # the lock. The age is read from the signed header, not from when the
        # request arrived, so retransmitting a captured request refreshes
        # nothing.
        header_age = self._header_age_seconds(header)
        stale_reason = self._header_freshness_refusal(header_age)
        if stale_reason is not None:
            metrics_registry.increment(f"attestation_refused_{stale_reason}_total")
            logger.info(
                "Attestation refusal: %s at height %s (header age %.1fs, bound %.0fs, future skew %.0fs)",
                stale_reason,
                height_int,
                header_age if header_age is not None else 0.0,
                float(getattr(settings, "attestation_header_max_age_seconds", 60.0)),
                float(getattr(settings, "attestation_header_future_skew_seconds", 10.0)),
            )
            return

        # #1242 round-keyed lock path: tip-height/canonical-parent check and
        # independent round derivation run before any lock evaluation, inside
        # the same await-free section as the signature — the head snapshot
        # cannot move between check and sign.
        round_lock = self._round_lock_enabled()
        request_round: int | None = None
        if round_lock:
            request_round = self._derive_request_round(header)
            try:
                declared_round = int(str(header.get("round")))
            except (TypeError, ValueError):
                declared_round = -1
            if request_round is None or declared_round != request_round:
                logger.info(
                    "Round-lock refusal: round mismatch/underivable at height %s — declared=%s derived=%s",
                    height_int,
                    header.get("round"),
                    request_round,
                )
                return
            tip_refusal = self._tip_authorizes(header, height_int, header_hash)
            if tip_refusal is not None:
                logger.info(
                    "Round-lock refusal: %s for %s at height %s",
                    tip_refusal,
                    header_hash[:18],
                    height_int,
                )
                return

        # Attestation lock: having signed one header at this height, refuse a
        # rival hash for one round window. Double-signing two blocks at h is
        # the equivocation that lets an asymmetric partition become a fork.
        window = float(getattr(settings, "consensus_proposer_round_seconds", 60))
        if not round_lock and getattr(settings, "attestation_lock_enabled", True):
            existing = self.attestation_lock(height_int, window)
            if existing is not None and existing[0] != header_hash:
                logger.info(
                    "Attestation lock: refusing to sign rival %s at height %s — already attested %s",
                    header_hash[:18],
                    height_int,
                    existing[0][:18],
                )
                return
            # #1245: this exact (height, hash) was signed before and its lock
            # has lapsed -- signing again would re-arm the lock for another
            # window, so a replayer could keep an attester locked out of a
            # height indefinitely. Refuse; a duplicate inside the window
            # (existing is not None) falls through as an idempotent re-publish.
            if existing is None and header_hash in self._signed_once.get(height_int, ()):
                metrics_registry.increment("attestation_refused_resign_after_expiry_total")
                logger.info(
                    "Attestation refusal: %s at height %s already signed and its lock has lapsed",
                    header_hash[:18],
                    height_int,
                )
                return

        # Only sign for blocks produced by a known validator in our set.
        validator_set = self._load_validator_set()
        if validator_set and canonical_address(proposer) not in {canonical_address(v) for v in validator_set}:
            return

        # The claimed proposer must be the scheduled one for (height, round):
        # a forged request used to get a signature and a lock anyway (#1058).
        if getattr(settings, "consensus_enforce_proposer_schedule", True):
            expected = self._scheduled_proposer(height_int, header)
            if expected and canonical_address(expected) != canonical_address(proposer):
                logger.info(
                    "Attestation refusal: %s is not the scheduled proposer at height %s (%s is)",
                    proposer[:18],
                    height_int,
                    expected[:18],
                )
                return

        # The schedule check proves the claimed name, not authorship: a
        # forged request naming the scheduled proposer passed it anyway
        # (#1058). The request must carry the proposer's block signature.
        # A present-but-invalid signature is always refused; an absent one
        # only once consensus_require_signed_attest_request is armed — old
        # peers send unsigned requests until their code lands, so unsigned
        # stays attestable (and counted) during the rollout.
        proposer_signature = request.get("proposer_signature")
        if proposer_signature:
            try:
                sig_ok = verify_block_signature(header, proposer_signature, proposer)
            except Exception:
                sig_ok = False
            if not sig_ok:
                logger.info(
                    "Attestation refusal: bad proposer_signature at height %s from %s",
                    height_int,
                    proposer[:18],
                )
                return
        elif getattr(settings, "consensus_require_signed_attest_request", False):
            logger.info("Attestation refusal: unsigned attest_request at height %s", height_int)
            return
        else:
            count_v9_would_reject("attest_unsigned_request")

        if round_lock and request_round is not None:
            # The request is authentic (proposer signature verified): record
            # it as U2 round-advance evidence, then apply the shared U1/U2
            # transition verdict. Recording before the verdict lets the
            # current later-round request itself serve as the "subsequent
            # request" the AD's U2 rule requires.
            self._record_request_seen(height_int, request_round)
            verdict = self.round_lock_verdict(height_int, request_round, header_hash)
            if not verdict.permitted:
                logger.info(
                    "Round-lock refusal: %s for %s at height %s round %s (locked %s by %s)",
                    verdict.reason,
                    header_hash[:18],
                    height_int,
                    request_round,
                    verdict.block_hash[:18],
                    verdict.proposer[:18],
                )
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

        if round_lock and request_round is not None:
            # Durable anti-equivocation record BEFORE any signature is
            # released (#1242 / AD Amendment D): a crash after this point can
            # never forget that (height, round) is bound to header_hash. A
            # persistence failure propagates — no signature goes out
            # unrecorded.
            self._record_round_lock(height_int, request_round, header_hash, proposer)

        # #1198/#1263 advisory: attestation equivocation is recorded inside the
        # signing loop below, AFTER a signature actually exists — evidence
        # without a signature is unverifiable and cannot satisfy the
        # validator_deactivation_evidence_required gate. Recording per actual
        # signer (not per configured key) also stops certifying equivocations
        # for keys that never signed the prior hash.

        for address, private_key in self._validator_keys.items():
            # Do not sign our own block.
            if _same_address(address, proposer):
                continue
            # Only sign with keys that are part of the configured validator set.
            if validator_set and canonical_address(address) not in {canonical_address(v) for v in validator_set}:
                continue

            # #1268: durable one-vote-per-height gate. Records the vote before
            # the signature exists; flag-guarded, off = nothing above changes.
            if vote_journal_enabled() and await self._journal_refuses(
                height_int, header_hash, address, proposer, request_round
            ):
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
            if round_lock and request_round is not None:
                # Amendment A: the round is inside the signed payload, not
                # transport metadata — changing it invalidates the signature.
                message["round"] = request_round
            try:
                signature = sign_consensus_message(message, private_key)
            except Exception as e:
                logger.warning("Failed to sign attestation: %s", e)
                continue
            # #1263: retain the signed attestation (durably) so a rival-hash
            # signing at this height can cite BOTH signatures as equivocation
            # evidence, then record the equivocation for this signer.
            self._record_signed_attestation(height_int, header_hash, address, message, request_round, round_lock, signature)
            self._record_attestation_equivocation_evidence(height_int, header_hash, address, proposer, request_round)
            if not round_lock:
                self._record_attestation_lock(height_int, header_hash, proposer)

            response = {
                "chain_id": self._chain_id,
                "height": message["height"],
                "hash": message["hash"],
                "validator": address,
                "signature": signature,
            }
            if round_lock and request_round is not None:
                response["round"] = request_round
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
                "Attestation response published: height=%s validator=%s proposer=%s header_age_ms=%s request_age_ms=%s",
                message["height"],
                address,
                proposer,
                int(header_age * 1000) if header_age is not None else "unknown",
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
                return self._v9_check_transactions(header, txs, _attempt + 1)
            logger.warning("v9 attestation tx check failed to run for height %s: %s", height, e)
            return "check_error"
        return None

    def _header_age_seconds(self, header: dict[str, Any]) -> float | None:
        """Seconds between this node's clock and the header's signed
        timestamp (negative = header is in the future). None when the header
        carries no parseable timestamp -- headers predate v9 without one."""
        raw = header.get("timestamp")
        if raw is None or raw == "":
            return None
        try:
            ts = raw if isinstance(raw, datetime) else datetime.fromisoformat(str(raw))
        except (TypeError, ValueError):
            return None
        if ts.tzinfo is None:
            # Block timestamps are stored as naive UTC.
            ts = ts.replace(tzinfo=UTC)
        return self._now_epoch() - ts.timestamp()

    def _header_freshness_refusal(self, header_age: float | None) -> str | None:
        """Refusal reason for a stale or future header, else None.

        A header with no timestamp skips the bound (counted): the v9 hash
        recompute in `_v9_check_transactions` binds the timestamp, so once v9
        is active a request cannot omit it and still pass.
        """
        max_age = float(getattr(settings, "attestation_header_max_age_seconds", 60.0))
        if max_age <= 0:
            return None
        if header_age is None:
            metrics_registry.increment("attestation_header_timestamp_missing_total")
            return None
        if header_age > max_age:
            return "stale_header"
        skew = float(getattr(settings, "attestation_header_future_skew_seconds", 10.0))
        if header_age < -skew:
            return "future_header"
        return None

    def _record_attestation_lock(self, height: int, block_hash: str, proposer: str) -> bool:
        """Record that this node's validator key(s) signed block `block_hash`
        at `height`. Locks expire by wall clock in `attestation_lock`.

        #1245: only the FIRST signing of (height, hash) starts the window.
        A duplicate returns False and leaves the lock untouched, so replaying
        a request can never extend or re-arm it."""
        if block_hash in self._signed_once.get(height, ()):
            return False
        now = time.monotonic()
        window = float(getattr(settings, "consensus_proposer_round_seconds", 60))
        self._attested = {h: e for h, e in self._attested.items() if now - e[2] < 2 * window}
        self._attested[height] = (block_hash, proposer, now)
        self._signed_once.setdefault(height, set()).add(block_hash)
        self._prune_signed_once()
        return True

    def _prune_signed_once(self) -> None:
        """Forget signings for heights below the local tip; hard-cap the rest.

        Pruned by height, never by wall clock: a replay must not be able to
        outwait a timer. A height below our own tip is settled, so a rival
        there no longer matters. The tip is the one the v9 check last read --
        no extra database access on the attestation path. The cap bounds
        memory when no tip has been read (shadow mode, no session factory)."""
        tip_height = self._tip_height_hint
        if tip_height is not None:
            self._signed_once = {h: s for h, s in self._signed_once.items() if h >= tip_height}
        if len(self._signed_once) > SIGNED_ONCE_MAX_HEIGHTS:
            keep = sorted(self._signed_once)[-SIGNED_ONCE_MAX_HEIGHTS:]
            self._signed_once = {h: self._signed_once[h] for h in keep}

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

    # ─── #1263: signature-bearing attestation records ─────────────

    @staticmethod
    def _signed_attestation_key(height: int, block_hash: str, signer: str) -> str:
        return f"{height}:{block_hash}:{canonical_address(signer)}"

    def _ensure_signed_attestations_loaded(self) -> None:
        if self._signed_attestations_loaded:
            return
        self._signed_attestations_loaded = True
        self._load_signed_attestations()

    def _load_signed_attestations(self) -> None:
        """Restore persisted signed-attestation records (#1263).

        Same contract as ``_load_round_locks``: wrong-chain files are
        ignored, malformed records are skipped, and a read failure leaves the
        in-memory index empty (equivocation evidence degrades to hash-only,
        never to a wrong signature).
        """
        try:
            if not self._signed_attestations_path.exists():
                return
            data = json.loads(self._signed_attestations_path.read_text())
            if data.get("chain_id") != self._chain_id:
                return
            for rec in data.get("records", []):
                key = rec.get("key")
                if isinstance(key, str) and isinstance(rec.get("record"), dict):
                    self._signed_attestations[key] = rec["record"]
        except Exception as e:
            logger.warning("Failed to load signed attestations for %s: %s", self._chain_id, e)

    def _persist_signed_attestations(self) -> None:
        """Atomically persist signed-attestation records (#1263).

        Temp-file + fsync + rename, same durability contract as
        ``_persist_round_locks``. Records are pruned by height — only the
        most recent ``SIGNED_ONCE_MAX_HEIGHTS`` heights are kept, which
        comfortably covers the window in which a rival hash at the same
        height can still be signed.
        """
        import os

        self._signed_attestations_path.parent.mkdir(parents=True, exist_ok=True)
        heights = []
        valid_keys = []
        for key in self._signed_attestations:
            try:
                heights.append(int(key.split(":", 1)[0]))
                valid_keys.append(key)
            except (ValueError, IndexError):
                continue
        cutoff = (max(heights) - SIGNED_ONCE_MAX_HEIGHTS) if heights else 0
        records = [
            {"key": key, "record": rec}
            for key, rec in ((k, self._signed_attestations[k]) for k in valid_keys)
            if int(key.split(":", 1)[0]) >= cutoff
        ]
        payload = json.dumps({"version": 1, "chain_id": self._chain_id, "records": records})
        tmp = self._signed_attestations_path.with_name(self._signed_attestations_path.name + ".tmp")
        with open(tmp, "w") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        tmp.replace(self._signed_attestations_path)

    def _record_signed_attestation(
        self,
        height: int,
        block_hash: str,
        signer: str,
        message: dict[str, Any],
        request_round: int | None,
        round_lock: bool,
        signature: str,
    ) -> None:
        """Durably retain a just-produced attestation signature (#1263).

        The record holds every field the signed preimage covers plus
        ``round_in_payload``/``request_round`` so on-chain verification can
        rebuild the message byte-identically under either round-lock flag
        state. A persistence failure is logged but does not block the
        attestation — the signature itself is already released; the evidence
        index is best-effort enrichment, not a consensus gate.
        """
        self._ensure_signed_attestations_loaded()
        record = {
            "chain_id": message.get("chain_id", self._chain_id),
            "height": message.get("height", height),
            "hash": message.get("hash", block_hash),
            "parent_hash": message.get("parent_hash", ""),
            "proposer": message.get("proposer", ""),
            "state_root": message.get("state_root", ""),
            "bridge_state_root": message.get("bridge_state_root", ""),
            "round_in_payload": bool(round_lock and request_round is not None),
            "request_round": request_round if round_lock else None,
            "signature": signature,
            "signer": canonical_address(signer),
        }
        key = self._signed_attestation_key(height, block_hash, signer)
        self._signed_attestations[key] = record
        try:
            self._persist_signed_attestations()
        except Exception as e:
            logger.warning("Failed to persist signed attestation for %s: %s", self._chain_id, e)

    def _equivocation_recorder(self):
        """The slashing recorder for this chain (#1198 routing, #1263 reuse)."""
        from .slashing import slashing_manager

        if getattr(settings, "multi_validator_consensus_enabled", False):
            try:
                from .multi_validator_poa import get_consensus

                return get_consensus(self._chain_id)
            except Exception:
                pass
        return slashing_manager

    def _record_attestation_equivocation_evidence(
        self,
        height: int,
        block_hash: str,
        signer: str,
        proposer: str,
        request_round: int | None,
    ) -> None:
        """Record attestation equivocation for the signer that just signed.

        #1263: pairs the new signature with each prior signed hash at this
        height FOR THIS SIGNER — per-signer precision replaces the old
        record-every-configured-key behavior. Pairs with a retained prior
        signature carry both attestations (gate-verifiable); pairs whose
        prior signature is unknown (pre-capture signing or lost index) fall
        back to the hash-only advisory record.
        """
        canon = canonical_address(signer)
        prior_hashes = set(self._signed_once.get(height, ()))
        prior_hashes |= {entry.block_hash for (h, _r), entry in self._round_locks.items() if h == height}
        if vote_journal_enabled():
            # #1268: the journal survives restarts and the valve, so a rival
            # signed after either is still certified against the prior vote.
            prior_hashes |= {r.block_hash for r in get_vote_journal(self._chain_id).votes_at(height, signer)}
        prior_hashes.discard(block_hash)
        if not prior_hashes:
            return
        current_key = self._signed_attestation_key(height, block_hash, signer)
        current = self._signed_attestations.get(current_key)
        if current is None:
            return
        recorder = self._equivocation_recorder()
        for prior_hash in sorted(prior_hashes):
            prior = self._signed_attestations.get(self._signed_attestation_key(height, prior_hash, signer))
            attestations = [prior, current] if prior is not None else None
            try:
                recorder.record_attestation_equivocation(
                    validator_address=canon,
                    height=height,
                    round_number=request_round,
                    block_hash_a=prior_hash,
                    block_hash_b=block_hash,
                    proposer=proposer,
                    attestations=attestations,
                )
            except AttributeError:
                # Fallback recorder (module-global SlashingManager pre-#1263
                # signature) — hash-only record, same as before.
                recorder.record_attestation_equivocation(
                    validator_address=canon,
                    height=height,
                    round_number=request_round,
                    block_hash_a=prior_hash,
                    block_hash_b=block_hash,
                    proposer=proposer,
                )
            except Exception as e:
                logger.warning("Failed to record attestation equivocation for %s: %s", canon, e)

    def record_proposal_equivocation(self, message: dict[str, Any], signature: str, round_number: int | None) -> None:
        """Retain the proposer's header signature and record same-height equivocation (#1278).

        The proposer signs its block header (``block.signature``) but is never
        its own attester, so a proposal sealed after the journal valve (or the
        legacy lock lapse) used to leave NO evidence on the node that sealed
        the rival. This retains the proposal signature in the same durable
        index as attestation signatures (``attestation_signed.json``) and runs
        the attester path's pairing against every prior vote this validator
        cast at the height — attestation locks, round locks and the vote
        journal — so the proposer-side pair is recorded exactly like the
        attester-side one. The signed message is the fixed header preimage
        (``round_in_payload`` false), which the on-chain verifier already
        reconstructs. Idempotent through the slashing dedup key.
        """
        if not signature:
            return
        height = int(message["height"])
        block_hash = str(message["hash"])
        proposer = str(message["proposer"])
        self._record_signed_attestation(height, block_hash, proposer, message, None, False, signature)
        evidence_round = round_number if self._round_lock_enabled() else None
        self._record_attestation_equivocation_evidence(height, block_hash, proposer, proposer, evidence_round)

    def _scheduled_proposer(self, height: int, header: dict) -> str | None:
        """Derive the round from parent/header timestamps and return the
        scheduled proposer for (height, round); None when it cannot be
        determined (permissive, like _is_scheduled_proposer in pbft.py)."""
        try:
            ts_raw = header.get("timestamp")
            block_ts = ts_raw if isinstance(ts_raw, datetime) else datetime.fromisoformat(str(ts_raw))
        except (TypeError, ValueError):
            return None
        parent_ts = self._parent_timestamp(str(header.get("parent_hash", "")))
        if parent_ts is None:
            return None
        try:
            from .multi_validator_poa import get_consensus, proposer_round

            window = int(float(getattr(settings, "consensus_proposer_round_seconds", 60)))
            rnd = proposer_round(parent_ts, block_ts, window)
            return get_consensus(self._chain_id).select_proposer(height, rnd)
        except Exception:
            return None

    def _parent_timestamp(self, parent_hash: str) -> datetime | None:
        """Parent block timestamp for the round derivation — the block itself
        if the DB has it, else the tip when parent_hash matches the tip."""
        if self._session_factory is None or not parent_hash:
            return None
        try:
            with self._session_factory() as session:
                row = session.exec(
                    select(Block.timestamp).where(Block.chain_id == self._chain_id).where(Block.hash == parent_hash)
                ).first()
                if row is not None:
                    return row if isinstance(row, datetime) else row[0]
                # Tip fallback is allowed ONLY when the tip IS the parent —
                # a lagging attester whose tip has moved past the parent must
                # not derive a round from the wrong block (#1058 rework).
                tip = session.exec(
                    select(Block.timestamp, Block.hash)
                    .where(Block.chain_id == self._chain_id)
                    .order_by(text("height DESC"))
                    .limit(1)
                ).first()
                if tip is not None:
                    tip_ts = tip[0] if not isinstance(tip, datetime) else tip
                    tip_hash = tip[1] if not isinstance(tip, datetime) else None
                    if tip_hash == parent_hash:
                        return tip_ts
        except Exception:
            return None
        return None

    def _load_validator_set(self) -> set[str]:
        validator_set_str = getattr(settings, "validator_set", "")
        if not validator_set_str:
            return set()
        try:
            data = json.loads(validator_set_str)
            return {v.get("address", "") for v in data if v.get("address")}
        except Exception:
            return set()

    # ------------------------------------------------------------------
    # #1242 round-keyed attestation lock (attestation_round_lock_enabled)
    # ------------------------------------------------------------------

    def _round_lock_enabled(self) -> bool:
        return bool(getattr(settings, "attestation_round_lock_enabled", False))

    def _round_seconds(self) -> int:
        return int(float(getattr(settings, "consensus_proposer_round_seconds", 60)))

    def _derive_request_round(self, header: dict) -> int | None:
        """Independently derive the proposer round for an attest_request header.

        Mirrors the proposer-side derivation exactly: ``proposer_round`` over
        (sealed parent timestamp, proposed block timestamp, round window).
        Returns None when either timestamp or the parent row is unavailable —
        callers must treat that as underivable, never as round 0.
        """
        try:
            ts_raw = header.get("timestamp")
            block_ts = ts_raw if isinstance(ts_raw, datetime) else datetime.fromisoformat(str(ts_raw))
        except (TypeError, ValueError):
            return None
        parent_ts = self._parent_timestamp(str(header.get("parent_hash", "")))
        if parent_ts is None:
            return None
        try:
            from .multi_validator_poa import proposer_round

            return proposer_round(parent_ts, block_ts, self._round_seconds())
        except Exception:
            return None

    def _collect_round_for_block(self, block: Any) -> int | None:
        """Round for the block this node is about to attest-collect.

        Same derivation attesters apply to the request header, so the
        declared round always matches their independent check.
        """
        parent_ts = self._parent_timestamp(str(getattr(block, "parent_hash", "") or ""))
        ts = getattr(block, "timestamp", None)
        if ts is None or parent_ts is None:
            return None
        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts)
            except ValueError:
                return None
        try:
            from .multi_validator_poa import proposer_round

            return proposer_round(parent_ts, ts, self._round_seconds())
        except Exception:
            return None

    def _unlock_window(self) -> float:
        """U2 protocol-evidence window: the applicable consensus_gates span.

        Defaults to the attestation-collection timeout + 1s margin, plus the
        PBFT view-change timeout when PBFT is armed. An explicit
        ``attestation_round_unlock_window_seconds`` wins.
        """
        override = float(getattr(settings, "attestation_round_unlock_window_seconds", 0.0) or 0.0)
        if override > 0:
            return override
        window = float(getattr(settings, "multi_validator_attestation_timeout_seconds", 15.0) or 15.0)
        if getattr(settings, "pbft_consensus_enabled", False):
            window += float(getattr(settings, "pbft_view_change_timeout", 30) or 0.0)
        return window + 1.0

    def _local_head(self) -> tuple[int, str] | None:
        """(height, hash) of the sealed tip, or None."""
        if self._session_factory is None:
            return None
        try:
            with self._session_factory() as session:
                row = session.exec(
                    select(Block.height, Block.hash)
                    .where(Block.chain_id == self._chain_id)
                    .order_by(text("height DESC"))
                    .limit(1)
                ).first()
                if row is None:
                    return None
                return int(row[0]), str(row[1])
        except Exception:
            return None

    def _canonical_hash_at(self, height: int) -> str | None:
        """The canonical block hash at ``height``, or None when unknown."""
        if self._session_factory is None:
            return None
        try:
            with self._session_factory() as session:
                row = session.exec(
                    select(Block.hash).where(Block.chain_id == self._chain_id).where(Block.height == height)
                ).first()
                return str(row[0]) if row is not None else None
        except Exception:
            return None

    def _tip_authorizes(self, header: dict, height_int: int, header_hash: str) -> str | None:
        """Tip-height / canonical-parent authorization for an attest_request.

        Returns a refusal reason, or None when the request may proceed. An
        ordinary proposal must extend the local tip (``height == tip + 1``
        and ``parent_hash == tip hash``). Requests at or below the tip are
        attestable only when the requested hash IS the canonical block at
        that height — idempotent re-signs and proof-path attestations of
        decided history. A different hash at a decided height is the
        stale-height harvest path and is refused. This runs before signing
        and before any lock mutation, inside the same await-free section, so
        the head snapshot cannot move between check and signature.
        """
        head = self._local_head()
        if head is None:
            return "no_local_head"
        head_height, head_hash = head
        if height_int == head_height + 1:
            if str(header.get("parent_hash", "")) != head_hash:
                return "parent_mismatch"
            return None
        if height_int <= head_height:
            canonical = self._canonical_hash_at(height_int)
            if canonical is not None and canonical == header_hash:
                return None
            return "stale_height_rival" if canonical is not None else "unknown_height"
        return "future_height"

    def _record_request_seen(self, height: int, round_: int) -> None:
        """Note the first time an authentic request for (height, round) arrived.

        U2 evidence: a later-round request's existence proves earlier rounds
        at this height were minted and (once the gates window elapses) are
        irrevocably closed.
        """
        now = time.monotonic()
        rounds = self._requests_seen.setdefault(height, {})
        if round_ not in rounds or now < rounds[round_]:
            rounds[round_] = now
        if len(self._requests_seen) > 32:
            keep_above = max(self._requests_seen) - 16
            self._requests_seen = {h: r for h, r in self._requests_seen.items() if h >= keep_above}

    def _u2_satisfied(
        self,
        height: int,
        locked_round: int,
        entry: _RoundLockEntry,
        round_: int,
        now: float,
        window: float,
        unlock_window: float,
    ) -> bool:
        """U2 failure evidence for a locked round (AD ruling: full gates window).

        Two routes, either sufficient:
          fallback — the monotonic lock window elapsed (liveness recovery;
            never overrides U1 or the tip check);
          protocol — an attest_request at a strictly later round (up to the
            round being signed) was observed at this height AND the locked
            round's full gates window has elapsed since its request was seen
            (its collection is closed and cannot be counted again).
        """
        if now - entry.signed_at >= window:
            return True
        if entry.request_seen_at is None:
            return False
        rounds = self._requests_seen.get(height) or {}
        if not any(locked_round < r <= round_ for r in rounds):
            return False
        return (now - entry.request_seen_at) >= unlock_window

    def round_lock_verdict(self, height: int, round_: int, block_hash: str) -> _RoundLockVerdict:
        """Shared U1/U2 transition check for attester signing and proposer suppression.

        Signing (or proposing) ``block_hash`` at ``(height, round_)`` is
        permitted iff every locked entry at ``height`` binding a DIFFERENT
        hash has satisfied unlock evidence:

          U1 — ``round_`` is strictly later than the locked round; and
          U2 — the locked round's failure is evidenced (see ``_u2_satisfied``).

        Both enforcement points call this single function so attester and
        proposer can never disagree about whether a lock transition is legal.
        """
        self._ensure_round_locks_loaded()
        now = time.monotonic()
        window = float(getattr(settings, "consensus_proposer_round_seconds", 60))
        unlock_window = self._unlock_window()
        for (lh, lr), entry in self._round_locks.items():
            if lh != height or entry.block_hash == block_hash:
                continue
            if round_ <= lr:
                return _RoundLockVerdict(
                    False,
                    f"round_not_advanced:locked_r{lr}_req_r{round_}",
                    entry.block_hash,
                    entry.proposer,
                )
            if not self._u2_satisfied(height, lr, entry, round_, now, window, unlock_window):
                return _RoundLockVerdict(False, "round_failure_unproven", entry.block_hash, entry.proposer)
        return _RoundLockVerdict(True, None)

    def _ensure_round_locks_loaded(self) -> None:
        if self._round_locks_loaded:
            return
        self._round_locks_loaded = True
        self._load_round_locks()

    def _load_round_locks(self) -> None:
        """Restore persisted signed (height, round, hash) records (#1242/D).

        Wall-clock timestamps are converted into monotonic-equivalent ages at
        load so the same U1/U2 math applies after restart. Records older than
        two lock windows are dropped — they can no longer bind anything.
        """
        try:
            if not self._round_locks_path.exists():
                return
            data = json.loads(self._round_locks_path.read_text())
            if data.get("chain_id") != self._chain_id:
                return
            now_mono = time.monotonic()
            now_wall = time.time()
            window = float(getattr(settings, "consensus_proposer_round_seconds", 60))
            for rec in data.get("records", []):
                try:
                    h, r = int(rec["h"]), int(rec["r"])
                    signed_wall = float(rec["signed_wall"])
                    age_wall = now_wall - signed_wall
                    if age_wall >= 2 * window:
                        continue
                    req_wall = rec.get("request_seen_wall")
                    self._round_locks[(h, r)] = _RoundLockEntry(
                        str(rec["hash"]),
                        str(rec.get("proposer", "")),
                        now_mono - age_wall,
                        signed_wall,
                        (now_mono - (now_wall - float(req_wall))) if req_wall is not None else None,
                        float(req_wall) if req_wall is not None else None,
                    )
                except (KeyError, TypeError, ValueError):
                    continue
        except Exception as e:
            logger.warning("Failed to load round-lock records for %s: %s", self._chain_id, e)

    def _persist_round_locks(self) -> None:
        """Atomically persist signed (height, round, hash) records.

        Temp-file + fsync + rename so a crash cannot leave a torn record.
        Raises on failure — the caller must not release a signature it could
        not durably record.
        """
        import os

        self._round_locks_path.parent.mkdir(parents=True, exist_ok=True)
        now_wall = time.time()
        window = float(getattr(settings, "consensus_proposer_round_seconds", 60))
        records = []
        for (h, r), e in self._round_locks.items():
            if now_wall - e.signed_wall >= 2 * window:
                continue
            records.append(
                {
                    "h": h,
                    "r": r,
                    "hash": e.block_hash,
                    "proposer": e.proposer,
                    "signed_wall": e.signed_wall,
                    "request_seen_wall": e.request_seen_wall,
                }
            )
        payload = json.dumps({"version": 1, "chain_id": self._chain_id, "records": records})
        tmp = self._round_locks_path.with_name(self._round_locks_path.name + ".tmp")
        with open(tmp, "w") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        tmp.replace(self._round_locks_path)
        try:
            dir_fd = os.open(str(self._round_locks_path.parent), os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            pass

    def _record_round_lock(self, height: int, round_: int, block_hash: str, proposer: str) -> None:
        """Record + durably persist that this node signed ``block_hash`` at
        ``(height, round_)``. Called BEFORE the signature is released; a
        persistence failure propagates so no signature goes out unrecorded."""
        self._ensure_round_locks_loaded()
        now_mono = time.monotonic()
        now_wall = time.time()
        window = float(getattr(settings, "consensus_proposer_round_seconds", 60))
        self._round_locks = {k: e for k, e in self._round_locks.items() if now_mono - e.signed_at < 2 * window}
        key = (height, round_)
        if key not in self._round_locks:
            req_seen = self._requests_seen.get(height, {}).get(round_)
            req_seen_wall = now_wall - (now_mono - req_seen) if req_seen is not None else None
            self._round_locks[key] = _RoundLockEntry(block_hash, proposer, now_mono, now_wall, req_seen, req_seen_wall)
        self._persist_round_locks()

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
            "aux_state_root": getattr(block, "aux_state_root", None) or "",
        }
        # #1242: under the round lock the request declares its round and the
        # attestation signature covers it. The value is derived exactly the
        # way attesters derive it (sealed parent ts + block ts + window), so
        # an honest attester's independent derivation always matches.
        collect_round: int | None = None
        if self._round_lock_enabled():
            collect_round = self._collect_round_for_block(block)
            if collect_round is None:
                logger.warning(
                    "Round-lock enabled but round underivable for height %s — remote attestations will be refused",
                    block.height,
                )
            else:
                header["round"] = collect_round
        request: dict[str, Any] = {"header": header, "timestamp": time.time()}
        # Carry the proposer's own block signature: attesters verify it
        # against the scheduled proposer before signing or locking, so a
        # forged request can no longer attest an invented block (#1058).
        if getattr(block, "signature", None):
            request["proposer_signature"] = block.signature
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
                if collect_round is not None and response.get("round") != collect_round:
                    # A response minted for a different round can never count
                    # toward this round's quorum — even if the hash matches.
                    logger.info(
                        "Attestation arrival: height=%s validator=%s arrived_ms=%d outcome=wrong_round response_round=%s",
                        block.height,
                        validator,
                        arrived_ms,
                        response.get("round"),
                    )
                    continue
                signature = response.get("signature", "")
                if not validator or not signature:
                    continue
                try:
                    vcanon = canonical_address(validator)
                except (AttributeError, TypeError, ValueError):
                    vcanon = ""
                if vcanon and vcanon in expected_remote:
                    answered.add(vcanon)
                outcome = "invalid_signature"
                try:
                    if collect_round is not None:
                        # Round-bound verification: the signed payload includes
                        # the round, so an old-round signature cannot verify
                        # against this round's header even on a hash match.
                        att_msg = {
                            "chain_id": header.get("chain_id", self._chain_id),
                            "height": header.get("height", 0),
                            "hash": header.get("hash", ""),
                            "parent_hash": header.get("parent_hash", ""),
                            "proposer": header.get("proposer", ""),
                            "state_root": header.get("state_root", ""),
                            "bridge_state_root": header.get("bridge_state_root", ""),
                            "round": collect_round,
                        }
                        sig_ok = verify_consensus_message(att_msg, signature, validator)
                    else:
                        sig_ok = verify_block_signature(header, signature, validator)
                    if sig_ok:
                        dedup_key = vcanon or validator
                        if dedup_key in counted:
                            outcome = "duplicate"
                        else:
                            counted.add(dedup_key)
                            attestation_record: dict[str, str] = {
                                "validator": validator,
                                "signature": signature,
                            }
                            if collect_round is not None:
                                # Carried for import-side verification: the
                                # signature covers this round, so verifiers
                                # rebuild the same round-bound payload.
                                attestation_record["round"] = str(collect_round)
                            attestations.append(attestation_record)
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
