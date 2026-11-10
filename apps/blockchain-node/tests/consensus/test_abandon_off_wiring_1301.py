"""#1301 L2 abandon — flag-OFF wiring: zero behavior change, end to end.

``test_abandon_1301.py`` proves the helper-level gate (``abandon_enabled``)
and that ``_publish_abandon`` is silent OFF. This file pins the *wiring*
around them with the flag OFF in the combinations that matter in operation:

* the listener side — ``RemoteAttestationService.start()`` creates no abandon
  task and subscribes to no ``consensus.abandon.*`` topic, including with
  ``vote_journal_enabled`` ON (the UC driver combination) and with the abandon
  flag ON but the journal OFF (``abandon_enabled`` requires both);
* the proposer failed-quorum exit — publishes nothing and moves no abandon
  metric OFF;
* armed control — the same harness does subscribe/publish when both flags are
  ON, so the OFF assertions cannot pass vacuously.

Characterization: ``handle_abandon`` itself has no internal flag gate; OFF
safety rests on the listener never being started (asserted below), not on the
handler refusing statements.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from aitbc_chain.config import settings
from aitbc_chain.consensus import abandon, vote_fetch, vote_journal
from aitbc_chain.consensus import remote_attestation as ra_module
from aitbc_chain.consensus.poa import PoAProposer
from aitbc_chain.consensus.remote_attestation import RemoteAttestationService
from aitbc_chain.consensus.vote_journal import reset_vote_journals
from aitbc_chain.metrics import metrics_registry

from .test_abandon_1301 import CHAIN, H, HASH, OUR, OUR_KEY, PROP, PROP_KEY


class _Sub:
    """Empty async-iterable subscription; ``close`` is synchronous like the real one."""

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


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    metrics_registry.reset()
    reset_vote_journals()
    vote_fetch.reset_throttle()
    monkeypatch.setattr(vote_journal, "DATA_DIR", tmp_path)
    monkeypatch.setattr(ra_module, "DATA_DIR", tmp_path)
    monkeypatch.setattr(settings, "validator_set", json.dumps([{"address": OUR}, {"address": PROP}]))
    # Only the abandon listener is under test: keep the #1281 listeners out.
    monkeypatch.setattr(settings, "vote_journal_justification_enabled", False)
    yield
    reset_vote_journals()
    metrics_registry.reset()


async def _start_and_collect(monkeypatch) -> tuple[RemoteAttestationService, _RecordingBroker]:
    broker = _RecordingBroker()
    monkeypatch.setattr(ra_module, "gossip_broker", broker)
    svc = RemoteAttestationService(CHAIN, {OUR: OUR_KEY})
    await svc.start()
    await asyncio.sleep(0.05)  # let the listener tasks reach subscribe()
    return svc, broker


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("journal", "abandon_flag"),
    [(False, False), (True, False), (False, True)],
    ids=["both-off", "journal-on-abandon-off", "abandon-on-journal-off"],
)
async def test_off_listener_not_started_and_no_abandon_subscription(monkeypatch, journal, abandon_flag):
    monkeypatch.setattr(settings, "vote_journal_enabled", journal)
    monkeypatch.setattr(settings, "vote_journal_abandon_enabled", abandon_flag)
    assert abandon.abandon_enabled() is False
    svc, broker = await _start_and_collect(monkeypatch)
    try:
        assert svc._abandon_task is None
        assert abandon.abandon_topic(CHAIN) not in broker.subscribed
        assert not any(t.startswith("consensus.abandon.") for t in broker.subscribed)
    finally:
        await svc.stop()


@pytest.mark.asyncio
async def test_armed_control_subscribes_to_abandon_topic(monkeypatch):
    """Control: both flags ON on the same harness DO start the listener and
    subscribe — so the OFF legs above cannot be vacuous."""
    monkeypatch.setattr(settings, "vote_journal_enabled", True)
    monkeypatch.setattr(settings, "vote_journal_abandon_enabled", True)
    svc, broker = await _start_and_collect(monkeypatch)
    try:
        assert svc._abandon_task is not None
        assert abandon.abandon_topic(CHAIN) in broker.subscribed
    finally:
        await svc.stop()
    assert svc._abandon_task is None


def _proposer(broker):
    return SimpleNamespace(
        _config=SimpleNamespace(chain_id=CHAIN),
        _validator_keys={PROP: PROP_KEY},
        _logger=SimpleNamespace(warning=lambda *a, **k: None),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("journal", "abandon_flag"),
    [(False, False), (True, False), (False, True)],
    ids=["both-off", "journal-on-abandon-off", "abandon-on-journal-off"],
)
async def test_off_failed_quorum_exit_publishes_nothing(monkeypatch, journal, abandon_flag):
    from aitbc_chain.consensus import poa as poa_module

    monkeypatch.setattr(settings, "vote_journal_enabled", journal)
    monkeypatch.setattr(settings, "vote_journal_abandon_enabled", abandon_flag)
    broker = _RecordingBroker()
    monkeypatch.setattr(poa_module, "gossip_broker", broker)
    await PoAProposer._publish_abandon(_proposer(broker), SimpleNamespace(proposer=PROP, height=H), HASH)
    assert broker.published == []
    assert metrics_registry._counters.get("vote_journal_abandon_published_total", 0.0) == 0.0
    assert metrics_registry._counters.get("vote_journal_abandon_rejected_total", 0.0) == 0.0
    assert metrics_registry._counters.get("vote_journal_abandon_released_total", 0.0) == 0.0


@pytest.mark.asyncio
async def test_armed_control_failed_quorum_exit_publishes(monkeypatch):
    from aitbc_chain.consensus import poa as poa_module

    monkeypatch.setattr(settings, "vote_journal_enabled", True)
    monkeypatch.setattr(settings, "vote_journal_abandon_enabled", True)
    broker = _RecordingBroker()
    monkeypatch.setattr(poa_module, "gossip_broker", broker)
    await PoAProposer._publish_abandon(_proposer(broker), SimpleNamespace(proposer=PROP, height=H), HASH)
    assert [t for t, _ in broker.published] == [abandon.abandon_topic(CHAIN)]


def test_handle_abandon_has_no_internal_flag_gate(monkeypatch):
    """Characterization: OFF safety is the un-started listener, not the
    handler. A directly-delivered valid statement is applied even with the
    flag OFF (only reachable if something calls handle_abandon bypassing
    start())."""
    from aitbc_chain.consensus.vote_journal import KIND_ATTEST, get_vote_journal

    monkeypatch.setattr(settings, "vote_journal_enabled", True)
    monkeypatch.setattr(settings, "vote_journal_abandon_enabled", False)
    get_vote_journal(CHAIN).record(H, OUR, HASH, KIND_ATTEST, None, PROP)
    svc = RemoteAttestationService(CHAIN, {OUR: OUR_KEY})
    stmt = abandon.build_abandon(CHAIN, H, HASH, None, PROP, PROP_KEY)
    assert svc.handle_abandon(stmt) == 1
