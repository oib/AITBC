"""Equivocation, abandon, and evidence replication hooks (#1950 pure-move split)."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any


from aitbc.crypto.signature_recovery import canonical_address

from ..config import settings
from ..metrics import metrics_registry
from . import abandon, evidence_replication
from .vote_journal import get_vote_journal, vote_journal_enabled
from .remote_attestation_crypto import (
    _active_signature_domain,
)
from . import remote_attestation as _ra

if TYPE_CHECKING:
    import logging

    logger: logging.Logger
else:
    logger = _ra.logger

from .remote_attestation import _V9Mixin


class _EvidenceMixin(_V9Mixin):
    if TYPE_CHECKING:

        def _ensure_round_locks_loaded(self, *args: Any, **kwargs: Any) -> Any: ...
        def _persist_round_locks(self, *args: Any, **kwargs: Any) -> Any: ...
        def _round_lock_enabled(self, *args: Any, **kwargs: Any) -> Any: ...

    def handle_evidence(self, payload: Any) -> evidence_replication.Outcome:
        """Ingest one replicated record; a slashable pair is recorded as advisory
        evidence through the same recorder local detection uses. Never re-published
        (a record received from a peer is not a local observation). Handler-level
        flag gate (like ``handle_abandon``): OFF ingests nothing, whoever calls it."""
        if not evidence_replication.enabled():
            return evidence_replication.Outcome("disabled")
        outcome = evidence_replication.ingest(self._chain_id, payload, self._validator_set_addresses())
        if outcome.status != "stored" or not outcome.slashable or outcome.record is None:
            return outcome
        rec = outcome.record
        recorder = self._equivocation_recorder()
        defer_save = callable(getattr(recorder, "save_state", None))
        extra: dict[str, Any] = {"persist": False} if defer_save else {}
        try:
            recorder.record_attestation_equivocation(
                validator_address=rec["validator"],
                height=rec["height"],
                round_number=rec["round"],
                block_hash_a=rec["block_hash_a"],
                block_hash_b=rec["block_hash_b"],
                proposer=str(rec["attestations"][0].get("proposer", "")),
                attestations=rec["attestations"],
                **extra,
            )
        except Exception as e:  # noqa: BLE001 - evidence is advisory; never break the listener
            metrics_registry.increment("equivocation_ingest_record_failed_total")
            logger.warning("Failed to record replicated equivocation evidence: %s", e)
            return outcome
        metrics_registry.increment("equivocation_ingest_recorded_total")
        if defer_save:
            self._schedule_deferred_state_save(recorder)
        return outcome

    def _emit_evidence(
        self, signer: str, height: int, round_: int | None, hash_a: str, hash_b: str, attestations: list[dict[str, Any]]
    ) -> None:
        """#1311: publish one locally observed signed pair (bounded, best effort).

        Only round-bound same-round pairs are emitted — a cross-round or legacy
        pair is local context, not slashable. Called only from local detection,
        so ingested records are never re-emitted.
        """
        if not evidence_replication.enabled() or round_ is None:
            return
        record = evidence_replication.build_record(self._chain_id, signer, height, round_, hash_a, hash_b, attestations)
        if evidence_replication.classify_attestation_pair(record) is not evidence_replication.PairClass.ROUND_BOUND_SAME_ROUND:
            return
        store = evidence_replication.get_store(self._chain_id)
        key = evidence_replication.pair_key(self._chain_id, signer, height, round_, hash_a, hash_b)
        store.add_if_absent(key, record)
        if not store.may_publish(key):
            metrics_registry.increment("equivocation_republish_suppressed_total")
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        task = loop.create_task(_ra.gossip_broker.publish(evidence_replication.equivocation_topic(self._chain_id), record))
        self._deferred_state_saves.add(task)
        task.add_done_callback(self._deferred_state_saves.discard)
        metrics_registry.increment("equivocation_published_total")

    def handle_abandon(self, payload: Any) -> int:
        """Apply one abandon statement; returns how many local votes it released.

        Flag-gated at the handler as well as at the listener (#1301): with the
        feature OFF a directly delivered statement releases nothing and moves
        no metric, so OFF safety no longer rests on the listener alone.
        """
        if not abandon.abandon_enabled():
            return 0
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
            self._note_abandoned_height(height, block_hash)
        if (released or locks) and stmt.get("round") is not None:
            self._note_abandoned_round(height, int(stmt["round"]), block_hash)
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

    def _note_abandoned_round(self, height: int, round_: int, block_hash: str) -> None:
        self._abandoned_rounds.setdefault((height, round_), set()).add(block_hash)
        for key in [k for k in self._abandoned_rounds if k[0] < height - 64]:
            del self._abandoned_rounds[key]

    def _note_abandoned_height(self, height: int, block_hash: str) -> None:
        """#1940 F2: height-level abandoned index for the round-underivable case.

        ``_abandoned_rounds`` needs a round; below the domain-separation
        height (or whenever the request carries none) the round is
        underivable, so a rival at the same height cannot be proven
        same-round vs cross-round. Recording the abandoned hash per height
        lets the listener fail closed instead.
        """
        self._abandoned_heights.setdefault(height, set()).add(block_hash)
        for h in [k for k in self._abandoned_heights if k < height - 64]:
            del self._abandoned_heights[h]

    def _abandoned_height_rival(self, height: int, block_hash: str) -> str | None:
        """An abandoned hash at ``height`` when the request round is underivable.

        Cannot distinguish same-round (slashable, unexcusable) from
        cross-round — fail closed on any different hash. Re-signing the
        abandoned hash itself stays allowed.
        """
        hashes = self._abandoned_heights.get(height)
        if hashes and block_hash not in hashes:
            return next(iter(sorted(hashes)))
        return None

    def _uc_unlock_justification(
        self,
        bundle: dict[str, Any] | None,
        prior: dict[str, Any] | None,
        current: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        """Consumer-shaped UC excuse for one equivocation pair, or None (#1940 F1).

        ``equivocation_policy._uc_justified`` wants
        ``{"kind": "uc", "cert": <cert>}`` bound to the EARLIER-round
        record's ``(height, hash)``; the producer bundle carries one cert
        per already-voted hash. Select on ``cert["hash"]`` — never on
        ``hashes[]`` index alignment. Any ambiguity (missing bundle, legacy
        or equal rounds, no matching cert) fails closed to None.
        """
        if not bundle or prior is None or current is None:
            return None
        r_prior = prior.get("request_round")
        r_current = current.get("request_round")
        if not (isinstance(r_prior, int) and isinstance(r_current, int)):
            return None
        if isinstance(r_prior, bool) or isinstance(r_current, bool) or r_prior == r_current:
            return None
        locked = prior if r_prior < r_current else current
        locked_hash = str(locked.get("hash", ""))
        if not locked_hash:
            return None
        for cert in bundle.get("certs") or []:
            if isinstance(cert, dict) and str(cert.get("hash", "")) == locked_hash:
                return {"kind": "uc", "cert": cert}
        return None

    def _abandoned_round_rival(self, height: int, round_: int, block_hash: str) -> str | None:
        """The abandoned hash this request would pair against in the same round, or None (#1736).

        After an abandon-release the validator may sign a rival only in a LATER round: a same-round
        rival forms a ROUND_BOUND_SAME_ROUND pair, which is slashable and carries no justification.
        Re-signing the abandoned hash itself is not equivocation and stays allowed.
        """
        hashes = self._abandoned_rounds.get((height, round_))
        if hashes and block_hash not in hashes:
            return next(iter(sorted(hashes)))
        return None

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
        entries = []
        for key, rec in self._signed_attestations.items():
            try:
                entries.append((key, rec, int(rec["height"])))
            except (KeyError, TypeError, ValueError):
                continue
        cap = _ra.SIGNED_ONCE_MAX_HEIGHTS
        cutoff = (max(h for _, _, h in entries) - cap) if entries else 0
        records = [{"key": key, "record": rec} for key, rec, h in entries if h >= cutoff]
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
        # #1298 T7a: ``round_in_payload``/``request_round`` describe the
        # message that was ACTUALLY signed — post-activation the round is in
        # the payload whether or not round_lock was armed, so both fields are
        # derived from ``message`` rather than the flag. On-chain
        # verification rebuilds the preimage from exactly these fields.
        round_in_payload = "round" in message
        record = {
            "chain_id": message.get("chain_id", self._chain_id),
            "height": message.get("height", height),
            "hash": message.get("hash", block_hash),
            "parent_hash": message.get("parent_hash", ""),
            "proposer": message.get("proposer", ""),
            "state_root": message.get("state_root", ""),
            "bridge_state_root": message.get("bridge_state_root", ""),
            "round_in_payload": round_in_payload,
            "request_round": message.get("round") if round_in_payload else None,
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
            except Exception as e:  # noqa: BLE001 - multi-validator consensus optional
                logger.debug("multi-validator consensus unavailable: %s", type(e).__name__)
        return slashing_manager

    def _prior_signed_hashes(self, height: int, block_hash: str, signer: str) -> set[str]:
        """Hashes this signer already signed at ``height`` (excluding ``block_hash``)."""
        # #1298: ``_signed_once`` is domain-keyed — prior hashes union across
        # ALL domains; the per-domain pairing lookup then binds each hash to
        # the record minted under the same domain.
        prior_hashes = {h for domains in self._signed_once.get(height, {}).values() for h in domains}
        prior_hashes |= {entry.block_hash for (h, _r, _d), entry in self._round_locks.items() if h == height}
        if vote_journal_enabled():
            # #1268: the journal survives restarts and the valve, so a rival
            # signed after either is still certified against the prior vote.
            prior_hashes |= {r.block_hash for r in get_vote_journal(self._chain_id).votes_at(height, signer)}
        prior_hashes.discard(block_hash)
        return prior_hashes

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
        prior_hashes = self._prior_signed_hashes(height, block_hash, signer)
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
        # #1940 F1: the UC bundle that released THIS vote (keyed by the new
        # hash). Only meaningful for attestation-domain records — the excuse
        # binds signed attestation rounds, never proposal signatures.
        from aitbc.crypto.consensus_signing import DOMAIN_BLOCK_ATTESTATION

        uc_bundle = (
            self._vote_justifications.get((height, block_hash))
            if signature_domain in (None, DOMAIN_BLOCK_ATTESTATION)
            else None
        )
        recorded = False
        for prior_hash in sorted(prior_hashes):
            prior = self._signed_attestations.get(self._signed_attestation_key(height, prior_hash, signer, signature_domain))
            attestations = [prior, current] if prior is not None else None
            unlock_just = self._uc_unlock_justification(uc_bundle, prior, current)
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
                    unlock_justification=unlock_just,
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
            else:
                if attestations is not None and justification is None:
                    try:
                        self._emit_evidence(canon, height, request_round, prior_hash, block_hash, attestations)
                    except Exception as e:  # noqa: BLE001 - replication is best effort
                        logger.warning("Failed to emit equivocation evidence for %s: %s", canon, e)
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
        delay = _ra.DEFERRED_SAVE_RETRY_DELAY
        attempts = _ra.DEFERRED_SAVE_ATTEMPTS
        for attempt in range(attempts):
            try:
                ok = await asyncio.to_thread(save)
            except Exception as e:  # noqa: BLE001 - never let evidence persistence kill the task silently
                logger.warning("Deferred consensus state save raised: %s", e)
                ok = False
            if ok is not False:
                return
            if attempt + 1 < attempts:
                await asyncio.sleep(delay)
                delay = min(delay * 2, _ra.DEFERRED_SAVE_RETRY_MAX_DELAY)
        metrics_registry.increment("proposal_equivocation_persist_failed_total")
        logger.error("Deferred consensus state save gave up after %d attempts for %s", attempts, self._chain_id)

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
