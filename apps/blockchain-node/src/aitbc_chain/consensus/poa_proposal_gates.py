"""Proposal freshness, attestation-lock, vote-journal recording, and mempool/assembly gates for ``PoAProposer`` (#1867 pure-move split).

Import ``aitbc_chain.consensus.poa`` first (it wires these
mixins into ``PoAProposer``); this module is not meant to be imported
directly."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from . import poa as _poa
from .poa import (
    _PoaBaseMixin,
    _CLOCK_SKEW_WARN_INTERVAL_SECONDS,
    _SEQUENTIAL_ONLY_TX_TYPES,
    _attestation_lock_peer_bases,
    _escrow_addresses_from_txs,
    _rejection_metadata,
)

from ..base_models import _to_ait_address
from ..config import settings
from ..cross_chain import bridge_lock_guard
from ..metrics import metrics_registry
from ..models import Account, Block, Transaction
from ..state import side_root_shadow
from ..state.pure_state_transition import _determine_tx_type
from ..state.state_root_utils import compute_state_root_full as _compute_state_root
from ..state.state_transition import build_bridge_lock_context, build_escrow_context, get_block_version_for_height
from .remote_attestation import attestation_lock_window_seconds
from .vote_journal import KIND_PROPOSE, VoteJournalError, get_vote_journal, vote_journal_enabled
from aitbc.network import SharedHttpClient
from datetime import UTC, datetime
from sqlalchemy import text
from sqlmodel import Session, select
import time

if TYPE_CHECKING:
    from ..mempool import DatabaseMempool, InMemoryMempool


class _ProposalGatesMixin(_PoaBaseMixin):
    if TYPE_CHECKING:

        def _collect_and_gate_attestations(self, *args: Any, **kwargs: Any) -> Any: ...
        def _process_txs_parallel(self, *args: Any, **kwargs: Any) -> tuple[list[Any], set[str], bool]: ...
        def _process_txs_sequential(self, *args: Any, **kwargs: Any) -> tuple[list[Any], set[str], bool]: ...

    async def _passes_early_gates(self) -> InMemoryMempool | DatabaseMempool | None:
        """Pre-session proposal gates.

        Returns the mempool when the proposal may proceed, else None. Checks,
        in order: the node is synced enough to propose, the stop event is not
        set, the selected proposer for the next height is a local key, and the
        generation-mode empty-mempool gate is satisfied. Also starts a fresh
        per-block replay cache once the node is known to be running.
        """
        from ..database import ensure_chain_db_healthy
        from ..mempool import get_mempool

        db_ok, db_reason = ensure_chain_db_healthy(self._config.chain_id)
        if not db_ok:
            self._logger.error(
                "[PROPOSE] Refusing block proposal on chain %s — chain.db integrity check failed: %s",
                self._config.chain_id,
                db_reason,
            )
            return None
        if not await self._ensure_synced_before_proposal():
            return None
        if self._stop_event.is_set():
            return None

        # Start a fresh per-block replay cache for this proposal.
        _poa.get_state_transition().reset_processed_cache()

        mempool = get_mempool()

        # If we are not the selected proposer for the next block, skip quietly.
        head = self._fetch_chain_head()
        if not self._selected_proposer_is_local(head):
            return None
        if self._should_skip_for_empty_mempool(head, mempool):
            return None
        if not await self._passes_freshness_gate(head):
            return None
        return mempool

    async def _passes_freshness_gate(self, head: Block | None) -> bool:
        """Refuse to propose on a head that mesh peers can prove is stale or forked.

        The sync-source gate cannot see "peers ahead of us" when our own source
        is ourselves or dead — the failure that let a restarted hub fork the
        fleet. This gate asks the gossip peers directly:

        - peer ahead      → bulk-pull from that peer and skip this proposal;
        - same height, rival hash strictly outvoting ours → skip and log (a
          forked minority holds while the majority proceeds; a tie proceeds
          and is counted — deterministic fork choice settles it);
        - all unreachable → propose anyway and bump
          ``proposal_freshness_unverified_total`` — blocking would trade
          liveness for safety on every blip;
        - otherwise       → proceed.

        Never queries the network when production is disabled — the proposer
        loop does not run then, and the production-off rejoin runbook depends
        on the node not touching peers during catch-up. Verdicts are cached
        per local head for ``proposal_freshness_cache_ttl_seconds`` only, and
        UNVERIFIED is never cached: the stale case is exactly the one where
        the local head doesn't move while peers advance, so an unbounded
        cache would re-open the fork this gate exists to close.
        """
        if not getattr(settings, "enable_block_production", True):
            return True
        if not getattr(settings, "proposal_freshness_check_enabled", True):
            return True
        key = (head.height if head is not None else -1, head.hash if head is not None and head.hash else "")
        peer_urls = settings.mesh_peer_urls_for_service(self._config.chain_id)
        if not peer_urls:
            self._warn_freshness_no_peers(key)
            return True
        now = self._monotonic()
        if self._freshness_cache_key == key and now < self._freshness_cache_expires:
            return self._freshness_cache_ok

        self._reconcile_freshness_pulls(key[0], now)
        quarantined = {p for p, until in self._freshness_quarantined.items() if until > now}

        from .proposal_freshness import FreshnessVerdict, ProposalFreshnessChecker

        checker = ProposalFreshnessChecker(
            chain_id=self._config.chain_id,
            peer_urls=peer_urls,
            fetch=self._freshness_fetch,
            timeout=getattr(settings, "proposal_freshness_peer_timeout_seconds", 2.0),
        )
        result = await checker.check(key[0], key[1], quarantined=quarantined)

        ok = self._freshness_verdict_ok(result, key)

        if result.verdict is not FreshnessVerdict.UNVERIFIED:
            ttl = getattr(settings, "proposal_freshness_cache_ttl_seconds", 5.0)
            self._freshness_cache_key = key
            self._freshness_cache_ok = ok
            self._freshness_cache_expires = now + ttl
        return ok

    def _warn_freshness_no_peers(self, key) -> None:
        if self._config.chain_id != settings.chain_id and self._no_peers_warned.get("freshness") != key:
            self._no_peers_warned["freshness"] = key
            metrics_registry.increment("proposal_freshness_no_peers_total")
            self._logger.warning(
                "[PROPOSE] freshness gate has no peers for chain %s — only chain-tagged "
                "GOSSIP_MESH_PEER_URLS entries reach it; proposing unverified",
                self._config.chain_id,
            )

    def _freshness_verdict_ok(self, result, key) -> bool:
        """Map a FreshnessVerdict to proceed/skip, emitting metrics + logs.
        Only STALE and HASH_MISMATCH block the proposal."""
        from .proposal_freshness import FreshnessVerdict

        ok = True
        if result.verdict is FreshnessVerdict.STALE:
            ok = False
            self._freshness_stale_pull(result, key[0])
        elif result.verdict is FreshnessVerdict.HASH_MISMATCH:
            ok = False
            metrics_registry.increment("proposal_freshness_hash_mismatch_total")
            self._logger.warning(
                "[PROPOSE] Peer hash %s outvotes ours at height %s (%s vs %s votes, e.g. %s) — not proposing on the minority side",
                result.peer_hash,
                result.peer_height,
                result.rival_votes,
                result.our_votes,
                result.peer_url,
            )
        elif result.verdict is FreshnessVerdict.HASH_TIE:
            metrics_registry.increment("proposal_freshness_hash_tie_total")
            self._logger.warning(
                "[PROPOSE] Hash vote tied at height %s (%s vs %s, rival %s) — proceeding; fork choice will settle it",
                result.peer_height,
                result.rival_votes,
                result.our_votes,
                result.peer_hash,
            )
        elif result.verdict is FreshnessVerdict.QUARANTINED:
            metrics_registry.increment("proposal_freshness_peer_quarantined_total")
            self._logger.warning(
                "[PROPOSE] Every ahead peer is quarantined (tallest %s at %s) — proposing on local head",
                result.peer_url,
                result.peer_height,
            )
        elif result.verdict is FreshnessVerdict.UNVERIFIED:
            metrics_registry.increment("proposal_freshness_unverified_total")
            self._logger.info("[PROPOSE] No mesh peer answered /rpc/head — proposing unverified")
        elif result.rival_votes:
            self._logger.info(
                "[PROPOSE] Peer %s reports a different hash at our height but is outvoted (%s vs %s) — proceeding",
                result.peer_url,
                result.rival_votes,
                result.our_votes,
            )
        return ok

    def _freshness_stale_pull(self, result, local_height: int) -> None:
        metrics_registry.increment("proposal_freshness_stale_total")
        self._logger.warning(
            "[PROPOSE] Peer %s is ahead at height %s (local %s) — pulling before proposing",
            result.peer_url,
            result.peer_height,
            local_height,
        )
        if self._sync_manager is not None and result.peer_url:
            try:
                # Recorded only when the pull actually starts — a deduped
                # call means someone else's pull is in flight and this
                # peer must not take the blame for it.
                if self._sync_manager.pull_from_peer(self._config.chain_id, result.peer_url):
                    self._freshness_pulls[result.peer_url] = local_height
            except Exception as exc:  # noqa: BLE001 - peer pull probe: a failed kick must not abort proposing
                self._logger.warning("[PROPOSE] freshness pull from %s failed to start: %s", result.peer_url, exc)

    def _reconcile_freshness_pulls(self, local_height: int, now: float) -> None:
        """Quarantine ahead peers whose pull finished without moving our head.

        A peer can be ahead yet useless — on a taller fork the importer
        rejects, or overstating its height. Recording (peer -> local height
        when its pull was kicked) lets the next check tell "pull still
        running" from "pull ran and we are still stuck"; the latter earns a
        quarantine window so other peers get a turn, and eventually a fully
        quarantined ahead set stops blocking proposals entirely.
        """
        if not self._freshness_pulls:
            return
        in_flight = False
        if self._sync_manager is not None:
            try:
                in_flight = bool(self._sync_manager.pull_in_flight(self._config.chain_id))
            except Exception:  # noqa: BLE001 - status probe: cannot tell -> assume in-flight, blame nobody
                in_flight = True  # cannot tell — do not blame anyone yet
        if in_flight:
            return
        quarantine_s = getattr(settings, "proposal_freshness_peer_quarantine_seconds", 600.0)
        for peer, pulled_at_height in list(self._freshness_pulls.items()):
            del self._freshness_pulls[peer]
            if local_height > pulled_at_height:
                continue  # head moved past the height the pull was kicked at — it helped
            self._freshness_quarantined[peer] = now + quarantine_s
            metrics_registry.increment("proposal_freshness_peer_quarantine_marked_total")
            self._logger.warning(
                "[PROPOSE] Pull from %s finished but head still at %s — quarantining peer for %ss",
                peer,
                local_height,
                quarantine_s,
            )

    async def _honor_attestation_lock(self, next_height: int, round_number: int | None = None) -> bool:
        """True while a live attestation lock suppresses this proposal.

        If this node's validator keys signed block X at ``next_height`` as an
        attester, producing a different block at the same height is
        equivocation — the mechanism that turned the live asymmetric
        partitions into same-height forks. While the lock is live we look
        for a mesh peer that actually serves X and kick a pull toward it, so
        the head advances onto the attested block instead of competing with
        it. If no peer can serve X, the proposal is still suppressed until
        the lock expires (the effective attestation-lock lapse — #1298 T15
        shares ``attestation_lock_window_seconds`` with the attester side),
        which bounds the liveness hit when the attested block never
        materialises.

        Under ``attestation_round_lock_enabled`` (#1242) the suppression
        decision uses the shared U1/U2 verdict for ``(next_height,
        round_number)`` — identical rules to the attester-side signing
        check, so the two enforcement points cannot disagree.
        """
        locked = self._attestation_lock_entry(next_height, round_number)
        if locked is None:
            return False
        locked_hash, locked_proposer = locked
        await self._attestation_lock_peer_scan(next_height, locked_hash, locked_proposer)
        return True

    def _attestation_lock_entry(self, next_height: int, round_number: int | None):
        """Resolve the live attestation lock for this height.

        Returns ``(locked_hash, locked_proposer)`` while a lock suppresses the
        proposal, or None when the proposal may proceed. Applies the shared
        U1/U2 round-lock verdict when ``attestation_round_lock_enabled`` is
        set, else the height-window attestation lock — identical rules to the
        attester-side signing check (#1242)."""
        if self._remote_attestation is None or self._sync_manager is None:
            return None
        if not getattr(settings, "attestation_lock_enabled", True):
            return None
        # #1298 T15: the SAME effective lapse window the attester enforces —
        # one shared constant, no attester/proposer drift.
        window = attestation_lock_window_seconds(next_height)
        if getattr(settings, "attestation_round_lock_enabled", False):
            if round_number is None:
                self._logger.warning(
                    "[PROPOSE] round lock enabled but no round for height %s — proceeding without suppression",
                    next_height,
                )
                return None
            # A fresh proposal always has a different hash than anything we
            # signed, so every locked entry at this height conflicts; the
            # empty hash can never match an entry's block_hash.
            verdict = self._remote_attestation.round_lock_verdict(next_height, round_number, "")
            if verdict.permitted:
                return None
            locked_hash, locked_proposer = verdict.block_hash, verdict.proposer
            self._logger.info(
                "[PROPOSE] Round-lock suppression at height %s round %s: %s (attested %s by %s)",
                next_height,
                round_number,
                verdict.reason,
                locked_hash[:18] if locked_hash else "?",
                locked_proposer[:12] if locked_proposer else "?",
            )
        else:
            lock = self._remote_attestation.attestation_lock(next_height, window)
            if lock is None:
                return None
            locked_hash, locked_proposer = lock
        return locked_hash, locked_proposer

    async def _attestation_lock_peer_scan(self, next_height: int, locked_hash: str, locked_proposer: str) -> None:
        """Look for a mesh peer serving the attested block and kick a pull.

        Always resolves — the caller holds the proposal either way: a peer
        that serves the block gets a pull kicked toward it, and a fully
        unserved lock is held until expiry (bounded liveness hit, #1298 T15)."""
        peer_urls = settings.mesh_peer_urls_for_service(self._config.chain_id)
        if (
            not peer_urls
            and self._config.chain_id != settings.chain_id
            and self._no_peers_warned.get("attlock") != next_height
        ):
            self._no_peers_warned["attlock"] = next_height
            metrics_registry.increment("poa_attestation_lock_no_peers_total")
            self._logger.warning(
                "[PROPOSE] attestation-lock peer scan has no peers for chain %s — only "
                "chain-tagged GOSSIP_MESH_PEER_URLS entries reach it; cannot fetch the "
                "attested block from a peer",
                self._config.chain_id,
            )
        timeout = getattr(settings, "proposal_freshness_peer_timeout_seconds", 2.0)
        for base in dict.fromkeys(_attestation_lock_peer_bases(peer_urls)):
            if await self._attestation_lock_fetch_peer(base, next_height, locked_hash, locked_proposer, timeout):
                return
        metrics_registry.increment("poa_attestation_lock_held_total")
        self._logger.warning(
            "[PROPOSE] Attestation lock held at height %s — we attested %s (proposer %s) but no peer serves it; holding until the lock expires",
            next_height,
            locked_hash[:18],
            locked_proposer[:12],
        )

    async def _attestation_lock_fetch_peer(
        self, base: str, next_height: int, locked_hash: str, locked_proposer: str, timeout: float
    ) -> bool:
        """Fetch the attested block from one peer; on a hash match kick the
        pull and return True. Any other outcome returns False."""
        try:
            resp = await SharedHttpClient.get(
                f"{base}/rpc/block/{next_height}",
                params={"chain_id": self._config.chain_id},
                timeout=timeout,
            )
            if resp.status_code != 200:
                return False
            block = resp.json()
        except Exception:  # noqa: BLE001 - per-peer fetch containment: one bad peer must not break the scan
            return False
        if not isinstance(block, dict) or block.get("hash") != locked_hash:
            return False
        self._logger.warning(
            "[PROPOSE] Attestation lock: we attested %s at height %s (proposer %s) — pulling from %s instead of proposing",
            locked_hash[:18],
            next_height,
            locked_proposer[:12],
            base,
        )
        metrics_registry.increment("poa_attestation_lock_fetch_total")
        try:
            # _attestation_lock_entry already gated on _sync_manager being set.
            self._sync_manager.pull_from_peer(self._config.chain_id, base)  # type: ignore[union-attr]
        except Exception as exc:  # noqa: BLE001 - peer pull probe: a failed kick still leaves the lock held
            self._logger.warning("[PROPOSE] attestation-lock pull from %s failed: %s", base, exc)
        return True

    async def _honor_prior_votes(self, next_height: int, round_number: int, proposer: str) -> bool:
        """True when an earlier vote (attestation lock or #1268 journal) forbids proposing now."""
        return await self._honor_attestation_lock(next_height, round_number) or await self._honor_vote_journal(
            next_height, proposer
        )

    async def _run_journaled_gates(
        self,
        session: Session,
        block: Block,
        block_hash: str,
        proposer: str,
        round_number: int,
        next_height: int,
        metadata_dict: dict[str, Any],
        transactions: list[dict[str, Any]],
    ) -> bool:
        """Record this proposal's vote durably, run the gates, void the vote if they fail (#1268)."""
        if not self._record_proposal_vote(session, next_height, block_hash, proposer, round_number):
            return False
        self._record_proposal_equivocation(block, proposer, round_number)
        if await self._run_consensus_gates(
            session, block, block_hash, proposer, round_number, next_height, metadata_dict, transactions=transactions
        ):
            return True
        self._retract_proposal_vote(next_height, block_hash, proposer)
        return False

    def _record_proposal_vote(
        self, session: Session, next_height: int, block_hash: str, proposer: str, round_number: int | None
    ) -> bool:
        """Make this proposal's vote durable before the attest request leaves.

        #1268: the proposer's own vote used to be unrecorded, so a proposer
        collecting attestations for B1 could attest a rival B2 at the same
        height. False aborts the proposal (and rolls the session back) when
        the journal cannot persist.
        """
        if not vote_journal_enabled():
            return True
        try:
            get_vote_journal(self._config.chain_id).record(
                next_height,
                proposer,
                block_hash,
                KIND_PROPOSE,
                round_number,
                proposer,
                justification=self._unlock_justifications.get(next_height),
            )
        except VoteJournalError as exc:
            self._logger.error("[PROPOSE] vote journal refuses proposal at height %s: %s", next_height, exc)
            if session is not None:
                session.rollback()
            return False
        return True

    def _record_proposal_equivocation(self, block: Block, proposer: str, round_number: int | None) -> None:
        """Certify this proposal against the proposer's earlier same-height votes (#1278).

        Runs once the proposal's vote is durable and BEFORE the attest request
        carries ``block.signature`` out, so the signature is never released
        without its evidence. Fail-open like the attester path (the evidence
        store must not stall block production) but never silent: a failure is
        counted and logged.
        """
        service = self._remote_attestation
        if service is None or not block.signature:
            return
        try:
            service.record_proposal_equivocation(self._block_header_message(block), block.signature, round_number)
        except Exception as exc:
            metrics_registry.increment("proposal_equivocation_record_failed_total")
            self._logger.warning(
                "[PROPOSE] Failed to record proposer equivocation evidence at height %s: %s", block.height, exc
            )

    def _retract_proposal_vote(self, next_height: int, block_hash: str, proposer: str) -> None:
        """Void the vote of a proposal this process rolled back before commit.

        Only the proposer commits its own block, so a rolled-back proposal can
        never be sealed by anyone: its vote cannot join a quorum, and keeping
        it would only block this validator from attesting the rival.
        """
        if vote_journal_enabled():
            get_vote_journal(self._config.chain_id).retract(next_height, proposer, block_hash)

    def _same_hash_retry_horizon_seconds(self) -> float:
        """Seconds a proposal timestamp stays reusable for same-hash retry.

        #1298: bounded by the tighter of the attestation-lock window and the
        signed-header max age, minus ONE collect window plus propagation
        slack — the margin must leave room for a final gate cycle to
        complete before the reused header goes stale at attesters. The
        earlier ``4 × attest_timeout + 8`` margin silently zeroed the
        horizon at the production 15 s collect timeout; the margin is now
        ``attest_timeout + proposer_same_hash_retry_margin_seconds``.
        0 disables reuse.
        """
        lock = float(getattr(settings, "consensus_proposer_round_seconds", 60))
        header = float(getattr(settings, "attestation_header_max_age_seconds", 60))
        collect = float(getattr(settings, "multi_validator_attestation_timeout_seconds", 1.0))
        slack = float(getattr(settings, "proposer_same_hash_retry_margin_seconds", 12.0))
        return max(0.0, min(lock, header) - (collect + slack))

    def _peek_same_hash_retry(
        self, next_height: int, parent_hash: Any
    ) -> tuple[int, Any, datetime, float, tuple[Any, ...]] | None:
        """The failed proposal's pin while its retry horizon holds.

        Returns the ``(height, parent_hash, timestamp, not_after, tx_key)``
        candidate, or None (dropping it) when the height moved on, the parent
        changed at the same height, the horizon lapsed, or the feature flag
        is off — the caller then stamps a fresh ``datetime.now(UTC)`` exactly
        as before #1298. Parent binding: a same-height reorg would assemble
        a different block under the pinned timestamp.
        """
        cand = self._same_hash_retry
        if cand is None:
            return None
        height, cand_parent, _timestamp, not_after, _tx_key = cand
        if (
            height != next_height
            or cand_parent != parent_hash
            or time.time() >= not_after
            or not getattr(settings, "proposer_same_hash_retry_enabled", False)
        ):
            self._same_hash_retry = None
            return None
        return cand

    @staticmethod
    def _stamp_rejected_tx_metadata(metadata_dict: dict[str, Any], rejected_txs: list[tuple[Any, str]]) -> None:
        """R14-M1 (#1248): publish apply-rejected tx identities into
        block_metadata so followers release the dead (sender, nonce) slots."""
        if not rejected_txs:
            return
        from ..mempool import _tx_nonce, _tx_sender

        metadata_dict["rejected_txs"] = [
            {
                "tx_hash": tx.tx_hash,
                "sender": _tx_sender(tx.content or {}),
                "nonce": _tx_nonce(tx.content or {}),
                "type": str((tx.content or {}).get("type") or "TRANSFER").upper(),
                "reason": reason,
            }
            for tx, reason in rejected_txs
        ]

    @staticmethod
    def _tx_snapshot_key(txs: Any) -> tuple[Any, ...]:
        """Identity tuple of a drained tx set for same-hash retry binding."""
        return tuple(getattr(tx, "tx_hash", tx) for tx in txs)

    async def _resolve_post_collect_proposal(
        self,
        head: Block | None,
        next_height: int,
        timestamp: datetime,
        proposer: str,
        round_number: int,
        retry_cand: tuple[int, Any, datetime, float, tuple[Any, ...]] | None,
        pending_txs: Any,
    ) -> tuple[datetime, str, int] | None:
        """Re-derive ``(timestamp, proposer, round_number)`` after tx collect.

        When the drained tx set drifted from the pinned snapshot, the pinned
        timestamp would assemble a DIFFERENT hash — a rival inside
        attesters' lock window — so the pin is dropped, a fresh timestamp is
        stamped, and proposer/round are re-derived for it. Returns the
        (possibly unchanged) triple, or None when the proposal must abort
        (re-selection found no local turn or the journal holds).
        """
        if retry_cand is None or self._tx_snapshot_key(pending_txs) == retry_cand[4]:
            return timestamp, proposer, round_number
        # E c20986 option A: under traffic the pin degrades to fresh-hash
        # behaviour — never worse than today, and the drift is observable.
        metrics_registry.increment("proposer_same_hash_retry_tx_drift_total")
        self._same_hash_retry = None
        timestamp = datetime.now(UTC)
        selected = self._select_round_proposer(head, next_height, timestamp)
        if selected is None:
            return None
        proposer, round_number = selected
        if await self._honor_prior_votes(next_height, round_number, proposer):
            return None
        return timestamp, proposer, round_number

    def _note_same_hash_retry(self, next_height: int, parent_hash: Any, timestamp: datetime, tx_key: tuple[Any, ...]) -> None:
        """Remember this proposal's timestamp/parent/tx-set so a gate-failed
        retry can reuse the same hash while attesters' locks are still live."""
        if not getattr(settings, "proposer_same_hash_retry_enabled", False):
            self._same_hash_retry = None
            return
        horizon = self._same_hash_retry_horizon_seconds()
        if horizon <= 0:
            self._same_hash_retry = None
            if not self._same_hash_retry_horizon_warned:
                self._same_hash_retry_horizon_warned = True
                self._logger.warning(
                    "[PROPOSE] same-hash retry horizon is 0 (lock/header bound "
                    "%.0fs <= collect window + margin) — every retry will stamp "
                    "a fresh hash; check multi_validator_attestation_timeout_seconds "
                    "and proposer_same_hash_retry_margin_seconds",
                    min(
                        float(getattr(settings, "consensus_proposer_round_seconds", 60)),
                        float(getattr(settings, "attestation_header_max_age_seconds", 60)),
                    ),
                )
            return
        self._same_hash_retry = (next_height, parent_hash, timestamp, timestamp.timestamp() + horizon, tx_key)

    def _resolve_proposal_head(self, session: Session) -> tuple[Block | None, int, str, float | None] | None:
        """Fetch the chain head and validate proposal freshness.

        Returns ``(head, next_height, parent_hash, interval_seconds)``, or None
        when the proposal must be skipped: the parent state_root could not be
        repaired by ``_reapply_parent_block``, or the head is younger than the
        configured block interval. The session is rolled back on the reapply
        failure path.
        """
        from ..database import ensure_chain_db_healthy

        db_ok, db_reason = ensure_chain_db_healthy(self._config.chain_id, session=session)
        if not db_ok:
            self._logger.error(
                "[PROPOSE] Refusing block proposal on chain %s — chain.db integrity check failed: %s",
                self._config.chain_id,
                db_reason,
            )
            return None
        head = session.exec(
            select(Block).where(Block.chain_id == self._config.chain_id).order_by(text("height DESC")).limit(1)
        ).first()
        next_height = 0
        parent_hash = "0x00"
        interval_seconds: float | None = None
        if head is not None:
            next_height = head.height + 1
            parent_hash = head.hash
            # v0.25.4: a validator must not build on a stale local state. If the
            # parent block's state_root does not match the state we have locally,
            # re-apply the parent block before proposing. This prevents a
            # multi-validator proposer from building a block whose header state_root
            # ignores the previous block's state transition.
            if head.state_root:
                local_state_root = _compute_state_root(session, self._config.chain_id)
                if local_state_root != head.state_root:
                    self._logger.warning(
                        "[PROPOSE] Parent state mismatch at height %s: parent state_root=%s, local=%s",
                        head.height,
                        head.state_root,
                        local_state_root,
                    )
                    if not self._reapply_parent_block(session, head):
                        session.rollback()
                        return None
            head_timestamp = head.timestamp if head.timestamp.tzinfo is not None else head.timestamp.replace(tzinfo=UTC)
            # #1741: a wall clock behind the head's timestamp means every
            # proposer round still looks future-dated — proposing would stamp
            # a header attesters refuse as stale_header anyway, so skip here
            # where the skew was just detected and logged.
            if self._note_wall_clock_skew(head_timestamp):
                return None
            interval_seconds = (datetime.now(UTC) - head_timestamp).total_seconds()
            if interval_seconds < self._config.interval_seconds:
                self._logger.debug(
                    "[PROPOSE] Skipping block proposal: too soon after last block (chain=%s, elapsed=%ss, interval=%ss)",
                    self._config.chain_id,
                    interval_seconds,
                    self._config.interval_seconds,
                )
                return None
        return head, next_height, parent_hash, interval_seconds

    def _select_round_proposer(self, head: Block | None, next_height: int, timestamp: datetime) -> tuple[str, int] | None:
        """Pick the proposer for ``next_height`` at this proposal's round.

        Returns ``(proposer, round_number)``, or None when the proposal must be
        skipped: no proposer is available, or the selected proposer is not a
        local validator key in multi-validator mode.

        v0.25.6: the round is how long this height has gone without a
        block. Derive it from the timestamp this block will actually
        carry, because that is the timestamp every other node will use to
        work out which validator was entitled to propose it.
        """
        round_number = self._proposer_round(head.timestamp if head is not None else None, timestamp)
        proposer = self._select_proposer(next_height, round_number)
        if round_number:
            # In hybrid mode the heartbeat gate fires at >=round_seconds idle,
            # so every empty block legitimately lands at round 1 — warning there
            # is guaranteed noise on an idle chain. Round >=2 means the
            # scheduled owner AND its first fallback were both silent.
            log = self._logger.warning if round_number >= 2 else self._logger.info
            log(
                "[PROPOSE] Height %s has gone %s round(s) without a block; this round belongs to %s",
                next_height,
                round_number,
                proposer,
            )
        if not proposer:
            self._logger.warning("[PROPOSE] No proposer available for height %s, skipping", next_height)
            return None
        if self._multi_validator and proposer not in self._validator_keys:
            self._logger.warning(
                "[PROPOSE] Selected proposer %s is not a local key, skipping proposal at height %s",
                proposer,
                next_height,
            )
            return None
        return proposer, round_number

    def _persist_rejected_txs(
        self,
        session: Session,
        rejected: list[tuple[Any, str]],
        next_height: int,
        timestamp: datetime,
        *,
        commit: bool,
    ) -> None:
        """Write a terminal ``rejected`` status for drained txs the apply path
        refused (DRAIN-SKIP-SILENT-1, #669).

        A drained mempool entry is deleted whether or not it seals, so an
        invalid tx used to disappear without a trace — the submitter's hash
        query found nothing (or a pre-registered row sat pending forever).
        Each rejected tx is upserted into the ``transaction`` table with
        ``status='rejected'``, ``block_height=None`` and the reason in
        ``tx_metadata``, so ``GET /transactions/{tx_hash}`` reports the
        outcome. The ``transaction`` table is service state (not part of the
        committed side-root set), so a proposer-local row cannot diverge
        consensus; a resubmitted tx that later seals flips the same row back
        to ``confirmed`` through the normal ``existing_tx_record`` path.

        Rows already ``confirmed`` (pre-registered bridge rows, or sealed
        duplicates) are left untouched — their status is a ledger fact, not
        a mempool outcome. ``commit=True`` is for the abort paths, whose
        session was already rolled back and would otherwise drop the records.
        """
        if not rejected:
            return
        for tx, reason in rejected:
            try:
                existing = session.exec(
                    select(Transaction).where(
                        Transaction.chain_id == self._config.chain_id,
                        Transaction.tx_hash == tx.tx_hash,
                    )
                ).first()
                if existing is not None:
                    if existing.status == "confirmed":
                        continue
                    existing.status = "rejected"
                    existing.tx_metadata = _rejection_metadata(reason, next_height, timestamp)
                    session.add(existing)
                    continue
                tx_data = tx.content or {}
                session.add(
                    Transaction(
                        chain_id=self._config.chain_id,
                        tx_hash=tx.tx_hash,
                        sender=tx_data.get("from", ""),
                        recipient=tx_data.get("to", ""),
                        payload=tx_data.get("payload", {}),
                        envelope=dict(tx_data),
                        value=tx_data.get("amount", 0),
                        fee=tx_data.get("fee", 0),
                        nonce=tx_data.get("nonce", 0),
                        timestamp=None,
                        block_height=None,
                        status="rejected",
                        type=(tx_data.get("type") or "TRANSFER").upper(),
                        tx_metadata=_rejection_metadata(reason, next_height, timestamp),
                    )
                )
            except Exception as exc:
                self._logger.warning("[PROPOSE] Failed to record rejection for tx %s: %s", tx.tx_hash, exc)
        if commit:
            try:
                session.commit()
            except Exception as exc:
                session.rollback()
                self._logger.warning("[PROPOSE] Failed to commit rejected-tx records: %s", exc)

    def _process_proposal_txs(
        self,
        session: Session,
        pending_txs: list[Any],
        account_map: dict[str, Account],
        existing_tx_map: dict[str, int],
        next_height: int,
        timestamp: datetime,
        rejected: list[tuple[Any, str]] | None = None,
    ) -> tuple[list[Any], set[str], bool]:
        """Apply the drained transactions through the state transition.

        Returns ``(processed_txs, changed_addresses, ok)``. Uses the parallel
        path when the ``parallel_tx_validation`` feature flag (v0.6.1, default
        off) is on and more than one tx is pending, falling back to sequential
        processing when parallel returns nothing (e.g. the conflict rate
        exceeded threshold).
        """
        block_version = get_block_version_for_height(next_height)
        # S-4: v2/v3 blocks can use the parallel path once escrow lock metadata
        # is prefetched. If any release/refund references a job with no
        # resolvable lock, keep the block sequential so the sequential path's own
        # rules apply.
        # Side-effect types that the pure delta map cannot model must always go
        # through the full sequential state transition.
        has_sequential_only = any(_determine_tx_type(tx.content) in _SEQUENTIAL_ONLY_TX_TYPES for tx in pending_txs)
        escrow_context: dict[str, dict[str, Any]] | None = None
        bridge_lock_context: dict[str, dict[str, Any]] | None = None
        use_parallel = (
            not has_sequential_only
            and getattr(settings, "parallel_tx_validation", False)
            and len(pending_txs) > 1
            # v5/v6 included: their fail-closed gates are mirrored in
            # pure_state_transition (escrow authority via escrow_context,
            # bridge pseudo-sender + signature + refund lock binding via
            # bridge_lock_context), so the parallel path stays identical.
            # v7/v8 have no apply-rule additions for the types this path
            # handles (v7's GPU_REGISTER gate is sequential-only), and the pure
            # path now enforces signature + signed nonce too. Upper bound is
            # explicit: a future version defaults to sequential until the pure
            # path is audited for its rules.
            and 2 <= block_version <= 8
        )
        if use_parallel:
            escrow_context = build_escrow_context(
                session, self._config.chain_id, [tx.content for tx in pending_txs], block_height=next_height
            )
            if escrow_context is None:
                use_parallel = False
        if (
            use_parallel
            and block_version >= 6
            and any(_determine_tx_type(tx.content) == "BRIDGE_REFUND" for tx in pending_txs)
        ):
            # Two refunds naming the same lock cannot be resolved in parallel —
            # build_bridge_lock_context returns None and the block goes
            # sequential, which applies the double-refund rule in order.
            bridge_lock_context = build_bridge_lock_context(session, self._config.chain_id, [tx.content for tx in pending_txs])
            if bridge_lock_context is None:
                use_parallel = False
        if use_parallel:
            processed_txs, changed_addresses, ok = self._process_txs_parallel(
                session,
                pending_txs,
                account_map,
                existing_tx_map,
                next_height,
                timestamp,
                block_version,
                escrow_context,
                bridge_lock_context,
                rejected,
            )
            if not ok:
                return processed_txs, changed_addresses, False
            # If parallel returned nothing (e.g. conflict rate exceeded
            # threshold), fall back to sequential processing.
            if processed_txs or not pending_txs:
                return processed_txs, changed_addresses, ok
        return self._process_txs_sequential(
            session, pending_txs, account_map, existing_tx_map, next_height, timestamp, rejected
        )

    def _reject_if_all_invalid(self, session: Session, pending_txs: list[Any], processed_txs: list[Any]) -> bool:
        """Return True when every drained transaction was rejected and the
        proposal must abort.

        Rolls the session back first, so nothing a rejected transaction
        touched survives into the next proposal — the same contract the PBFT
        and attestation failure paths follow.
        """
        if not (pending_txs and (not processed_txs) and getattr(settings, "propose_only_if_mempool_not_empty", True)):
            return False
        self._logger.warning(
            "[PROPOSE] Skipping block proposal: all drained transactions were invalid (count=%s, chain=%s)",
            len(pending_txs),
            self._config.chain_id,
        )
        session.rollback()
        return True

    def _assemble_proposal_block(
        self,
        session: Session,
        next_height: int,
        parent_hash: str,
        timestamp: datetime,
        processed_txs: list[Any],
        proposer: str,
    ) -> tuple[Block, str]:
        """Compute the state roots and build the unsigned proposal block.

        Returns ``(block, block_hash)``. The block hash binds chain, height,
        parent, time, txs, proposer, account state root, and bridge event
        trie root (v0.7.2).
        """
        # Compute state root from the full account state. The previous
        # "incremental" approach created a fresh trie per call but only
        # populated it with changed accounts — producing a wrong root that
        # excluded all other accounts. Since the trie is not persisted across
        # blocks, a full recompute is the only correct option.
        state_root = _compute_state_root(session, self._config.chain_id)
        # v0.7.2: compute the bridge event trie root from BRIDGE_LOCK events.
        bridge_state_root = self._compute_bridge_state_root(session, processed_txs, self._config.chain_id, next_height)
        # V-4 dry-run missing-data guard (flag-gated, logs/counts only —
        # the block below is built exactly as before).
        bridge_lock_guard.run_guard_dryrun(processed_txs, height=next_height, chain_id=self._config.chain_id, log=self._logger)
        # v14 (V-3): commit the 13-table side-table root fingerprint into the
        # header as aux_state_root. It is computed over the committed set after
        # this block's transactions applied — flush so the fingerprint sees
        # them. Below the shared activation height it stays None and the hash
        # preimage is byte-identical to the old formula.
        aux_state_root = None
        next_block_version = get_block_version_for_height(next_height)
        if next_block_version >= 14:
            session.flush()
            aux_state_root = side_root_shadow.committed_fingerprint(session.connection().connection, next_block_version)[
                "fingerprint"
            ]
        # v0.7.2: block hash binds chain, height, parent, time, txs,
        # proposer, account state root, and bridge event trie root.
        block_hash = self._compute_block_hash(
            next_height, parent_hash, timestamp, processed_txs, proposer, state_root, bridge_state_root, aux_state_root
        )

        block = Block(
            chain_id=self._config.chain_id,
            height=next_height,
            hash=block_hash,
            parent_hash=parent_hash,
            proposer=proposer,
            timestamp=timestamp,
            tx_count=len(processed_txs),
            state_root=state_root,
            bridge_state_root=bridge_state_root,
            aux_state_root=aux_state_root,
            signature="",
            block_metadata=None,
        )
        return block, block_hash

    async def _run_consensus_gates(
        self,
        session: Session,
        block: Block,
        block_hash: str,
        proposer: str,
        round_number: int,
        next_height: int,
        metadata_dict: dict[str, Any],
        transactions: list[dict[str, Any]] | None = None,
    ) -> bool:
        """Run the post-assembly consensus gates: the PBFT round and the
        attestation collection.

        Rolls the session back and returns False on abort or failure — the
        caller only has to propagate the False.
        """
        # v0.7.7: if PBFT is enabled, run the full consensus round before
        # writing the block. The block hash is the digest of the proposed
        # block and the certificate is stored in block_metadata.
        if self._stop_event.is_set():
            session.rollback()
            return False
        if self._pbft_consensus:
            pbft_ok = await self._pbft_consensus.propose_and_wait(
                proposer,
                block_hash,
                timeout=getattr(settings, "pbft_view_change_timeout", 30),
                sequence=next_height,
                view=round_number,
            )
            if not pbft_ok:
                self._logger.warning(
                    "PBFT consensus failed for block %s on chain %s; skipping proposal",
                    next_height,
                    self._config.chain_id,
                )
                session.rollback()
                return False

        # v0.7.5: collect attestations from other local validators and store
        # them in block_metadata as JSON. The proposer signature remains the
        # canonical block signature.
        if self._stop_event.is_set():
            session.rollback()
            return False

        if not await self._collect_and_gate_attestations(
            block, block_hash, metadata_dict, transactions, round_number=round_number
        ):
            session.rollback()
            return False
        return True

    def _note_wall_clock_skew(self, head_timestamp: datetime | None) -> float:
        """#1741: detect a wall clock behind the chain's latest header timestamp.

        Proposer rounds derive from ``now - head.timestamp`` deltas, so a
        clock more than ``attestation_header_future_skew_seconds`` behind
        makes every scheduled slot look future-dated: the node silently
        stops proposing (and, via #1709, attesting) while peers see only
        round-robin fallthrough. Returns the estimated lag in seconds —
        ``0.0`` when there is no head or the clock is not behind — and
        publishes ``proposer_clock_behind_seconds`` every call plus a
        throttled CRITICAL log while the skew persists.

        Detection only, deliberately: stamping a corrected timestamp or
        re-deriving rounds from monotonic time changes what the signed
        header timestamp means and how every node computes the claimed
        round — consensus-semantics territory left for E/Validator review.
        """
        if head_timestamp is None:
            return 0.0
        if head_timestamp.tzinfo is None:
            head_timestamp = head_timestamp.replace(tzinfo=UTC)
        behind = (head_timestamp - datetime.now(UTC)).total_seconds()
        metrics_registry.set_gauge("proposer_clock_behind_seconds", max(0.0, behind))
        skew_bound = float(getattr(settings, "attestation_header_future_skew_seconds", 10.0))
        if behind <= skew_bound:
            return 0.0
        metrics_registry.increment("proposer_clock_skew_detected_total")
        now_mono = self._monotonic()
        if now_mono - self._clock_skew_warned_at >= _CLOCK_SKEW_WARN_INTERVAL_SECONDS:
            self._clock_skew_warned_at = now_mono
            self._logger.error(
                "[PROPOSE] Wall clock is ~%.0fs behind the chain head timestamp %s — "
                "proposer rounds derive from wall-clock deltas, so this node's "
                "scheduled turns never come due and it is silently out of consensus "
                "until the clock is fixed (Refs #1741, #1709)",
                behind,
                head_timestamp.isoformat(),
            )
        return behind

    def _selected_proposer_is_local(self, head: Block | None) -> bool:
        """Return False when the selected proposer for the next height is not
        one of this node's validator keys.

        In multi-validator mode this prevents follower nodes from repeatedly
        forcing heartbeat blocks, draining the mempool, and recomputing state
        roots when they cannot sign.
        """
        # #1741: this gate is exactly where a behind-clock node exits
        # silently — the skewed round selects somebody else's slot every
        # iteration, so _resolve_proposal_head never runs. Detect here.
        if head is not None:
            self._note_wall_clock_skew(head.timestamp)
        next_height = (head.height + 1) if head is not None else 0
        proposer = self._select_proposer(
            next_height,
            self._proposer_round(head.timestamp if head is not None else None, datetime.now(UTC)),
        )
        if self._multi_validator and proposer and proposer not in self._validator_keys:
            self._logger.debug(
                "[PROPOSE] Proposer %s for height %s is not a local key, skipping quietly (chain=%s)",
                proposer,
                next_height,
                self._config.chain_id,
            )
            return False
        return True

    def _should_skip_for_empty_mempool(self, head: Block | None, mempool: InMemoryMempool | DatabaseMempool) -> bool:
        """Apply the ``block_generation_mode`` empty-mempool gate.

        Returns True when the proposal should be skipped: in ``mempool-only``
        mode whenever the mempool is empty, and in ``hybrid`` mode when the
        heartbeat gate says no heartbeat block is due.
        """
        block_generation_mode = getattr(settings, "block_generation_mode", "hybrid")
        max_empty_block_interval = getattr(settings, "max_empty_block_interval", 60)
        if block_generation_mode not in ["mempool-only", "hybrid"]:
            return False
        mempool_size = mempool.size(self._config.chain_id)
        if block_generation_mode == "mempool-only":
            if mempool_size == 0:
                self._logger.debug(
                    "[PROPOSE] Skipping block proposal: mempool is empty (chain=%s, mode=mempool-only)",
                    self._config.chain_id,
                )
                metrics_registry.increment("sync_empty_blocks_skipped_total")
                return True
            return False
        return self._hybrid_empty_mempool_gate(head, mempool_size, max_empty_block_interval)

    def _hybrid_empty_mempool_gate(self, head: Block | None, mempool_size: int, max_empty_block_interval: int) -> bool:
        """Hybrid-mode half of the empty-mempool gate.

        Returns True when the proposal should be skipped because the mempool
        is empty and either the heartbeat interval has not elapsed or no
        previous block timestamp exists. Emits the heartbeat metrics when a
        heartbeat block is due and the proposal proceeds.
        """
        last_block_timestamp = head.timestamp if head is not None else self._last_block_timestamp
        if last_block_timestamp:
            last_timestamp = (
                last_block_timestamp if last_block_timestamp.tzinfo is not None else last_block_timestamp.replace(tzinfo=UTC)
            )
            time_since_last_block = (datetime.now(UTC) - last_timestamp).total_seconds()
            if mempool_size == 0 and time_since_last_block < max_empty_block_interval:
                self._logger.debug(
                    "[PROPOSE] Skipping block proposal: mempool empty, heartbeat not yet due (chain=%s, mode=hybrid, idle_time=%ss)",
                    self._config.chain_id,
                    time_since_last_block,
                )
                metrics_registry.increment("sync_empty_blocks_skipped_total")
                return True
            elif mempool_size == 0 and time_since_last_block >= max_empty_block_interval:
                self._logger.info(
                    "[PROPOSE] Forcing heartbeat block: idle for %ss (chain=%s, mode=hybrid)",
                    time_since_last_block,
                    self._config.chain_id,
                )
                metrics_registry.increment("sync_heartbeat_blocks_forced_total")
                metrics_registry.observe("sync_time_since_last_block_seconds", time_since_last_block)
        elif mempool_size == 0:
            self._logger.debug(
                "[PROPOSE] Skipping block proposal: no previous block timestamp (chain=%s, mode=hybrid)",
                self._config.chain_id,
            )
            metrics_registry.increment("sync_empty_blocks_skipped_total")
            return True
        return False

    def _select_mempool_txs(
        self,
        session: Session,
        mempool: InMemoryMempool | DatabaseMempool,
        max_txs: int,
        max_bytes: int,
        *,
        reservation_owner: str = "",
        reservation_proposer: str = "",
        reservation_height: int | None = None,
        reservation_round: int | None = None,
        reservation_attempt: int = 0,
    ) -> tuple[list[Any], set[str]]:
        """#1300: reconcile sealed rows, then drain — or peek_reserve when the
        reservation flag is armed on the database backend (S3)."""
        # Reconcile sealed rows before selecting — a tx sealed via a peer's
        # block must not be re-proposed as a duplicate. Read-only on the
        # proposal session; reconcile_sealed owns its own mempool txn.
        pooled_hashes = mempool.pending_tx_hashes(self._config.chain_id)
        if pooled_hashes:
            sealed_rows = session.exec(
                select(Transaction.tx_hash).where(
                    Transaction.chain_id == self._config.chain_id,
                    Transaction.status == "confirmed",
                    Transaction.block_height.is_not(None),  # type: ignore[union-attr]
                    Transaction.tx_hash.in_(sorted(pooled_hashes)),  # type: ignore[attr-defined]
                )
            ).all()
            if sealed_rows:
                mempool.reconcile_sealed(self._config.chain_id, sealed_rows)
        if settings.mempool_reservation_enabled and reservation_owner and reservation_height is not None:
            from ..mempool import DatabaseMempool

            if isinstance(mempool, DatabaseMempool):
                peeked = mempool.peek_reserve(
                    self._config.chain_id,
                    owner_id=reservation_owner,
                    proposer=reservation_proposer,
                    height=reservation_height,
                    round=reservation_round,
                    attempt_seq=reservation_attempt,
                    max_count=max_txs,
                    max_bytes=max_bytes,
                )
                pending_txs = list(peeked)
                self._logger.info(
                    "[PROPOSE] peek_reserve selected %s txs (owner=%s, height=%s), chain=%s",
                    len(pending_txs),
                    reservation_owner,
                    reservation_height,
                    self._config.chain_id,
                )
                return pending_txs, {tx.tx_hash for tx in pending_txs}
        return list(mempool.drain(max_txs, max_bytes, self._config.chain_id)), set()

    def _collect_proposal_txs(
        self,
        session: Session,
        mempool: InMemoryMempool | DatabaseMempool,
        *,
        reservation_owner: str = "",
        reservation_proposer: str = "",
        reservation_height: int | None = None,
        reservation_round: int | None = None,
        reservation_attempt: int = 0,
    ) -> tuple[list[Any], dict[str, Account], dict[str, int], set[str]]:
        """Drain the mempool and batch-fetch the state the tx loop needs.

        Returns ``(pending_txs, account_map, existing_tx_map, reserved_hashes)``:
        the drained transactions plus pre-registered, still-unassigned DB
        transactions (e.g. bridge releases), the batch-fetched sender/recipient
        accounts, the tx_hash → block_height map used for duplicate detection,
        and the set of tx_hashes this attempt reserved (empty unless
        ``mempool_reservation_enabled`` and the database backend is active —
        #1300 P2-v2.4/S3).
        """
        from ..mempool import PendingTransaction as MempoolPendingTx

        max_txs = self._config.max_txs_per_block
        max_bytes = self._config.max_block_size_bytes
        pending_txs, reserved_hashes = self._select_mempool_txs(
            session,
            mempool,
            max_txs,
            max_bytes,
            reservation_owner=reservation_owner,
            reservation_proposer=reservation_proposer,
            reservation_height=reservation_height,
            reservation_round=reservation_round,
            reservation_attempt=reservation_attempt,
        )
        self._logger.info("[PROPOSE] drained %s txs from mempool, chain=%s", len(pending_txs), self._config.chain_id)
        # Include transactions that were pre-registered in the DB (e.g. bridge releases)
        # but not yet assigned to a block.
        pre_registered = session.exec(
            select(Transaction).where(
                Transaction.chain_id == self._config.chain_id,
                Transaction.block_height.is_(None),  # type: ignore[union-attr]
                Transaction.status == "confirmed",
            )
        ).all()
        for tx_rec in pre_registered:
            content = {
                "from": tx_rec.sender or "bridge_release",
                "to": tx_rec.recipient or "",
                "amount": tx_rec.value or 0,
                "value": tx_rec.value or 0,
                "fee": tx_rec.fee or 0,
                "nonce": tx_rec.nonce or 0,
                "type": tx_rec.type or "TRANSFER",
                "payload": tx_rec.payload or {},
                "signature": "",
            }
            pending_txs.append(
                MempoolPendingTx(
                    tx_hash=tx_rec.tx_hash,
                    content=content,
                    received_at=0.0,
                    fee=content["fee"],  # type: ignore[arg-type]
                    size_bytes=len(str(content).encode()),
                )
            )
        if pre_registered:
            self._logger.info("[PROPOSE] added %s pre-registered DB txs, chain=%s", len(pre_registered), self._config.chain_id)
        # Batch-fetch all unique sender, recipient and v3 escrow accounts in one
        # query (eliminates the per-tx session.get() round-trips).
        unique_addresses: set[str] = set()
        for tx in pending_txs:
            tx_data = tx.content
            sender = _to_ait_address(tx_data.get("from", ""))
            recipient = _to_ait_address(tx_data.get("to", ""))
            if sender:
                unique_addresses.add(sender)
            if recipient:
                unique_addresses.add(recipient)
        unique_addresses.update(_escrow_addresses_from_txs([tx.content for tx in pending_txs]))
        account_map: dict[str, Account] = {}
        if unique_addresses:
            existing_accounts = session.exec(
                select(Account).where(
                    Account.chain_id == self._config.chain_id,
                    Account.address.in_(unique_addresses),  # type: ignore[attr-defined]
                )
            ).all()
            account_map = {acc.address: acc for acc in existing_accounts}
        # Batch-fetch duplicate tx hashes in one query (eliminates the
        # per-tx duplicate-check DB round-trip).
        existing_tx_map: dict[str, int] = {}
        if pending_txs:
            existing_tx_rows = session.execute(
                select(Transaction.tx_hash, Transaction.block_height).where(
                    Transaction.chain_id == self._config.chain_id,
                    Transaction.tx_hash.in_([tx.tx_hash for tx in pending_txs]),  # type: ignore[attr-defined]
                )
            ).all()
            existing_tx_map = {row[0]: row[1] for row in existing_tx_rows}
        return pending_txs, account_map, existing_tx_map, reserved_hashes

    def _evict_mempool_txs(self, mempool: InMemoryMempool | DatabaseMempool, txs: list[Any]) -> None:
        """Remove terminal (apply-rejected) txs from the pool after their
        reservations are released — reserved rows are protected from the
        generic deleters, so release must happen first (#1300 §3)."""
        hashes = [tx.tx_hash for tx in txs]
        if not hashes:
            return
        try:
            mempool.batch_remove(hashes, self._config.chain_id)
        except Exception as exc:
            self._logger.warning("[PROPOSE] mempool eviction of %d rejected txs failed: %s", len(hashes), exc)
