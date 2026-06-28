from __future__ import annotations

import threading

from aitbc.sync.peer_capability import PeerCapability, PeerCapabilityTracker


def test_register_and_get_peer():
    tracker = PeerCapabilityTracker()
    cap = PeerCapability(peer_id="peer1", rpc_url="http://peer1:8202", block_range=(0, 1000))
    tracker.register_peer(cap)
    assert tracker.get_peer("peer1") is not None
    assert tracker.get_peer("peer1").rpc_url == "http://peer1:8202"
    tracker.remove_peer("peer1")
    assert tracker.get_peer("peer1") is None


def test_select_peers_for_range_even_division():
    """4 peers, 100 blocks -> 4 sub-ranges of 25."""
    tracker = PeerCapabilityTracker()
    for i in range(4):
        tracker.register_peer(
            PeerCapability(
                peer_id=f"peer{i}",
                rpc_url=f"http://peer{i}:8202",
                block_range=(0, 1000),
                latency_ms=10.0 * i,
            )
        )
    result = tracker.select_peers_for_range(1, 100, max_peers=4)
    assert len(result) == 4
    # Verify ranges cover 1-100 with no gaps
    ranges = [r for _, r in result]
    assert ranges[0][0] == 1
    assert ranges[-1][1] == 100
    for i in range(len(ranges) - 1):
        assert ranges[i][1] + 1 == ranges[i + 1][0]


def test_select_peers_fewer_peers_than_ranges():
    """2 peers, 100 blocks -> 2 sub-ranges of 50."""
    tracker = PeerCapabilityTracker()
    tracker.register_peer(PeerCapability(peer_id="p1", rpc_url="http://p1", block_range=(0, 1000)))
    tracker.register_peer(PeerCapability(peer_id="p2", rpc_url="http://p2", block_range=(0, 1000)))
    result = tracker.select_peers_for_range(1, 100, max_peers=4)
    assert len(result) == 2
    total = sum(r[1] - r[0] + 1 for _, r in result)
    assert total == 100


def test_select_peers_no_peers_with_range():
    """No peers have the blocks -> empty list."""
    tracker = PeerCapabilityTracker()
    tracker.register_peer(PeerCapability(peer_id="p1", rpc_url="http://p1", block_range=(0, 50)))
    result = tracker.select_peers_for_range(60, 100)
    assert result == []


def test_select_peers_filters_low_reputation():
    """Peer with reputation < 0.3 excluded."""
    tracker = PeerCapabilityTracker()
    tracker.register_peer(PeerCapability(peer_id="p1", rpc_url="http://p1", block_range=(0, 1000), reputation=0.2))
    result = tracker.select_peers_for_range(1, 100)
    assert result == []


def test_select_peers_sorts_by_reputation_and_latency():
    """Best peer (highest reputation, lowest latency) gets first pick."""
    tracker = PeerCapabilityTracker()
    tracker.register_peer(PeerCapability(peer_id="slow", rpc_url="http://slow", block_range=(0, 1000), latency_ms=500))
    tracker.register_peer(PeerCapability(peer_id="fast", rpc_url="http://fast", block_range=(0, 1000), latency_ms=10))
    result = tracker.select_peers_for_range(1, 100, max_peers=2)
    assert result[0][0] == "fast"  # lower latency = higher score


def test_record_success_increases_reputation():
    tracker = PeerCapabilityTracker()
    tracker.register_peer(PeerCapability(peer_id="p1", rpc_url="http://p1", block_range=(0, 1000), reputation=0.5))
    tracker.record_success("p1", blocks_fetched=50)
    assert tracker.get_peer("p1").reputation == 0.55


def test_record_failure_decreases_reputation():
    tracker = PeerCapabilityTracker()
    tracker.register_peer(PeerCapability(peer_id="p1", rpc_url="http://p1", block_range=(0, 1000), reputation=0.5))
    tracker.record_failure("p1", reason="timeout")
    assert tracker.get_peer("p1").reputation == 0.4


def test_record_success_caps_at_1():
    tracker = PeerCapabilityTracker()
    tracker.register_peer(PeerCapability(peer_id="p1", rpc_url="http://p1", block_range=(0, 1000), reputation=0.98))
    tracker.record_success("p1", blocks_fetched=10)
    assert tracker.get_peer("p1").reputation == 1.0


def test_record_failure_floors_at_0():
    tracker = PeerCapabilityTracker()
    tracker.register_peer(PeerCapability(peer_id="p1", rpc_url="http://p1", block_range=(0, 1000), reputation=0.05))
    tracker.record_failure("p1")
    assert tracker.get_peer("p1").reputation == 0.0


def test_get_stats():
    tracker = PeerCapabilityTracker()
    tracker.register_peer(
        PeerCapability(peer_id="p1", rpc_url="http://p1", block_range=(0, 1000), reputation=0.8, latency_ms=10)
    )
    tracker.register_peer(
        PeerCapability(peer_id="p2", rpc_url="http://p2", block_range=(0, 1000), reputation=0.6, latency_ms=30)
    )
    stats = tracker.get_stats()
    assert stats["total_peers"] == 2
    assert abs(stats["avg_reputation"] - 0.7) < 0.01
    assert abs(stats["avg_latency"] - 20.0) < 0.01


def test_get_stats_empty():
    tracker = PeerCapabilityTracker()
    stats = tracker.get_stats()
    assert stats["total_peers"] == 0
    assert stats["avg_reputation"] == 0.0


def test_thread_safety():
    """Concurrent register/select doesn't crash."""
    tracker = PeerCapabilityTracker()
    errors = []

    def worker():
        try:
            for i in range(100):
                tracker.register_peer(
                    PeerCapability(
                        peer_id=f"peer-{threading.get_ident()}-{i}",
                        rpc_url="http://peer",
                        block_range=(0, 10000),
                    )
                )
                tracker.select_peers_for_range(1, 100)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors


def test_get_all_peers_sorted_by_reputation():
    tracker = PeerCapabilityTracker()
    tracker.register_peer(PeerCapability(peer_id="low", rpc_url="http://low", block_range=(0, 1000), reputation=0.3))
    tracker.register_peer(PeerCapability(peer_id="high", rpc_url="http://high", block_range=(0, 1000), reputation=0.9))
    peers = tracker.get_all_peers()
    assert peers[0].peer_id == "high"
    assert peers[1].peer_id == "low"
