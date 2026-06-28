from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PeerCapability:
    """Tracks what blocks a peer has available for sync."""

    peer_id: str
    rpc_url: str
    block_range: tuple[int, int]  # (min_height, max_height)
    has_state: bool = False  # can provide state snapshots/deltas
    last_updated: float = field(default_factory=time.time)
    latency_ms: float = 0.0  # measured latency
    reputation: float = 1.0  # 0.0-1.0, decreases on failures


class PeerCapabilityTracker:
    """Tracks peer capabilities for parallel sync peer selection.

    Maintains a registry of peers and their block ranges. When a sync
    is needed, divides the missing range into sub-ranges and assigns
    each to the best available peer (lowest latency, highest reputation).
    """

    MIN_REPUTATION = 0.3  # peers below this are excluded from selection
    REPUTATION_INCREMENT = 0.05
    REPUTATION_DECREMENT = 0.1

    def __init__(self) -> None:
        self._peers: dict[str, PeerCapability] = {}
        self._lock = threading.Lock()

    def register_peer(self, capability: PeerCapability) -> None:
        """Register or update a peer's capabilities."""
        with self._lock:
            self._peers[capability.peer_id] = capability

    def remove_peer(self, peer_id: str) -> None:
        """Remove a peer from the tracker."""
        with self._lock:
            self._peers.pop(peer_id, None)

    def get_peer(self, peer_id: str) -> PeerCapability | None:
        """Get a peer's capability by ID."""
        with self._lock:
            return self._peers.get(peer_id)

    def get_all_peers(self) -> list[PeerCapability]:
        """Get all registered peers, sorted by reputation (descending)."""
        with self._lock:
            peers = list(self._peers.values())
        peers.sort(key=lambda p: p.reputation, reverse=True)
        return peers

    def select_peers_for_range(
        self, start_height: int, end_height: int, max_peers: int = 4
    ) -> list[tuple[str, tuple[int, int]]]:
        """Select peers to fetch a block range in parallel.

        Divides [start_height, end_height] into sub-ranges, one per peer.
        Returns list of (peer_id, sub_range) tuples.

        Selection criteria:
        1. Peer must have the block range (block_range covers sub-range)
        2. Sort by (reputation * 1000 - latency_ms) descending
        3. Assign sub-ranges to top N peers

        If fewer peers than sub-ranges, some peers get larger ranges.
        If no peers have the range, return empty list (caller falls back to sequential).
        """
        if start_height > end_height:
            return []
        with self._lock:
            peers = list(self._peers.values())
        # Filter by reputation threshold and block range coverage
        eligible = [
            p
            for p in peers
            if p.reputation >= self.MIN_REPUTATION and p.block_range[0] <= start_height and p.block_range[1] >= end_height
        ]
        if not eligible:
            return []
        # Sort by score: reputation * 1000 - latency_ms (descending)
        eligible.sort(key=lambda p: p.reputation * 1000 - p.latency_ms, reverse=True)
        # Limit to max_peers
        selected = eligible[:max_peers]
        # Divide range into sub-ranges
        total_blocks = end_height - start_height + 1
        num_peers = len(selected)
        base_size = total_blocks // num_peers
        remainder = total_blocks % num_peers
        result: list[tuple[str, tuple[int, int]]] = []
        current = start_height
        for i, peer in enumerate(selected):
            size = base_size + (1 if i < remainder else 0)
            sub_end = current + size - 1
            result.append((peer.peer_id, (current, sub_end)))
            current = sub_end + 1
        return result

    def record_success(self, peer_id: str, blocks_fetched: int) -> None:
        """Record a successful sync from this peer (increases reputation)."""
        with self._lock:
            peer = self._peers.get(peer_id)
            if peer:
                peer.reputation = min(1.0, peer.reputation + self.REPUTATION_INCREMENT)
                peer.last_updated = time.time()

    def record_failure(self, peer_id: str, reason: str = "") -> None:
        """Record a failed sync from this peer (decreases reputation)."""
        with self._lock:
            peer = self._peers.get(peer_id)
            if peer:
                peer.reputation = max(0.0, peer.reputation - self.REPUTATION_DECREMENT)
                peer.last_updated = time.time()

    def get_stats(self) -> dict[str, Any]:
        """Return stats: total_peers, avg_reputation, avg_latency."""
        with self._lock:
            peers = list(self._peers.values())
        if not peers:
            return {"total_peers": 0, "avg_reputation": 0.0, "avg_latency": 0.0}
        avg_rep = sum(p.reputation for p in peers) / len(peers)
        avg_lat = sum(p.latency_ms for p in peers) / len(peers)
        return {
            "total_peers": len(peers),
            "avg_reputation": avg_rep,
            "avg_latency": avg_lat,
        }
