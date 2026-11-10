"""#1311 equivocation replication — flag-OFF wiring: zero behavior change.

``test_equivocation_replication_1311.py`` proves ingest/emit mechanics with
the flag ON and one inert-emit check OFF. This file pins the OFF *wiring*
(same pattern as the abandon/reservation OFF suites):

* the listener side — ``RemoteAttestationService.start()`` creates no evidence
  task and subscribes to no ``consensus.equivocation.*`` topic;
* the emit side — a local same-round signed pair publishes nothing, stores
  nothing and moves no replication counter;
* armed control — the same harness subscribes/publishes with the flag ON, so
  the OFF assertions cannot pass vacuously.

``handle_evidence`` carries its own flag gate (defense in depth, like
``handle_abandon``): OFF it ingests nothing even if called directly.
"""

from __future__ import annotations

import asyncio

import pytest
from aitbc_chain.config import ChainSettings, settings
from aitbc_chain.consensus import evidence_replication as er
from aitbc_chain.consensus import remote_attestation as ra_module
from aitbc_chain.consensus.remote_attestation import RemoteAttestationService

from . import test_equivocation_replication_1311 as _base

# Re-exported autouse fixture + helpers (assignment, not import: avoids F811).
_env = _base._env
CHAIN, H, HA, HB = _base.CHAIN, _base.H, _base.HA, _base.HB
OUR_KEY = _base.OUR_KEY
_record, _counter = _base._record, _base._counter

REPLICATION_COUNTERS = (
    "equivocation_published_total",
    "equivocation_republish_suppressed_total",
    "equivocation_ingest_recorded_total",
)


class _Sub:
    def __aiter__(self):
        return self

    async def __anext__(self):
        await asyncio.sleep(3600)
        raise StopAsyncIteration

    def close(self) -> None:
        pass


class _RecordingBroker:
    def __init__(self) -> None:
        self.subscribed: list[str] = []
        self.published: list[tuple[str, object]] = []

    async def subscribe(self, topic: str, max_queue_size: int = 0):
        self.subscribed.append(topic)
        return _Sub()

    async def publish(self, topic: str, message: object) -> None:
        self.published.append((topic, message))


def _svc() -> RemoteAttestationService:
    return RemoteAttestationService(CHAIN, {_base.OUR: OUR_KEY})


async def _start(monkeypatch) -> tuple[RemoteAttestationService, _RecordingBroker]:
    monkeypatch.setattr(settings, "vote_journal_justification_enabled", False)
    broker = _RecordingBroker()
    monkeypatch.setattr(ra_module, "gossip_broker", broker)
    svc = _svc()
    await svc.start()
    await asyncio.sleep(0.05)  # let the listener tasks reach subscribe()
    return svc, broker


def test_shipped_default_is_off():
    assert ChainSettings.model_fields["equivocation_replication_enabled"].default is False


@pytest.mark.asyncio
async def test_off_listener_not_started_and_no_equivocation_subscription(monkeypatch):
    monkeypatch.setattr(settings, "equivocation_replication_enabled", False)
    assert not er.enabled()
    svc, broker = await _start(monkeypatch)
    try:
        assert svc._evidence_task is None
        assert er.equivocation_topic(CHAIN) not in broker.subscribed
        assert not any(t.startswith("consensus.equivocation.") for t in broker.subscribed)
    finally:
        await svc.stop()


@pytest.mark.asyncio
async def test_armed_control_subscribes_to_equivocation_topic(monkeypatch):
    monkeypatch.setattr(settings, "equivocation_replication_enabled", True)
    svc, broker = await _start(monkeypatch)
    try:
        assert svc._evidence_task is not None
        assert er.equivocation_topic(CHAIN) in broker.subscribed
    finally:
        await svc.stop()
    assert svc._evidence_task is None


@pytest.mark.asyncio
async def test_off_local_pair_emits_nothing(monkeypatch):
    monkeypatch.setattr(settings, "equivocation_replication_enabled", False)
    broker = _RecordingBroker()
    monkeypatch.setattr(ra_module, "gossip_broker", broker)
    svc = _svc()
    atts = _record()["attestations"]
    for _ in range(3):
        svc._emit_evidence(_base.VAL, H, 1, HA, HB, atts)
    await asyncio.sleep(0)
    assert broker.published == []
    assert len(er.get_store(CHAIN)) == 0
    assert all(_counter(name) == 0.0 for name in REPLICATION_COUNTERS)


@pytest.mark.asyncio
async def test_armed_control_local_pair_publishes(monkeypatch):
    monkeypatch.setattr(settings, "equivocation_replication_enabled", True)
    broker = _RecordingBroker()
    monkeypatch.setattr(ra_module, "gossip_broker", broker)
    svc = _svc()
    svc._emit_evidence(_base.VAL, H, 1, HA, HB, _record()["attestations"])
    await asyncio.sleep(0)
    assert [t for t, _ in broker.published] == [er.equivocation_topic(CHAIN)]
    assert _counter("equivocation_published_total") == 1.0


def test_handle_evidence_ignores_records_when_off(monkeypatch):
    """OFF: a directly-delivered valid record is dropped, stored and counted nowhere."""
    from aitbc_chain.consensus.slashing import SlashingManager

    monkeypatch.setattr(settings, "equivocation_replication_enabled", False)
    mgr = SlashingManager()
    svc = _svc()
    monkeypatch.setattr(svc, "_equivocation_recorder", lambda: mgr)
    out = svc.handle_evidence(_record())
    assert out.status == "disabled" and not out.slashable and out.record is None
    assert len(er.get_store(CHAIN)) == 0
    assert mgr.get_slashing_history(_base.VAL) == []
    assert all(_counter(name) == 0.0 for name in REPLICATION_COUNTERS)


def test_handle_evidence_ingests_when_armed(monkeypatch):
    """Armed control: the same record is stored and slashable, so the OFF test is not vacuous."""
    from aitbc_chain.consensus.slashing import SlashingManager

    monkeypatch.setattr(settings, "equivocation_replication_enabled", True)
    mgr = SlashingManager()
    svc = _svc()
    monkeypatch.setattr(svc, "_equivocation_recorder", lambda: mgr)
    out = svc.handle_evidence(_record())
    assert out.status == "stored" and out.slashable
