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

- any peer ahead → STALE: skip this proposal and kick a bulk pull from that
  peer directly, bypassing the configured sync source;
- same height: the local hash votes alongside the peers'. A rival hash only
  blocks the proposal when it has STRICTLY more support than ours (a
  hash-diverged node then holds while the majority keeps producing); a tie
  proceeds and bumps ``proposal_freshness_hash_tie_total`` — holding on a tie
  would let one bad peer halt the whole chain;
- all peers unreachable → UNVERIFIED: propose anyway and bump
  ``proposal_freshness_unverified_total`` — blocking would trade liveness for
  safety on every network blip, and a partition is visible via the metric;
- otherwise → FRESH.

Two failure modes of the naive version are handled by the caller (PoA side):
an ahead peer whose pull never moves the local head — a taller fork the
importer rejects, or a peer overstating its height — is quarantined and
excluded from the ahead check for a while; when every ahead peer is
quarantined the verdict is QUARANTINED and the proposal proceeds with a
``proposal_freshness_peer_quarantined_total`` bump. And verdicts are cached
per local head only for a few seconds — UNVERIFIED is never cached — so a
network blip cannot carry a stale "fresh" verdict into a later round.
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
    HASH_MISMATCH = "hash_mismatch"  # a rival hash has strictly more support — hold
    HASH_TIE = "hash_tie"  # rival hash support ties ours — proceed, fork choice settles it
    QUARANTINED = "quarantined"  # every ahead peer was quarantined — proceed
    UNVERIFIED = "unverified"


@dataclass
class FreshnessResult:
    verdict: FreshnessVerdict
    peer_url: str | None = None
    peer_height: int | None = None
    peer_hash: str | None = None
    our_votes: int = 0
    rival_votes: int = 0


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
        """Fetch a peer's head; a malformed reply counts as unreachable."""
        try:
            resp = await SharedHttpClient.get(
                f"{base_url}/rpc/head",
                params={"chain_id": self._chain_id},
                timeout=self._timeout,
            )
            resp.raise_for_status()
            head = resp.json()
        except Exception:
            return None
        if not isinstance(head, dict):
            return None
        height, block_hash = head.get("height"), head.get("hash")
        if not isinstance(height, int) or isinstance(height, bool):
            return None
        if not isinstance(block_hash, str):
            return None
        return head

    async def check(
        self,
        local_height: int,
        local_hash: str,
        *,
        quarantined: set[str] | None = None,
    ) -> FreshnessResult:
        """Compare the local head against every configured peer, in parallel.

        ``quarantined`` peers still answer and still vote on hashes — they are
        only excluded from the ahead check, where their taller fork would
        otherwise silence us forever.
        """
        bases = []
        for u in self._peer_urls:
            if u.startswith(("http://", "https://")):
                bases.append(u)
            else:
                base = peer_base_url(u)
                if base:
                    bases.append(base)
        bases = list(dict.fromkeys(bases))
        if not bases:
            return FreshnessResult(FreshnessVerdict.FRESH)

        heads = await asyncio.gather(
            *(self._fetch(b) for b in bases),
            return_exceptions=True,
        )
        reachable = {
            base: head
            for base, head in zip(bases, heads, strict=True)
            if isinstance(head, dict)
            and isinstance(head.get("height"), int)
            and not isinstance(head.get("height"), bool)
            and isinstance(head.get("hash"), str)
        }
        if not reachable:
            return FreshnessResult(FreshnessVerdict.UNVERIFIED)

        skip = quarantined or set()
        ahead_all = {base: head for base, head in reachable.items() if head["height"] > local_height}
        ahead = {base: head for base, head in ahead_all.items() if base not in skip}
        if ahead:
            base, head = max(ahead.items(), key=lambda kv: kv[1]["height"])
            return FreshnessResult(
                FreshnessVerdict.STALE,
                peer_url=base,
                peer_height=head["height"],
                peer_hash=head.get("hash"),
            )

        # Nobody ahead (that we still trust): vote on the hash at our height.
        our_votes = 1  # we vote for our own head
        rivals: dict[str, int] = {}
        rival_peer: str | None = None
        for base, head in reachable.items():
            if head["height"] != local_height:
                continue
            if head["hash"] == local_hash:
                our_votes += 1
            else:
                rivals[head["hash"]] = rivals.get(head["hash"], 0) + 1
                rival_peer = base
        if rivals:
            rival_hash, rival_votes = max(rivals.items(), key=lambda kv: kv[1])
            if rival_votes > our_votes:
                return FreshnessResult(
                    FreshnessVerdict.HASH_MISMATCH,
                    peer_url=rival_peer,
                    peer_height=local_height,
                    peer_hash=rival_hash,
                    our_votes=our_votes,
                    rival_votes=rival_votes,
                )
            if rival_votes == our_votes:
                return FreshnessResult(
                    FreshnessVerdict.HASH_TIE,
                    peer_url=rival_peer,
                    peer_height=local_height,
                    peer_hash=rival_hash,
                    our_votes=our_votes,
                    rival_votes=rival_votes,
                )
            # Rival in the minority: proceed, but keep the observation in the
            # result so the caller can log that a diverged peer exists.
            return FreshnessResult(
                FreshnessVerdict.FRESH,
                peer_url=rival_peer,
                peer_height=local_height,
                peer_hash=rival_hash,
                our_votes=our_votes,
                rival_votes=rival_votes,
            )

        if ahead_all:
            tallest = max(ahead_all.items(), key=lambda kv: kv[1]["height"])
            return FreshnessResult(
                FreshnessVerdict.QUARANTINED,
                peer_url=tallest[0],
                peer_height=tallest[1]["height"],
            )
        return FreshnessResult(FreshnessVerdict.FRESH)
