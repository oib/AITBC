"""B4: HTLC contract integration tests (v0.9.0).

The Python-native HTLCContract mirrors CrossChainAtomicSwap.sol. Its three
mutators — initiate_swap, complete_swap, refund_swap — are retired and raise
``RetiredProtocolTransfer`` unconditionally (pinned in
``test_retired_protocol_transfers.py``); what remains live is the read path,
``get_swap``, exercised here.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from types import SimpleNamespace

# Ensure blockchain-node source is importable
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from aitbc_chain.base_models import (  # noqa: E402
    Account,
    CrossChainEscrowRecord,
    EscrowProofRecord,
    HTLCSwapState,
    Transaction,
)
from aitbc_chain.contracts.htlc_contract import HTLCContract, SwapStatus  # noqa: E402


# ---------------------------------------------------------------------------
# Chain heads and timelocks
# ---------------------------------------------------------------------------
#
# A timelock is an absolute block height on a specific chain, so it only means
# anything relative to that chain's current head. These tests used to write
# ``int(time.time() // 5) + 720`` -- the Unix epoch over the block time, roughly
# 357 million -- which is the same unit confusion that V23-29..31 were about.
# They passed only because 357 million happens to clear a head of 10,000 by a
# wide margin, so "far future" was true by accident rather than by construction.

CHAIN_HEADS: dict[str, int] = {"ait-hub": 10_000, "ait-island-1": 8_000}
HUB_HEAD = CHAIN_HEADS["ait-hub"]

# 720 blocks either side of the head: ~1 hour at a 5-second block time.
FUTURE_TIMELOCK = HUB_HEAD + 720


# ---------------------------------------------------------------------------
# In-memory mock DB (extends settlement test pattern)
# ---------------------------------------------------------------------------


class _MockResult:
    def __init__(self, rows: list):
        self._rows = rows

    def scalars(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return list(self._rows)


class MockSession:
    """In-memory mock session supporting Account, HTLCSwapState, escrows, proofs."""

    def __init__(self):
        self.accounts: dict[tuple[str, str], Account] = {}
        self.swaps: dict[str, HTLCSwapState] = {}
        self.escrows: dict[str, CrossChainEscrowRecord] = {}
        # Chain heads. The contract compares swap timelocks against the real
        # head height; it used to derive one from time.time(), so these tests
        # never had to model a chain with blocks in it.
        self.block_heights: dict[str, int] = CHAIN_HEADS.copy()
        self.proofs: list[EscrowProofRecord] = []
        # Confirmed lock transfers, i.e. rows with a block_height. The
        # contract refuses to pay out of the shared escrow without one.
        self.transactions: list[Transaction] = []
        self._escrow_counter = 0
        self._proof_counter = 0

    def get(self, model_cls, primary_key):
        if model_cls is Account:
            return self.accounts.get(primary_key)
        elif model_cls is HTLCSwapState:
            return self.swaps.get(primary_key)
        elif model_cls is CrossChainEscrowRecord:
            # primary_key is escrow_id string
            return self.escrows.get(primary_key)
        return None

    def add(self, record):
        if isinstance(record, Account):
            self.accounts[(record.chain_id, record.address)] = record
        elif isinstance(record, HTLCSwapState):
            self.swaps[record.swap_id] = record
        elif isinstance(record, CrossChainEscrowRecord):
            if record.id is None:
                self._escrow_counter += 1
                record.id = self._escrow_counter
            self.escrows[record.escrow_id] = record
        elif isinstance(record, Transaction):
            self.transactions.append(record)
        elif isinstance(record, EscrowProofRecord):
            if record.id is None:
                self._proof_counter += 1
                record.id = self._proof_counter
            self.proofs = [p for p in self.proofs if p.id != record.id]
            self.proofs.append(record)

    def commit(self):
        pass

    def refresh(self, record):
        pass

    def flush(self):
        pass

    def exec(self, stmt):
        """SQLModel-style exec. Only the Transaction lookup uses this path."""
        froms = stmt.get_final_froms()
        table_name = froms[0].name if froms else ""
        if table_name != "transaction":
            return _MockResult([])
        filters = self._extract_filters(stmt.whereclause)
        rows = [t for t in self.transactions if t.block_height is not None]
        if "chain_id" in filters:
            rows = [t for t in rows if t.chain_id == filters["chain_id"]]
        if "type" in filters:
            rows = [t for t in rows if t.type == filters["type"]]
        return _MockResult(rows)

    def confirm_lock(self, swap_id: str, amount: int, chain_id: str = "ait-hub") -> None:
        """Record the HTLC_LOCK for ``swap_id`` as included in a block."""
        self.add(
            Transaction(
                hash=f"0xlock_{swap_id}",
                chain_id=chain_id,
                type="HTLC_LOCK",
                value=amount,
                block_height=CHAIN_HEADS[chain_id],
                payload={"swap_id": swap_id},
            )
        )

    def execute(self, stmt):
        froms = stmt.get_final_froms()
        table_name = froms[0].name if froms else ""
        where = stmt.whereclause
        filters = self._extract_filters(where)

        if table_name == "cross_chain_escrows":
            rows = list(self.escrows.values())
            if "escrow_id" in filters:
                rows = [r for r in rows if r.escrow_id == filters["escrow_id"]]
            if "status" in filters:
                rows = [r for r in rows if r.status in filters["status"]]
        elif table_name == "block":
            chain_id = filters.get("chain_id")
            height = self.block_heights.get(chain_id) if chain_id else None
            rows = [SimpleNamespace(height=height, chain_id=chain_id)] if height is not None else []
        elif table_name == "escrow_proofs":
            rows = list(self.proofs)
            if "escrow_id" in filters:
                rows = [r for r in rows if r.escrow_id == filters["escrow_id"]]
            if stmt._order_by_clauses:
                rows.sort(key=lambda r: r.id, reverse=True)
        else:
            rows = []

        return _MockResult(rows)

    def _extract_filters(self, where) -> dict:
        filters: dict = {}
        if where is None:
            return filters
        clauses = [where]
        if hasattr(where, "clauses") and where.operator.__name__ == "and_":
            clauses = list(where.clauses)
        for clause in clauses:
            if not hasattr(clause, "left") or not hasattr(clause, "operator"):
                continue
            col = clause.left
            key = getattr(col, "key", str(col))
            op = clause.operator
            right = getattr(clause, "right", None)
            if getattr(op, "__name__", "") == "eq":
                val = getattr(right, "value", right)
                filters[key] = val
            elif getattr(op, "__name__", "") == "in_op":
                val = getattr(right, "value", right)
                filters[key] = val
        return filters


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session():
    """Create a fresh MockSession."""
    return MockSession()


@pytest.fixture
def htlc(mock_session):
    """Create an HTLCContract with the mock session's chain_id."""
    return HTLCContract(chain_id="ait-hub")


# ---------------------------------------------------------------------------
# HTLCContract unit tests
# ---------------------------------------------------------------------------


class TestHTLCContract:
    """Test the Python-native HTLC contract (mirrors CrossChainAtomicSwap.sol).

    The three mutators are retired and raise ``RetiredProtocolTransfer`` —
    that contract is pinned in ``test_retired_protocol_transfers.py``; only
    the read path (``get_swap``) is exercised here.
    """

    def test_get_swap_returns_state(self, htlc, mock_session):
        """get_swap returns the current swap state."""
        mock_session.add(
            HTLCSwapState(
                swap_id="swap-1",
                initiator="0xalice",
                participant="0xbob",
                amount=1000,
                hashlock="cd" * 32,
                timelock=FUTURE_TIMELOCK,
                status="open",
            )
        )

        result = htlc.get_swap(session=mock_session, swap_id="swap-1")
        assert result is not None
        assert result.status == SwapStatus.OPEN

        # Non-existent swap
        assert htlc.get_swap(session=mock_session, swap_id="nonexistent") is None
