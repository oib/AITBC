"""#1962 — the producer signs the proposal round into the abandon statement.

Before: ``_publish_abandon`` hard-coded ``round=None`` although its only
caller, ``_collect_and_gate_attestations``, holds the round, so the
``stmt["round"]`` branch of ``handle_abandon`` never ran in production.
Pins: the production call path (quorum miss -> gossip statement) carries the
round; the consumer populates the same-round guard from a signed round alone
(no local derivation needed) and keeps the round-less legacy shape working;
a round that contradicts the voter's own evidence is counted and both rounds
stay refused (fail-closed direction). Dormant: flag off publishes nothing.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from aitbc_chain.config import settings
from aitbc_chain.consensus import abandon
from aitbc_chain.consensus.poa import PoAProposer
from aitbc_chain.metrics import metrics_registry

from . import test_round_lock as rl
from .test_abandon_release_evidence_1724 import _env  # noqa: F401  (autouse fixture)

_round_lock_on = rl._round_lock_on  # reuse the round-lock fixture (autouse)
CHAIN = "test-chain"
A = "0x" + "aa" * 32
B = "0x" + "bb" * 32


def _counter(name: str) -> float:
    return metrics_registry._counters.get(name, 0.0)


class _Broker:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict]] = []

    async def publish(self, topic, msg):
        self.published.append((topic, msg))


def _quorum_miss_proposer(prop: str, prop_key: str, round_number_seen: list):
    """A stub proposer that fails the attestation minimum through the REAL
    ``_collect_and_gate_attestations`` / ``_publish_abandon`` code."""

    async def _collect(block, transactions=None, round_number=None, **_kw):
        round_number_seen.append(round_number)
        return []

    ns = SimpleNamespace(
        _config=SimpleNamespace(chain_id=CHAIN),
        _validator_keys={prop: prop_key},
        _logger=SimpleNamespace(warning=lambda *a, **k: None, info=lambda *a, **k: None),
        _pbft_consensus=None,
        _multi_validator=SimpleNamespace(get_consensus_participants=lambda: [prop, "x", "y"]),
        _collect_attestations=_collect,
        _effective_min_attestations=lambda block, participants, configured: 2,
        _certificate_commit_count=lambda cert, block_hash, participants: 0,
    )
    ns._publish_abandon = lambda block, block_hash, round_number=None: PoAProposer._publish_abandon(
        ns, block, block_hash, round_number
    )
    return ns


@pytest.mark.asyncio
@pytest.mark.parametrize("round_number", [0, 1, 7])
async def test_production_path_signs_the_collected_round(monkeypatch, round_number):
    from aitbc_chain.consensus import poa as poa_module

    _our, _our_key, prop, prop_key = rl._keys()
    broker = _Broker()
    monkeypatch.setattr(poa_module, "gossip_broker", broker)
    seen: list = []
    stub = _quorum_miss_proposer(prop, prop_key, seen)
    block = SimpleNamespace(proposer=prop, height=100, hash=A)
    ok = await PoAProposer._collect_and_gate_attestations.__get__(stub)(block, A, {}, None, round_number)
    assert ok is False
    assert seen == [round_number]
    assert len(broker.published) == 1
    stmt = abandon.verify_abandon(CHAIN, broker.published[0][1])
    assert stmt is not None
    assert stmt["round"] == round_number  # was always None before #1962


@pytest.mark.asyncio
async def test_round_none_call_keeps_the_legacy_shape(monkeypatch):
    from aitbc_chain.consensus import poa as poa_module

    _our, _our_key, prop, prop_key = rl._keys()
    broker = _Broker()
    monkeypatch.setattr(poa_module, "gossip_broker", broker)
    stub = _quorum_miss_proposer(prop, prop_key, [])
    await PoAProposer._publish_abandon(stub, SimpleNamespace(proposer=prop, height=100), A)
    assert broker.published[0][1]["round"] is None


@pytest.mark.asyncio
async def test_flag_off_publishes_nothing(monkeypatch):
    from aitbc_chain.consensus import poa as poa_module

    monkeypatch.setattr(settings, "vote_journal_abandon_enabled", False)
    _our, _our_key, prop, prop_key = rl._keys()
    broker = _Broker()
    monkeypatch.setattr(poa_module, "gossip_broker", broker)
    stub = _quorum_miss_proposer(prop, prop_key, [])
    await PoAProposer._publish_abandon(stub, SimpleNamespace(proposer=prop, height=100), A, 3)
    assert broker.published == []


@pytest.mark.asyncio
async def test_signed_round_alone_populates_the_same_round_guard(monkeypatch, tmp_path):
    """End to end with a PRODUCTION-signed statement (round=0): the voter
    refuses the same-round rival, and the round came from the statement."""
    monkeypatch.setattr(settings, "vote_journal_justification_enabled", False)
    our, our_key, prop, prop_key = rl._keys()
    svc, broker = rl._service(monkeypatch, our, our_key, prop, tmp_path)
    await svc._handle_request(rl._header(100, A, prop, 0))
    assert len(broker.published) == 1
    stmt = abandon.build_abandon(CHAIN, 100, A, 0, prop, prop_key)
    assert svc.handle_abandon(stmt) >= 1
    assert A in svc._abandoned_rounds.get((100, 0), set())
    assert _counter("vote_journal_abandon_round_mismatch_total") == 0
    await svc._handle_request(rl._header(100, B, prop, 0))
    assert [m["hash"] for _, m in broker.published] == [A]  # same-round rival refused
    await svc._handle_request(rl._header(100, B, prop, 1))
    assert [m["hash"] for _, m in broker.published] == [A, B]  # cross-round stays allowed


@pytest.mark.asyncio
async def test_round_none_statement_still_works_and_counts_no_mismatch(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "vote_journal_justification_enabled", False)
    our, our_key, prop, prop_key = rl._keys()
    svc, broker = rl._service(monkeypatch, our, our_key, prop, tmp_path)
    await svc._handle_request(rl._header(100, A, prop, 0))
    stmt = abandon.build_abandon(CHAIN, 100, A, None, prop, prop_key)
    assert svc.handle_abandon(stmt) >= 1
    assert A in svc._abandoned_rounds.get((100, 0), set())
    assert _counter("vote_journal_abandon_round_mismatch_total") == 0


@pytest.mark.asyncio
async def test_contradicting_round_is_counted_and_both_rounds_stay_refused(monkeypatch, tmp_path):
    """The voter voted in round 0; the statement claims round 3. Fail-closed
    direction: both (100,0) and (100,3) refuse a different hash, and the
    mismatch counter makes the producer visible."""
    monkeypatch.setattr(settings, "vote_journal_justification_enabled", False)
    our, our_key, prop, prop_key = rl._keys()
    svc, broker = rl._service(monkeypatch, our, our_key, prop, tmp_path)
    await svc._handle_request(rl._header(100, A, prop, 0))
    stmt = abandon.build_abandon(CHAIN, 100, A, 3, prop, prop_key)
    assert svc.handle_abandon(stmt) >= 1
    assert _counter("vote_journal_abandon_round_mismatch_total") == 1
    assert A in svc._abandoned_rounds.get((100, 0), set())
    assert A in svc._abandoned_rounds.get((100, 3), set())
    await svc._handle_request(rl._header(100, B, prop, 0))
    await svc._handle_request(rl._header(100, B, prop, 3))
    assert [m["hash"] for _, m in broker.published] == [A]
