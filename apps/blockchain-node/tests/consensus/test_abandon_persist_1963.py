"""#1963 — abandoned-hash indexes must survive a restart.

``release_abandoned``→``retract`` erases the vote record, so before this
fix a restart inside the abandon→retry gap forgot ``_abandoned_rounds`` /
``_abandoned_heights`` and the same-round rival guard silently lapsed —
the validator could sign a ROUND_BOUND_SAME_ROUND pair (slashable, no UC
excuse). Pins: round=None statements (the only shape the producer emits
today) still populate the round index via local evidence, and a fresh
service instance refuses the same-round rival after "restart".
"""

from __future__ import annotations

import pytest
from aitbc_chain.config import settings
from aitbc_chain.consensus import abandon

from . import test_round_lock as rl
from .test_abandon_release_evidence_1724 import _env  # noqa: F401  (autouse fixture)

_round_lock_on = rl._round_lock_on  # reuse the round-lock fixture (autouse)
CHAIN = "test-chain"
A = "0x" + "aa" * 32
B = "0x" + "bb" * 32


async def _release_with_round_none(monkeypatch, tmp_path):
    """Sign A at round 0, then apply the PRODUCTION abandon shape (round=None)."""
    monkeypatch.setattr(settings, "vote_journal_justification_enabled", False)
    our, our_key, prop, prop_key = rl._keys()
    svc, broker = rl._service(monkeypatch, our, our_key, prop, tmp_path)
    await svc._handle_request(rl._header(100, A, prop, 0))
    assert len(broker.published) == 1
    stmt = abandon.build_abandon(CHAIN, 100, A, None, prop, prop_key)
    assert stmt["round"] is None
    assert svc.handle_abandon(stmt) >= 1
    return svc, broker, our, our_key, prop, prop_key


@pytest.mark.asyncio
async def test_round_none_statement_derives_round_from_local_evidence(monkeypatch, tmp_path):
    """The journal vote's round populates _abandoned_rounds even when the
    statement carries none — the guard no longer depends on #1962 alone."""
    svc, _broker, *_ = await _release_with_round_none(monkeypatch, tmp_path)
    assert A in svc._abandoned_rounds.get((100, 0), set())
    assert A in svc._abandoned_heights.get(100, set())


@pytest.mark.asyncio
async def test_same_round_rival_refused_after_round_none_release(monkeypatch, tmp_path):
    """End-to-end: production-shaped abandon still refuses the same-round rival."""
    _svc, broker, our, our_key, prop, _prop_key = await _release_with_round_none(monkeypatch, tmp_path)
    await _svc._handle_request(rl._header(100, B, prop, 0))
    assert [m["hash"] for _, m in broker.published] == [A]


@pytest.mark.asyncio
async def test_abandoned_indexes_survive_restart(monkeypatch, tmp_path):
    """A fresh service on the same DATA_DIR refuses the same-round rival —
    the persisted index replaces the lost memory."""
    _svc1, _b1, our, our_key, prop, _pk = await _release_with_round_none(monkeypatch, tmp_path)

    # "Restart": new service instance, same chain/data dir, empty memory.
    svc2, broker2 = rl._service(monkeypatch, our, our_key, prop, tmp_path)
    assert svc2._abandoned_rounds == {}
    assert svc2._abandoned_heights == {}

    await svc2._handle_request(rl._header(100, B, prop, 0))
    assert broker2.published == []

    # Later-round rival stays allowed (cross-round is context-only).
    await svc2._handle_request(rl._header(100, B, prop, 1))
    assert [m["hash"] for _, m in broker2.published] == [B]
    assert broker2.published[0][1]["round"] == 1


@pytest.mark.asyncio
async def test_persisted_file_carries_rounds(monkeypatch, tmp_path):
    svc, *_ = await _release_with_round_none(monkeypatch, tmp_path)
    path = svc._abandoned_path
    assert path.exists()
    import json

    data = json.loads(path.read_text())
    assert data["chain_id"] == CHAIN
    rec = next(r for r in data["records"] if r["h"] == 100 and r["hash"] == A)
    assert rec["rounds"] == [0]
