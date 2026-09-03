"""B4: HTLC contract integration tests (v0.9.0).

Tests the Python-native HTLCContract that mirrors CrossChainAtomicSwap.sol:
  - initiate_swap: queues a lock from initiator to the contract escrow account
  - complete_swap: queues a release from the escrow to the participant (with secret)
  - refund_swap: queues a return from the escrow to the initiator (after timelock)

None of those three writes an account balance. Balances are covered by the block
header's ``state_root``, so the contract queues mempool transfers and lets block
processing settle them; the tests below assert the balances stay put and the
right transaction is queued.

Also tests the settlement service integration with the HTLC contract.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path

import pytest
from types import SimpleNamespace

# Ensure blockchain-node source is importable
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from aitbc.settlement.htlc import compute_hashlock, generate_secret  # noqa: E402
from aitbc_chain.base_models import (  # noqa: E402
    Account,
    CrossChainEscrowRecord,
    EscrowProofRecord,
    HTLCSwapState,
    Transaction,
)
from aitbc_chain.config import settings  # noqa: E402
from aitbc_chain.contracts.htlc_contract import HTLC_CONTRACT_ADDRESS, HTLCContract, SwapStatus  # noqa: E402


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
EXPIRED_TIMELOCK = HUB_HEAD - 720


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


@pytest.fixture(autouse=True)
def queued(monkeypatch):
    """Capture everything queue_protocol_transfer puts in the mempool.

    Autouse deliberately: every test that initiates a swap queues a transfer, and
    without this the real mempool backend would be reached. That is a live sqlite
    file on a node.
    """
    from aitbc_chain import mempool as mempool_module

    captured: list[dict] = []

    class _Mempool:
        def add(self, tx, chain_id=None, tx_hash=None):
            captured.append(tx)
            return "0x" + format(len(captured), "064x")

    monkeypatch.setattr(mempool_module, "get_mempool", lambda: _Mempool())
    return captured


def _balances(session) -> dict:
    return {key: acct.balance for key, acct in session.accounts.items()}


@pytest.fixture
def funded_accounts(mock_session):
    """Create initiator and participant accounts with balances."""
    initiator = Account(chain_id="ait-hub", address="0xalice", balance=10000, nonce=0)
    participant = Account(chain_id="ait-hub", address="0xbob", balance=5000, nonce=0)
    mock_session.add(initiator)
    mock_session.add(participant)
    mock_session.flush()
    return initiator, participant


# ---------------------------------------------------------------------------
# HTLCContract unit tests
# ---------------------------------------------------------------------------


class TestHTLCContract:
    """Test the Python-native HTLC contract (mirrors CrossChainAtomicSwap.sol)."""

    def test_initiate_swap_queues_the_lock_without_moving_balances(self, htlc, mock_session, funded_accounts, queued):
        """initiate_swap queues initiator -> escrow; the debit happens in a block.

        This test used to assert ``alice.balance == 9000`` immediately. That was
        pinning the defect: a balance written outside block processing makes the
        proposer's recomputed state root disagree with the header it signed.
        """
        initiator, participant = funded_accounts
        secret = generate_secret()
        hashlock = compute_hashlock(secret)

        swap = htlc.initiate_swap(
            session=mock_session,
            initiator="0xalice",
            participant="0xbob",
            amount=1000,
            hashlock=hashlock,
            timelock=FUTURE_TIMELOCK,
        )

        assert swap.status == SwapStatus.OPEN
        assert swap.initiator == "0xalice"
        assert swap.participant == "0xbob"
        assert swap.amount == 1000
        assert swap.hashlock == hashlock

        # No balance moved, and no escrow row was conjured into existence.
        assert _balances(mock_session) == {("ait-hub", "0xalice"): 10000, ("ait-hub", "0xbob"): 5000}
        assert mock_session.get(Account, ("ait-hub", HTLC_CONTRACT_ADDRESS)) is None

        assert len(queued) == 1
        assert queued[0]["type"] == "HTLC_LOCK"
        assert queued[0]["amount"] == 1000
        assert queued[0]["payload"] == {"swap_id": swap.swap_id}

    def test_initiate_swap_rejects_duplicate(self, htlc, mock_session, funded_accounts):
        """initiate_swap rejects a duplicate swap_id."""
        initiator, participant = funded_accounts
        secret = generate_secret()
        hashlock = compute_hashlock(secret)

        htlc.initiate_swap(
            session=mock_session,
            initiator="0xalice",
            participant="0xbob",
            amount=1000,
            hashlock=hashlock,
            timelock=FUTURE_TIMELOCK,
            swap_id="swap_1",
        )

        with pytest.raises(ValueError, match="Swap ID already exists"):
            htlc.initiate_swap(
                session=mock_session,
                initiator="0xalice",
                participant="0xbob",
                amount=500,
                hashlock=hashlock,
                timelock=FUTURE_TIMELOCK,
                swap_id="swap_1",
            )

    def test_initiate_swap_rejects_zero_participant(self, htlc, mock_session, funded_accounts):
        """initiate_swap rejects zero address participant."""
        secret = generate_secret()
        with pytest.raises(ValueError, match="Invalid participant"):
            htlc.initiate_swap(
                session=mock_session,
                initiator="0xalice",
                participant="0x0",
                amount=100,
                hashlock=compute_hashlock(secret),
                timelock=FUTURE_TIMELOCK,
            )

    def test_initiate_swap_rejects_insufficient_balance(self, htlc, mock_session, funded_accounts):
        """initiate_swap rejects when initiator has insufficient balance."""
        secret = generate_secret()
        with pytest.raises(ValueError, match="Insufficient balance"):
            htlc.initiate_swap(
                session=mock_session,
                initiator="0xalice",
                participant="0xbob",
                amount=999999,
                hashlock=compute_hashlock(secret),
                timelock=FUTURE_TIMELOCK,
            )

    def test_complete_swap_releases_funds(self, htlc, mock_session, funded_accounts, queued):
        """complete_swap verifies the secret and queues the release to the participant."""
        initiator, participant = funded_accounts
        secret = generate_secret()
        hashlock = compute_hashlock(secret)

        swap = htlc.initiate_swap(
            session=mock_session,
            initiator="0xalice",
            participant="0xbob",
            amount=1000,
            hashlock=hashlock,
            timelock=FUTURE_TIMELOCK,
        )

        mock_session.confirm_lock(swap.swap_id, 1000)
        before = _balances(mock_session)

        result = htlc.complete_swap(
            session=mock_session,
            swap_id=swap.swap_id,
            secret=secret,
        )

        assert result.status == SwapStatus.COMPLETED

        # The release is queued, not applied.
        assert _balances(mock_session) == before
        release = queued[-1]
        assert release["type"] == "HTLC_CLAIM"
        assert release["to"].lower().endswith("bob")
        assert release["amount"] == 1000
        assert release["payload"] == {"swap_id": swap.swap_id}

    def test_complete_swap_refuses_while_the_lock_is_unconfirmed(self, htlc, mock_session, funded_accounts, queued):
        """The escrow is shared, so a release before the lock lands would pay out of other swaps.

        The proposer drops a lock whose sender has since spent the balance, so a
        swap row can exist with nothing behind it.
        """
        secret = generate_secret()
        swap = htlc.initiate_swap(
            session=mock_session,
            initiator="0xalice",
            participant="0xbob",
            amount=1000,
            hashlock=compute_hashlock(secret),
            timelock=FUTURE_TIMELOCK,
        )

        with pytest.raises(ValueError, match="lock is not confirmed on-chain"):
            htlc.complete_swap(session=mock_session, swap_id=swap.swap_id, secret=secret)

        assert [tx["type"] for tx in queued] == ["HTLC_LOCK"]
        assert mock_session.get(HTLCSwapState, swap.swap_id).status == SwapStatus.OPEN.value

    def test_complete_swap_rejects_wrong_secret(self, htlc, mock_session, funded_accounts):
        """complete_swap rejects an invalid secret."""
        secret = generate_secret()
        hashlock = compute_hashlock(secret)

        swap = htlc.initiate_swap(
            session=mock_session,
            initiator="0xalice",
            participant="0xbob",
            amount=1000,
            hashlock=hashlock,
            timelock=FUTURE_TIMELOCK,
        )

        wrong_secret = generate_secret()
        with pytest.raises(ValueError, match="Invalid secret"):
            htlc.complete_swap(
                session=mock_session,
                swap_id=swap.swap_id,
                secret=wrong_secret,
            )

    def test_complete_swap_rejects_expired(self, htlc, mock_session, funded_accounts):
        """complete_swap rejects when timelock has expired."""
        secret = generate_secret()
        hashlock = compute_hashlock(secret)
        swap = htlc.initiate_swap(
            session=mock_session,
            initiator="0xalice",
            participant="0xbob",
            amount=1000,
            hashlock=hashlock,
            timelock=EXPIRED_TIMELOCK,
        )

        with pytest.raises(ValueError, match="timelock expired"):
            htlc.complete_swap(
                session=mock_session,
                swap_id=swap.swap_id,
                secret=secret,
            )

    def test_refund_swap_returns_funds(self, htlc, mock_session, funded_accounts, queued):
        """refund_swap queues the return to the initiator after timelock expiry."""
        initiator, participant = funded_accounts
        secret = generate_secret()
        hashlock = compute_hashlock(secret)
        # Timelock already behind the chain head, so refund is allowed
        swap = htlc.initiate_swap(
            session=mock_session,
            initiator="0xalice",
            participant="0xbob",
            amount=1000,
            hashlock=hashlock,
            timelock=EXPIRED_TIMELOCK,
        )

        mock_session.confirm_lock(swap.swap_id, 1000)
        before = _balances(mock_session)

        result = htlc.refund_swap(
            session=mock_session,
            swap_id=swap.swap_id,
        )

        assert result.status == SwapStatus.REFUNDED

        assert _balances(mock_session) == before
        refund = queued[-1]
        assert refund["type"] == "HTLC_REFUND"
        assert refund["to"].lower().endswith("alice")
        assert refund["amount"] == 1000
        assert refund["payload"] == {"swap_id": swap.swap_id}

    def test_refund_swap_rejects_not_expired(self, htlc, mock_session, funded_accounts):
        """refund_swap rejects when timelock hasn't expired yet."""
        secret = generate_secret()
        hashlock = compute_hashlock(secret)

        swap = htlc.initiate_swap(
            session=mock_session,
            initiator="0xalice",
            participant="0xbob",
            amount=1000,
            hashlock=hashlock,
            timelock=FUTURE_TIMELOCK,
        )

        with pytest.raises(ValueError, match="timelock not yet expired"):
            htlc.refund_swap(
                session=mock_session,
                swap_id=swap.swap_id,
            )

    def test_get_swap_returns_state(self, htlc, mock_session, funded_accounts):
        """get_swap returns the current swap state."""
        secret = generate_secret()
        hashlock = compute_hashlock(secret)

        swap = htlc.initiate_swap(
            session=mock_session,
            initiator="0xalice",
            participant="0xbob",
            amount=1000,
            hashlock=hashlock,
            timelock=FUTURE_TIMELOCK,
        )

        result = htlc.get_swap(session=mock_session, swap_id=swap.swap_id)
        assert result is not None
        assert result.status == SwapStatus.OPEN

        # Non-existent swap
        assert htlc.get_swap(session=mock_session, swap_id="nonexistent") is None


# ---------------------------------------------------------------------------
# Settlement service integration tests (B4)
# ---------------------------------------------------------------------------


class TestSettlementB4Integration:
    """Test that CrossChainSettlementService uses HTLCContract for fund movement."""

    @pytest.fixture
    def mock_session_b4(self):
        """Create a fresh MockSession and patch session_scope."""
        session = MockSession()

        # Pre-fund the sender account
        alice = Account(chain_id="ait-hub", address="alice", balance=100000, nonce=0)
        bob = Account(chain_id="ait-hub", address="bob", balance=50000, nonce=0)
        session.add(alice)
        session.add(bob)
        session.flush()

        @contextmanager
        def fake_scope(chain_id: str = ""):
            yield session

        with pytest.MonkeyPatch().context() as mp:
            mp.setattr("aitbc_chain.cross_chain.settlement.session_scope", fake_scope)
            yield session

    @pytest.fixture(autouse=True)
    def enable_escrow(self):
        """Enable escrow for all tests, restore afterwards."""
        original = settings.escrow_enabled
        settings.escrow_enabled = True
        yield
        settings.escrow_enabled = original
