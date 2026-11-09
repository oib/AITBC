"""#1311: replicate signature-bearing attestation-equivocation evidence.

Local detection (``remote_attestation._record_attestation_equivocation_evidence``)
records a pair of signed attestations on the node that saw them. Without
replication every other node's ``slashing_events_json`` is blind to it, so a
validator-deactivation bundle can only be built where the evidence happened to
be observed. This module is the gossip layer: a bounded in-memory store, a
record codec and the ingest pipeline. It is advisory — never slashes, never
gates a block — and every entry point is inert without
``equivocation_replication_enabled`` (default OFF).

Ingest order (design-v2 FINAL, c23274 + addendum c23455 + E's c24111):
size -> schema -> chain id -> reporter rate cap -> read-only duplicate
pre-filter -> validator membership -> signature verification (the admission
gate; ``deactivation_evidence._verify_attestation_equivocation``, domain-aware)
-> pair predicate -> atomic insert-or-ignore. Any failure drops the record with
a metric; nothing partial is stored.

Pair predicate: a record is *slashable context* only when BOTH signatures bind
the SAME round in their preimage (``PairClass.ROUND_BOUND_SAME_ROUND``). A
cross-round pair (a legitimate re-attest after a #1301 abandon), a legacy
height-only pair or a mixed-format pair is stored as non-slashable context and
is never handed to the recorder.
"""

from __future__ import annotations

import json
import time
from collections import OrderedDict, deque
from dataclasses import dataclass
from typing import Any

from aitbc.crypto.signature_recovery import canonical_address

from ..metrics import metrics_registry
from .equivocation_policy import PairClass, classify_attestation_pair

SCHEMA = 1
KIND = "attestation_equivocation"


def equivocation_topic(chain_id: str) -> str:
    return f"consensus.equivocation.{chain_id}"


def enabled() -> bool:
    from ..config import settings

    return bool(getattr(settings, "equivocation_replication_enabled", False))


def _cfg(name: str, default: int) -> int:
    from ..config import settings

    try:
        return int(getattr(settings, name, default))
    except (TypeError, ValueError):
        return default


def sorted_pair(a: str, b: str) -> tuple[str, str]:
    a, b = a.lower(), b.lower()
    return (a, b) if a <= b else (b, a)


def slot_key(chain_id: str, validator: str, height: int, round_: int | None) -> tuple[Any, ...]:
    return (chain_id, canonical_address(validator), int(height), round_)


def pair_key(chain_id: str, validator: str, height: int, round_: int | None, hash_a: str, hash_b: str) -> tuple[Any, ...]:
    a, b = sorted_pair(hash_a, hash_b)
    return (*slot_key(chain_id, validator, height, round_), a, b)


def build_record(
    chain_id: str,
    validator: str,
    height: int,
    round_: int | None,
    hash_a: str,
    hash_b: str,
    attestations: list[dict[str, Any]],
) -> dict[str, Any]:
    """The schema-1 wire record for one signed attestation pair."""
    a, b = sorted_pair(hash_a, hash_b)
    return {
        "schema": SCHEMA,
        "kind": KIND,
        "chain_id": chain_id,
        "height": int(height),
        "round": round_,
        "validator": canonical_address(validator),
        "block_hash_a": a,
        "block_hash_b": b,
        "attestations": sorted(attestations, key=lambda x: str(x.get("hash", "")).lower()),
    }


@dataclass(frozen=True)
class Outcome:
    status: str  # "stored" or the drop reason
    slashable: bool = False
    record: dict[str, Any] | None = None


class _Window:
    """Sliding-window rate cap per key (reporter address; the in-process broker
    carries no peer identity, and the signer is the party that is being reported)."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = {}

    def allow(self, key: str, limit: int, now: float, window: float = 60.0) -> bool:
        hits = self._hits.setdefault(key, deque())
        while hits and now - hits[0] > window:
            hits.popleft()
        if len(hits) >= limit:
            return False
        hits.append(now)
        if len(self._hits) > 4096:  # bound the key space against address spraying
            for stale in [k for k, h in self._hits.items() if not h or now - h[-1] > window]:
                del self._hits[stale]
        return True


class EvidenceStore:
    """Bounded FIFO store of accepted records for one chain.

    All mutation happens synchronously (no ``await`` between the membership
    test and the insert), so on the single event loop ``add_if_absent`` is an
    atomic insert-or-ignore. ``has`` is a pure read: no reorder, no expiry, no
    counter — it is a pre-filter only, never the admission gate.
    """

    def __init__(self, ring_cap: int | None = None) -> None:
        self._ring_cap = ring_cap
        self._records: OrderedDict[tuple[Any, ...], dict[str, Any]] = OrderedDict()
        self._slot_hashes: dict[tuple[Any, ...], dict[str, int]] = {}
        self._published: dict[tuple[Any, ...], int] = {}
        self.window = _Window()

    def __len__(self) -> int:
        return len(self._records)

    @property
    def cap(self) -> int:
        return self._ring_cap if self._ring_cap is not None else _cfg("equivocation_replication_ring_cap", 10000)

    def has(self, key: tuple[Any, ...]) -> bool:
        return key in self._records

    def get(self, key: tuple[Any, ...]) -> dict[str, Any] | None:
        return self._records.get(key)

    def slot_would_exceed(self, slot: tuple[Any, ...], hashes: tuple[str, str]) -> bool:
        known = self._slot_hashes.get(slot, {})
        distinct = set(known) | set(hashes)
        return len(distinct) > _cfg("equivocation_replication_max_hashes_per_slot", 4)

    def add_if_absent(self, key: tuple[Any, ...], record: dict[str, Any]) -> bool:
        if key in self._records:
            return False
        self._records[key] = record
        slot = key[:4]
        counts = self._slot_hashes.setdefault(slot, {})
        for h in key[4:6]:
            counts[h] = counts.get(h, 0) + 1
        while len(self._records) > self.cap:
            old_key, _ = self._records.popitem(last=False)
            self._published.pop(old_key, None)
            old_counts = self._slot_hashes.get(old_key[:4], {})
            for h in old_key[4:6]:
                if h in old_counts:
                    old_counts[h] -= 1
                    if old_counts[h] <= 0:
                        del old_counts[h]
            if not old_counts:
                self._slot_hashes.pop(old_key[:4], None)
            metrics_registry.increment("equivocation_evidence_evicted_total")
        return True

    def may_publish(self, key: tuple[Any, ...]) -> bool:
        """Per-record publish budget, per process lifetime (a restart resets it;
        receiver-side dedup is the real storm guard)."""
        used = self._published.get(key, 0)
        if used >= _cfg("equivocation_replication_max_publishes", 3):
            return False
        self._published[key] = used + 1
        return True


_stores: dict[str, EvidenceStore] = {}


def get_store(chain_id: str) -> EvidenceStore:
    store = _stores.get(chain_id)
    if store is None:
        store = _stores[chain_id] = EvidenceStore()
    return store


def reset_stores() -> None:
    _stores.clear()


def _drop(reason: str) -> Outcome:
    metrics_registry.increment("equivocation_ingest_dropped_total")
    metrics_registry.increment(f"equivocation_ingest_dropped_{reason}_total")
    return Outcome(reason)


def ingest(
    chain_id: str,
    payload: Any,
    validator_set: set[str],
    *,
    store: EvidenceStore | None = None,
    now: float | None = None,
) -> Outcome:
    """Run one received record through the pipeline; the caller records a
    ``slashable`` outcome through the chain's slashing recorder."""
    store = store if store is not None else get_store(chain_id)
    now = time.monotonic() if now is None else now
    # 1. size
    try:
        size = len(json.dumps(payload, sort_keys=True, default=str))
    except (TypeError, ValueError):
        return _drop("schema")
    if size > _cfg("equivocation_replication_max_record_bytes", 4096):
        return _drop("oversize")
    # 2. schema
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA or payload.get("kind") != KIND:
        return _drop("schema")
    try:
        height = int(payload["height"])
        round_ = payload.get("round")
        round_ = int(round_) if round_ is not None else None
        validator = canonical_address(str(payload["validator"]))
        hash_a, hash_b = str(payload["block_hash_a"]).lower(), str(payload["block_hash_b"]).lower()
    except (KeyError, TypeError, ValueError, AttributeError):
        return _drop("schema")
    attestations = payload.get("attestations")
    if not isinstance(attestations, list) or len(attestations) != 2 or not all(isinstance(a, dict) for a in attestations):
        return _drop("schema")  # hash-only records carry no slashable content
    if not hash_a or not hash_b or hash_a == hash_b or (hash_a, hash_b) != sorted_pair(hash_a, hash_b):
        return _drop("schema")
    # 3. chain id (the record, and each signed message that binds it)
    if payload.get("chain_id") != chain_id or any(a.get("chain_id") != chain_id for a in attestations):
        return _drop("chain")
    try:
        if any(int(a.get("height", height)) != height for a in attestations):
            return _drop("schema")
    except (TypeError, ValueError):
        return _drop("schema")
    # 4. reporter rate cap (keyed by the reported validator; broker gives no peer id)
    if not store.window.allow(validator, _cfg("equivocation_replication_rate_per_minute", 20), now):
        return _drop("rate")
    # 5. read-only duplicate pre-filter — a pure read, never the admission gate
    key = pair_key(chain_id, validator, height, round_, hash_a, hash_b)
    if store.has(key):
        metrics_registry.increment("equivocation_ingest_duplicate_total")
        return Outcome("duplicate")
    # 6. only a configured validator can be reported (blocks address-spray eviction)
    if validator not in {canonical_address(v) for v in validator_set}:
        return _drop("not_validator")
    # 7. signature verification — the admission gate
    if not _verify(payload, validator, height):
        return _drop("verify")
    # 8. pair predicate
    klass = classify_attestation_pair(payload)
    slashable = klass is PairClass.ROUND_BOUND_SAME_ROUND and round_ is not None
    if slashable:
        rounds = {a.get("request_round") for a in attestations}
        slashable = rounds == {round_}
    # 9. per-slot distinct-hash cap, then atomic insert-or-ignore
    if store.slot_would_exceed(key[:4], (hash_a, hash_b)):
        return _drop("slot_cap")
    stored = {k: v for k, v in payload.items() if k != "justification"}  # sender cannot pre-excuse a pair
    if not store.add_if_absent(key, stored):
        metrics_registry.increment("equivocation_ingest_duplicate_total")
        return Outcome("duplicate")
    metrics_registry.increment("equivocation_ingest_stored_total")
    if not slashable:
        metrics_registry.increment("equivocation_ingest_context_only_total")
    return Outcome("stored", slashable=slashable, record=stored)


def _verify(payload: dict[str, Any], validator: str, height: int) -> bool:
    from ..state.deactivation_evidence import _verify_attestation_equivocation
    from .slashing import SlashingCondition, SlashingEvent

    event = SlashingEvent(
        validator_address=validator,
        condition=SlashingCondition.DOUBLE_SIGN,
        evidence="",
        block_height=height,
        timestamp=0.0,
        slash_rate=0.0,
    )
    try:
        return bool(_verify_attestation_equivocation(payload, event, validator))
    except Exception:  # noqa: BLE001 - a malformed record is a drop, never a crash
        return False
