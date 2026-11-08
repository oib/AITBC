"""Fetch-before-unlock for the vote journal (#1268 Phase 1, item 2; #1280 P15-1).

When a validator holds a live vote for block X at height h and is asked to
vote for a rival Y (or to propose at h), the right first move is not to wait
out a timer but to find X: if any mesh peer serves it, pulling it advances the
tip past h, the rival then fails the parent check, and no second vote is ever
cast. Only when X cannot be found anywhere does the liveness valve in
``vote_journal.valve_open`` get a say.

#1280 three-way verdict: the same scan also distinguishes CONTENTION — a peer
serving a *different* block at h is positive evidence the height is contested
(a sealed rival propagating, or a live fork), which suppresses the re-vote
path as delay-only evidence rather than relying on the 300 s timer alone.
EMPTY (nobody serves anything at h) is neutral and leaves the valve as the
sole decider. Contention sightings are tracked per (chain, height) with a
freshness window and a fixed cap (``CONTENDED_MAX_SECONDS``) so stale or
stuck-peer evidence cannot suppress forever.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterable
from typing import Any, NamedTuple

from aitbc.aitbc_logging import get_logger
from aitbc.network import SharedHttpClient

from ..config import settings
from ..metrics import metrics_registry
from .proposal_freshness import peer_base_url

logger = get_logger(__name__)

# Seconds a (height, hash) lookup result is reused. Request storms at one
# height (several proposers, retries) must not turn into a peer-scan storm.
_THROTTLE_SECONDS = 5.0
_throttle: dict[tuple[str, int, str], tuple[float, str | None, str]] = {}
_THROTTLE_MAX = 256

# #1280: fixed cap on how long contention evidence may suppress the re-vote
# path, measured from the FIRST sighting at (chain, height). Delay-only: past
# the cap the normal valve semantics resume.
CONTENDED_MAX_SECONDS = 600.0

# (chain_id, height) -> contention sighting state.
_contention: dict[tuple[str, int], dict[str, Any]] = {}
_CONTENTION_MAX = 512


class ContentionInfo(NamedTuple):
    """Active contention sighting for one (chain, height)."""

    rival_hash: str
    sealed: bool
    base: str | None
    first_seen: float
    last_seen: float
    peers: int


def _peer_bases(chain_id: str) -> list[str]:
    bases: list[str] = []
    for u in settings.mesh_peer_urls_for_service(chain_id):
        if u.startswith(("http://", "https://")):
            bases.append(u)
        else:
            base = peer_base_url(u)
            if base:
                bases.append(base)
    return list(dict.fromkeys(bases))


def _rival_sealed(block: dict[str, Any]) -> bool:
    """True when the served rival carries enough remote attestations to be
    sealed material (self-authenticating quorum evidence in block metadata)."""
    meta = block.get("block_metadata")
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except Exception:  # noqa: BLE001 - malformed metadata reads as unsealed, the safe side for pulling
            return False
    if not isinstance(meta, dict):
        return False
    attestations = meta.get("attestations")
    if not isinstance(attestations, list):
        return False
    try:
        required = int(getattr(settings, "multi_validator_min_attestations", 2) or 2)
    except (TypeError, ValueError):
        required = 2
    return len(attestations) >= required


def _note_contention(chain_id: str, height: int, rival_hash: str, sealed: bool, base: str | None, peers: int) -> None:
    """Record/refresh a contention sighting. In-memory only: a restart simply
    re-observes on the next scan (the conservative direction is a fresh cap)."""
    key = (chain_id, height)
    now = time.time()
    entry = _contention.get(key)
    if entry is None:
        if len(_contention) >= _CONTENTION_MAX:
            _contention.clear()
        entry = {"first_seen": now, "rival_hash": rival_hash, "sealed": False, "base": None, "peers": 0}
        _contention[key] = entry
    entry["last_seen"] = now
    entry["peers"] = max(entry["peers"], peers)
    # Prefer sealed evidence and the peer that served it for the accelerant.
    if sealed or not entry["sealed"]:
        entry["rival_hash"] = rival_hash
        entry["sealed"] = entry["sealed"] or sealed
        if base is not None:
            entry["base"] = base


def contention_hold(chain_id: str, height: int, now: float | None = None) -> ContentionInfo | None:
    """Active contention suppression for (chain, height), or None.

    Returns the sighting while it is fresh (seen within
    ``vote_journal_contention_fresh_seconds``) AND under the fixed
    ``CONTENDED_MAX_SECONDS`` cap from first observation. Stale or capped
    entries are dropped — the caller then falls back to plain valve timing.
    """
    key = (chain_id, height)
    entry = _contention.get(key)
    if entry is None:
        return None
    now = time.time() if now is None else now
    fresh = float(getattr(settings, "vote_journal_contention_fresh_seconds", 60.0) or 60.0)
    if now - float(entry["last_seen"]) > fresh or now - float(entry["first_seen"]) >= CONTENDED_MAX_SECONDS:
        _contention.pop(key, None)
        return None
    return ContentionInfo(
        rival_hash=str(entry["rival_hash"]),
        sealed=bool(entry["sealed"]),
        base=entry.get("base"),
        first_seen=float(entry["first_seen"]),
        last_seen=float(entry["last_seen"]),
        peers=int(entry["peers"]),
    )


async def _scan_peers(
    chain_id: str, height: int, wanted: list[str], timeout: float
) -> tuple[str | None, list[tuple[str, dict[str, Any]]]]:
    """One pass over the mesh: (base serving a wanted hash, peers serving a rival at h)."""
    found: str | None = None
    contention: list[tuple[str, dict[str, Any]]] = []
    for base in _peer_bases(chain_id):
        try:
            resp = await SharedHttpClient.get(f"{base}/rpc/block/{height}", params={"chain_id": chain_id}, timeout=timeout)
            if resp.status_code != 200:
                continue
            block = resp.json()
        except Exception:  # noqa: BLE001 - per-peer fetch containment: one bad peer must not break the scan
            continue
        if not isinstance(block, dict):
            continue
        served_hash = block.get("hash")
        if served_hash in wanted:
            found = base
            break
        if served_hash:
            contention.append((base, block))
    return found, contention


def _note_contention_sighting(chain_id: str, height: int, contention: list[tuple[str, dict[str, Any]]]) -> None:
    """Record the best rival sighting: sealed evidence preferred for the accelerant."""
    sealed_pick = next(((b, blk) for b, blk in contention if _rival_sealed(blk)), None)
    pick_base, pick_block = sealed_pick or contention[0]
    _note_contention(
        chain_id,
        height,
        str(pick_block.get("hash") or ""),
        _rival_sealed(pick_block),
        pick_base,
        len({b for b, _ in contention}),
    )


async def locate_voted_block(chain_id: str, height: int, block_hashes: Iterable[str]) -> str | None:
    """Base URL of a mesh peer that serves one of ``block_hashes`` at ``height``.

    Three-way verdict (#1280): FOUND returns the serving peer's base (caller
    pulls + refuses); CONTENTION — a peer serves a different block at h — is
    recorded via ``_note_contention`` and returns None like EMPTY, but
    ``contention_hold`` then suppresses the re-vote path while fresh and
    under the cap. A found result, a contention sighting and a miss are all
    reused for ``_THROTTLE_SECONDS``.
    """
    wanted = sorted({h for h in block_hashes if h})
    if not wanted:
        return None
    key = (chain_id, height, ",".join(wanted))
    now = time.monotonic()
    cached = _throttle.get(key)
    if cached is not None and now - cached[0] < _THROTTLE_SECONDS:
        return cached[1]
    timeout = getattr(settings, "proposal_freshness_peer_timeout_seconds", 2.0)
    found, contention = await _scan_peers(chain_id, height, wanted, timeout)
    if found is not None:
        verdict = "found"
    elif contention:
        verdict = "contention"
        _note_contention_sighting(chain_id, height, contention)
        metrics_registry.increment("vote_fetch_contention_total")
    else:
        verdict = "empty"
    if len(_throttle) >= _THROTTLE_MAX:
        _throttle.clear()
    _throttle[key] = (now, found, verdict)
    if verdict == "found":
        metrics_registry.increment("vote_fetch_found_total")
    elif verdict == "empty":
        metrics_registry.increment("vote_fetch_missing_total")
    return found


def kick_pull(pull: Callable[[str, str], Any] | None, chain_id: str, base: str) -> bool:
    """Ask the sync manager to pull from ``base``; False when it cannot."""
    if pull is None:
        return False
    try:
        pull(chain_id, base)
        return True
    except Exception as exc:  # noqa: BLE001 - a failed kick leaves the vote held, which is the safe side
        logger.warning("vote-journal pull from %s failed: %s", base, exc)
        return False


def reset_throttle() -> None:
    _throttle.clear()
    _contention.clear()
