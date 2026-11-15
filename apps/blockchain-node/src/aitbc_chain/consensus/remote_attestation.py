"""Remote block-header attestation over the gossip broker (#1950 facade).

v0.7.6: minimal second-node validator PoC. Proposers publish a block header
over the ``consensus.attest_request.<chain_id>`` gossip topic. Other validators
sign the canonical header and publish responses on
``consensus.attest_response.<chain_id>``. The proposer collects responses and
includes them in ``block_metadata``.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlmodel import select

from aitbc.aitbc_logging import get_logger
from aitbc.constants import DATA_DIR
from aitbc.crypto.signature_recovery import canonical_address

from ..config import settings
from ..gossip import gossip_broker
from ..metrics import metrics_registry
from ..models import Block
from . import unavail
from .vote_fetch import contention_hold, kick_pull, locate_voted_block
from .vote_journal import KIND_ATTEST, VoteJournalError, get_vote_journal, valve_open
from .remote_attestation_crypto import (
    DEFERRED_SAVE_ATTEMPTS,
    DEFERRED_SAVE_RETRY_DELAY,
    DEFERRED_SAVE_RETRY_MAX_DELAY,
    SIGNED_ONCE_MAX_HEIGHTS,
    V9_CHECK_ATTEMPTS,
    V9_CHECK_RETRY_DELAY_S,
    _attestation_message,
    _lock_lapse_seconds,
    _verify_attestation,
    attestation_lock_window_seconds,
)
from .remote_attestation_round_lock_types import _RoundLockEntry

logger = get_logger(__name__)


class _RaBaseMixin:
    """Core lifecycle, journal gates, and shared chain queries (#1950 pure-move split)."""

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
        # #1940 F4: at most one post-state probe worker at a time per
        # service. Non-blocking acquire -> "post_state_busy" refusal; the
        # worker that wins the permit releases it when it actually finishes
        # (an async timeout cannot free it early or stack workers).
        self._attest_probe_lock = threading.Lock()
        self._request_topic = f"consensus.attest_request.{chain_id}"
        self._response_topic = f"consensus.attest_response.{chain_id}"
        self._listener_task: asyncio.Task[None] | None = None
        self._unavail_task: asyncio.Task[None] | None = None
        self._abandon_task: asyncio.Task[None] | None = None
        self._evidence_task: asyncio.Task[None] | None = None
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
        # #1736: (height, round) -> hashes this validator voted for that the proposer abandoned in that
        # round. A different hash in the same round is refused (it would sign a slashable same-round
        # pair). Reseeded from ``attestation_abandoned.json`` on load (#1963).
        self._abandoned_rounds: dict[tuple[int, int], set[str]] = {}
        # #1940 F2: height-level abandoned index for the round-underivable
        # case (round-lock off / pre-domain-separation) — same persistence
        # contract as ``_abandoned_rounds``.
        self._abandoned_heights: dict[int, set[str]] = {}
        # #1963: both indexes are reseeded from this durable file on load —
        # release_abandoned→retract leaves no trace in the vote journal, so
        # without it a restart inside the abandon→retry gap reopens the
        # same-round equivocation window the guards exist to close.
        self._abandoned_loaded = False
        self._abandoned_path = DATA_DIR / "data" / chain_id / "attestation_abandoned.json"
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
                # #1306: leg 1 would otherwise park this serial listener for
                # the whole T_evidence window; flag-gated, default blocking.
                nonblocking_persist=unavail.nonblocking_persist_enabled(),
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

    def _validator_set_addresses(self) -> set[str]:
        return {canonical_address(v) for v in self._load_validator_set()}

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
        except Exception as e:  # noqa: BLE001 - optional consensus helper, None means unavailable
            logger.debug("consensus helper failed: %s", type(e).__name__)
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
        except Exception as e:  # noqa: BLE001 - optional consensus helper, None means unavailable
            logger.debug("consensus helper failed: %s", type(e).__name__)
            return None
        return None

    def _load_validator_set(self) -> set[str]:
        validator_set_str = getattr(settings, "validator_set", "")
        if not validator_set_str:
            return set()
        try:
            data = json.loads(validator_set_str)
            return {v.get("address", "") for v in data if v.get("address")}
        except (TypeError, ValueError):
            return set()

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
        except Exception as e:  # noqa: BLE001 - optional consensus helper, None means unavailable
            logger.debug("consensus helper failed: %s", type(e).__name__)
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
        except Exception as e:  # noqa: BLE001 - optional consensus helper, None means unavailable
            logger.debug("consensus helper failed: %s", type(e).__name__)
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


from .remote_attestation_listener import _ListenerMixin
from .remote_attestation_v9 import _V9Mixin
from .remote_attestation_evidence import _EvidenceMixin
from .remote_attestation_round_lock import _RoundLockMixin
from .remote_attestation_collect import _CollectMixin


class RemoteAttestationService(
    _CollectMixin,
    _RoundLockMixin,
    _EvidenceMixin,
    _V9Mixin,
    _ListenerMixin,
    _RaBaseMixin,
):
    """Collect and serve remote block-header attestations over gossip."""


# Re-exported at module tail so static analysis sees names after mixin imports.
__all__ = [
    "RemoteAttestationService",
    "SIGNED_ONCE_MAX_HEIGHTS",
    "V9_CHECK_ATTEMPTS",
    "V9_CHECK_RETRY_DELAY_S",
    "DEFERRED_SAVE_ATTEMPTS",
    "DEFERRED_SAVE_RETRY_DELAY",
    "DEFERRED_SAVE_RETRY_MAX_DELAY",
    "_attestation_message",
    "_lock_lapse_seconds",
    "_verify_attestation",
    "attestation_lock_window_seconds",
    "gossip_broker",
    "settings",
    "time",
    "logger",
    "DATA_DIR",
    "contention_hold",
    "locate_voted_block",
]
