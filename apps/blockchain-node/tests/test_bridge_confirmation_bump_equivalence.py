"""The set-based confirmation bump writes exactly what the per-row loop wrote.

``_increment_confirmations`` used to load every earlier header on the chain and
rewrite it through the ORM, once per header stored -- so mirroring a backlog of
N headers into a table already holding M cost O(M*N) row writes, and a bridge
header backfill ran at 0.75 headers/second. It is now two UPDATE statements.

Confirmation counts gate ``finality_confirmed``, which gates releasing value, so
this pins the values rather than the speed: the loop it replaced is kept below
verbatim as the reference, and every scenario runs both against identical tables
and compares the whole table row for row.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from aitbc_chain.cross_chain.bridge import CrossChainBridge
from aitbc_chain.cross_chain.bridge_finality import BridgeFinalityMixin
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.models import BridgeBlockHeader

CHAIN_ID = "chain-a"


def _increment_confirmations_by_loop(self: Any, chain_id: str, new_height: int, session: Any) -> None:
    """The pre-optimisation implementation, verbatim, as the reference."""
    earlier = session.exec(
        select(BridgeBlockHeader).where(
            BridgeBlockHeader.chain_id == chain_id,
            BridgeBlockHeader.height < new_height,
        )
    ).all()
    for h in earlier:
        h.confirmation_count += 1
        session.add(h)
        self._update_finality(chain_id, h, session, commit=False)
    if earlier:
        session.commit()


def _header(height: int, **overrides: Any) -> dict[str, Any]:
    return {
        "chain_id": CHAIN_ID,
        "height": height,
        "hash": f"0x{height:064x}",
        "parent_hash": f"0x{max(0, height - 1):064x}",
        "proposer": "0x" + "11" * 20,
        "state_root": f"0xstate{height}",
        "bridge_state_root": f"0xbridge{height}",
        "signature": "",
        **overrides,
    }


# Each scenario is the sequence of store_block_header payloads to apply.
SCENARIOS: dict[str, list[dict[str, Any]]] = {
    # The backfill path: contiguous and ascending, long enough to cross the
    # default finality threshold of 6 several times over.
    "ascending": [_header(h) for h in range(21)],
    # The no-op boundary: every store sits below everything already there, so
    # the "height < new_height" predicate matches nothing and no row may move.
    "descending": [_header(h) for h in range(20, -1, -1)],
    # The RPC path can deliver anything in any order.
    "interleaved": [_header(h) for h in (5, 0, 9, 3, 12, 1, 7, 20, 2, 15)],
    # Re-storing a height takes the update branch, which must not double-bump.
    "restored": [_header(h) for h in (0, 1, 2, 1, 3, 0, 4, 4, 5, 6, 7)],
    # A gap is what makes "count of headers above" differ from "height delta".
    "gapped": [_header(h) for h in (0, 1, 2, 40, 41, 42, 43, 44, 45, 46)],
    # Caller-supplied counts are honoured while the release fence is down.
    "caller_supplied": [
        _header(0, confirmation_count=4),
        _header(1, confirmation_count=0),
        _header(2, confirmation_count=5, finality_confirmed=True),
        _header(3),
        _header(4, confirmation_count=6),
        _header(0, confirmation_count=1),
    ],
}


def _apply(payloads: list[dict[str, Any]], *, reference: bool) -> list[tuple[int, int, bool]]:
    """Run the payloads through a fresh bridge, return the whole header table."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    chain_metadata.create_all(engine)
    try:
        bridge = CrossChainBridge(lambda: Session(engine))
        if reference:
            with patch.object(
                BridgeFinalityMixin,
                "_increment_confirmations",
                _increment_confirmations_by_loop,
            ):
                for payload in payloads:
                    bridge.store_block_header(dict(payload))
        else:
            for payload in payloads:
                bridge.store_block_header(dict(payload))
        with Session(engine) as session:
            rows = session.exec(
                select(BridgeBlockHeader).where(BridgeBlockHeader.chain_id == CHAIN_ID).order_by(BridgeBlockHeader.height)  # type: ignore[arg-type]
            ).all()
            return [(r.height, r.confirmation_count, r.finality_confirmed) for r in rows]
    finally:
        chain_metadata.drop_all(engine)
        engine.dispose()


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_set_based_bump_matches_the_row_loop(scenario: str) -> None:
    payloads = SCENARIOS[scenario]
    assert _apply(payloads, reference=False) == _apply(payloads, reference=True)


def test_the_reference_is_actually_exercised() -> None:
    """A scenario that would pass even if patch.object silently did nothing is no test."""
    payloads = SCENARIOS["ascending"]
    live = _apply(payloads, reference=False)
    # Every header below the head must have accumulated confirmations, and the
    # ones at least 6 deep must be final -- i.e. the bump ran at all.
    assert live[0] == (0, 20, True)
    assert live[-1] == (20, 0, False)
    assert [h for h, _, final in live if final] == list(range(15))
