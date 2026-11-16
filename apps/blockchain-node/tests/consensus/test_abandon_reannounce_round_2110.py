"""#2110: every abandon statement carries the round it was owed for.

#1962 made the first publish sign the collected round; #1985 added the durable
re-announce and orphan recovery. These pins close the loop: the AbandonLedger
entry's round is what the re-announce signs, also after a proposer restart, and
an orphaned journal proposal is abandoned with its journaled round — so a
re-sent statement is never the legacy round-less shape.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from aitbc_chain.consensus.poa import PoAProposer
from aitbc_chain.consensus.vote_journal import KIND_PROPOSE, get_vote_journal

from .test_journal_liveness_1985 import CHAIN, H, HASH_A, _env, _proposer_stub, _restarted  # noqa: F401
from .test_vote_journal_1268 import _Clock


@pytest.mark.asyncio
@pytest.mark.parametrize("round_number", [0, 3])
async def test_first_send_and_reannounce_carry_the_owed_round(monkeypatch, round_number):
    clock = _Clock()
    stub, broker, me = _proposer_stub(monkeypatch, clock)
    await PoAProposer._publish_abandon(stub, SimpleNamespace(proposer=me, height=H), HASH_A, round_number)
    assert [m["round"] for m in broker.published] == [round_number]
    clock.advance(31)
    await stub._abandon_liveness_tick(H - 1)
    assert [m["round"] for m in broker.published] == [round_number, round_number]


@pytest.mark.asyncio
async def test_reannounce_after_a_restart_still_carries_the_round(monkeypatch):
    """The ledger entry is on disk; the restarted process re-signs its stored round."""
    clock = _Clock()
    stub, broker, me = _proposer_stub(monkeypatch, clock)
    await PoAProposer._publish_abandon(stub, SimpleNamespace(proposer=me, height=H), HASH_A, 5)
    broker.published.clear()
    restarted = _restarted(stub)
    clock.advance(31)
    await restarted._abandon_liveness_tick(H - 1)
    assert [m["round"] for m in broker.published] == [5]


@pytest.mark.asyncio
async def test_round_none_entry_stays_round_less(monkeypatch):
    """Legacy callers (no round) keep the legacy statement shape on re-announce."""
    clock = _Clock()
    stub, broker, me = _proposer_stub(monkeypatch, clock)
    await PoAProposer._publish_abandon(stub, SimpleNamespace(proposer=me, height=H), HASH_A)
    clock.advance(31)
    await stub._abandon_liveness_tick(H - 1)
    assert [m["round"] for m in broker.published] == [None, None]


@pytest.mark.asyncio
async def test_orphan_recovery_abandons_with_the_journaled_round(monkeypatch):
    clock = _Clock()
    stub, broker, me = _proposer_stub(monkeypatch, clock)
    get_vote_journal(CHAIN).record(H, me, HASH_A, KIND_PROPOSE, 4, me, now=clock.now)
    await stub._abandon_liveness_tick(H - 1)
    assert [(m["hash"], m["round"]) for m in broker.published] == [(HASH_A, 4)]
    clock.advance(31)
    await stub._abandon_liveness_tick(H - 1)  # and the re-announce keeps it
    assert [m["round"] for m in broker.published] == [4, 4]
