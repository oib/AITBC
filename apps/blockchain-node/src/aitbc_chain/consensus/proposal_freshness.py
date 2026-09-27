"""Pre-proposal freshness check.

Closes the stale-head fork vector found 2026-09-27: a validator whose sync
source was itself (or dead) restarted behind the tip and proposed on its old
head, creating a same-height fork that followers then pulled. CHAIN_SYNC_SOURCES
maps at most one URL per chain, so the pull topology is a star — while the
default source is down, a follower that misses a gossip block has nowhere to
catch up from and still owns rounds.

Before a proposal is assembled, this gate fetches ``/rpc/head`` from every
peer in ``GOSSIP_MESH_PEER_URLS`` (the ``wss://…/rpc/gossip/ws`` URLs map to
their ``https://`` origin) in parallel:

- any peer ahead  → STALE: skip this proposal and kick a bulk pull from that
  peer directly, bypassing the configured sync source;
- same height but a different hash → HASH_MISMATCH: skip; resolving the fork
  is the deterministic fork-choice task, and proposing on top deepens it;
- all peers unreachable → UNVERIFIED: propose anyway and bump
  ``proposal_freshness_unverified_total`` — blocking would trade liveness for
  safety on every network blip, and a partition is visible via the metric;
- otherwise → FRESH.

The result is cached per local head (height, hash): heads are monotonic, so a
single-slot cache suffices and rapid proposer ticks do not refetch.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any
from urllib.parse import urlparse

from aitbc.network import SharedHttpClient

from ..logger import get_logger

logger = get_logger(__name__)


class FreshnessVerdict(Enum):
    FRESH = "fresh"
    STALE = "stale"
    HASH_MISMATCH = "hash_mismatch"
    UNVERIFIED = "unverified"


@dataclass
class FreshnessResult:
    verdict: FreshnessVerdict
    peer_url: str | None = None
    peer_height: int | None = None
    peer_hash: str | None = None


def peer_base_url(gossip_url: str) -> str | None:
    """Map a mesh gossip URL to the peer's HTTP(S) RPC origin.

    ``wss://hub1.example/rpc/gossip/ws`` → ``https://hub1.example``;
    ``ws://10.0.0.1:8202/rpc/gossip/ws`` → ``http://10.0.0.1:8202``.
    Returns None for URLs that are not ws/wss or carry no host.
    """
    try:
        parsed = urlparse(gossip_url.strip())
    except ValueError:
        return None
    if parsed.scheme == "wss":
        scheme = "https"
    elif parsed.scheme == "ws":
        scheme = "http"
    else:
        return None
    if not parsed.netloc:
        return None
    return f"{scheme}://{parsed.netloc}"


class ProposalFreshnessChecker:
    """Queries peer heads and decides whether the local head is fresh enough to build on."""

    def __init__(
        self,
        *,
        chain_id: str,
        peer_urls: list[str] | None = None,
        fetch: Callable[[str], Awaitable[dict[str, Any] | None]] | None = None,
        timeout: float = 2.0,
    ) -> None:
        self._chain_id = chain_id
        self._peer_urls = peer_urls or []
        self._timeout = timeout
        self._fetch = fetch or self._fetch_head

    @property
    def peer_urls(self) -> list[str]:
        return list(self._peer_urls)

    async def _fetch_head(self, base_url: str) -> dict[str, Any] | None:
        try:
            resp = await SharedHttpClient.get(
                f"{base_url}/rpc/head",
                params={"chain_id": self._chain_id},
                timeout=self._timeout,
            )
            resp.raise_for_status()
            head = resp.json()
            if not isinstance(head, dict) or "height" not in head:
                return None
            return head
        except Exception:
            return None

    async def check(self, local_height: int, local_hash: str) -> FreshnessResult:
        """Compare the local head against every configured peer, in parallel."""
        bases = []
        for u in self._peer_urls:
            if u.startswith(("http://", "https://")):
                bases.append(u)
            else:
                base = peer_base_url(u)
                if base:
                    bases.append(base)
        if not bases:
            return FreshnessResult(FreshnessVerdict.FRESH)

        heads = await asyncio.gather(
            *(self._fetch(b) for b in bases),
            return_exceptions=True,
        )
        reachable = {base: head for base, head in zip(bases, heads, strict=True) if isinstance(head, dict)}
        if not reachable:
            return FreshnessResult(FreshnessVerdict.UNVERIFIED)

        ahead = {base: head for base, head in reachable.items() if int(head.get("height") or -1) > local_height}
        if ahead:
            base, head = max(ahead.items(), key=lambda kv: int(kv[1].get("height") or -1))
            return FreshnessResult(
                FreshnessVerdict.STALE,
                peer_url=base,
                peer_height=int(head.get("height") or -1),
                peer_hash=head.get("hash"),
            )

        for base, head in reachable.items():
            peer_height = int(head.get("height") or -1)
            peer_hash = head.get("hash") or ""
            if peer_height == local_height and peer_hash and peer_hash != local_hash:
                return FreshnessResult(
                    FreshnessVerdict.HASH_MISMATCH,
                    peer_url=base,
                    peer_height=peer_height,
                    peer_hash=peer_hash,
                )
        return FreshnessResult(FreshnessVerdict.FRESH)
