"""Gossip-observation index for ``unavail`` (#1279 substrate).

Extracted verbatim from ``unavail.py``: ``GossipObservationIndex`` records
observed ``attest_request``/``attest_response`` traffic per
``(height, block_hash)`` — the "can never join quorum" leg of the unlock
justification. ``unavail.py`` re-exports the class so
``aitbc_chain.consensus.unavail.GossipObservationIndex`` keeps resolving
exactly as before.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from aitbc.crypto.signature_recovery import canonical_address

from ..metrics import metrics_registry
from .unavail_core import evidence_seconds, min_responses, obs_height_plausible, visibility_seconds

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

    @staticmethod
    def _entry_last(ent: dict[str, Any]) -> float:
        stamps = list(ent["req_actors"].values()) + list(ent["attestations"].values())
        return max(stamps) if stamps else 0.0

    def _evict_for(self, height: int) -> bool:
        """Make room for one new key at ``height``; False when nothing may go.

        #1964: never ``.clear()`` — a flood must not wipe unrelated quiet-window
        evidence. Victim order: (1) the entry whose last activity is oldest AND
        already outside ``evidence_seconds()`` (it can no longer block a quiet
        verdict); (2) the lowest-height entry strictly below the newcomer's
        height (older heights matter least); otherwise the newcomer is refused
        and the table keeps every in-window entry.
        """
        now = self._mono()
        win = evidence_seconds()
        stale = [(self._entry_last(e), k) for k, e in self._entries.items() if now - self._entry_last(e) >= win]
        if stale:
            del self._entries[min(stale)[1]]
            return True
        lower = [k for k in self._entries if k[0] < int(height)]
        if lower:
            del self._entries[min(lower)]
            return True
        return False

    def _entry(self, height: int, block_hash: str) -> dict[str, Any] | None:
        key = (int(height), block_hash)
        ent = self._entries.get(key)
        if ent is None:
            if len(self._entries) >= self._max_entries and not self._evict_for(height):
                metrics_registry.increment("unavail_obs_entry_refused_total")
                return None
            ent = {
                "requests": 0,
                "req_actors": {},  # actor -> last_request_mono
                "attestations": {},  # signer -> last_attest_mono
                # The signed attestation payload of the verified request that
                # created this entry (#1964): responses are authenticated
                # against it, so they can never create an entry themselves.
                "att_message": None,
            }
            self._entries[key] = ent
        return ent

    def attestation_message(self, height: int, block_hash: str) -> dict[str, Any] | None:
        """The verified request's attestation payload for ``(height, hash)``, if seen."""
        ent = self._entries.get((int(height), block_hash))
        msg = ent.get("att_message") if ent else None
        return msg if isinstance(msg, dict) else None

    def note_request(
        self,
        height: int,
        block_hash: str,
        actor: str,
        *,
        ignore: set[str] | None = None,
        att_message: dict[str, Any] | None = None,
        tip_hint: int | None = None,
    ) -> None:
        """An ``attest_request`` for ``block_hash`` was observed.

        Caller contract: the request already passed every authenticity check.
        ``att_message`` is its signed attestation payload; the first one for a
        key is kept so ``note_response`` feeds can be signature-checked (#1964).
        """
        try:
            canon = canonical_address(actor) if actor else ""
        except (AttributeError, TypeError, ValueError):
            canon = ""
        if canon and ignore and canon in ignore:
            return
        if not obs_height_plausible(height, tip_hint):
            metrics_registry.increment("unavail_obs_height_rejected_total")
            return
        now = self._mono()
        ent = self._entry(height, block_hash)
        if ent is None:
            return
        ent["requests"] += 1
        if att_message is not None and ent.get("att_message") is None:
            ent["att_message"] = att_message
        if canon:
            ent["req_actors"][canon] = now
        self._note_actor(height, canon or actor, now)

    def note_response(
        self,
        height: int,
        block_hash: str,
        validator: str,
        *,
        ignore: set[str] | None = None,
        tip_hint: int | None = None,
    ) -> None:
        """An ``attest_response`` for ``block_hash`` was observed.

        Caller contract (#1964): the response signature was verified against
        ``attestation_message`` — the production feed does this and only calls
        here for keys a verified request created, so responses cannot grow
        the table; this method records, it does not authenticate.
        """
        try:
            canon = canonical_address(validator)
        except (AttributeError, TypeError, ValueError):
            return
        if ignore and canon in ignore:
            return
        if not obs_height_plausible(height, tip_hint):
            metrics_registry.increment("unavail_obs_height_rejected_total")
            return
        now = self._mono()
        ent = self._entry(height, block_hash)
        if ent is None:
            return
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
