"""Detection and reporting of chain divergence from a peer.

A follower that holds a different block than its peer at the same height cannot recover on its
own. Pushed blocks are refused by the longest-chain rule in `_resolve_fork`, and pulls answer
"Already up to date" because the peer's height is *below* ours — which is exactly what a
follower sees after its hub is reset to genesis while the follower keeps the pre-reset history.

That state persisted for 46 hours in production (V23-90) while four separate mechanisms watched
it happen: the bulk sync compared heights and never hashes, the force-pull gap check could not
represent a negative gap, fork rejections were never counted toward the resync threshold, and
the state-root comparison logged `match=False` 414 times at INFO.

This module notices and reports. It deliberately does not act: discarding accepted local
history is a decision for an operator, and the peer is not always the side that is right.

The throttle state is module-level because nothing that detects divergence lives long enough to
hold it — `ChainSync` is constructed per pushed block in `subscription_client._import_block` and
per cycle in `main._periodic_sync_task`.
"""

from __future__ import annotations

import time
from typing import Any, NamedTuple

from sqlmodel import select

from .base_models import Block
from .config import settings
from .logger import get_logger
from .metrics import metrics_registry
from .sync_base import SyncBase

logger = get_logger(__name__)


class Divergence(NamedTuple):
    """A height at which our block and the peer's disagree."""

    height: int
    our_hash: str
    peer_hash: str
    peer_url: str


_last_reported: dict[str, float] = {}


def report_divergence(chain_id: str, div: Divergence) -> bool:
    """Log one actionable error per `divergence_report_interval`; return whether it logged.

    Every caller reports every time it notices, and the throttle decides what reaches the log —
    otherwise a follower that receives a block a second would emit a line a second.
    """
    metrics_registry.increment("sync_divergence_detected_total")
    metrics_registry.set_gauge("sync_diverged", 1.0)
    now = time.monotonic()
    last = _last_reported.get(chain_id)
    interval = getattr(settings, "divergence_report_interval", 300)
    if last is not None and now - last < interval:
        return False
    _last_reported[chain_id] = now
    logger.error(
        "Chain divergence on %s: peer %s has block %s at height %s where we have %s. No block from this peer can be "
        "imported until this is resolved. If the peer is authoritative, resync this node with "
        "`sudo CHAIN_ID=%s /opt/aitbc/scripts/ops/reset-follower-to-genesis.sh` — it backs the database up first and "
        "discards local blocks from height %s upward. If this node is authoritative, the peer needs the resync instead.",
        chain_id,
        div.peer_url,
        div.peer_hash,
        div.height,
        div.our_hash,
        chain_id,
        div.height,
        extra={
            "chain_id": chain_id,
            "divergence_height": div.height,
            "our_hash": div.our_hash,
            "peer_hash": div.peer_hash,
            "peer_url": div.peer_url,
        },
    )
    return True


def clear_divergence(chain_id: str) -> None:
    """Forget a resolved divergence, so the next one is reported immediately rather than throttled."""
    _last_reported.pop(chain_id, None)
    metrics_registry.set_gauge("sync_diverged", 0.0)


class DivergenceMixin(SyncBase):
    """Compare a peer's history against our own."""

    def detect_divergence(self, peer_url: str, peer_height: int, peer_hash: str) -> Divergence | None:
        """Return the disagreement at the peer's head height, or None if there is none.

        `peer_height <= our_height` on its own does not mean we are up to date — it is also what
        a diverged follower sees. The hash we hold at that height is what tells the two apart.
        Returns None when we have no block at that height, which is the ordinary case of a peer
        ahead of us with nothing to compare.
        """
        if peer_height < 0 or not peer_hash:
            return None
        with self._session_factory() as session:
            ours = session.exec(
                select(Block).where(Block.chain_id == self._chain_id).where(Block.height == peer_height)
            ).first()
        if ours is None or ours.hash == peer_hash:
            return None
        return Divergence(height=peer_height, our_hash=ours.hash, peer_hash=peer_hash, peer_url=peer_url)

    async def peer_head_divergence(self, source_url: str) -> Divergence | None:
        """Fetch the peer's head and compare it with the block we hold at that height."""
        try:
            resp = await self._client.get(f"{source_url}/rpc/head", params={"chain_id": self._chain_id})
            resp.raise_for_status()
            head: dict[str, Any] = resp.json()
        except Exception as e:
            logger.warning(
                "Divergence check skipped: could not fetch peer head from %s: %s",
                source_url,
                e,
                extra={"chain_id": self._chain_id, "source_url": source_url},
            )
            return None
        return self.detect_divergence(source_url, head.get("height", -1), head.get("hash", ""))
