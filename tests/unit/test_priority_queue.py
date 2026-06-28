from __future__ import annotations

import threading
import time

from aitbc.gossip.priority_queue import PriorityMessageQueue


def test_priority_ordering():
    """Block messages come before transaction messages."""
    q = PriorityMessageQueue()
    q.put("transactions", {"tx": "abc"}, priority=PriorityMessageQueue.PRIORITY_TRANSACTION)
    q.put("blocks", {"block": 1}, priority=PriorityMessageQueue.PRIORITY_BLOCK)
    q.put("status", {"status": "ok"}, priority=PriorityMessageQueue.PRIORITY_STATUS)

    first = q.get()
    second = q.get()
    third = q.get()

    assert first.topic == "blocks"  # PRIORITY_BLOCK = 1 (highest)
    assert second.topic == "transactions"  # PRIORITY_TRANSACTION = 3
    assert third.topic == "status"  # PRIORITY_STATUS = 4


def test_fifo_within_same_priority():
    """Same priority, FIFO by sequence."""
    q = PriorityMessageQueue()
    q.put("blocks", {"block": 1}, priority=PriorityMessageQueue.PRIORITY_BLOCK)
    q.put("blocks", {"block": 2}, priority=PriorityMessageQueue.PRIORITY_BLOCK)
    q.put("blocks", {"block": 3}, priority=PriorityMessageQueue.PRIORITY_BLOCK)

    first = q.get()
    second = q.get()
    third = q.get()

    assert first.message["block"] == 1
    assert second.message["block"] == 2
    assert third.message["block"] == 3


def test_get_batch():
    """Get multiple messages at once."""
    q = PriorityMessageQueue()
    for i in range(5):
        q.put("blocks", {"block": i}, priority=PriorityMessageQueue.PRIORITY_BLOCK)
    for i in range(3):
        q.put("transactions", {"tx": i}, priority=PriorityMessageQueue.PRIORITY_TRANSACTION)

    batch = q.get_batch(max_count=4)
    assert len(batch) == 4
    # Blocks should come first (higher priority)
    assert all(m.topic == "blocks" for m in batch)
    # Remaining: 1 block + 3 transactions
    assert q.qsize() == 4


def test_empty_queue_get_returns_none():
    """get on empty queue returns None."""
    q = PriorityMessageQueue()
    assert q.get() is None
    assert q.get(timeout=0.1) is None


def test_qsize():
    """Verify size tracking."""
    q = PriorityMessageQueue()
    assert q.qsize() == 0
    q.put("topic", "msg1")
    q.put("topic", "msg2")
    assert q.qsize() == 2
    q.get()
    assert q.qsize() == 1


def test_clear():
    """Clear all messages."""
    q = PriorityMessageQueue()
    q.put("topic", "msg1")
    q.put("topic", "msg2")
    assert q.qsize() == 2
    q.clear()
    assert q.qsize() == 0
    assert q.get() is None


def test_max_size():
    """Queue rejects messages when full."""
    q = PriorityMessageQueue(max_size=3)
    assert q.put("topic", "msg1") is True
    assert q.put("topic", "msg2") is True
    assert q.put("topic", "msg3") is True
    assert q.put("topic", "msg4") is False  # rejected
    assert q.qsize() == 3


def test_thread_safety():
    """Concurrent put/get doesn't crash."""
    q = PriorityMessageQueue(max_size=10000)
    errors = []

    def producer():
        try:
            for i in range(500):
                q.put("topic", f"msg-{i}", priority=PriorityMessageQueue.PRIORITY_TRANSACTION)
        except Exception as e:
            errors.append(e)

    def consumer():
        try:
            for _ in range(500):
                q.get(timeout=1.0)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=producer) for _ in range(2)]
    threads.append(threading.Thread(target=consumer))
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)
    assert not errors


def test_get_blocking_with_timeout():
    """get with timeout waits for a message."""
    q = PriorityMessageQueue()

    def delayed_put():
        time.sleep(0.1)
        q.put("topic", "msg")

    t = threading.Thread(target=delayed_put)
    t.start()
    msg = q.get(timeout=1.0)
    t.join()
    assert msg is not None
    assert msg.message == "msg"
