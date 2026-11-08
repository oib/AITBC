"""Unavailability Certificate + gossip-observation index (#1281, Phase 2).

The Phase-1 vote journal's liveness valve opened on local wall-clock age
plus a private peer lookup — the #1274 ruling (c20233) rejects that as
unlock justification. This module is the verifiable-justification
barrier specified in ``docs/design/consensus-valve-justification-barrier.md``
and planned in ``consensus-valve-uc-implementation-plan.md`` (operator
ruling: folded together with A's #1279 evidence-valve substrate).

Two cooperating proofs, one release predicate::

    unlock_permitted = unfetchable_persists(T_evidence)
                    AND index_clean(GossipObservationIndex, T_evidence)
                    AND uc_valid(UnavailabilityCertificate)

* ``UnavailabilityCertificate`` — validator-signed statements that they
  do not possess/serve ``(chain_id, height, block_hash)`` at a given
  ``epoch``. Threshold = ``MIN_ATTESTATIONS`` (quorum-intersection: a
  future quorum for the old hash must then include a validator that
  signed against it — self-incriminating evidence).
* ``GossipObservationIndex`` — per-(height, hash) record of observed
  ``attest_request``/``attest_response`` traffic. ``index_clean`` is the
  "can never join quorum" leg: no attestations or request re-broadcasts
  for the voted hash inside ``T_evidence`` while the mesh is visibly
  alive. Honest residual (A's c20248 caveat): ephemeral gossip means
  "zero observed" is not proof of "zero cast" — the rule stays sound
  because a seal requires proposer-received quorum pre-isolation and the
  sealed block re-propagates post-heal into the fetch path.

Everything here is dormant unless ``vote_journal_justification_enabled``
is set; with the flag off none of this code runs.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from functools import partial
from typing import Any

from aitbc.aitbc_logging import get_logger
from aitbc.crypto.consensus_signing import sign_consensus_message, verify_consensus_message
from aitbc.crypto.signature_recovery import canonical_address

from ..config import settings
from ..gossip import gossip_broker
from ..metrics import metrics_registry
from .vote_fetch import locate_voted_block

logger = get_logger(__name__)

# Domain separation: an attestation signature must never verify as an
# unavailability statement (and vice versa). The tag is inside the signed
# payload, so it is covered by the signature.
UNAVAIL_TAG = "unavail-v1"
UC_VERSION = 1

QUERY_TYPE = "unavail_query"
RESPONSE_TYPE = "unavail_resp"


def justification_enabled() -> bool:
    """#1281 master switch — dormant default-off like Phase 1."""
    return bool(
        getattr(settings, "vote_journal_enabled", False) and getattr(settings, "vote_journal_justification_enabled", False)
    )


def _float(name: str, default: float) -> float:
    return float(getattr(settings, name, default))


def _int(name: str, default: int) -> int:
    return int(getattr(settings, name, default))


def collect_seconds() -> float:
    return _float("unavail_collect_seconds", 15.0)


def cert_max_age_seconds() -> float:
    return _float("unavail_cert_max_age_seconds", 120.0)


def evidence_seconds() -> float:
    return _float("unavail_evidence_seconds", 90.0)


def visibility_seconds() -> float:
    """Mesh-liveness window — deliberately much longer than T_evidence.

    "Peers answering" is a coarse reachability signal, not the quiet-window
    evidence: validator traffic is continuous in production, and the UC
    responders themselves refresh it. A partition still fails visibility
    once pre-partition actors age out of this window.
    """
    return _float("unavail_visibility_seconds", 300.0)


def sample_seconds() -> float:
    return _float("unavail_sample_seconds", 10.0)


def min_responses() -> int:
    """UC quorum-intersection threshold — ``MIN_ATTESTATIONS`` by ruling."""
    configured = _int("unavail_min_responses", 0)
    if configured > 0:
        return configured
    return max(1, _int("multi_validator_min_attestations", 2))


def collect_backoff_seconds() -> float:
    """Negative-result backoff after a failed UC probe (#1281 respin).

    Floored at ``2 * collect_seconds`` per the respin ruling — a failed
    collection must not be retried inside its own window, and gate retries
    every few seconds must not storm the query topic.
    """
    return max(_float("unavail_collect_backoff_seconds", 30.0), 2.0 * collect_seconds())


def query_topic(chain_id: str) -> str:
    return f"consensus.unavail_query.{chain_id}"


def response_topic(chain_id: str) -> str:
    return f"consensus.unavail_resp.{chain_id}"


def validator_addresses() -> set[str]:
    """Canonical validator set from settings (same parse as the gates)."""
    raw = getattr(settings, "validator_set", "")
    if not raw:
        return set()
    try:
        data = json.loads(raw)
        entries = data if isinstance(data, list) else data.get("validators", [])
        return {canonical_address(str(v.get("address", ""))) for v in entries if isinstance(v, dict) and v.get("address")}
    except Exception:  # noqa: BLE001 - a malformed set means no UC can verify anyway
        return set()


# ---------------------------------------------------------------------------
# Wire payloads
# ---------------------------------------------------------------------------


def unavail_response_message(chain_id: str, height: int, block_hash: str, epoch: int) -> dict[str, Any]:
    """The exact dict a responder signs (canonical-JSON + keccak + secp256k1)."""
    return {
        "tag": UNAVAIL_TAG,
        "chain_id": chain_id,
        "height": int(height),
        "hash": block_hash,
        "epoch": int(epoch),
    }


def build_unavail_response(
    chain_id: str, height: int, block_hash: str, epoch: int, signer: str, private_key: str
) -> dict[str, Any]:
    """One signed ``UNAVAIL_RESP`` payload."""
    return {
        "type": RESPONSE_TYPE,
        "chain_id": chain_id,
        "height": int(height),
        "hash": block_hash,
        "epoch": int(epoch),
        "signer": canonical_address(signer),
        "signature": sign_consensus_message(unavail_response_message(chain_id, height, block_hash, epoch), private_key),
    }


def verify_unavail_response(resp: dict[str, Any], validator_set: set[str]) -> str | None:
    """Canonical signer address when ``resp`` is a valid unavailability statement.

    Checks type, field binding is left to the caller (the cert verifier
    re-checks chain/height/hash/epoch), signature recovers to ``signer``,
    and ``signer`` is in ``validator_set``. Returns None on any failure.
    """
    if not isinstance(resp, dict) or resp.get("type") != RESPONSE_TYPE:
        return None
    signer = resp.get("signer")
    signature = resp.get("signature")
    if not signer or not signature:
        return None
    try:
        canon = canonical_address(str(signer))
    except (AttributeError, TypeError, ValueError):
        return None
    if canon not in validator_set:
        return None
    try:
        height = int(resp.get("height", 0))
        epoch = int(resp.get("epoch", 0))
    except (TypeError, ValueError):
        return None
    message = unavail_response_message(str(resp.get("chain_id", "")), height, str(resp.get("hash", "")), epoch)
    try:
        if not verify_consensus_message(message, str(signature), canon):
            return None
    except Exception:  # noqa: BLE001 - malformed signature is just an invalid response
        return None
    return canon


# ---------------------------------------------------------------------------
# UnavailabilityCertificate
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UnavailabilityCertificate:
    """Signed proof that a quorum-intersecting set of validators declared
    ``(chain_id, height, hash)`` unservable at ``epoch``."""

    chain_id: str
    height: int
    hash: str
    epoch: int
    responses: tuple[dict[str, str], ...]  # {"validator","signature"}
    index_verdict: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "version": UC_VERSION,
            "kind": "unavailability_cert",
            "chain_id": self.chain_id,
            "height": self.height,
            "hash": self.hash,
            "epoch": self.epoch,
            "responses": [dict(r) for r in self.responses],
        }
        if self.index_verdict:
            out["index_verdict"] = dict(self.index_verdict)
        return out

    @classmethod
    def from_dict(cls, raw: Any) -> UnavailabilityCertificate | None:
        if not isinstance(raw, dict) or raw.get("kind") != "unavailability_cert":
            return None
        try:
            responses = tuple(
                {"validator": str(r.get("validator", "")), "signature": str(r.get("signature", ""))}
                for r in raw.get("responses", [])
                if isinstance(r, dict)
            )
            verdict = raw.get("index_verdict")
            return cls(
                chain_id=str(raw.get("chain_id", "")),
                height=int(raw.get("height", 0)),
                hash=str(raw.get("hash", "")),
                epoch=int(raw.get("epoch", 0)),
                responses=responses,
                index_verdict=verdict if isinstance(verdict, dict) else {},
            )
        except (TypeError, ValueError):
            return None


def cert_message(cert: UnavailabilityCertificate) -> dict[str, Any]:
    """Reconstruct the per-response signed payload for verification."""
    return unavail_response_message(cert.chain_id, cert.height, cert.hash, cert.epoch)


def verify_unavailability_cert(
    cert: UnavailabilityCertificate | dict[str, Any],
    *,
    chain_id: str,
    height: int,
    block_hash: str,
    validator_set: set[str] | None = None,
    now: float | None = None,
) -> tuple[bool, str]:
    """The one pure verifier shared by every consumer (#1281).

    Returns ``(True, "")`` or ``(False, reason)``. Checks, in order:
    version/kind, chain/height/hash binding, epoch freshness, per-response
    signature + validator-set membership, distinct signers, threshold.
    """
    cert_obj = UnavailabilityCertificate.from_dict(cert) if isinstance(cert, dict) else cert
    if cert_obj is None:
        return False, "malformed"
    if cert_obj.chain_id != chain_id:
        return False, "chain_mismatch"
    if cert_obj.height != int(height):
        return False, "height_mismatch"
    if cert_obj.hash != block_hash:
        return False, "hash_mismatch"
    now_w = time.time() if now is None else now
    if abs(now_w - cert_obj.epoch) > cert_max_age_seconds():
        return False, "stale_epoch"
    vset = validator_set if validator_set is not None else validator_addresses()
    if not vset:
        return False, "no_validator_set"
    message = cert_message(cert_obj)
    seen: set[str] = set()
    for resp in cert_obj.responses:
        reason = _verify_cert_response(resp, message, vset, seen)
        if reason is not None:
            return False, reason
    if len(seen) < min_responses():
        return False, "below_threshold"
    return True, ""


def _verify_cert_response(resp: dict[str, str], message: dict[str, Any], vset: set[str], seen: set[str]) -> str | None:
    """One certificate response: distinct in-set signer + valid signature."""
    signer = str(resp.get("validator", ""))
    signature = str(resp.get("signature", ""))
    try:
        canon = canonical_address(signer)
    except (AttributeError, TypeError, ValueError):
        return "bad_signer"
    if canon in seen:
        return "duplicate_signer"
    seen.add(canon)
    if canon not in vset:
        return "signer_not_validator"
    try:
        ok = verify_consensus_message(message, signature, canon)
    except Exception:  # noqa: BLE001 - a bad signature invalidates the cert
        return "bad_signature"
    if not ok:
        return "bad_signature"
    return None


# ---------------------------------------------------------------------------
# UC collection (gossip round)
# ---------------------------------------------------------------------------


async def _next_response(sub: Any, deadline: float) -> Any:
    """Next gossip message within the collect window; None on timeout."""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return None
    try:
        return await asyncio.wait_for(sub.get(), timeout=min(remaining, 1.0))
    except (asyncio.TimeoutError, TimeoutError):
        return None


def _matching_response_signer(
    resp: Any, chain_id: str, height: int, block_hash: str, epoch: int, vset: set[str]
) -> str | None:
    """Canonical signer when ``resp`` answers THIS query, else None."""
    if not isinstance(resp, dict):
        return None
    try:
        resp_height = int(resp.get("height", 0))
        resp_epoch = int(resp.get("epoch", 0))
    except (TypeError, ValueError):
        return None
    if resp.get("chain_id") != chain_id or resp_height != int(height):
        return None
    if resp.get("hash") != block_hash or resp_epoch != epoch:
        return None
    return verify_unavail_response(resp, vset)


async def collect_unavailability_cert(
    chain_id: str,
    height: int,
    block_hash: str,
    *,
    requester: str = "",
    broker: Any | None = None,
) -> UnavailabilityCertificate | None:
    """Broadcast ``UNAVAIL_QUERY`` and assemble a cert from responses.

    Returns a self-verified certificate, or None on timeout/insufficient
    responses. ``broker`` is injectable for tests (defaults to the process
    gossip broker).
    """
    if broker is None:
        broker = gossip_broker

    epoch = int(time.time())
    query = {
        "type": QUERY_TYPE,
        "chain_id": chain_id,
        "height": int(height),
        "hash": block_hash,
        "epoch": epoch,
        "requester": requester,
    }
    resp_topic = response_topic(chain_id)
    try:
        sub = await broker.subscribe(resp_topic, max_queue_size=256)
    except Exception as exc:  # noqa: BLE001 - no subscription means no cert
        logger.warning("unavail: subscribe failed for %s: %s", resp_topic, exc)
        return None
    vset = validator_addresses()
    responses: list[dict[str, str]] = []
    seen: set[str] = set()
    deadline = time.monotonic() + collect_seconds()
    try:
        await broker.publish(query_topic(chain_id), query)
        while time.monotonic() < deadline:
            resp = await _next_response(sub, deadline)
            signer = _matching_response_signer(resp, chain_id, height, block_hash, epoch, vset)
            if signer is None or signer in seen:
                continue
            seen.add(signer)
            responses.append({"validator": signer, "signature": str(resp.get("signature", ""))})
            # A signed response is fresh proof this validator is reachable —
            # feed mesh visibility so the index leg can see the round trip.
            index = await get_observation_index(chain_id)
            index.note_actor(height, signer)
            # Everyone who can answer has answered — no need to wait out the window.
            if len(seen) >= max(1, len(vset) - 1):
                break
    finally:
        sub.close()  # noqa: unawaited-async — TopicSubscription.close() is synchronous
    if len(responses) < min_responses():
        metrics_registry.increment("unavail_collect_insufficient_total")
        return None
    cert = UnavailabilityCertificate(
        chain_id=chain_id,
        height=int(height),
        hash=block_hash,
        epoch=epoch,
        responses=tuple(responses),
    )
    ok, reason = verify_unavailability_cert(cert, chain_id=chain_id, height=height, block_hash=block_hash)
    if not ok:
        logger.warning("unavail: self-assembled cert failed verification: %s", reason)
        metrics_registry.increment("unavail_collect_invalid_total")
        return None
    metrics_registry.increment("unavail_cert_collected_total")
    return cert


# ---------------------------------------------------------------------------
# GossipObservationIndex — the "can never join quorum" leg (#1279 substrate)
# ---------------------------------------------------------------------------


class GossipObservationIndex:
    """Per-(height, hash) record of observed attestation traffic.

    Fed by the persistent ``attest_request`` handler and a persistent
    ``attest_response`` subscriber. Own validator addresses are excluded —
    "foreign attestations" means OTHER validators; our own prior vote is
    journal business, not gossip evidence.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        # (height, hash) -> observation record
        self._entries: dict[tuple[int, str], dict[str, Any]] = {}
        # height -> {validator_addr: last_seen_mono} — mesh-visibility actors
        self._actors: dict[int, dict[str, float]] = {}
        self._max_entries = 512

    @staticmethod
    def _mono() -> float:
        return time.monotonic()

    def _entry(self, height: int, block_hash: str) -> dict[str, Any]:
        key = (int(height), block_hash)
        ent = self._entries.get(key)
        if ent is None:
            if len(self._entries) >= self._max_entries:
                self._entries.clear()
            ent = {
                "requests": 0,
                "req_actors": {},  # actor -> last_request_mono
                "attestations": {},  # signer -> last_attest_mono
            }
            self._entries[key] = ent
        return ent

    def note_request(self, height: int, block_hash: str, actor: str, *, ignore: set[str] | None = None) -> None:
        """An ``attest_request`` for ``block_hash`` was observed."""
        try:
            canon = canonical_address(actor) if actor else ""
        except (AttributeError, TypeError, ValueError):
            canon = ""
        if canon and ignore and canon in ignore:
            return
        now = self._mono()
        ent = self._entry(height, block_hash)
        ent["requests"] += 1
        if canon:
            ent["req_actors"][canon] = now
        self._note_actor(height, canon or actor, now)

    def note_response(self, height: int, block_hash: str, validator: str, *, ignore: set[str] | None = None) -> None:
        """An ``attest_response`` for ``block_hash`` was observed."""
        try:
            canon = canonical_address(validator)
        except (AttributeError, TypeError, ValueError):
            return
        if ignore and canon in ignore:
            return
        now = self._mono()
        ent = self._entry(height, block_hash)
        ent["attestations"][canon] = now
        self._note_actor(height, canon, now)

    def note_actor(self, height: int, address: str) -> None:
        """Record a validator as recently reachable at ``height`` — used for
        UC responders, whose signatures are themselves fresh proof the mesh
        is delivering gossip right now."""
        self._note_actor(height, address, self._mono())

    def _note_actor(self, height: int, actor: str, now: float) -> None:
        if not actor:
            return
        try:
            canon = canonical_address(actor)
        except (AttributeError, TypeError, ValueError):
            return
        actors = self._actors.setdefault(int(height), {})
        actors[canon] = now
        # Bound the actor table: drop heights far below anything recent.
        if len(self._actors) > 256:
            cutoff = now - 4 * evidence_seconds()
            for h in [h for h, m in self._actors.items() if max(m.values(), default=0.0) < cutoff]:
                self._actors.pop(h, None)

    def quiet_verdict(
        self,
        height: int,
        block_hash: str,
        *,
        ignore: set[str] | None = None,
        window: float | None = None,
    ) -> dict[str, Any]:
        """The quiet half of ``index_clean`` — exposed separately for the
        #1281 respin's probe ordering.

        Quiet iff no attest_request re-broadcast and no foreign
        attestation for the hash inside ``window`` (T_evidence). This is
        the cheap passive gate: a hash with live attest traffic is not an
        abandoned one, and probing it would be spam.
        """
        win = evidence_seconds() if window is None else window
        now = self._mono()
        ent = self._entries.get((int(height), block_hash))
        if not ent:
            return {"quiet": True, "quiet_seconds": None, "requests_seen": 0, "attestations_seen": 0}
        req_actors = {a: ts for a, ts in ent["req_actors"].items() if not (ignore and a in ignore)}
        attesters = {a: ts for a, ts in ent["attestations"].items() if not (ignore and a in ignore)}
        stamps = list(req_actors.values()) + list(attesters.values())
        last_activity = max(stamps) if stamps else 0.0
        return {
            "quiet": (now - last_activity) >= win,
            "quiet_seconds": round(now - last_activity, 3),
            "requests_seen": int(ent["requests"]),
            "attestations_seen": len(attesters),
        }

    def clean_verdict(
        self,
        height: int,
        block_hash: str,
        *,
        ignore: set[str] | None = None,
        min_peers: int | None = None,
        window: float | None = None,
    ) -> dict[str, Any]:
        """``index_clean`` verdict for ``(height, block_hash)``.

        Clean iff quiet (``quiet_verdict``) AND the mesh shows ≥
        ``min_peers`` distinct validators active at this height inside the
        visibility window — which, post-respin, is established by
        authenticated UC probe responses rather than passive traffic
        alone (partition ⇒ not visible ⇒ not clean ⇒ hold preserved).
        """
        q = self.quiet_verdict(height, block_hash, ignore=ignore, window=window)
        peers = min_responses() if min_peers is None else min_peers
        now = self._mono()
        actors = self._actors.get(int(height), {})
        vis_win = visibility_seconds()
        visible = sum(1 for a, ts in actors.items() if now - ts <= vis_win and not (ignore and a in ignore))
        mesh_visible = visible >= peers
        return {
            **q,
            "clean": q["quiet"] and mesh_visible,
            "mesh_visible": mesh_visible,
            "validators_visible": visible,
        }

    def reset(self) -> None:
        self._entries.clear()
        self._actors.clear()


_INDICES: dict[str, GossipObservationIndex] = {}
_INDICES_LOCK = asyncio.Lock()


async def get_observation_index(chain_id: str) -> GossipObservationIndex:
    async with _INDICES_LOCK:
        idx = _INDICES.get(chain_id)
        if idx is None:
            idx = GossipObservationIndex()
            _INDICES[chain_id] = idx
        return idx


async def reset_observation_indices() -> None:
    async with _INDICES_LOCK:
        _INDICES.clear()
        for sampler in list(_FETCH_SAMPLERS.values()):
            sampler.cancel()
        _FETCH_SAMPLERS.clear()
        # #1281 respin: probe state is per-process evidence too — a reset
        # (tests, chain re-init) must not leak cached certs, backoff
        # suppression, or in-flight collections into the next context.
        for task in list(_PROBE_TASKS.values()):
            task.cancel()
        _PROBE_TASKS.clear()
        _PROBE_BACKOFF.clear()
        _PROBE_LAST_SUCCESS.clear()
        _CERT_CACHE.clear()


# ---------------------------------------------------------------------------
# Unfetchable-persistence sampler
# ---------------------------------------------------------------------------


class _FetchSampler:
    """Samples ``locate_voted_block`` until the miss streak reaches the
    evidence window (or a peer starts serving the block — streak resets).

    One sampler per (chain, height, hash-set); concurrent gate callers
    share it. Keeps sampling after proving so a late re-appearance of the
    block revokes the proof.
    """

    def __init__(self, chain_id: str, height: int, hashes: tuple[str, ...]) -> None:
        self.chain_id = chain_id
        self.height = height
        self.hashes = hashes
        self.miss_since: float | None = None
        self.proven = False
        self.last_miss_mono: float | None = None
        self.hit = False
        self.task: asyncio.Task[None] | None = None
        self._stopped = False

    def cancel(self) -> None:
        self._stopped = True
        if self.task is not None:
            self.task.cancel()

    async def run(self) -> None:
        interval = max(0.2, sample_seconds())
        need = evidence_seconds()
        try:
            while not self._stopped:
                found = await locate_voted_block(self.chain_id, self.height, self.hashes)
                now = time.monotonic()
                if found is not None:
                    self.hit = True
                    self.proven = False
                    self.miss_since = None
                    metrics_registry.increment("unavail_fetch_hit_total")
                else:
                    self.last_miss_mono = now
                    if self.miss_since is None:
                        self.miss_since = now
                    if now - self.miss_since >= need:
                        if not self.proven:
                            self.proven = True
                            metrics_registry.increment("unavail_fetch_persisted_total")
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - sampler failure must not wedge the gate
            logger.warning("unavail fetch sampler failed for %s h%s: %s", self.chain_id, self.height, exc)

    def state(self) -> bool:
        """True while the miss streak currently proves unavailability."""
        if self.hit or self.miss_since is None:
            return False
        # A stale last sample means the sampler is dead — do not trust it.
        # Freshness must exceed the sampler's own cadence (interval floor
        # 0.2 s, production default 10 s) or a healthy sampler reads stale.
        if self.last_miss_mono is None or time.monotonic() - self.last_miss_mono > max(1.0, 3 * sample_seconds()):
            return False
        return self.proven


_FETCH_SAMPLERS: dict[tuple[str, int, str], _FetchSampler] = {}
_FETCH_LOCK = asyncio.Lock()


async def unfetchable_persists(
    chain_id: str,
    height: int,
    block_hashes: list[str] | tuple[str, ...] | set[str],
    *,
    timeout: float | None = None,
) -> bool:
    """Await until ``block_hashes`` have been unfetchable for T_evidence.

    Returns True when the shared sampler proves a continuous miss streak
    of ``unavail_evidence_seconds``; False on a fetch hit, sampler failure,
    or ``timeout`` (default T_evidence + sampling slack). Concurrent calls
    for the same (chain, height, hashes) share one sampler.
    """
    wanted = tuple(sorted({h for h in block_hashes if h}))
    if not wanted:
        return False
    key = (chain_id, int(height), ",".join(wanted))
    async with _FETCH_LOCK:
        sampler = _FETCH_SAMPLERS.get(key)
        if sampler is None or sampler._stopped:
            sampler = _FetchSampler(chain_id, int(height), wanted)
            _FETCH_SAMPLERS[key] = sampler
            sampler.task = asyncio.ensure_future(sampler.run())
    need = evidence_seconds()
    interval = max(1.0, sample_seconds())
    wait = timeout if timeout is not None else need + 3 * interval + 5.0
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        if sampler.hit:
            return False
        if sampler.state():
            return True
        await asyncio.sleep(min(interval, max(0.05, deadline - time.monotonic())))
    return sampler.state()


# ---------------------------------------------------------------------------
# Combined predicate — the single release rule both gates share
# ---------------------------------------------------------------------------


def _carried_certs(
    request_cert: dict[str, Any] | UnavailabilityCertificate | None,
) -> dict[str, UnavailabilityCertificate]:
    """Normalise a carried justification into ``{block_hash: cert}``.

    Accepts a single cert (dict or dataclass) or the full unlock bundle
    whose ``certs`` list holds one cert per voted hash.
    """
    carried: dict[str, UnavailabilityCertificate] = {}
    if request_cert is None:
        return carried
    if isinstance(request_cert, dict) and isinstance(request_cert.get("certs"), list):
        items: list[Any] = list(request_cert["certs"])
    else:
        items = [request_cert]
    for item in items:
        cand = item if isinstance(item, UnavailabilityCertificate) else UnavailabilityCertificate.from_dict(item)
        if cand is not None:
            carried[cand.hash] = cand
    return carried


# ---------------------------------------------------------------------------
# UC probe — single-flight collection, negative backoff, success cache
# (#1281 respin guard rails A–D)
# ---------------------------------------------------------------------------
#
# The respin ordering is quiet-hash → probe → full re-verdict. The probe
# must never block the attest-request listener and must never storm the
# query topic, so collections are single-flight per (chain, height, hash):
#
# * ``_PROBE_TASKS`` — at most one in-flight ``collect_unavailability_cert``
#   per key; concurrent gate evaluations share it.
# * ``_PROBE_BACKOFF`` — monotonic deadline after a FAILED collection;
#   inside it ``_probe_cert`` returns None immediately (bounded — it always
#   expires, so a transient outage cannot suppress forever).
# * ``_CERT_CACHE`` — successful certs keyed by (chain, height, hash,
#   ignore-context); reused while the cert epoch is within
#   ``cert_max_age_seconds - 30``. Legs 1–2 are re-evaluated on every call,
#   so a revoked fetch or fresh attest traffic still blocks the unlock —
#   the cache only skips re-querying.

_PROBE_TASKS: dict[tuple[str, int, str], asyncio.Task[UnavailabilityCertificate | None]] = {}
_PROBE_BACKOFF: dict[tuple[str, int, str], float] = {}
_PROBE_LAST_SUCCESS: dict[tuple[str, int, str], float] = {}
_CERT_CACHE: dict[tuple[str, int, str, frozenset[str]], tuple[UnavailabilityCertificate, float]] = {}


def _probe_key(chain_id: str, height: int, block_hash: str) -> tuple[str, int, str]:
    return (chain_id, int(height), block_hash)


def _drop_probe_task(key: tuple[str, int, str], task: asyncio.Task[Any]) -> None:
    """Done-callback for ``_PROBE_TASKS`` — drops the entry only when it
    still refers to THIS task (a newer probe may already have replaced it)."""
    if _PROBE_TASKS.get(key) is task:
        _PROBE_TASKS.pop(key, None)


def _cert_cache_key(
    chain_id: str, height: int, block_hash: str, ignore: set[str] | None
) -> tuple[str, int, str, frozenset[str]]:
    return (chain_id, int(height), block_hash, frozenset(ignore or ()))


def _cert_cache_fresh(cert: UnavailabilityCertificate) -> bool:
    """Reuse margin: cert epoch must be within ``max_age - 30 s`` so a
    cached cert cannot be consumed in its final seconds of validity."""
    return time.time() - cert.epoch < cert_max_age_seconds() - 30.0


async def _run_probe(
    chain_id: str,
    height: int,
    block_hash: str,
    broker: Any | None,
    ignore: set[str] | None,
) -> UnavailabilityCertificate | None:
    """One shared collection; records success into the cache or arms the
    negative backoff. Runs as the ``_PROBE_TASKS`` value so every waiter
    observes the same outcome."""
    try:
        cert = await collect_unavailability_cert(chain_id, height, block_hash, broker=broker)
    except Exception as exc:  # noqa: BLE001 - a probe failure is a hold, never a crash
        logger.warning("unavail probe for %s h%s %s failed: %s", chain_id, height, block_hash[:18], exc)
        cert = None
    key = _probe_key(chain_id, height, block_hash)
    if cert is not None:
        _cert_cache_put(_cert_cache_key(chain_id, height, block_hash, ignore), cert)
        _PROBE_LAST_SUCCESS[key] = time.monotonic()
        if len(_PROBE_LAST_SUCCESS) > _PROBE_BOOKKEEPING_MAX:
            cutoff = time.monotonic() - (cert_max_age_seconds() - 30.0)
            for k in [k for k, ts in _PROBE_LAST_SUCCESS.items() if ts < cutoff]:
                _PROBE_LAST_SUCCESS.pop(k, None)
            if len(_PROBE_LAST_SUCCESS) > _PROBE_BOOKKEEPING_MAX:
                oldest = min(_PROBE_LAST_SUCCESS.items(), key=lambda kv: kv[1])
                _PROBE_LAST_SUCCESS.pop(oldest[0], None)
    else:
        _backoff_put(key, time.monotonic() + collect_backoff_seconds())
        metrics_registry.increment("unavail_collect_failed_total")
    return cert


# Bound the probe bookkeeping: heights that are never revisited must not
# grow these dicts without limit (E review c20822).
_PROBE_BOOKKEEPING_MAX = 512


def _cert_cache_put(key: tuple[str, int, str, frozenset[str]], cert: UnavailabilityCertificate) -> None:
    """Insert into ``_CERT_CACHE``, evicting stale-then-oldest past the cap."""
    if len(_CERT_CACHE) >= _PROBE_BOOKKEEPING_MAX:
        now = time.time()
        for k in [k for k, (c, _ts) in _CERT_CACHE.items() if now - c.epoch >= cert_max_age_seconds() - 30.0]:
            _CERT_CACHE.pop(k, None)
        if len(_CERT_CACHE) >= _PROBE_BOOKKEEPING_MAX:
            oldest = min(_CERT_CACHE.items(), key=lambda kv: kv[1][1])
            _CERT_CACHE.pop(oldest[0], None)
    _CERT_CACHE[key] = (cert, time.monotonic())


def _backoff_put(key: tuple[str, int, str], deadline: float) -> None:
    """Insert into ``_PROBE_BACKOFF``, evicting expired-then-earliest past the cap."""
    if len(_PROBE_BACKOFF) >= _PROBE_BOOKKEEPING_MAX:
        now = time.monotonic()
        for k in [k for k, d in _PROBE_BACKOFF.items() if d <= now]:
            _PROBE_BACKOFF.pop(k, None)
        if len(_PROBE_BACKOFF) >= _PROBE_BOOKKEEPING_MAX:
            earliest = min(_PROBE_BACKOFF.items(), key=lambda kv: kv[1])
            _PROBE_BACKOFF.pop(earliest[0], None)
    _PROBE_BACKOFF[key] = deadline


async def _probe_cert(
    chain_id: str,
    height: int,
    block_hash: str,
    carried: UnavailabilityCertificate | None,
    broker: Any | None,
    ignore: set[str] | None,
    *,
    wait: bool,
) -> UnavailabilityCertificate | None:
    """A valid UC for ``block_hash`` plus the visibility probe it feeds.

    Cert resolution order: carried (request-bound, verifies) → fresh
    cache → probe result. Independently of where the cert came from, the
    single-flight probe still runs whenever the quiet gate passed — it is
    the ONLY path that refreshes mesh-visibility actors on a cold index,
    so a carried cert alone must not skip it (E review c20822: a cold
    attester would otherwise never unlock). ``wait=False`` never awaits
    an in-flight collection — it returns the carried/cached cert (or
    None) so the attest-request listener stays responsive; the finished
    probe is picked up by the next evaluation.
    """
    cert = _resolve_local_cert(chain_id, height, block_hash, carried, ignore)
    task = _probe_task_for(chain_id, height, block_hash, broker, ignore, cert_resolved=cert is not None)
    if task is None:
        # Collection suppressed (backoff) or freshly completed — a
        # carried/cached cert may still be returned, but no new probe
        # runs to refresh visibility.
        return cert
    if not wait and not task.done():
        # Collection is in flight; the caller must not block — the cert
        # (carried/cached, possibly None) stands and the probe lands in
        # the cache for the next evaluation.
        return cert
    # shield: a cancelled waiter must not CancelledError the shared probe
    # out from under other waiters (E review c20822).
    result = await asyncio.shield(task)
    if cert is None:
        cert = result
    return cert


def _resolve_local_cert(
    chain_id: str,
    height: int,
    block_hash: str,
    carried: UnavailabilityCertificate | None,
    ignore: set[str] | None,
) -> UnavailabilityCertificate | None:
    """Carried (request-bound, verifies) then fresh-cache cert resolution."""
    if carried is not None:
        ok, _reason = verify_unavailability_cert(carried, chain_id=chain_id, height=height, block_hash=block_hash)
        if ok:
            return carried
    ckey = _cert_cache_key(chain_id, height, block_hash, ignore)
    cached = _CERT_CACHE.get(ckey)
    if cached is None or not _cert_cache_fresh(cached[0]):
        return None
    ok, _reason = verify_unavailability_cert(cached[0], chain_id=chain_id, height=height, block_hash=block_hash)
    if ok:
        return cached[0]
    _CERT_CACHE.pop(ckey, None)
    return None


def _probe_task_for(
    chain_id: str,
    height: int,
    block_hash: str,
    broker: Any | None,
    ignore: set[str] | None,
    *,
    cert_resolved: bool,
) -> asyncio.Task[UnavailabilityCertificate | None] | None:
    """The shared in-flight probe task, starting one unless suppressed.

    Returns None when collection is in backoff or a probe completed within
    the cert-cache lifetime while a servable cert exists (success-side
    throttle).
    """
    pkey = _probe_key(chain_id, height, block_hash)
    backoff_until = _PROBE_BACKOFF.get(pkey)
    if backoff_until is not None:
        if time.monotonic() < backoff_until:
            metrics_registry.increment("unavail_collect_backoff_total")
            return None
        _PROBE_BACKOFF.pop(pkey, None)
    task = _PROBE_TASKS.get(pkey)
    if task is not None:
        return task
    # Success-side throttle: while a servable cert exists (carried or
    # fresh-cached), a completed probe stays authoritative for the
    # cert-cache lifetime — responders' note_actor keeps mesh visibility
    # fresh far longer (visibility_seconds), so re-probing inside the
    # margin would only storm the topic. With NO servable cert the recent
    # success is not authoritative for this caller — the cache entry may
    # be stale/evicted or belong to a different ignore-context — so the
    # re-probe is allowed (backoff and single-flight still bound it).
    last_ok = _PROBE_LAST_SUCCESS.get(pkey)
    if cert_resolved and last_ok is not None and time.monotonic() - last_ok < cert_max_age_seconds() - 30.0:
        return None
    metrics_registry.increment("unavail_probe_total")
    task = asyncio.ensure_future(_run_probe(chain_id, height, block_hash, broker, ignore))
    _PROBE_TASKS[pkey] = task
    task.add_done_callback(partial(_drop_probe_task, pkey))
    return task


async def unlock_justification(
    chain_id: str,
    height: int,
    voted_hashes: list[str] | tuple[str, ...] | set[str],
    *,
    ignore: set[str] | None = None,
    request_cert: dict[str, Any] | UnavailabilityCertificate | None = None,
    broker: Any | None = None,
    wait_for_probe: bool = True,
) -> dict[str, Any] | None:
    """The armed-mode unlock justification, or None.

    Respin ordering (#1281 h35 deadlock fix — probe, then verify):

    1. ``unfetchable_persists`` — unchanged leg 1.
    2. Quiet gate per voted hash — no attest traffic inside T_evidence;
       fails ⇒ None with NO collection (a live hash is not abandoned).
    3. UC probe — single-flight collection; responders refresh the
       observation index's mesh-visibility actors.
    4. Post-probe FULL re-evaluation — quiet AND mesh_visible AND
       unfetchable AND cert, all re-checked: cert quorum is not mesh
       visibility, and acquisition is not authorization.

    ``wait_for_probe=False`` is for the attest-request listener path: it
    starts/shares the probe but returns None while a collection is in
    flight rather than blocking the listener for the collect window.
    """
    hashes = sorted({h for h in voted_hashes if h})
    if not hashes:
        return None
    # Leg 1: the voted block(s) must stay unfetchable for T_evidence.
    if not await unfetchable_persists(chain_id, height, hashes):
        return None
    index = await get_observation_index(chain_id)
    # Per voted hash: quiet gate → probe → full re-verdict. All conflicting
    # hashes must independently justify — a rival may only be voted against
    # a hash proven unable to join a quorum.
    carried = _carried_certs(request_cert)
    certs: list[UnavailabilityCertificate] = []
    verdicts: dict[str, dict[str, Any]] = {}
    for block_hash in hashes:
        quiet = index.quiet_verdict(height, block_hash, ignore=ignore)
        if not quiet["quiet"]:
            metrics_registry.increment("unavail_index_not_clean_total")
            metrics_registry.increment("unavail_not_quiet_total")
            return None
        cert = await _probe_cert(chain_id, height, block_hash, carried.get(block_hash), broker, ignore, wait=wait_for_probe)
        if cert is None:
            return None
        # Post-probe re-evaluation: a fetch hit or fresh attest traffic
        # during the collect window revokes the unlock; cert quorum alone
        # is not mesh visibility.
        if not await unfetchable_persists(chain_id, height, hashes):
            return None
        verdict = index.clean_verdict(height, block_hash, ignore=ignore)
        verdicts[block_hash] = verdict
        if not verdict["clean"]:
            metrics_registry.increment("unavail_index_not_clean_total")
            if not verdict.get("quiet", True):
                metrics_registry.increment("unavail_not_quiet_total")
            elif not verdict.get("mesh_visible", False):
                metrics_registry.increment("unavail_mesh_not_visible_total")
            return None
        certs.append(cert)
        metrics_registry.increment("unavail_unlock_justified_total")
    # Verdict summary for the first hash (per-hash counters differ only in
    # requests/attestations observed; the clean/mesh legs are shared).
    first = verdicts.get(hashes[0]) or index.clean_verdict(height, hashes[0], ignore=ignore)
    return {
        "kind": "unavailability_cert",
        "height": int(height),
        "hashes": hashes,
        "index": first,
        "certs": [c.to_dict() for c in certs],
    }
