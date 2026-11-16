"""#1998 H4 — a ``seen=0`` collect logs why nothing arrived (observational only).

The first collect of the 15 Nov bc-2 halt ended ``counted=0 seen=0`` with a live
SUBSCRIBE and responses relayed; the journals could not say whether they reached
the node. A 0/0 collect now logs the transient subscription's counters next to the
persistent observer's per-height response count.
"""

from __future__ import annotations

import logging

import pytest
from aitbc_chain.consensus import attest_response_diag
from aitbc_chain.consensus import remote_attestation as ra_module
from aitbc_chain.metrics import metrics_registry

from .test_attestation_arrival_log import CHAIN, ATTESTER_A, _attest, _block, _collect, _lines, _unsigned_requests_allowed  # noqa: F401

DIAG = "Attestation collect 0/0 diagnostic"


@pytest.fixture(autouse=True)
def _reset():
    attest_response_diag.reset()
    metrics_registry.reset()
    yield
    attest_response_diag.reset()


class TestObserverCounter:
    def test_counts_per_height_and_is_bounded(self):
        for _ in range(3):
            attest_response_diag.note_observer_response(7)
        assert attest_response_diag.observer_count(7) == 3
        assert attest_response_diag.observer_count(8) == 0
        for h in range(1000, 1000 + 300):
            attest_response_diag.note_observer_response(h)
        assert attest_response_diag.observer_count(7) == 0  # aged out
        assert attest_response_diag.observer_count(1299) == 1


class TestObserverWiring:
    @pytest.mark.asyncio
    async def test_observer_loop_counts_each_well_formed_response(self, monkeypatch):
        from aitbc_chain.consensus import unavail
        from aitbc_chain.consensus.remote_attestation import RemoteAttestationService

        class _Sub:
            def __init__(self, items):
                self._items = items

            def __aiter__(self):
                return self._gen()

            async def _gen(self):
                for item in self._items:
                    yield item

            def close(self):
                pass

        good = {"chain_id": CHAIN, "height": 100, "hash": "0xaa", "validator": ATTESTER_A[0]}
        junk = {"chain_id": "other-chain", "height": 100, "hash": "0xaa", "validator": ATTESTER_A[0]}

        async def _subscribe(topic, max_queue_size=0):
            return _Sub([good, junk, good, "not-a-dict"])

        await unavail.reset_observation_indices()
        monkeypatch.setattr(ra_module, "gossip_broker", type("B", (), {"subscribe": staticmethod(_subscribe)})())
        await RemoteAttestationService(CHAIN, {})._listen_responses_for_index()
        assert attest_response_diag.observer_count(100) == 2  # chain-filtered, shape-filtered
        await unavail.reset_observation_indices()


class TestZeroSeenLine:
    @pytest.mark.asyncio
    async def test_zero_seen_collect_logs_subscription_and_observer_state(self, monkeypatch, caplog):
        caplog.set_level(logging.INFO, logger=ra_module.logger.name)
        block = _block(height=4242)
        attest_response_diag.note_observer_response(4242)
        attest_response_diag.note_observer_response(4242)

        got = await _collect(monkeypatch, [], block, timeout=0.2)

        assert got == []
        lines = _lines(caplog, DIAG)
        assert len(lines) == 1
        assert "height=4242" in lines[0] and "observer_responses=2" in lines[0]
        assert "sub_stats=" in lines[0]
        assert metrics_registry._counters["attest_collect_zero_seen_total"] == 1

    @pytest.mark.asyncio
    async def test_collect_that_saw_a_response_logs_no_diagnostic(self, monkeypatch, caplog):
        caplog.set_level(logging.INFO, logger=ra_module.logger.name)
        block = _block()
        first = await _attest(monkeypatch, ATTESTER_A, block)

        await _collect(monkeypatch, [(0.0, first)], block, min_count=1)

        assert _lines(caplog, DIAG) == []
        assert "attest_collect_zero_seen_total" not in metrics_registry._counters


class TestBroadcastSubscriptionStats:
    @pytest.mark.asyncio
    async def test_stats_track_frames_items_and_end(self, monkeypatch):
        import asyncio

        from aitbc_chain.gossip._internal import _encode_message
        from aitbc_chain.gossip.backends import broadcast as bmod

        class _PubSub:
            def __init__(self):
                self.sent = [{"type": "message", "data": _encode_message({"a": 1})}]

            async def subscribe(self, topic):
                return None

            async def get_message(self, ignore_subscribe_messages=True, timeout=0.5):
                if self.sent:
                    return self.sent.pop(0)
                await asyncio.sleep(0.01)
                return None

            async def aclose(self):
                return None

        class _Redis:
            def pubsub(self):
                return _PubSub()

            async def aclose(self):
                return None

        import redis.asyncio as aioredis

        monkeypatch.setattr(aioredis.Redis, "from_url", staticmethod(lambda *a, **k: _Redis()))
        backend = bmod.BroadcastGossipBackend("redis://127.0.0.1:6379/0")
        await backend.start()
        sub = await backend.subscribe("t")
        assert await asyncio.wait_for(sub.get(), 1) == {"a": 1}
        assert sub.stats["ready"] is True and sub.stats["frames"] == 1 and sub.stats["items"] == 1
        sub.close()
        await asyncio.sleep(0.05)
        assert sub.stats["ended"] is True
