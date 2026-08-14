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
