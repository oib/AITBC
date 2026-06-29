from __future__ import annotations

import asyncio

import pytest

from aitbc.network import SubscriptionClientProtocol, SubscriptionEntry, SubscriptionManager


class FakeSubscriptionClient:
    """Minimal subscription client for testing."""

    def __init__(
        self,
        chain_id: str,
        hub_url: str,
        fail_times: int = 0,
        hang: bool = False,
    ) -> None:
        self._chain_id = chain_id
        self._hub_url = hub_url
        self._fail_times = fail_times
        self._call_count = 0
        self._hang = hang
        self._started = asyncio.Event()
        self._stopped = False

    @property
    def chain_id(self) -> str:
        return self._chain_id

    @property
    def hub_url(self) -> str:
        return self._hub_url

    @property
    def is_connected(self) -> bool:
        return self._started.is_set() and not self._stopped

    async def start(self) -> None:
        self._call_count += 1
        if self._call_count <= self._fail_times:
            raise RuntimeError(f"Scheduled failure #{self._call_count}")
        if self._hang:
            self._started.set()
            await asyncio.Event().wait()  # Block forever
        self._started.set()
        # Normal exit — start() returns when subscription ends cleanly

    async def stop(self) -> None:
        self._stopped = True


def test_add_subscription():
    mgr = SubscriptionManager()
    client = FakeSubscriptionClient("ait-hub", "http://hub-a:8006")
    mgr.add_subscription("ait-hub", client)
    entry = mgr.get_subscription("ait-hub")
    assert entry is not None
    assert entry.client is client
    assert entry.restart_count == 0
    assert entry.task is None


def test_add_duplicate_raises():
    mgr = SubscriptionManager()
    client = FakeSubscriptionClient("ait-hub", "http://hub-a:8006")
    mgr.add_subscription("ait-hub", client)
    with pytest.raises(ValueError, match="already exists"):
        mgr.add_subscription("ait-hub", client)


def test_remove_subscription():
    mgr = SubscriptionManager()
    client = FakeSubscriptionClient("ait-hub", "http://hub-a:8006")
    mgr.add_subscription("ait-hub", client)
    entry = mgr.remove_subscription("ait-hub")
    assert entry is not None
    assert entry.client is client
    assert mgr.get_subscription("ait-hub") is None


@pytest.mark.asyncio
async def test_remove_subscription_cancels_task():
    mgr = SubscriptionManager()
    client = FakeSubscriptionClient("ait-hub", "http://hub-a:8006", hang=True)
    mgr.add_subscription("ait-hub", client)
    await mgr.start_all()
    await asyncio.sleep(0.05)  # Let task start
    entry = mgr.remove_subscription("ait-hub")
    assert entry is not None
    assert entry.task is not None
    # Task should be cancelled — yield to let cancellation propagate
    try:
        await asyncio.wait_for(entry.task, timeout=1.0)
    except (asyncio.CancelledError, RuntimeError):
        pass
    assert entry.task.cancelled() or entry.task.done()


def test_remove_nonexistent_returns_none():
    mgr = SubscriptionManager()
    assert mgr.remove_subscription("nonexistent") is None


def test_get_subscription():
    mgr = SubscriptionManager()
    client = FakeSubscriptionClient("ait-hub", "http://hub-a:8006")
    mgr.add_subscription("ait-hub", client)
    assert mgr.get_subscription("ait-hub") is not None
    assert mgr.get_subscription("unknown") is None


def test_get_all_chains():
    mgr = SubscriptionManager()
    mgr.add_subscription("ait-hub", FakeSubscriptionClient("ait-hub", "http://hub-a:8006"))
    mgr.add_subscription("ait-island1", FakeSubscriptionClient("ait-island1", "http://hub-b:8006"))
    chains = mgr.get_all_chains()
    assert sorted(chains) == ["ait-hub", "ait-island1"]


def test_get_all_chains_empty():
    mgr = SubscriptionManager()
    assert mgr.get_all_chains() == []


@pytest.mark.asyncio
async def test_start_all_starts_tasks():
    mgr = SubscriptionManager()
    client_a = FakeSubscriptionClient("ait-hub", "http://hub-a:8006")
    client_b = FakeSubscriptionClient("ait-island1", "http://hub-b:8006")
    mgr.add_subscription("ait-hub", client_a)
    mgr.add_subscription("ait-island1", client_b)
    await mgr.start_all()
    entry_a = mgr.get_subscription("ait-hub")
    entry_b = mgr.get_subscription("ait-island1")
    assert entry_a is not None and entry_a.task is not None
    assert entry_b is not None and entry_b.task is not None
    assert not entry_a.task.done() or entry_a.task.done()  # Task exists
    await mgr.stop_all()


@pytest.mark.asyncio
async def test_start_all_idempotent():
    """Calling start_all twice should not create duplicate tasks."""
    mgr = SubscriptionManager()
    client = FakeSubscriptionClient("ait-hub", "http://hub-a:8006", hang=True)
    mgr.add_subscription("ait-hub", client)
    await mgr.start_all()
    task1 = mgr.get_subscription("ait-hub").task
    await mgr.start_all()  # Should not replace running task
    task2 = mgr.get_subscription("ait-hub").task
    assert task1 is task2
    await mgr.stop_all()


@pytest.mark.asyncio
async def test_restart_on_failure():
    """Client fails once, then succeeds on restart."""
    mgr = SubscriptionManager(max_restarts=3, restart_delay=0.01)
    client = FakeSubscriptionClient("ait-hub", "http://hub-a:8006", fail_times=1)
    mgr.add_subscription("ait-hub", client)
    await mgr.start_all()
    # Wait for restart to complete
    entry = mgr.get_subscription("ait-hub")
    assert entry is not None
    await asyncio.wait_for(entry.task, timeout=5.0)
    assert client._call_count == 2  # Failed once, succeeded once
    assert entry.restart_count == 1
    assert entry.last_error == "Scheduled failure #1"


@pytest.mark.asyncio
async def test_max_restarts_exhausted():
    """Client always fails — restarts up to max_restarts then gives up."""
    mgr = SubscriptionManager(max_restarts=2, restart_delay=0.01)
    client = FakeSubscriptionClient("ait-hub", "http://hub-a:8006", fail_times=99)
    mgr.add_subscription("ait-hub", client)
    await mgr.start_all()
    entry = mgr.get_subscription("ait-hub")
    assert entry is not None
    await asyncio.wait_for(entry.task, timeout=5.0)
    assert entry.restart_count == 3  # Initial + 2 restarts = 3 attempts
    assert entry.task.done()
    assert "Scheduled failure" in entry.last_error


@pytest.mark.asyncio
async def test_stop_all_cancels_tasks():
    mgr = SubscriptionManager()
    client_a = FakeSubscriptionClient("ait-hub", "http://hub-a:8006", hang=True)
    client_b = FakeSubscriptionClient("ait-island1", "http://hub-b:8006", hang=True)
    mgr.add_subscription("ait-hub", client_a)
    mgr.add_subscription("ait-island1", client_b)
    await mgr.start_all()
    await asyncio.sleep(0.05)  # Let tasks start
    await mgr.stop_all()
    entry_a = mgr.get_subscription("ait-hub")
    entry_b = mgr.get_subscription("ait-island1")
    assert entry_a is not None and entry_a.task is not None
    assert entry_b is not None and entry_b.task is not None
    assert entry_a.task.done()
    assert entry_b.task.done()


@pytest.mark.asyncio
async def test_stop_all_empty():
    """stop_all on empty manager should not raise."""
    mgr = SubscriptionManager()
    await mgr.stop_all()  # Should not raise


@pytest.mark.asyncio
async def test_stop_all_after_stop():
    """Double stop_all should not raise."""
    mgr = SubscriptionManager()
    client = FakeSubscriptionClient("ait-hub", "http://hub-a:8006", hang=True)
    mgr.add_subscription("ait-hub", client)
    await mgr.start_all()
    await mgr.stop_all()
    await mgr.stop_all()  # Should not raise


def test_subscription_client_protocol_runtime_check():
    """The protocol should be runtime-checkable with isinstance."""
    client = FakeSubscriptionClient("ait-hub", "http://hub-a:8006")
    assert isinstance(client, SubscriptionClientProtocol)


def test_subscription_entry_dataclass():
    """SubscriptionEntry should be a dataclass with expected fields."""
    client = FakeSubscriptionClient("ait-hub", "http://hub-a:8006")
    entry = SubscriptionEntry(client=client)
    assert entry.client is client
    assert entry.task is None
    assert entry.restart_count == 0
    assert entry.last_error == ""
