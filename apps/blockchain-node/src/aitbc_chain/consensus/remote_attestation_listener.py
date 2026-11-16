"""Gossip listener tasks and attestation request handling for ``RemoteAttestationService`` (#1950 pure-move split)."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import select

from aitbc.async_tasks import create_task_with_logging
from aitbc.crypto.consensus_signing import (
    verify_block_signature,
)
from aitbc.crypto.signature_recovery import canonical_address

from ..config import settings
from ..metrics import metrics_registry
from ..models import Block
from ..state.v9_policy import count_v9_would_reject
from . import abandon, attest_response_diag, evidence_replication, unavail
from .vote_journal import vote_journal_enabled
from .remote_attestation_crypto import (
    _attestation_domain_active,
    _attestation_message,
    _attestation_signature_domain,
    _same_address,
    _sign_attestation,
    _verify_attestation,
    attestation_lock_window_seconds,
)
from . import remote_attestation as _ra

if TYPE_CHECKING:
    import logging

    logger: logging.Logger
else:
    logger = _ra.logger

from .remote_attestation import _RaBaseMixin


@dataclass
class _AttestRequestCtx:
    """Verified-request context shared by the per-key signing helpers."""

    request: dict[str, Any]
    header: dict[str, Any]
    proposer: str
    height_int: int
    header_hash: str
    request_round: int | None
    request_cert: Any
    round_lock: bool
    att_sig_domain: Any
    validator_set: set[str]
    header_age: float | None
    lock_minted: bool = False


class _ListenerMixin(_RaBaseMixin):
    if TYPE_CHECKING:

        def _abandoned_round_rival(self, *args: Any, **kwargs: Any) -> Any: ...
        def _abandoned_height_rival(self, *args: Any, **kwargs: Any) -> Any: ...
        def _derive_request_round(self, *args: Any, **kwargs: Any) -> Any: ...
        def _round_lock_enabled(self, *args: Any, **kwargs: Any) -> Any: ...
        def _ensure_round_locks_loaded(self, *args: Any, **kwargs: Any) -> Any: ...
        def _header_age_seconds(self, *args: Any, **kwargs: Any) -> Any: ...
        def _header_freshness_refusal(self, *args: Any, **kwargs: Any) -> Any: ...
        def _record_attestation_equivocation_evidence(self, *args: Any, **kwargs: Any) -> Any: ...
        def _record_attestation_lock(self, *args: Any, **kwargs: Any) -> Any: ...
        def _record_pre_sign_lock(self, *args: Any, **kwargs: Any) -> Any: ...
        def _record_request_seen(self, *args: Any, **kwargs: Any) -> Any: ...
        def _record_signed_attestation(self, *args: Any, **kwargs: Any) -> Any: ...
        def _run_v9_check(self, *args: Any, **kwargs: Any) -> Any: ...
        def attestation_lock(self, *args: Any, **kwargs: Any) -> Any: ...
        def round_lock_verdict(self, *args: Any, **kwargs: Any) -> Any: ...
        def _signed_once_contains(self, *args: Any, **kwargs: Any) -> Any: ...
        def handle_abandon(self, *args: Any, **kwargs: Any) -> Any: ...
        def handle_evidence(self, *args: Any, **kwargs: Any) -> Any: ...

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
        if evidence_replication.enabled():
            self._evidence_task = create_task_with_logging(
                self._listen_evidence(), name=f"equivocation_evidence_listener_{self._chain_id}"
            )
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
        self._stop_event.set()  # noqa: unawaited-async — asyncio.Event.set() is synchronous
        for task in (
            self._listener_task,
            self._unavail_task,
            self._response_index_task,
            self._abandon_task,
            self._evidence_task,
        ):
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
        self._evidence_task = None

    async def _listen(self) -> None:
        try:
            sub = await _ra.gossip_broker.subscribe(self._request_topic, max_queue_size=1000)
        except Exception as e:  # noqa: BLE001 - gossip subscribe is a pluggable backend (in-memory/redis/websocket); driver error families differ per backend
            logger.warning("Failed to subscribe to attestation requests: %s", e)
            return

        logger.info("Subscribed to remote attestation requests on %s", self._request_topic)
        try:
            async for request in sub:
                if self._stop_event.is_set():
                    break
                try:
                    await self._handle_request(request)
                except (
                    ImportError,
                    SQLAlchemyError,
                    ArithmeticError,
                    OSError,
                    RuntimeError,
                    ValueError,
                    TypeError,
                    AttributeError,
                    KeyError,
                ) as e:
                    logger.warning("Error handling attestation request: %s", e)
        finally:
            sub.close()  # noqa: unawaited-async — TopicSubscription.close() is synchronous

    async def _listen_abandon(self) -> None:
        """#1301 L2: release journal votes for hashes their proposer abandoned."""
        topic = abandon.abandon_topic(self._chain_id)
        try:
            sub = await _ra.gossip_broker.subscribe(topic, max_queue_size=256)
        except Exception as e:  # noqa: BLE001 - gossip subscribe is a pluggable backend (in-memory/redis/websocket); driver error families differ per backend
            logger.warning("Failed to subscribe to abandon statements: %s", e)
            return
        try:
            async for payload in sub:
                if self._stop_event.is_set():
                    break
                try:
                    self.handle_abandon(payload)
                except (
                    ImportError,
                    ArithmeticError,
                    AttributeError,
                    KeyError,
                    OSError,
                    RuntimeError,
                    TypeError,
                    ValueError,
                ) as e:
                    logger.warning("Error handling abandon statement: %s", e)
        finally:
            sub.close()  # noqa: unawaited-async — TopicSubscription.close() is synchronous

    async def _listen_evidence(self) -> None:
        """#1311: ingest replicated attestation-equivocation evidence."""
        topic = evidence_replication.equivocation_topic(self._chain_id)
        try:
            sub = await _ra.gossip_broker.subscribe(topic, max_queue_size=256)
        except Exception as e:  # noqa: BLE001 - evidence replication is advisory; a dead listener must not break startup
            logger.warning("Failed to subscribe to equivocation evidence: %s", e)
            return
        try:
            async for payload in sub:
                if self._stop_event.is_set():
                    break
                try:
                    self.handle_evidence(payload)
                except Exception as e:  # noqa: BLE001 - one malformed record is a drop, never a listener crash
                    logger.warning("Error handling equivocation evidence: %s", e)
        finally:
            sub.close()  # noqa: unawaited-async — TopicSubscription.close() is synchronous

    async def _listen_unavail(self) -> None:
        """#1281: answer ``UNAVAIL_QUERY`` for hashes we do not possess."""
        topic = unavail.query_topic(self._chain_id)
        try:
            sub = await _ra.gossip_broker.subscribe(topic, max_queue_size=256)
        except Exception as e:  # noqa: BLE001 - gossip subscribe is a pluggable backend (in-memory/redis/websocket); driver error families differ per backend
            logger.warning("Failed to subscribe to unavailability queries: %s", e)
            return
        logger.info("Subscribed to unavailability queries on %s", topic)
        try:
            async for query in sub:
                if self._stop_event.is_set():
                    break
                try:
                    await self._handle_unavail_query(query)
                except (
                    ImportError,
                    SQLAlchemyError,
                    ArithmeticError,
                    OSError,
                    RuntimeError,
                    ValueError,
                    TypeError,
                    AttributeError,
                    KeyError,
                ) as e:
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
            sub = await _ra.gossip_broker.subscribe(self._response_topic, max_queue_size=2000)
        except Exception as e:  # noqa: BLE001 - gossip subscribe is a pluggable backend (in-memory/redis/websocket); driver error families differ per backend
            logger.warning("Failed to subscribe to attestation responses for index: %s", e)
            return
        logger.info("Subscribed to attestation responses for observation index on %s", self._response_topic)
        vset = self._validator_set_addresses()
        try:
            async for response in sub:
                if self._stop_event.is_set():
                    break
                parsed = self._parse_index_response(response, vset)
                if parsed is None:
                    continue
                height, block_hash, validator, canon = parsed
                attest_response_diag.note_observer_response(height)  # #1998 H4 (observational)
                index = await unavail.get_observation_index(self._chain_id)
                if not self._index_response_authentic(index, response, height, block_hash, validator):
                    continue
                index.note_response(height, block_hash, canon, ignore=self._own_addresses(), tip_hint=self._tip_height_hint)
        finally:
            sub.close()  # noqa: unawaited-async — TopicSubscription.close() is synchronous

    def _parse_index_response(self, response: Any, vset: set[str]) -> tuple[int, str, str, str] | None:
        """Shape/chain/vset filter for the index feed: ``(height, hash, validator, canon)``
        or None. Membership is checked here, authenticity in
        ``_index_response_authentic`` — a claimed in-set address proves nothing."""
        if not isinstance(response, dict) or response.get("chain_id") != self._chain_id:
            return None
        try:
            height = int(response.get("height", 0))
        except (TypeError, ValueError):
            return None
        block_hash = str(response.get("hash", ""))
        validator = str(response.get("validator", ""))
        if not block_hash or not validator:
            return None
        try:
            canon = canonical_address(validator)
        except (AttributeError, TypeError, ValueError):
            return None
        if vset and canon not in vset:
            return None
        return height, block_hash, validator, canon

    def _index_response_authentic(
        self, index: Any, response: dict[str, Any], height: int, block_hash: str, validator: str
    ) -> bool:
        """#1964: an ``attest_response`` feeds the observation index only when
        its signature verifies, for ``validator``, against the attestation
        payload of the *verified request* the index holds for this key.

        A response with no matching verified request, no signature, a bad
        signature, or a round that contradicts the request's is dropped and
        counted — transport auth proves some validator published, not which
        one, so the claimed ``validator`` is never trusted on its own.
        """
        message = index.attestation_message(height, block_hash)
        if message is None:
            metrics_registry.increment("unavail_obs_response_unverified_total")
            return False
        signature = response.get("signature")
        if not isinstance(signature, str) or not signature:
            metrics_registry.increment("unavail_obs_response_unverified_total")
            return False
        declared = response.get("round")
        if declared is not None and "round" in message and declared != message["round"]:
            metrics_registry.increment("unavail_obs_response_unverified_total")
            return False
        try:
            ok = _verify_attestation(message, signature, validator, height)
        except Exception:  # noqa: BLE001 - a malformed signature is a rejection, never a crash of the observer
            ok = False
        if not ok:
            metrics_registry.increment("unavail_obs_response_unverified_total")
        return bool(ok)

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
                await _ra.gossip_broker.publish(unavail.response_topic(self._chain_id), response)
            except Exception as e:  # noqa: BLE001 - gossip publish is a pluggable backend (in-memory/redis/websocket); driver error families differ per backend
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

    @staticmethod
    def _count_refusal(reason: str) -> None:
        """#1709: count every attestation refusal, not just freshness ones.

        A past-skewed validator used to drop peer requests with only a
        journal line — a silent quorum dropout no metric or peer could
        see. ``attestation_refused_total`` is the alertable rate;
        ``attestation_refused_<reason>_total`` breaks it down. Reasons are
        code-controlled constants, so the suffix stays bounded."""
        metrics_registry.increment("attestation_refused_total")
        metrics_registry.increment(f"attestation_refused_{reason}_total")

    def _attest_request_fields(self, request: Any) -> tuple[dict[str, Any], str, int, str, float | None] | None:
        """Shape/identity fields of a well-formed attest request, else None."""
        if not isinstance(request, dict):
            return None
        header = request.get("header")
        if not isinstance(header, dict):
            return None

        proposer = header.get("proposer", "")
        if not proposer:
            return None

        try:
            height_int = int(header.get("height", 0))
        except (TypeError, ValueError):
            return None
        header_hash = str(header.get("hash", ""))
        if not header_hash:
            return None

        # #1245: a stale or far-future header is refused before it can touch
        # the lock. The age is read from the signed header, not from when the
        # request arrived, so retransmitting a captured request refreshes
        # nothing.
        header_age = self._header_age_seconds(header)
        return header, proposer, height_int, header_hash, header_age

    def _refuse_stale_header(self, header_age: float | None, height_int: int) -> bool:
        """Count+log and refuse a stale/far-future header; True = refused."""
        stale_reason = self._header_freshness_refusal(header_age)
        if stale_reason is None:
            return False
        self._count_refusal(stale_reason)
        logger.info(
            "Attestation refusal: %s at height %s (header age %.1fs, bound %.0fs, future skew %.0fs)",
            stale_reason,
            height_int,
            header_age if header_age is not None else 0.0,
            float(getattr(settings, "attestation_header_max_age_seconds", 60.0)),
            float(getattr(settings, "attestation_header_future_skew_seconds", 10.0)),
        )
        return True

    def _request_round_gate(self, header: dict[str, Any], height_int: int, header_hash: str) -> tuple[int | None, bool, bool]:
        """Round authentication for the request.

        Returns ``(request_round, round_lock, proceed)`` — ``proceed`` is
        False after a counted refusal was logged.
        """
        # #1242 round-keyed lock path: tip-height/canonical-parent check and
        # independent round derivation run before any lock evaluation, inside
        # the same await-free section as the signature — the head snapshot
        # cannot move between check and sign.
        # #1298 T7a/T14: at/above the armed domain-separation height the round
        # is inside the signed attestation payload UNCONDITIONALLY — the
        # declared-vs-derived check and the underivable refusal run whether or
        # not ``attestation_round_lock_enabled`` is set (design v2 §1 N1:
        # round authenticates, it does not activate locking). Below H only the
        # round-lock flag arms this path — byte-identical legacy behaviour.
        round_lock = self._round_lock_enabled()
        round_authenticated = round_lock or _attestation_domain_active(height_int)
        request_round: int | None = None
        if not round_authenticated:
            return request_round, round_lock, True
        request_round = self._derive_request_round(header)
        try:
            declared_round = int(str(header.get("round")))
        except (TypeError, ValueError):
            declared_round = -1
        if request_round is None or declared_round != request_round:
            self._count_refusal("round_auth_mismatch")
            logger.info(
                "Round authentication refusal: round mismatch/underivable at height %s — declared=%s derived=%s",
                height_int,
                header.get("round"),
                request_round,
            )
            return request_round, round_lock, False
        if round_lock:
            tip_refusal = self._tip_authorizes(header, height_int, header_hash)
            if tip_refusal is not None:
                self._count_refusal(f"tip_{tip_refusal}")
                logger.info(
                    "Round-lock refusal: %s for %s at height %s",
                    tip_refusal,
                    header_hash[:18],
                    height_int,
                )
                return request_round, round_lock, False
        return request_round, round_lock, True

    def _refuse_attestation_lock_rival(
        self,
        height_int: int,
        header_hash: str,
        round_lock: bool,
        att_sig_domain: Any,
        window: float,
    ) -> bool:
        """Attestation-lock + signed-once refusals; True = refused."""
        # Attestation lock: having signed one header at this height, refuse a
        # rival hash for one round window. Double-signing two blocks at h is
        # the equivocation that lets an asymmetric partition become a fork.
        if round_lock or not getattr(settings, "attestation_lock_enabled", True):
            return False
        existing = self.attestation_lock(height_int, window, att_sig_domain)
        if existing is not None and existing[0] != header_hash:
            self._count_refusal("attestation_lock_rival")
            logger.info(
                "Attestation lock: refusing to sign rival %s at height %s — already attested %s",
                header_hash[:18],
                height_int,
                existing[0][:18],
            )
            return True
        # #1245: this exact (height, hash) was signed before and its lock
        # has lapsed -- signing again would re-arm the lock for another
        # window, so a replayer could keep an attester locked out of a
        # height indefinitely. Refuse; a duplicate inside the window
        # (existing is not None) falls through as an idempotent re-publish.
        if existing is None and self._signed_once_contains(height_int, header_hash, att_sig_domain):
            self._count_refusal("resign_after_expiry")
            logger.info(
                "Attestation refusal: %s at height %s already signed and its lock has lapsed",
                header_hash[:18],
                height_int,
            )
            return True
        return False

    def _refuse_untrusted_proposer(
        self, proposer: str, validator_set: set[str], height_int: int, header: dict[str, Any]
    ) -> bool:
        """Validator-set membership + scheduled-proposer refusals; True = refused."""
        # Only sign for blocks produced by a known validator in our set.
        if validator_set and canonical_address(proposer) not in {canonical_address(v) for v in validator_set}:
            self._count_refusal("non_validator_proposer")
            return True

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
                self._count_refusal("not_scheduled_proposer")
                return True
        return False

    def _proposer_signature_refused(
        self, request: dict[str, Any], header: dict[str, Any], proposer: str, height_int: int
    ) -> bool:
        """Verify the carried proposer block signature; True = refused."""
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
            except Exception as e:  # noqa: BLE001 - any verify failure means unsigned
                logger.debug("proposer signature verify raised: %s", type(e).__name__)
                sig_ok = False
            if not sig_ok:
                logger.info(
                    "Attestation refusal: bad proposer_signature at height %s from %s",
                    height_int,
                    proposer[:18],
                )
                self._count_refusal("bad_proposer_signature")
                return True
        elif getattr(settings, "consensus_require_signed_attest_request", False):
            logger.info("Attestation refusal: unsigned attest_request at height %s", height_int)
            self._count_refusal("unsigned_attest_request")
            return True
        else:
            count_v9_would_reject("attest_unsigned_request")
        return False

    def _round_or_abandon_refused(
        self, height_int: int, request_round: int | None, header_hash: str, round_lock: bool
    ) -> bool:
        """Round-lock verdict + abandon-statement refusals; True = refused."""
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
                self._count_refusal("round_lock_refusal")
                return True
            abandoned = self._abandoned_round_rival(height_int, request_round, header_hash)
            if abandoned is not None:
                metrics_registry.increment("vote_journal_abandon_same_round_refused_total")
                logger.info(
                    "Abandon same-round refusal: %s at height %s round %s (abandoned %s)",
                    header_hash[:18],
                    height_int,
                    request_round,
                    abandoned[:18],
                )
                self._count_refusal("abandon_same_round_refusal")
                return True
        elif abandon.abandon_enabled():
            # #1940 F2: round-lock off (or round underivable) — the
            # (height, round) index cannot prove same-round vs cross-round,
            # so any abandoned hash at this height fails closed. Re-signing
            # the abandoned hash itself stays allowed. Flag-gated: with
            # abandon OFF this branch is inert and behavior is unchanged.
            if request_round is not None:
                abandoned = self._abandoned_round_rival(height_int, request_round, header_hash)
                kind = "same-round"
            else:
                abandoned = self._abandoned_height_rival(height_int, header_hash)
                kind = "unbounded"
            if abandoned is not None:
                metrics_registry.increment("vote_journal_abandon_same_round_refused_total")
                logger.info(
                    "Abandon %s refusal: %s at height %s (abandoned %s)",
                    kind,
                    header_hash[:18],
                    height_int,
                    abandoned[:18],
                )
                self._count_refusal(f"abandon_{kind}_refusal")
                return True
        return False

    async def _v9_request_refused(
        self,
        request: dict[str, Any],
        header: dict[str, Any],
        proposer_signature: Any,
        height_int: int,
        header_hash: str,
    ) -> bool:
        """v9 transaction-check refusal for the request; True = refused."""
        # v9: before signing, verify every transaction in the request —
        # sender signature (except the shared internal allowlist) and nonce
        # order against this validator's own state at the block's parent.
        # Full re-execution is deferred; an attestation then means "these
        # transactions are authorized", not just "the header came from a
        # validator". While the v9 height is unset a failed check only logs
        # and counts — the attestation still goes out (shadow mode).
        txs = request.get("transactions")
        from ..state.state_transition import get_block_version_for_height

        from .attestation_state_probe import post_state_probe_active

        # #1940 F4: an armed post-state gate refuses regardless of the legacy
        # v9 activation height — shadow-mode v9 (<9) must not soften it.
        probe_gate = post_state_probe_active(height_int)
        refusal: str | None
        if not isinstance(txs, list):
            refusal = "transactions_absent"
        elif len(json.dumps(request).encode()) > int(getattr(settings, "gossip_max_message_size", 1_048_576)):
            refusal = "request_too_large"
        else:
            if probe_gate:
                # The verified request-envelope signature feeds the probe's
                # proposer-schedule check — never an embedded field.
                refusal = await self._run_v9_check(header, txs, proposer_signature=proposer_signature)
            else:
                refusal = await self._run_v9_check(header, txs)
        if refusal is None:
            return False
        count_v9_would_reject(f"attest_{refusal}")
        if probe_gate or get_block_version_for_height(height_int) >= 9:
            logger.warning(
                "v9: refusing attestation for block %s at height %s — %s",
                header_hash[:18],
                height_int,
                refusal,
            )
            self._count_refusal(f"v9_{refusal}")
            return True
        logger.warning(
            "v9 shadow: would refuse attestation for block %s at height %s — %s",
            header_hash[:18],
            height_int,
            refusal,
        )
        return False

    async def _attest_for_key(self, ctx: _AttestRequestCtx, address: str, private_key: Any) -> bool:
        """Sign+publish one attestation for ``address``; True ends the request.

        Returns True when handling must stop (a response was published, or
        the pre-sign lock could not be persisted); False continues to the
        next key.
        """
        # Do not sign our own block.
        if _same_address(address, ctx.proposer):
            return False
        # Only sign with keys that are part of the configured validator set.
        if ctx.validator_set and canonical_address(address) not in {canonical_address(v) for v in ctx.validator_set}:
            return False

        # #1268: durable one-vote-per-height gate. Records the vote before
        # the signature exists; flag-guarded, off = nothing above changes.
        if vote_journal_enabled() and await self._journal_refuses(
            ctx.height_int,
            ctx.header_hash,
            address,
            ctx.proposer,
            ctx.request_round,
            request_cert=ctx.request_cert,
        ):
            return False
        if not ctx.lock_minted:
            if not self._record_pre_sign_lock(
                ctx.height_int, ctx.request_round, ctx.header_hash, ctx.proposer, ctx.header, ctx.round_lock
            ):
                return True
            ctx.lock_minted = True

        message = {
            "chain_id": ctx.header.get("chain_id", self._chain_id),
            "height": ctx.header.get("height", 0),
            "hash": ctx.header.get("hash", ""),
            "parent_hash": ctx.header.get("parent_hash", ""),
            "proposer": ctx.proposer,
            "state_root": ctx.header.get("state_root", ""),
            "bridge_state_root": ctx.header.get("bridge_state_root", ""),
        }
        if ctx.request_round is not None:
            # Amendment A + #1298 T7a: the round is inside the signed
            # payload — under round_lock at any height, and
            # unconditionally at/above the domain-separation height —
            # not transport metadata; changing it invalidates the
            # signature. ``request_round`` is only ever set on those two
            # paths, so this condition covers both.
            message["round"] = ctx.request_round
        try:
            signature = _sign_attestation(message, private_key, ctx.height_int)
        except (ImportError, RuntimeError, ValueError, TypeError, AttributeError, KeyError) as e:
            logger.warning("Failed to sign attestation: %s", e)
            return False
        return await self._record_and_publish(ctx, address, message, signature)

    async def _record_and_publish(self, ctx: _AttestRequestCtx, address: str, message: dict[str, Any], signature: str) -> bool:
        """Record evidence/locks for a fresh signature, then publish it.

        True = the response was published (caller stops); False = publish
        failed and the caller may try the next key.
        """
        # #1263: retain the signed attestation (durably) so a rival-hash
        # signing at this height can cite BOTH signatures as equivocation
        # evidence, then record the equivocation for this signer.
        self._record_signed_attestation(
            ctx.height_int,
            ctx.header_hash,
            address,
            message,
            ctx.request_round,
            ctx.round_lock,
            signature,
            ctx.att_sig_domain,
        )
        # #1281: distinct evidence class — "unavailability_cert" when the
        # armed barrier released this vote under a verified UC,
        # "unjustified" for any other armed-mode conflicting vote.
        # Absent entirely with the flag off (pre-#1281 evidence shape).
        just_class: str | None = None
        if unavail.justification_enabled():
            just_class = (
                "unavailability_cert" if (ctx.height_int, ctx.header_hash) in self._vote_justifications else "unjustified"
            )
        self._record_attestation_equivocation_evidence(
            ctx.height_int,
            ctx.header_hash,
            address,
            ctx.proposer,
            ctx.request_round,
            justification=just_class,
            signature_domain=ctx.att_sig_domain,
        )
        if not ctx.round_lock:
            self._record_attestation_lock(ctx.height_int, ctx.header_hash, ctx.proposer, ctx.att_sig_domain)

        response = {
            "chain_id": self._chain_id,
            "height": message["height"],
            "hash": message["hash"],
            "validator": address,
            "signature": signature,
        }
        stored_just = self._vote_justifications.get((ctx.height_int, ctx.header_hash))
        if stored_just is not None:
            # #1281: carry the unlock justification on the vote itself so
            # collectors and evidence verifiers see the same artifact.
            response["unlock_justification"] = stored_just
        if ctx.request_round is not None:
            # #1298 T7a: post-H round-auth responses carry the round even
            # with round_lock OFF — collectors use it as the verify hint.
            response["round"] = ctx.request_round
        # #1709: request_age_ms is this node's clock minus the proposer's
        # request timestamp — transit, queueing, v9 checks, plus any clock
        # offset between the hosts. Carried on the response so collectors
        # can distinguish a slow-but-honest responder from a skewed one;
        # it is unsigned transport metadata like `round`, not part of the
        # attestation payload.
        request_ts = ctx.request.get("timestamp")
        if isinstance(request_ts, (int, float)):
            response["request_age_ms"] = int((_ra.time.time() - float(request_ts)) * 1000)
        try:
            await _ra.gossip_broker.publish(self._response_topic, response)
        except Exception as e:  # noqa: BLE001 - gossip publish is a pluggable backend (in-memory/redis/websocket); driver error families differ per backend
            logger.warning("Failed to publish attestation response: %s", e)
            return False
        request_age_ms = response.get("request_age_ms", "unknown")
        logger.info(
            "Attestation response published: height=%s validator=%s proposer=%s header_age_ms=%s request_age_ms=%s",
            message["height"],
            address,
            ctx.proposer,
            int(ctx.header_age * 1000) if ctx.header_age is not None else "unknown",
            request_age_ms,
        )
        return True

    async def _handle_request(self, request: Any) -> None:
        fields = self._attest_request_fields(request)
        if fields is None:
            return
        header, proposer, height_int, header_hash, header_age = fields
        if self._refuse_stale_header(header_age, height_int):
            return

        # #1298: the domain this request's signatures are minted under —
        # computed once and reused for the acceptance-key lookups below and
        # the evidence-record stamping in the signing loop. None below the
        # armed activation height (legacy shared preimage).
        att_sig_domain = _attestation_signature_domain(height_int)

        request_round, round_lock, round_ok = self._request_round_gate(header, height_int, header_hash)
        if not round_ok:
            return

        # #1298: the durable lock journal also reseeds the in-memory
        # attestation lock and ``_signed_once`` across restarts — load it
        # once before either lock path consults them.
        self._ensure_round_locks_loaded()

        # Durable lock record BEFORE any signature is released (#1242
        # round-lock / #1298 attestation-lock journal): a crash after this
        # point can never forget that this height is bound to header_hash,
        # and a persistence failure refuses the signing — no signature goes
        # out unrecorded.
        # #1985 (liveness flag): the lock is minted only once a signer has passed the
        # journal gate below, so a rival this validator refuses to vote for leaves no
        # lock for a hash it never signed (it used to pin the round for the proposer).
        window = attestation_lock_window_seconds(height_int)
        if self._refuse_attestation_lock_rival(height_int, header_hash, round_lock, att_sig_domain, window):
            return

        validator_set = await self._request_semantics_ok(
            request, header, proposer, height_int, header_hash, request_round, round_lock
        )
        if validator_set is None:
            return

        ctx = await self._signing_context(
            request,
            header,
            proposer,
            height_int,
            header_hash,
            request_round,
            round_lock,
            att_sig_domain,
            validator_set,
            header_age,
        )
        if ctx is None:
            return
        for address, private_key in self._validator_keys.items():
            if await self._attest_for_key(ctx, address, private_key):
                return

    async def _request_semantics_ok(
        self,
        request: dict[str, Any],
        header: dict[str, Any],
        proposer: str,
        height_int: int,
        header_hash: str,
        request_round: int | None,
        round_lock: bool,
    ) -> set[str] | None:
        """Proposer-authenticity + round/abandon + v9 gates.

        Returns the loaded validator set when every gate passes; None after
        a counted refusal was logged.
        """
        # Only sign for blocks produced by a known validator in our set.
        validator_set = self._load_validator_set()
        if self._refuse_untrusted_proposer(proposer, validator_set, height_int, header):
            return None

        if self._proposer_signature_refused(request, header, proposer, height_int):
            return None

        if self._round_or_abandon_refused(height_int, request_round, header_hash, round_lock):
            return None

        proposer_signature = request.get("proposer_signature")
        if await self._v9_request_refused(request, header, proposer_signature, height_int, header_hash):
            return None
        return validator_set

    async def _signing_context(
        self,
        request: dict[str, Any],
        header: dict[str, Any],
        proposer: str,
        height_int: int,
        header_hash: str,
        request_round: int | None,
        round_lock: bool,
        att_sig_domain: Any,
        validator_set: set[str],
        header_age: float | None,
    ) -> _AttestRequestCtx | None:
        """Pre-sign lock + observation-index note; None refuses the request."""
        # Durable lock record BEFORE any signature is released (#1242
        # round-lock / #1298 attestation-lock journal): a crash after this
        # point can never forget that this height is bound to header_hash,
        # and a persistence failure refuses the signing — no signature goes
        # out unrecorded.
        # #1985 (liveness flag): the lock is minted only once a signer has passed the
        # journal gate below, so a rival this validator refuses to vote for leaves no
        # lock for a hash it never signed (it used to pin the round for the proposer).
        lock_after_gate = abandon.liveness_enabled()
        lock_minted = False
        if not lock_after_gate:
            if not self._record_pre_sign_lock(height_int, request_round, header_hash, proposer, header, round_lock):
                return None
            lock_minted = True

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
            index.note_request(
                height_int,
                header_hash,
                proposer,
                ignore=self._own_addresses(),
                att_message=_attestation_message(header, self._chain_id, request_round),
                tip_hint=self._tip_height_hint,
            )
        request_cert = request.get("unlock_justification")

        return _AttestRequestCtx(
            request=request,
            header=header,
            proposer=proposer,
            height_int=height_int,
            header_hash=header_hash,
            request_round=request_round,
            request_cert=request_cert,
            round_lock=round_lock,
            att_sig_domain=att_sig_domain,
            validator_set=validator_set,
            header_age=header_age,
            lock_minted=lock_minted,
        )
