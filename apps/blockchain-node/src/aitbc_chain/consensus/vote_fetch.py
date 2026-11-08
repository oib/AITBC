"""Fetch-before-unlock for the vote journal (#1268 Phase 1, item 2).

When a validator holds a live vote for block X at height h and is asked to
vote for a rival Y (or to propose at h), the right first move is not to wait
out a timer but to find X: if any mesh peer serves it, pulling it advances the
tip past h, the rival then fails the parent check, and no second vote is ever
cast. Only when X cannot be found anywhere does the liveness valve in
``vote_journal.valve_open`` get a say.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from typing import Any

from aitbc.aitbc_logging import get_logger
from aitbc.network import SharedHttpClient

from ..config import settings
from ..metrics import metrics_registry
from .proposal_freshness import peer_base_url

logger = get_logger(__name__)

# Seconds a (height, hash) lookup result is reused. Request storms at one
# height (several proposers, retries) must not turn into a peer-scan storm.
_THROTTLE_SECONDS = 5.0
_throttle: dict[tuple[str, int, str], tuple[float, str | None]] = {}
_THROTTLE_MAX = 256


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


async def locate_voted_block(chain_id: str, height: int, block_hashes: Iterable[str]) -> str | None:
    """Base URL of a mesh peer that serves one of ``block_hashes`` at ``height``.

    None when no peer does (or no peers are configured). A found result and a
    miss are both reused for ``_THROTTLE_SECONDS``.
    """
    wanted = sorted({h for h in block_hashes if h})
    if not wanted:
        return None
    key = (chain_id, height, ",".join(wanted))
    now = time.monotonic()
    cached = _throttle.get(key)
    if cached is not None and now - cached[0] < _THROTTLE_SECONDS:
        return cached[1]
    found: str | None = None
    timeout = getattr(settings, "proposal_freshness_peer_timeout_seconds", 2.0)
    for base in _peer_bases(chain_id):
        try:
            resp = await SharedHttpClient.get(f"{base}/rpc/block/{height}", params={"chain_id": chain_id}, timeout=timeout)
            if resp.status_code != 200:
                continue
            block = resp.json()
        except Exception:  # noqa: BLE001 - per-peer fetch containment: one bad peer must not break the scan
            continue
        if isinstance(block, dict) and block.get("hash") in wanted:
            found = base
            break
    if len(_throttle) >= _THROTTLE_MAX:
        _throttle.clear()
    _throttle[key] = (now, found)
    metrics_registry.increment("vote_fetch_found_total" if found else "vote_fetch_missing_total")
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
