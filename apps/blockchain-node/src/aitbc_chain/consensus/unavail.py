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
import time
from functools import partial
from typing import Any

from aitbc.aitbc_logging import get_logger

from ..gossip import gossip_broker
from ..metrics import metrics_registry
from .vote_fetch import locate_voted_block

logger = get_logger(__name__)


def verify_unavailability_cert(
    cert: UnavailabilityCertificate | dict[str, Any],
    *,
    chain_id: str,
    height: int,
    block_hash: str,
    validator_set: set[str] | None = None,
    now: float | None = None,
    max_age: float | None = None,
    min_resp: int | None = None,
) -> tuple[bool, str]:
    """The one pure verifier shared by every consumer (#1281).

    Returns ``(True, "")`` or ``(False, reason)``. Checks, in order:
    version/kind, chain/height/hash binding, epoch freshness, per-response
    signature + validator-set membership, distinct signers, threshold.

    ``max_age`` / ``min_resp`` override the node-local settings; the on-chain
    apply path (#1281) passes them with ``now`` and ``validator_set`` so the
    verdict depends only on chain state, never on this node's clock/settings.
    """
    cert_obj = UnavailabilityCertificate.from_dict(cert) if isinstance(cert, dict) else cert
    if not isinstance(cert_obj, UnavailabilityCertificate):
        return False, "malformed"
    if cert_obj.chain_id != chain_id:
        return False, "chain_mismatch"
    if cert_obj.height != int(height):
        return False, "height_mismatch"
    if cert_obj.hash != block_hash:
        return False, "hash_mismatch"
    now_w = time.time() if now is None else now
    if abs(now_w - cert_obj.epoch) > (cert_max_age_seconds() if max_age is None else max_age):
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
    if len(seen) < (min_responses() if min_resp is None else min_resp):
        return False, "below_threshold"
    return True, ""


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
    block: bool = True,
) -> bool:
    """Await until ``block_hashes`` have been unfetchable for T_evidence.

    ``block=False`` (#1306, attest-listener path): start/join the shared
    sampler and return its *current* verdict at once — True only if the
    miss streak has already matured to T_evidence — never polling or
    sleeping. The sampler keeps running, so a later call sees the matured
    streak.

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
    if not block:
        return (not sampler.hit) and sampler.state()
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
    nonblocking_persist: bool = False,
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

    ``nonblocking_persist=True`` (#1306, flag-gated by the caller) applies the
    same idea to leg 1: ``unfetchable_persists(..., block=False)`` reads the
    sampler's current verdict instead of waiting out T_evidence inside the
    listener. Default False = blocking, unchanged.
    """
    hashes = sorted({h for h in voted_hashes if h})
    if not hashes:
        return None
    # Leg 1: the voted block(s) must stay unfetchable for T_evidence.
    if not await unfetchable_persists(chain_id, height, hashes, block=not nonblocking_persist):
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
        if not await unfetchable_persists(chain_id, height, hashes, block=not nonblocking_persist):
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


# -- Split helpers -------------------------------------------------------------
# Payloads/cert helpers live in ``unavail_core`` and the observation index in
# ``unavail_index``; every name is re-exported here so
# ``aitbc_chain.consensus.unavail.<name>`` keeps resolving (and staying
# monkeypatchable) exactly as it did when this was a single module.
from .unavail_core import (  # noqa: F401
    OBS_HEIGHT_AHEAD,
    OBS_HEIGHT_BEHIND,
    QUERY_TYPE,
    RESPONSE_TYPE,
    UC_VERSION,
    UNAVAIL_TAG,
    UnavailabilityCertificate,
    _carried_certs,
    _float,
    _int,
    _matching_response_signer,
    _verify_cert_response,
    build_unavail_response,
    cert_max_age_seconds,
    cert_message,
    collect_backoff_seconds,
    collect_seconds,
    evidence_seconds,
    justification_enabled,
    min_responses,
    nonblocking_persist_enabled,
    obs_height_plausible,
    query_topic,
    response_topic,
    sample_seconds,
    unavail_response_message,
    validator_addresses,
    verify_unavail_response,
    visibility_seconds,
)
from .unavail_index import GossipObservationIndex  # noqa: F401


def __getattr__(name: str):
    """Resolve any other previously-importable name against the helper modules.

    Keeps collaborator names that moved with the helpers (``settings``,
    ``canonical_address``, ``verify_consensus_message`` …) importable from
    ``aitbc_chain.consensus.unavail`` exactly as before the split.
    """
    from . import unavail_core as _core
    from . import unavail_index as _index_mod

    for _mod in (_core, _index_mod):
        try:
            return getattr(_mod, name)
        except AttributeError:
            continue
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
