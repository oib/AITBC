"""Proposer-side attestation collection (#1950 pure-move split)."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any


from aitbc.crypto.consensus_signing import (
    verify_block_signature,
)
from aitbc.crypto.signature_recovery import canonical_address

from ..config import settings
from ..metrics import metrics_registry
from ..models import Block
from .remote_attestation_crypto import (
    _attestation_domain_active,
    _attestation_message,
    _verify_attestation,
)
from . import attest_response_diag
from . import remote_attestation as _ra

if TYPE_CHECKING:
    import logging

    logger: logging.Logger
else:
    logger = _ra.logger

from .remote_attestation import _RoundLockMixin


class _CollectMixin(_RoundLockMixin):
    def _log_zero_seen_diagnostic(self, height: int, sub: Any) -> None:
        """#1998 H4: one WARNING line when a collect saw no response at all.

        Reports the transient subscription's counters next to what the persistent
        observer saw for this height, so "never reached the node" / "reached the
        observer but not the collector" / "subscription ended" can be told apart.
        Observational only.
        """
        stats = dict(getattr(sub, "stats", None) or {})
        queue = getattr(sub, "queue", None)
        metrics_registry.increment("attest_collect_zero_seen_total")
        logger.warning(
            "Attestation collect 0/0 diagnostic: height=%s topic=%s sub_stats=%s sub_qsize=%s observer_responses=%d",
            height,
            self._response_topic,
            stats,
            queue.qsize() if queue is not None else None,
            attest_response_diag.observer_count(height),
        )

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
        # #1242/#1298 T7a: the request declares its round under round_lock at
        # any height AND unconditionally at/above the domain-separation
        # height — attesters refuse a missing/mismatched declared round
        # post-H, and the attestation signature covers the derived round.
        # The value is derived exactly the way attesters derive it (sealed
        # parent ts + block ts + window), so an honest attester's independent
        # derivation always matches.
        collect_round: int | None = None
        round_lock = self._round_lock_enabled()
        if round_lock or _attestation_domain_active(block.height):
            collect_round = self._collect_round_for_block(block)
            if collect_round is None:
                logger.warning(
                    "Round authentication armed but round underivable for height %s — remote attestations will be refused",
                    block.height,
                )
            else:
                header["round"] = collect_round
            # Attesters derive the round from the SIGNED block timestamp in
            # the request header — carry it whenever round authentication is
            # armed, not only when a transaction list rides along (the
            # transactions branch below sets the same field).
            if "timestamp" not in header:
                header["timestamp"] = block.timestamp.isoformat() if block.timestamp else ""
        request: dict[str, Any] = {"header": header, "timestamp": _ra.time.time()}
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
            sub = await _ra.gossip_broker.subscribe(self._response_topic, max_queue_size=1000)
        except Exception as e:
            logger.warning("Failed to subscribe to attestation responses: %s", e)
            return []

        try:
            await _ra.gossip_broker.publish(self._request_topic, request)
        except Exception as e:
            logger.warning("Failed to publish attestation request: %s", e)
            sub.close()  # noqa: unawaited-async — TopicSubscription.close() is synchronous
            return []

        attestations: list[dict[str, str]] = []
        start = _ra.time.monotonic()

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
            while _ra.time.monotonic() - start < effective_timeout:
                remaining = effective_timeout - (_ra.time.monotonic() - start)
                if quorum_at is not None:
                    remaining = min(remaining, linger - (_ra.time.monotonic() - quorum_at))
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
                arrived_ms = int((_ra.time.monotonic() - start) * 1000)
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
                response_round = response.get("round")
                round_mismatch = False
                if collect_round is not None:
                    if round_lock:
                        round_mismatch = response_round != collect_round
                    else:
                        # #1298 T7a: post-H round authentication without
                        # round_lock — a response that declares NO round is a
                        # pre-slice signer; let signature verification decide
                        # (the dual-accept window still applies). A declared
                        # but wrong round is junk and is dropped here.
                        try:
                            round_mismatch = response_round is not None and int(response_round) != collect_round
                        except (TypeError, ValueError):
                            round_mismatch = True
                if round_mismatch:
                    # A response minted for a different round can never count
                    # toward this round's quorum — even if the hash matches.
                    logger.info(
                        "Attestation arrival: height=%s validator=%s arrived_ms=%d outcome=wrong_round response_round=%s",
                        block.height,
                        validator,
                        arrived_ms,
                        response_round,
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
                        if not sig_ok and not round_lock and _attestation_domain_active(block.height):
                            # #1298 T7a/T13: post-H round authentication without
                            # round_lock — a response without round binding
                            # (pre-slice signer, or a legacy attestation inside
                            # the [H,S) dual-accept window) still gets its
                            # unbound-message chance; the domain/legacy rules
                            # inside _verify_attestation decide. Round-lock
                            # stays strict: no unbound fallback there.
                            sig_ok = _verify_attestation(
                                _attestation_message(header, self._chain_id), signature, validator, block.height
                            )
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
                        quorum_at = _ra.time.monotonic()
                    elif _ra.time.monotonic() - quorum_at >= linger:
                        break
        finally:
            if not seen_validators:
                # Before close(): the subscription's counters must read as they
                # were when the collect gave up (#1998 H4).
                self._log_zero_seen_diagnostic(block.height, sub)
            sub.close()  # noqa: unawaited-async — TopicSubscription.close() is synchronous
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
                int((_ra.time.monotonic() - start) * 1000),
            )

        return attestations
