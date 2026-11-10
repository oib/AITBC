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

from ..config import legacy_attestation_dual_accept_open, settings
from ..gossip import gossip_broker
from ..metrics import metrics_registry


def _attestation_domain_active(height: int | None) -> bool:
    """#1298: attestation signatures are domain-separated at/above the armed
    activation height; below it the legacy shared preimage stays authoritative."""
    activation = getattr(settings, "consensus_domain_separation_height", None)
    return activation is not None and height is not None and height >= activation


def _active_signature_domain(height: int | None, domain: str) -> str | None:
    """#1298: the domain tag for a signature minted at ``height`` — ``domain``
    at/above the armed activation height, else None (legacy shared preimage).

    The return value is stamped on evidence records as ``signature_domain``
    so on-chain verification rebuilds the exact preimage the signer used.
    """
    activation = getattr(settings, "consensus_domain_separation_height", None)
    if activation is None or height is None or height < activation:
        return None
    return domain


def _attestation_signature_domain(height: int | None) -> str | None:
    """#1298: the ``signature_domain`` an attestation signing at ``height`` is
    minted under — ``DOMAIN_BLOCK_ATTESTATION`` at/above the armed activation
    height, else None (legacy shared preimage). Used to key the in-memory and
    durable acceptance/dedup state so a proposal-domain and an
    attestation-domain signing of the same (height, hash) never collide."""
    if not _attestation_domain_active(height):
        return None
    from aitbc.crypto.consensus_signing import DOMAIN_BLOCK_ATTESTATION

    return DOMAIN_BLOCK_ATTESTATION


def _sign_attestation(message: dict[str, Any], private_key: str, height: int | None) -> str:
    if _attestation_domain_active(height):
        from aitbc.crypto.consensus_signing import DOMAIN_BLOCK_ATTESTATION, sign_consensus_message_domain

        return sign_consensus_message_domain(message, private_key, DOMAIN_BLOCK_ATTESTATION)
    return sign_consensus_message(message, private_key)


def _verify_attestation(message: dict[str, Any], signature: str, validator: str, height: int | None) -> bool:
    if _attestation_domain_active(height):
        from aitbc.crypto.consensus_signing import DOMAIN_BLOCK_ATTESTATION, verify_consensus_message_domain

        if verify_consensus_message_domain(message, signature, validator, DOMAIN_BLOCK_ATTESTATION):
            return True
        # #1298 dual-accept window [H, S): inside it a legacy shared-preimage
        # attestation signature still counts while the fleet converges; at
        # heights >= S (or with the window unset) it is rejected outright.
        # The accepted legacy signature is counted for the migration metric.
        if legacy_attestation_dual_accept_open(height) and verify_consensus_message(message, signature, validator):
            metrics_registry.increment("consensus_legacy_attestation_accepted_total")
            return True
        return False
    return verify_consensus_message(message, signature, validator)


def _attestation_message(header: dict[str, Any], chain_id: str, round_: int | None = None) -> dict[str, Any]:
    """The exact dict an attestation signature covers (round included only
    under round-lock) — shared by the domain and legacy verify paths."""
    message = {
        "chain_id": header.get("chain_id", chain_id),
        "height": header.get("height", 0),
        "hash": header.get("hash", ""),
        "parent_hash": header.get("parent_hash", ""),
        "proposer": header.get("proposer", ""),
        "state_root": header.get("state_root", ""),
        "bridge_state_root": header.get("bridge_state_root", ""),
    }
    if round_ is not None:
        message["round"] = round_
    return message


from ..models import Block
from ..state.v9_policy import V9_UNSIGNED_ALLOWED_TX_TYPES, count_v9_would_reject
from . import abandon, unavail
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
# #1278: deferred (off-loop) persistence of proposer-side equivocation evidence.
DEFERRED_SAVE_ATTEMPTS = 8
DEFERRED_SAVE_RETRY_DELAY = 1.0
DEFERRED_SAVE_RETRY_MAX_DELAY = 30.0
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


def _lock_lapse_seconds() -> float:
    """#1298 (design v2.2 O1 / v2.6): the effective attestation-lock lapse —
    proposer round window + header max-age + future skew (130s at defaults).
    An honest re-attestation after this window is guaranteed to land in a
    new derived round. The durable lock journal prunes at 2x this — the
    round-lock journal's "two windows" rule applied to the CORRECT window
    (v2.6 defect 1: pruning at 2x the 60s round would drop a record 10s
    before its 130s lock lapsed) — so a record is never dropped while its
    lock could still bind."""
    return (
        float(getattr(settings, "consensus_proposer_round_seconds", 60))
        + float(getattr(settings, "attestation_header_max_age_seconds", 60.0))
        + float(getattr(settings, "attestation_header_future_skew_seconds", 10.0))
    )


def attestation_lock_window_seconds(height: int | None) -> float:
    """#1298 T15 (design v2.2 proposer coupling, v2.6 single derived
    constant): the binding attestation-lock lapse window for signings at
    ``height``. Attester lock call sites AND the proposer suppression in
    ``_honor_attestation_lock`` both consume this one function so the two
    windows cannot drift.

    At/above the armed ``consensus_domain_separation_height`` the window is
    ``_lock_lapse_seconds()`` (round + header max-age + future skew = 130s
    at defaults): an honest re-attestation after it provably lands in a
    new derived round, so same-round multi-hash stays equivocation, period.
    Below the armed height the legacy ``consensus_proposer_round_seconds``
    window stays byte-identical — the 60→130s resize bundles into
    activation (design rollout), so pre-activation behaviour is
    replay-unchanged. The durable journal keeps pruning at 2x the lapse
    unconditionally: a longer keep is conservative, never a coverage hole.
    """
    if _attestation_domain_active(height):
        return _lock_lapse_seconds()
    return float(getattr(settings, "consensus_proposer_round_seconds", 60))


class _RoundLockEntry:
    """One signed (height, round) -> block_hash record (#1242).

    ``signed_at``/``request_seen_at`` are monotonic for live entries; records
    restored from disk carry wall-clock-derived equivalents so the same U1/U2
    math applies after a restart.
    """

    __slots__ = (
        "block_hash",
        "proposer",
        "signed_at",
        "signed_wall",
        "request_seen_at",
        "request_seen_wall",
        "signature_domain",
    )

    def __init__(
        self,
        block_hash: str,
        proposer: str,
        signed_at: float,
        signed_wall: float,
        request_seen_at: float | None,
        request_seen_wall: float | None,
        signature_domain: str | None = None,
    ) -> None:
        self.block_hash = block_hash
        self.proposer = proposer
        self.signed_at = signed_at
        self.signed_wall = signed_wall
        self.request_seen_at = request_seen_at
        self.request_seen_wall = request_seen_wall
        # #1298: the domain preimage this signing was minted under (None =
        # legacy shared preimage). Part of the acceptance key so records of
        # different domains at the same (height, round) never merge.
        self.signature_domain = signature_domain


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
        self._unavail_task: asyncio.Task[None] | None = None
        self._abandon_task: asyncio.Task[None] | None = None
        self._response_index_task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        # #1281: unlock justification produced by the armed evidence valve
        # for the (height, hash) currently being signed — consumed by the
        # equivocation recorder and the gossip response. Entries are
        # per-request and bounded by pruning below the tip.
        self._vote_justifications: dict[tuple[int, str], dict[str, Any]] = {}
        # Attester locks: height -> signature_domain -> (block_hash, proposer,
        # signed_at). A validator that signs block X at height h must not
        # propose — or re-attest — a different block at h for one proposer
        # round. Without this a validator can attest a block it never
        # receives and then build a rival at the same height — the
        # asymmetric-partition fork mechanism seen live 2026-09-27.
        # #1298: the domain component is part of the acceptance key — a
        # proposal-domain and an attestation-domain signing of the same
        # (height, hash) coexist instead of overwriting each other. Below
        # ``consensus_domain_separation_height`` every entry sits under the
        # None (legacy) domain, so behavior is byte-identical.
        self._attested: dict[int, dict[str | None, tuple[str, str, float]]] = {}
        # #1242 round-keyed lock state — used only when
        # ``attestation_round_lock_enabled`` is set; the legacy ``_attested``
        # path above is untouched when it is not.
        #   _round_locks: (height, round, signature_domain) -> _RoundLockEntry
        #   _requests_seen: height -> {round: first_seen_mono} — U2 evidence
        # The same file also carries the always-on attestation-lock journal
        # (#1298, kind="attestation" records) written by the non-round-lock
        # path — see ``_attested_lock_records`` below.
        self._round_locks: dict[tuple[int, int, str | None], _RoundLockEntry] = {}
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
        # #1298: both this and the lock itself are reseeded from the durable
        # attestation-lock journal on load, so a restart no longer forgets
        # them (the header freshness bound still covers pre-journal gaps).
        # height -> signature_domain -> set of block hashes: the domain is
        # part of the acceptance key, so the same (height, hash) signed under
        # two domains is tracked independently (T9-class coexistence).
        self._signed_once: dict[int, dict[str | None, set[str]]] = {}
        # #1298 (design v2.5/v2.6): durable attestation-lock journal — the
        # non-round-lock path's counterpart to ``_round_locks``. Records
        # (height, hash, signature_domain) -> signing metadata {proposer,
        # signed_wall, derived_round, signature_domain}, persisted in the
        # SAME ``attestation_round_locks.json`` file so a restart re-derives
        # ``_attested``/``_signed_once`` instead of amnesia. Always-on:
        # independent of ``attestation_round_lock_enabled`` and of the
        # UC-gated vote journal. The domain sits in the key so a
        # proposal-domain and an attestation-domain record for the same
        # (height, hash) coexist (the persisted record already carries
        # ``signature_domain``; only the in-memory key gains the component).
        self._attested_lock_records: dict[tuple[int, str, str | None], dict[str, Any]] = {}
        # #1278: in-flight deferred evidence saves (strong refs so the tasks
        # are not garbage-collected before they finish).
        self._deferred_state_saves: set[asyncio.Future[Any]] = set()
        # #1263: signature-bearing attestation records for equivocation
        # evidence — "height:block_hash:signer" below the #1298 activation
        # height, "chain_id:height:signature_domain:block_hash:signer"
        # at/above it — the exact fields the signature covers plus the
        # signature itself, so a later rival-hash signing at the same height
        # can cite BOTH attestations on-chain. Persisted next to the round
        # locks so a restart cannot lose the prior signature an equivocation
        # record needs.
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
        request_cert: Any = None,
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

        #1281: with ``vote_journal_justification_enabled`` the valve's age+miss
        is only the *trigger* — release additionally requires the combined
        predicate (T_evidence unfetchability AND clean observation index AND
        a valid UnavailabilityCertificate). No time-only escape remains.
        """
        journal = get_vote_journal(self._chain_id)
        journal.prune_below(self._tip_height_hint)
        if self._vote_justifications and self._tip_height_hint is not None:
            for key in [k for k in self._vote_justifications if k[0] < self._tip_height_hint]:
                self._vote_justifications.pop(key, None)
        justification: dict[str, Any] | None = None
        conflicts = journal.conflicting(height, address, header_hash)
        if conflicts:
            refuse, justification = await self._journal_conflict_gate(height, header_hash, address, conflicts, request_cert)
            if refuse:
                return True
        try:
            journal.record(height, address, header_hash, KIND_ATTEST, request_round, proposer, justification=justification)
        except VoteJournalError as exc:
            logger.error("Vote journal refuses attestation at height %s: %s", height, exc)
            return True
        if justification is not None:
            self._vote_justifications[(height, header_hash)] = justification
        return False

    async def _journal_conflict_gate(
        self,
        height: int,
        header_hash: str,
        address: str,
        conflicts: list[Any],
        request_cert: Any,
    ) -> tuple[bool, dict[str, Any] | None]:
        """#1268/#1280/#1281 rival-vote gate. ``(True, None)`` = refuse;
        ``(False, justification)`` = valve released (justification may be
        None in dormant Phase-1 mode)."""
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
            return True, None
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
            return True, None
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
                "Vote journal contention hold at height %s: peer serves rival %s (sealed=%s) — refusing %s despite valve age",
                height,
                hold.rival_hash[:18],
                hold.sealed,
                header_hash[:18],
            )
            return True, None
        justification: dict[str, Any] | None = None
        if unavail.justification_enabled():
            # #1281 armed barrier: age+miss only triggers collection —
            # release needs the verifiable justification bundle.
            # #1306: this await runs inside the serial attest-request
            # listener — leg-1 unfetchable_persists can park it for the
            # full evidence window. Time it so the stall is measurable.
            just_start = time.monotonic()
            justification = await unavail.unlock_justification(
                self._chain_id,
                height,
                voted_hashes,
                ignore=self._own_addresses(),
                request_cert=request_cert,
                broker=gossip_broker,
                # #1281 respin: this runs inside the attest-request listener —
                # never await an in-flight UC collection here; a carried or
                # cached cert still releases, otherwise the probe finishes in
                # the background and the next evaluation picks it up.
                wait_for_probe=False,
            )
            just_elapsed = time.monotonic() - just_start
            metrics_registry.observe("attest_unlock_justification_seconds", just_elapsed)
            stall_after = float(getattr(settings, "attest_listener_stall_seconds", 5.0))
            if just_elapsed >= stall_after:
                metrics_registry.increment("attest_listener_unlock_stall_total")
                logger.warning(
                    "Attest listener stalled %.1fs inside unlock_justification at height %s",
                    just_elapsed,
                    height,
                )
            if justification is None:
                metrics_registry.increment("vote_journal_refused_rival_total")
                logger.warning(
                    "Vote journal barrier holds rival %s at height %s — valve expired but no verifiable unlock justification",
                    header_hash[:18],
                    height,
                )
                return True, None
        metrics_registry.increment("vote_journal_valve_opened_total")
        logger.warning(
            "Vote journal valve opened at height %s: %s voted %s over %.0fs ago and no peer serves it — "
            "allowing rival %s (recorded as equivocation evidence)%s",
            height,
            canonical_address(address)[:18],
            sorted(voted_hashes)[0][:18],
            unlock,
            header_hash[:18],
            " [justified: unavailability_cert]" if justification is not None else "",
        )
        return False, justification

    def _own_addresses(self) -> set[str]:
        """Canonical addresses of every validator key this node holds."""
        return {canonical_address(a) for a in self._validator_keys}

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
        if abandon.abandon_enabled():
            self._abandon_task = create_task_with_logging(self._listen_abandon(), name=f"abandon_listener_{self._chain_id}")
        if unavail.justification_enabled():
            # #1281: the unavailability-query listener and the persistent
            # attest_response observer that feeds the GossipObservationIndex.
            # Both are dormant without the flag — no extra subscriptions.
            self._unavail_task = create_task_with_logging(
                self._listen_unavail(),
                name=f"unavail_listener_{self._chain_id}",
            )
            self._response_index_task = create_task_with_logging(
                self._listen_responses_for_index(),
                name=f"attest_response_index_{self._chain_id}",
            )

    async def stop(self) -> None:
        self._stop_event.set()
        for task in (self._listener_task, self._unavail_task, self._response_index_task, self._abandon_task):
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._listener_task = None
        self._unavail_task = None
        self._response_index_task = None
        self._abandon_task = None

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

    async def _listen_abandon(self) -> None:
        """#1301 L2: release journal votes for hashes their proposer abandoned."""
        topic = abandon.abandon_topic(self._chain_id)
        try:
            sub = await gossip_broker.subscribe(topic, max_queue_size=256)
        except Exception as e:
            logger.warning("Failed to subscribe to abandon statements: %s", e)
            return
        try:
            async for payload in sub:
                if self._stop_event.is_set():
                    break
                try:
                    self.handle_abandon(payload)
                except Exception as e:
                    logger.warning("Error handling abandon statement: %s", e)
        finally:
            sub.close()  # noqa: unawaited-async — TopicSubscription.close() is synchronous

    def handle_abandon(self, payload: Any) -> int:
        """Apply one abandon statement; returns how many local votes it released."""
        stmt = abandon.verify_abandon(self._chain_id, payload)
        if stmt is None:
            metrics_registry.increment("vote_journal_abandon_rejected_total")
            return 0
        height, block_hash, proposer = stmt["height"], stmt["hash"], stmt["proposer"]
        if self._tip_height_hint is not None and height <= self._tip_height_hint:
            return 0  # decided locally; the journal prunes it anyway
        journal = get_vote_journal(self._chain_id)
        released = 0
        for addr in self._own_addresses():
            if journal.release_abandoned(height, addr, block_hash, proposer):
                released += 1
        # The legacy height lock and the round locks refuse rivals independently
        # of the journal (d9: voters released the journal yet kept refusing).
        # Release only entries for this exact hash from this exact proposer.
        locks = self._release_abandoned_locks(height, block_hash, proposer)
        if released or locks:
            metrics_registry.increment("vote_journal_abandon_released_total", released)
            logger.warning(
                "Vote journal: released %d vote(s) at height %s — proposer %s abandoned %s",
                released,
                height,
                proposer[:18],
                block_hash[:18],
            )
        return released + locks

    def _release_abandoned_locks(self, height: int, block_hash: str, proposer: str) -> int:
        """Drop the legacy ``_attested`` entry and round locks for exactly
        ``(height, block_hash)`` signed against ``proposer``; evidence records
        (``_signed_attestations``) are kept."""
        released = 0
        canon = canonical_address(proposer)
        entries = self._attested.get(height)
        if entries:
            # #1298: the lock is domain-keyed — release matching entries
            # under EVERY domain (an abandon releases the vote, not one
            # domain's view of it).
            for dom in [d for d, e in entries.items() if e[0] == block_hash and canonical_address(e[1]) == canon]:
                del entries[dom]
                released += 1
            if not entries:
                del self._attested[height]
        self._ensure_round_locks_loaded()
        drop = [
            k
            for k, e in self._round_locks.items()
            if k[0] == height and e.block_hash == block_hash and canonical_address(e.proposer) == canon
        ]
        for k in drop:
            del self._round_locks[k]
        if drop:
            try:
                self._persist_round_locks()
            except Exception as exc:  # noqa: BLE001 - a stale lock on disk is the conservative side
                logger.warning("Round lock release not persisted at height %s: %s", height, exc)
            released += len(drop)
        return released

    async def _listen_unavail(self) -> None:
        """#1281: answer ``UNAVAIL_QUERY`` for hashes we do not possess."""
        topic = unavail.query_topic(self._chain_id)
        try:
            sub = await gossip_broker.subscribe(topic, max_queue_size=256)
        except Exception as e:
            logger.warning("Failed to subscribe to unavailability queries: %s", e)
            return
        logger.info("Subscribed to unavailability queries on %s", topic)
        try:
            async for query in sub:
                if self._stop_event.is_set():
                    break
                try:
                    await self._handle_unavail_query(query)
                except Exception as e:
                    logger.warning("Error handling unavailability query: %s", e)
        finally:
            sub.close()  # noqa: unawaited-async — TopicSubscription.close() is synchronous

    async def _listen_responses_for_index(self) -> None:
        """#1281/#1279: persistent ``attest_response`` observer.

        Feeds the GossipObservationIndex only — attestation collection for
        sealing stays on the proposer's transient subscription, so this
        listener changes no consensus behavior, just what the node has
        *seen*.
        """
        try:
            sub = await gossip_broker.subscribe(self._response_topic, max_queue_size=2000)
        except Exception as e:
            logger.warning("Failed to subscribe to attestation responses for index: %s", e)
            return
        logger.info("Subscribed to attestation responses for observation index on %s", self._response_topic)
        vset = self._validator_set_addresses()
        try:
            async for response in sub:
                if self._stop_event.is_set():
                    break
                if not isinstance(response, dict):
                    continue
                if response.get("chain_id") != self._chain_id:
                    continue
                try:
                    height = int(response.get("height", 0))
                except (TypeError, ValueError):
                    continue
                block_hash = str(response.get("hash", ""))
                validator = str(response.get("validator", ""))
                if not block_hash or not validator:
                    continue
                try:
                    canon = canonical_address(validator)
                except (AttributeError, TypeError, ValueError):
                    continue
                # Only count in-set validators — the topic is validator-
                # restricted at the transport, but the index must not trust
                # an unchecked claim either.
                if vset and canon not in vset:
                    continue
                index = await unavail.get_observation_index(self._chain_id)
                index.note_response(height, block_hash, canon, ignore=self._own_addresses())
        finally:
            sub.close()  # noqa: unawaited-async — TopicSubscription.close() is synchronous

    def _validator_set_addresses(self) -> set[str]:
        return {canonical_address(v) for v in self._load_validator_set()}

    def _possesses_block(self, height: int, block_hash: str) -> bool | None:
        """True when our DB serves ``block_hash`` at ``height``; None when
        the state cannot be read (caller must not sign a response)."""
        if self._session_factory is None:
            return None
        try:
            with self._session_factory() as session:
                row = session.exec(
                    select(Block.hash).where(Block.chain_id == self._chain_id).where(Block.height == height)
                ).first()
        except Exception as exc:  # noqa: BLE001 - unreadable state means no statement
            logger.warning("unavail: possession check failed at height %s: %s", height, exc)
            return None
        if row is None:
            return False
        served = row[0] if isinstance(row, tuple) else row
        return str(served) == block_hash

    async def _handle_unavail_query(self, query: Any) -> None:
        """Sign an unavailability response iff we do not possess the block.

        A validator holding the voted block MUST NOT sign — it should serve
        the block instead (the fetch-before-unlock path owns that case).
        Signing while holding it is a self-contradiction the certificate
        design already prices in, but honesty here keeps the artifact
        meaningful.
        """
        if not unavail.justification_enabled() or not isinstance(query, dict):
            return
        parsed = self._parse_unavail_query(query)
        if parsed is None:
            return
        height, epoch, block_hash = parsed
        # A decided height needs no unavailability statement.
        if self._tip_height_hint is not None and height < self._tip_height_hint:
            return
        possesses = self._possesses_block(height, block_hash)
        if possesses is not False:
            # True = we serve it (stay silent, let fetch win); None = cannot
            # determine (stay silent — a false statement is worse than none).
            return
        vset = self._validator_set_addresses()
        if not vset:
            return
        for address, private_key in self._validator_keys.items():
            try:
                canon = canonical_address(address)
            except (AttributeError, TypeError, ValueError):
                continue
            if canon not in vset:
                continue
            try:
                response = unavail.build_unavail_response(self._chain_id, height, block_hash, epoch, canon, private_key)
                await gossip_broker.publish(unavail.response_topic(self._chain_id), response)
            except Exception as e:
                logger.warning("Failed to publish unavailability response: %s", e)
            # One statement per node keeps the certificate compact; a node
            # holding several validator keys still answers once — the
            # threshold counts distinct validators, not keys per node.
            return

    def _parse_unavail_query(self, query: dict[str, Any]) -> tuple[int, int, str] | None:
        """``(height, epoch, block_hash)`` for a well-formed query, else None."""
        if query.get("type") != unavail.QUERY_TYPE or query.get("chain_id") != self._chain_id:
            return None
        try:
            height = int(query.get("height", 0))
            epoch = int(query.get("epoch", 0))
        except (TypeError, ValueError):
            return None
        block_hash = str(query.get("hash", ""))
        if not block_hash or height <= 0 or epoch <= 0:
            return None
        return height, epoch, block_hash

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

        # #1298: the domain this request's signatures are minted under —
        # computed once and reused for the acceptance-key lookups below and
        # the evidence-record stamping in the signing loop. None below the
        # armed activation height (legacy shared preimage).
        att_sig_domain = _attestation_signature_domain(height_int)

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

        # #1298: the durable lock journal also reseeds the in-memory
        # attestation lock and ``_signed_once`` across restarts — load it
        # once before either lock path consults them.
        self._ensure_round_locks_loaded()

        # Attestation lock: having signed one header at this height, refuse a
        # rival hash for one round window. Double-signing two blocks at h is
        # the equivocation that lets an asymmetric partition become a fork.
        window = attestation_lock_window_seconds(height_int)
        if not round_lock and getattr(settings, "attestation_lock_enabled", True):
            existing = self.attestation_lock(height_int, window, att_sig_domain)
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
            if existing is None and self._signed_once_contains(height_int, header_hash, att_sig_domain):
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
                # #1298: the proposer's block signature is a PROPOSAL-domain
                # signature at/above the armed height — verify accordingly.
                from aitbc.crypto.consensus_signing import (
                    DOMAIN_BLOCK_PROPOSAL,
                    block_header_message,
                    verify_consensus_message_domain,
                )

                req_height = header.get("height", 0)
                activation = getattr(settings, "consensus_domain_separation_height", None)
                if activation is not None and isinstance(req_height, int) and req_height >= activation:
                    sig_ok = verify_consensus_message_domain(
                        block_header_message(header), proposer_signature, proposer, DOMAIN_BLOCK_PROPOSAL
                    )
                else:
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
            refusal = await self._run_v9_check(header, txs)
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

        # Durable lock record BEFORE any signature is released (#1242
        # round-lock / #1298 attestation-lock journal): a crash after this
        # point can never forget that this height is bound to header_hash,
        # and a persistence failure refuses the signing — no signature goes
        # out unrecorded.
        if not self._record_pre_sign_lock(height_int, request_round, header_hash, proposer, header, round_lock):
            return

        # #1198/#1263 advisory: attestation equivocation is recorded inside the
        # signing loop below, AFTER a signature actually exists — evidence
        # without a signature is unverifiable and cannot satisfy the
        # validator_deactivation_evidence_required gate. Recording per actual
        # signer (not per configured key) also stops certifying equivocations
        # for keys that never signed the prior hash.

        # #1281: this request survived every authenticity check — it is a
        # genuine proposer broadcast, so it feeds the observation index.
        # (Recording earlier would let unauthenticated gossip inject fake
        # requests for the voted hash and hold the unlock shut forever.)
        if unavail.justification_enabled():
            index = await unavail.get_observation_index(self._chain_id)
            index.note_request(height_int, header_hash, proposer, ignore=self._own_addresses())
        request_cert = request.get("unlock_justification")

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
                height_int, header_hash, address, proposer, request_round, request_cert=request_cert
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
                signature = _sign_attestation(message, private_key, height_int)
            except Exception as e:
                logger.warning("Failed to sign attestation: %s", e)
                continue
            # #1263: retain the signed attestation (durably) so a rival-hash
            # signing at this height can cite BOTH signatures as equivocation
            # evidence, then record the equivocation for this signer.
            self._record_signed_attestation(
                height_int, header_hash, address, message, request_round, round_lock, signature, att_sig_domain
            )
            # #1281: distinct evidence class — "unavailability_cert" when the
            # armed barrier released this vote under a verified UC,
            # "unjustified" for any other armed-mode conflicting vote.
            # Absent entirely with the flag off (pre-#1281 evidence shape).
            just_class: str | None = None
            if unavail.justification_enabled():
                just_class = "unavailability_cert" if (height_int, header_hash) in self._vote_justifications else "unjustified"
            self._record_attestation_equivocation_evidence(
                height_int,
                header_hash,
                address,
                proposer,
                request_round,
                justification=just_class,
                signature_domain=att_sig_domain,
            )
            if not round_lock:
                self._record_attestation_lock(height_int, header_hash, proposer, att_sig_domain)

            response = {
                "chain_id": self._chain_id,
                "height": message["height"],
                "hash": message["hash"],
                "validator": address,
                "signature": signature,
            }
            stored_just = self._vote_justifications.get((height_int, header_hash))
            if stored_just is not None:
                # #1281: carry the unlock justification on the vote itself so
                # collectors and evidence verifiers see the same artifact.
                response["unlock_justification"] = stored_just
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

    async def _run_v9_check(self, header: dict[str, Any], txs: list[Any]) -> str | None:
        """#1310: run the v9 tx check, timed; optionally off the event loop.

        With ``attest_v9_check_offload_enabled`` the (read-only, idempotent)
        check runs in a worker thread -- ecrecover, sqlite reads and the lock
        retry sleep no longer freeze the loop. The handler still awaits the
        verdict before any signing decision, so serial ordering is unchanged.
        ``attest_v9_check_seconds`` records the cost either way.
        """
        start = time.monotonic()
        try:
            if getattr(settings, "attest_v9_check_offload_enabled", False):
                return await asyncio.to_thread(self._v9_check_transactions, header, txs)
            return self._v9_check_transactions(header, txs)
        finally:
            metrics_registry.observe("attest_v9_check_seconds", time.monotonic() - start)

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

    def _signed_once_contains(self, height: int, block_hash: str, domain: str | None) -> bool:
        """#1298: True when (height, block_hash) was already signed under
        ``domain`` — the domain is part of the acceptance key, so a signing
        under another domain does not count (T9-class coexistence)."""
        domains = self._signed_once.get(height)
        if not domains:
            return False
        return block_hash in domains.get(domain, ())

    def _signed_once_add(self, height: int, block_hash: str, domain: str | None) -> None:
        """#1298: record a signing of (height, block_hash) under ``domain``."""
        self._signed_once.setdefault(height, {}).setdefault(domain, set()).add(block_hash)

    def _record_attestation_lock(
        self, height: int, block_hash: str, proposer: str, signature_domain: str | None = None
    ) -> bool:
        """Record that this node's validator key(s) signed block `block_hash`
        at `height`. Locks expire by wall clock in `attestation_lock`.

        #1245: only the FIRST signing of (height, hash) starts the window.
        A duplicate returns False and leaves the lock untouched, so replaying
        a request can never extend or re-arm it. #1298: ``signature_domain``
        is part of the acceptance key — the same (height, hash) signed under
        a different domain is a distinct signing, not a duplicate."""
        self._ensure_round_locks_loaded()
        if self._signed_once_contains(height, block_hash, signature_domain):
            return False
        now = time.monotonic()
        # #1298 T15: each height prunes at 2x ITS effective lock window —
        # pre-activation heights keep the 60s round window, post-activation
        # heights the 130s lapse, so a live lock is never dropped early.
        self._attested = {
            h: {d: e for d, e in domains.items() if now - e[2] < 2 * attestation_lock_window_seconds(h)}
            for h, domains in self._attested.items()
        }
        self._attested = {h: domains for h, domains in self._attested.items() if domains}
        self._attested.setdefault(height, {})[signature_domain] = (block_hash, proposer, now)
        self._signed_once_add(height, block_hash, signature_domain)
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
        self._signed_once = {h: domains for h, domains in self._signed_once.items() if domains}
        if len(self._signed_once) > SIGNED_ONCE_MAX_HEIGHTS:
            keep = sorted(self._signed_once)[-SIGNED_ONCE_MAX_HEIGHTS:]
            self._signed_once = {h: self._signed_once[h] for h in keep}

    def attestation_lock(
        self, height: int, window_seconds: float, signature_domain: str | None = None
    ) -> tuple[str, str] | None:
        """Return ``(block_hash, proposer)`` this validator attested at
        ``height`` if the lock is still live, else None. Expired entries are
        dropped lazily. #1298: the durable journal is loaded first so a
        restart cannot forget a live lock (proposer-side callers included).

        ``signature_domain`` scopes the lookup to one domain's entries;
        ``None`` matches entries under ANY domain — the proposer-side
        suppression in ``_honor_attestation_lock`` uses that wider view so a
        signing under any domain still suppresses a rival proposal."""
        self._ensure_round_locks_loaded()
        entries = self._attested.get(height)
        if not entries:
            return None
        now = time.monotonic()
        best: tuple[str, str, float] | None = None
        for dom, entry in list(entries.items()):
            block_hash, proposer, signed_at = entry
            if now - signed_at >= window_seconds:
                del entries[dom]
                continue
            if signature_domain is not None and dom != signature_domain:
                continue
            if best is None or signed_at > best[2]:
                best = entry
        if not entries:
            del self._attested[height]
        return (best[0], best[1]) if best is not None else None

    # ─── #1263: signature-bearing attestation records ─────────────

    def _signed_attestation_key(self, height: int, block_hash: str, signer: str, signature_domain: str | None = None) -> str:
        """Evidence-index key (#1298).

        Below the armed activation height every signature is legacy, so the
        key stays the historical ``height:block_hash:signer`` — persisted
        files and in-memory lookups are byte-identical. At/above it the key
        carries ``signature_domain`` (design key
        ``chain_id:height:signature_domain:block_hash:signer``) so a
        proposal-domain and an attestation-domain record for the same
        (height, hash, signer) coexist instead of overwriting each other,
        and pairing lookups are domain-scoped by construction.
        """
        if signature_domain is None:
            return f"{height}:{block_hash}:{canonical_address(signer)}"
        return f"{self._chain_id}:{height}:{signature_domain}:{block_hash}:{canonical_address(signer)}"

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
        height can still be signed. The height is read from the record, not
        parsed out of the key: #1298 domain-separated keys lead with
        ``chain_id`` and cannot be split on ":" for a height.
        """
        import os

        self._signed_attestations_path.parent.mkdir(parents=True, exist_ok=True)
        heights = []
        valid_keys = []
        for key, rec in self._signed_attestations.items():
            try:
                heights.append(int(rec["height"]))
                valid_keys.append(key)
            except (KeyError, TypeError, ValueError):
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
        signature_domain: str | None = None,
    ) -> None:
        """Durably retain a just-produced attestation signature (#1263).

        The record holds every field the signed preimage covers plus
        ``round_in_payload``/``request_round`` so on-chain verification can
        rebuild the message byte-identically under either round-lock flag
        state. #1298: ``signature_domain`` records which domain preimage the
        signature actually used (``DOMAIN_BLOCK_ATTESTATION`` /
        ``DOMAIN_BLOCK_PROPOSAL``); it is written only when set, so legacy
        records stay byte-identical and "field absent" keeps meaning
        "pre-activation signature" to the on-chain verifier. A persistence
        failure is logged but does not block the attestation — the signature
        itself is already released; the evidence index is best-effort
        enrichment, not a consensus gate.
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
        if signature_domain is not None:
            record["signature_domain"] = signature_domain
        key = self._signed_attestation_key(height, block_hash, signer, signature_domain)
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
        justification: str | None = None,
        persist: bool = True,
        signature_domain: str | None = None,
    ) -> None:
        """Record attestation equivocation for the signer that just signed.

        #1263: pairs the new signature with each prior signed hash at this
        height FOR THIS SIGNER — per-signer precision replaces the old
        record-every-configured-key behavior. Pairs with a retained prior
        signature carry both attestations (gate-verifiable); pairs whose
        prior signature is unknown (pre-capture signing or lost index) fall
        back to the hash-only advisory record.

        #1298: ``signature_domain`` scopes the pairing — a record pairs only
        with prior signatures minted under the SAME domain preimage
        (proposal records with proposal records, attestation with
        attestation), so cross-role pairs can never be signed evidence.
        ``None`` (below the activation height) pairs exactly as before.
        """
        canon = canonical_address(signer)
        # #1298: ``_signed_once`` is domain-keyed — prior hashes union across
        # ALL domains; the per-domain pairing lookup below then binds each
        # hash to the record minted under the same domain.
        prior_hashes = {h for domains in self._signed_once.get(height, {}).values() for h in domains}
        prior_hashes |= {entry.block_hash for (h, _r, _d), entry in self._round_locks.items() if h == height}
        if vote_journal_enabled():
            # #1268: the journal survives restarts and the valve, so a rival
            # signed after either is still certified against the prior vote.
            prior_hashes |= {r.block_hash for r in get_vote_journal(self._chain_id).votes_at(height, signer)}
        prior_hashes.discard(block_hash)
        if not prior_hashes:
            return
        current_key = self._signed_attestation_key(height, block_hash, signer, signature_domain)
        current = self._signed_attestations.get(current_key)
        if current is None:
            return
        recorder = self._equivocation_recorder()
        # Only the per-chain consensus recorder persists on record; the
        # module-global SlashingManager never does, so there is nothing to defer.
        defer_save = not persist and callable(getattr(recorder, "save_state", None))
        extra: dict[str, Any] = {"persist": False} if defer_save else {}
        recorded = False
        for prior_hash in sorted(prior_hashes):
            prior = self._signed_attestations.get(self._signed_attestation_key(height, prior_hash, signer, signature_domain))
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
                    justification=justification,
                    **extra,
                )
                recorded = True
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
        if defer_save and recorded:
            self._schedule_deferred_state_save(recorder)

    def _schedule_deferred_state_save(self, recorder: Any) -> None:
        """Persist the recorder's state off the event loop, retrying (#1278 fix).

        The evidence is already in memory (it exists before the proposal
        signature leaves the node). ``save_state()`` opens its own sqlite
        connection and, while the proposal session still holds the write lock,
        blocks for the busy timeout — run inline it froze the loop for ~60 s
        (database is locked, stalled proposer, gossip keepalive timeouts). The
        save runs in a worker thread and retries until the lock clears. With
        no running loop (sync callers, tests) it saves inline.
        """
        save = recorder.save_state
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            if save() is False:
                metrics_registry.increment("proposal_equivocation_persist_failed_total")
            return
        task = loop.create_task(self._deferred_state_save(save))
        self._deferred_state_saves.add(task)
        task.add_done_callback(self._deferred_state_saves.discard)

    async def _deferred_state_save(self, save: Any) -> None:
        delay = DEFERRED_SAVE_RETRY_DELAY
        for attempt in range(DEFERRED_SAVE_ATTEMPTS):
            try:
                ok = await asyncio.to_thread(save)
            except Exception as e:  # noqa: BLE001 - never let evidence persistence kill the task silently
                logger.warning("Deferred consensus state save raised: %s", e)
                ok = False
            if ok is not False:
                return
            if attempt + 1 < DEFERRED_SAVE_ATTEMPTS:
                await asyncio.sleep(delay)
                delay = min(delay * 2, DEFERRED_SAVE_RETRY_MAX_DELAY)
        metrics_registry.increment("proposal_equivocation_persist_failed_total")
        logger.error("Deferred consensus state save gave up after %d attempts for %s", DEFERRED_SAVE_ATTEMPTS, self._chain_id)

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
        # #1298: the block signature was minted under the proposal domain at/
        # above the armed activation height — stamp the same domain so the
        # evidence record pairs only with same-domain signatures and the
        # on-chain verifier rebuilds the right preimage.
        from aitbc.crypto.consensus_signing import DOMAIN_BLOCK_PROPOSAL

        sig_domain = _active_signature_domain(height, DOMAIN_BLOCK_PROPOSAL)
        self._record_signed_attestation(height, block_hash, proposer, message, None, False, signature, sig_domain)
        evidence_round = round_number if self._round_lock_enabled() else None
        self._record_attestation_equivocation_evidence(
            height, block_hash, proposer, proposer, evidence_round, persist=False, signature_domain=sig_domain
        )

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
        # #1298 T15: the U2 monotonic-fallback window is the same effective
        # attestation-lock lapse the attester path enforces.
        window = attestation_lock_window_seconds(height)
        unlock_window = self._unlock_window()
        for (lh, lr, _domain), entry in self._round_locks.items():
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
        """Restore persisted signed (height, round, hash) records (#1242/D)
        plus the always-on attestation-lock journal records (#1298).

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
            for rec in data.get("records", []):
                try:
                    if rec.get("kind") == "attestation":
                        self._load_attestation_lock_record(rec, now_mono, now_wall)
                        continue
                    h, r = int(rec["h"]), int(rec["r"])
                    signed_wall = float(rec["signed_wall"])
                    age_wall = now_wall - signed_wall
                    # #1298 T15: prune at 2x the record height's effective
                    # lock window (post-activation lapse, not the 60s round).
                    if age_wall >= 2 * attestation_lock_window_seconds(h):
                        continue
                    req_wall = rec.get("request_seen_wall")
                    # #1298: the record's signature_domain is part of the
                    # acceptance key — absent/malformed reads as the legacy
                    # (None) domain so pre-#1298 records reseed unchanged.
                    raw_domain = rec.get("signature_domain")
                    domain = raw_domain if isinstance(raw_domain, str) else None
                    self._round_locks[(h, r, domain)] = _RoundLockEntry(
                        str(rec["hash"]),
                        str(rec.get("proposer", "")),
                        now_mono - age_wall,
                        signed_wall,
                        (now_mono - (now_wall - float(req_wall))) if req_wall is not None else None,
                        float(req_wall) if req_wall is not None else None,
                        signature_domain=domain,
                    )
                except (KeyError, TypeError, ValueError):
                    continue
            # Reseeded ``_signed_once`` entries prune by height/cap exactly
            # like live ones.
            self._prune_signed_once()
        except Exception as e:
            logger.warning("Failed to load round-lock records for %s: %s", self._chain_id, e)

    def _load_attestation_lock_record(self, rec: dict[str, Any], now_mono: float, now_wall: float) -> None:
        """Reseed one durable attestation-lock journal record (#1298 v2.5).

        ``signed_wall`` converts to a monotonic-equivalent timestamp with the
        same ``now_mono - (now_wall - signed_wall)`` math ``_load_round_locks``
        uses, clamped at zero age so a backwards wall-clock step cannot mint
        a negative age. Records older than two lock-lapse windows (260s at
        defaults — v2.6 defect-1 fix) are dropped: they can no longer bind
        anything. Records without a derived round or domain tag (legacy or
        underivable) still reseed — the lock state is (height, hash,
        domain)-keyed, so coverage is never weaker than a round-tagged
        record (T21).
        """
        h = int(rec["h"])
        block_hash = str(rec["hash"])
        signed_wall = float(rec["signed_wall"])
        age_wall = max(0.0, now_wall - signed_wall)
        if age_wall >= 2 * _lock_lapse_seconds():
            return
        signed_at = now_mono - age_wall
        proposer = str(rec.get("proposer", ""))
        raw_round = rec.get("derived_round")
        try:
            derived_round = int(raw_round) if raw_round is not None else None
        except (TypeError, ValueError):
            derived_round = None
        domain = rec.get("signature_domain")
        domain = domain if isinstance(domain, str) else None
        key = (h, block_hash, domain)
        self._attested_lock_records[key] = {
            "proposer": proposer,
            "signed_wall": signed_wall,
            "derived_round": derived_round,
            "signature_domain": domain,
        }
        self._signed_once_add(h, block_hash, domain)
        # ``_attested`` keeps the LATEST signing per (height, domain) — the
        # same last-write-wins semantics ``_record_attestation_lock`` applies.
        domains = self._attested.setdefault(h, {})
        current = domains.get(domain)
        if current is None or signed_at > current[2]:
            domains[domain] = (block_hash, proposer, signed_at)

    def _persist_round_locks(self) -> None:
        """Atomically persist signed (height, round, hash) records.

        Temp-file + fsync + rename so a crash cannot leave a torn record.
        Raises on failure — the caller must not release a signature it could
        not durably record.
        """
        import os

        self._round_locks_path.parent.mkdir(parents=True, exist_ok=True)
        now_wall = time.time()
        payload_records = []
        for (h, r, _domain), e in self._round_locks.items():
            # #1298 T15: 2x the record height's effective lock window.
            if now_wall - e.signed_wall >= 2 * attestation_lock_window_seconds(h):
                continue
            record = {
                "h": h,
                "r": r,
                "hash": e.block_hash,
                "proposer": e.proposer,
                "signed_wall": e.signed_wall,
                "request_seen_wall": e.request_seen_wall,
            }
            # #1298: signature_domain joins the acceptance key — written only
            # when set so legacy (pre-activation) records stay byte-identical.
            if e.signature_domain is not None:
                record["signature_domain"] = e.signature_domain
            payload_records.append(record)
        # #1298: the always-on attestation-lock journal shares this file.
        # kind="attestation" records carry no "r" key, so a pre-#1298 build
        # reading this file skips them (KeyError) instead of misreading them
        # as round locks. Pruned by WALL AGE at 2x the lock-lapse window
        # (260s at defaults), never the 60s round window — v2.6 defect 1.
        lapse_prune = 2 * _lock_lapse_seconds()
        for (h, block_hash, _domain), rec in self._attested_lock_records.items():
            signed_wall = float(rec["signed_wall"])
            if now_wall - signed_wall >= lapse_prune:
                continue
            payload_records.append(
                {
                    "kind": "attestation",
                    "h": h,
                    "hash": block_hash,
                    "proposer": rec["proposer"],
                    "signed_wall": signed_wall,
                    "derived_round": rec["derived_round"],
                    "signature_domain": rec["signature_domain"],
                }
            )
        payload = json.dumps({"version": 1, "chain_id": self._chain_id, "records": payload_records})
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

    def _record_round_lock(
        self, height: int, round_: int, block_hash: str, proposer: str, signature_domain: str | None = None
    ) -> None:
        """Record + durably persist that this node signed ``block_hash`` at
        ``(height, round_)``. Called BEFORE the signature is released; a
        persistence failure propagates so no signature goes out unrecorded."""
        self._ensure_round_locks_loaded()
        now_mono = time.monotonic()
        now_wall = time.time()
        # #1298 T15: prune each entry at 2x ITS height's effective lock
        # window — post-activation heights keep records for the full lapse.
        self._round_locks = {
            k: e for k, e in self._round_locks.items() if now_mono - e.signed_at < 2 * attestation_lock_window_seconds(k[0])
        }
        key = (height, round_, signature_domain)
        if key not in self._round_locks:
            req_seen = self._requests_seen.get(height, {}).get(round_)
            req_seen_wall = now_wall - (now_mono - req_seen) if req_seen is not None else None
            self._round_locks[key] = _RoundLockEntry(
                block_hash, proposer, now_mono, now_wall, req_seen, req_seen_wall, signature_domain=signature_domain
            )
        self._persist_round_locks()

    def _record_attestation_lock_journal(
        self,
        height: int,
        block_hash: str,
        proposer: str,
        header: dict[str, Any],
    ) -> None:
        """Durably record an attestation-lock signing BEFORE release (#1298).

        Always-on counterpart of ``_record_round_lock`` for the non-round-lock
        path: the record carries the signing wall-clock time, the best-effort
        derived round, and the signature domain in effect, so a restart can
        re-derive ``_attested``/``_signed_once`` instead of forgetting every
        lock (design v2.5 restart fix — best-effort reseed was rejected).
        Idempotent per (height, hash, signature_domain): a duplicate request
        adds nothing and skips the fsync. A persistence failure propagates —
        the caller must not release a signature it could not durably record.
        """
        self._ensure_round_locks_loaded()
        domain = _attestation_signature_domain(height)
        # #1298: the domain is part of the journal key — the same
        # (height, hash) signed under another domain is a distinct record.
        key = (height, block_hash, domain)
        if key in self._attested_lock_records:
            return
        now_wall = time.time()
        lapse_prune = 2 * _lock_lapse_seconds()
        self._attested_lock_records = {
            k: r for k, r in self._attested_lock_records.items() if now_wall - float(r["signed_wall"]) < lapse_prune
        }
        record = {
            "proposer": proposer,
            "signed_wall": now_wall,
            "derived_round": self._derive_request_round(header),
            "signature_domain": domain,
        }
        self._attested_lock_records[key] = record
        try:
            self._persist_round_locks()
        except Exception:
            # Roll back the in-memory record: an unpersisted entry must not
            # dedup a later retry into releasing a signature it never
            # durably recorded (fail-closed, not fail-open).
            if self._attested_lock_records.get(key) is record:
                del self._attested_lock_records[key]
            raise

    def _record_pre_sign_lock(
        self,
        height: int,
        request_round: int | None,
        header_hash: str,
        proposer: str,
        header: dict[str, Any],
        round_lock: bool,
    ) -> bool:
        """Persist the durable lock record for this signing; False = refuse.

        Round-lock path keeps the ``_record_round_lock`` contract — a
        persistence failure propagates. The attestation-lock journal path
        (#1298) catches the failure, counts it, and refuses the signature
        (fail-closed): the node stops attesting until the disk recovers,
        which is the detectable liveness cost the design accepted over
        silently losing restart coverage.
        """
        if round_lock and request_round is not None:
            self._record_round_lock(height, request_round, header_hash, proposer, _attestation_signature_domain(height))
            return True
        try:
            self._record_attestation_lock_journal(height, header_hash, proposer, header)
        except Exception as e:
            metrics_registry.increment("attestation_lock_persist_failure_total")
            logger.error(
                "Attestation-lock journal persist failed at height %s — refusing to sign: %s",
                height,
                e,
            )
            return False
        return True

    async def collect_attestations(
        self,
        block: Block,
        min_count: int,
        timeout: float | None = None,
        transactions: list[dict[str, Any]] | None = None,
        unlock_justification: dict[str, Any] | None = None,
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
        if unlock_justification is not None:
            # #1281: the proposer's own unlock justification rides the
            # request so attesters can verify the UC without a collect round.
            request["unlock_justification"] = unlock_justification
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
        seen_validators: set[str] = set()
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
                seen_validators.add(str(validator))
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
                        att_msg = _attestation_message(header, self._chain_id, collect_round)
                        sig_ok = _verify_attestation(att_msg, signature, validator, block.height)
                    elif _attestation_domain_active(block.height):
                        # #1298: post-activation attestations live under the
                        # attestation domain — the proposal/raw-hash fallbacks
                        # inside verify_block_signature must not accept them.
                        sig_ok = _verify_attestation(
                            _attestation_message(header, self._chain_id), signature, validator, block.height
                        )
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
            # #1306: one line per collect round so a quorum miss can be read
            # as "responses never reached us" vs "reached us and were refused".
            metrics_registry.observe("attest_collect_responses_seen", float(len(seen_validators)))
            logger.info(
                "Attestation collect summary: height=%s hash=%s counted=%d seen=%d expected=%d elapsed_ms=%d",
                block.height,
                block.hash[:18],
                len(attestations),
                len(seen_validators),
                len(expected_remote),
                int((time.monotonic() - start) * 1000),
            )

        return attestations
