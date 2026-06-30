"""B4: HTLC contract integration tests (v0.9.0).

Tests the Python-native HTLCContract that mirrors CrossChainAtomicSwap.sol:
  - initiate_swap: locks funds from initiator to contract escrow account
  - complete_swap: releases funds from contract to participant (with secret)
  - refund_swap: returns funds from contract to initiator (after timelock)

Also tests the settlement service integration with the HTLC contract.
"""

from __future__ import annotations

import sys
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

# Ensure blockchain-node source is importable
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from aitbc.settlement.htlc import compute_hashlock, generate_secret  # noqa: E402
from aitbc_chain.base_models import Account, CrossChainEscrowRecord, EscrowProofRecord, HTLCSwapState  # noqa: E402
from aitbc_chain.config import settings  # noqa: E402
from aitbc_chain.contracts.htlc_contract import HTLC_CONTRACT_ADDRESS, HTLCContract, SwapStatus  # noqa: E402


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
        self.proofs: list[EscrowProofRecord] = []
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
            col = clause.left
            key = getattr(col, "key", str(col))
            op = clause.operator
            right = clause.right
            if op.__name__ == "eq":
                val = getattr(right, "value", right)
                filters[key] = val
            elif op.__name__ == "in_op":
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

    def test_initiate_swap_locks_funds(self, htlc, mock_session, funded_accounts):
        """initiate_swap debits initiator and credits contract escrow account."""
        initiator, participant = funded_accounts
        secret = generate_secret()
        hashlock = compute_hashlock(secret)
        timelock = int(time.time() // 5) + 720  # far future

        swap = htlc.initiate_swap(
            session=mock_session,
            initiator="0xalice",
            participant="0xbob",
            amount=1000,
            hashlock=hashlock,
            timelock=timelock,
        )

        assert swap.status == SwapStatus.OPEN
        assert swap.initiator == "0xalice"
        assert swap.participant == "0xbob"
        assert swap.amount == 1000
        assert swap.hashlock == hashlock

        # Check balance movement
        alice = mock_session.get(Account, ("ait-hub", "0xalice"))
        assert alice.balance == 9000  # 10000 - 1000

        contract = mock_session.get(Account, ("ait-hub", HTLC_CONTRACT_ADDRESS))
        assert contract is not None
        assert contract.balance == 1000

    def test_initiate_swap_rejects_duplicate(self, htlc, mock_session, funded_accounts):
        """initiate_swap rejects a duplicate swap_id."""
        initiator, participant = funded_accounts
        secret = generate_secret()
        hashlock = compute_hashlock(secret)
        timelock = int(time.time() // 5) + 720

        htlc.initiate_swap(
            session=mock_session,
            initiator="0xalice",
            participant="0xbob",
            amount=1000,
            hashlock=hashlock,
            timelock=timelock,
            swap_id="swap_1",
        )

        with pytest.raises(ValueError, match="Swap ID already exists"):
            htlc.initiate_swap(
                session=mock_session,
                initiator="0xalice",
                participant="0xbob",
                amount=500,
                hashlock=hashlock,
                timelock=timelock,
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
                timelock=720,
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
                timelock=720,
            )

    def test_complete_swap_releases_funds(self, htlc, mock_session, funded_accounts):
        """complete_swap verifies secret and releases funds to participant."""
        initiator, participant = funded_accounts
        secret = generate_secret()
        hashlock = compute_hashlock(secret)
        timelock = int(time.time() // 5) + 720

        swap = htlc.initiate_swap(
            session=mock_session,
            initiator="0xalice",
            participant="0xbob",
            amount=1000,
            hashlock=hashlock,
            timelock=timelock,
        )

        result = htlc.complete_swap(
            session=mock_session,
            swap_id=swap.swap_id,
            secret=secret,
        )

        assert result.status == SwapStatus.COMPLETED

        # Funds moved from contract to participant
        contract = mock_session.get(Account, ("ait-hub", HTLC_CONTRACT_ADDRESS))
        assert contract.balance == 0

        bob = mock_session.get(Account, ("ait-hub", "0xbob"))
        assert bob.balance == 6000  # 5000 + 1000

    def test_complete_swap_rejects_wrong_secret(self, htlc, mock_session, funded_accounts):
        """complete_swap rejects an invalid secret."""
        secret = generate_secret()
        hashlock = compute_hashlock(secret)
        timelock = int(time.time() // 5) + 720

        swap = htlc.initiate_swap(
            session=mock_session,
            initiator="0xalice",
            participant="0xbob",
            amount=1000,
            hashlock=hashlock,
            timelock=timelock,
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
        # Set timelock in the past
        timelock = 1

        swap = htlc.initiate_swap(
            session=mock_session,
            initiator="0xalice",
            participant="0xbob",
            amount=1000,
            hashlock=hashlock,
            timelock=timelock,
        )

        with pytest.raises(ValueError, match="timelock expired"):
            htlc.complete_swap(
                session=mock_session,
                swap_id=swap.swap_id,
                secret=secret,
            )

    def test_refund_swap_returns_funds(self, htlc, mock_session, funded_accounts):
        """refund_swap returns funds to initiator after timelock expiry."""
        initiator, participant = funded_accounts
        secret = generate_secret()
        hashlock = compute_hashlock(secret)
        # Set timelock in the past so refund is allowed
        timelock = 1

        swap = htlc.initiate_swap(
            session=mock_session,
            initiator="0xalice",
            participant="0xbob",
            amount=1000,
            hashlock=hashlock,
            timelock=timelock,
        )

        result = htlc.refund_swap(
            session=mock_session,
            swap_id=swap.swap_id,
        )

        assert result.status == SwapStatus.REFUNDED

        # Funds returned to initiator
        contract = mock_session.get(Account, ("ait-hub", HTLC_CONTRACT_ADDRESS))
        assert contract.balance == 0

        alice = mock_session.get(Account, ("ait-hub", "0xalice"))
        assert alice.balance == 10000  # back to original

    def test_refund_swap_rejects_not_expired(self, htlc, mock_session, funded_accounts):
        """refund_swap rejects when timelock hasn't expired yet."""
        secret = generate_secret()
        hashlock = compute_hashlock(secret)
        timelock = int(time.time() // 5) + 720  # far future

        swap = htlc.initiate_swap(
            session=mock_session,
            initiator="0xalice",
            participant="0xbob",
            amount=1000,
            hashlock=hashlock,
            timelock=timelock,
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
        timelock = int(time.time() // 5) + 720

        swap = htlc.initiate_swap(
            session=mock_session,
            initiator="0xalice",
            participant="0xbob",
            amount=1000,
            hashlock=hashlock,
            timelock=timelock,
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

    async def test_lock_escrow_moves_funds(self, mock_session_b4):
        """lock_escrow calls HTLCContract.initiate_swap to move funds."""
        from aitbc_chain.cross_chain.settlement import CrossChainSettlementService

        svc = CrossChainSettlementService("ait-hub")
        create_result = await svc.create_escrow(
            trade_id="trade_1",
            source_chain="ait-hub",
            dest_chain="ait-island-1",
            sender="alice",
            recipient="bob",
            amount=1000,
            timeout_seconds=3600,
        )
        escrow_id = create_result["escrow_id"]

        # Lock the escrow
        lock_result = await svc.lock_escrow(escrow_id)

        assert lock_result["status"] == "locked"
        assert lock_result["tx_hash"] is not None

        # Verify funds moved: alice debited, contract escrow credited
        alice = mock_session_b4.get(Account, ("ait-hub", "alice"))
        assert alice.balance == 99000  # 100000 - 1000

        contract = mock_session_b4.get(Account, ("ait-hub", HTLC_CONTRACT_ADDRESS))
        assert contract is not None
        assert contract.balance == 1000

    async def test_settle_releases_funds(self, mock_session_b4):
        """Full lifecycle: create → lock → verify → execute → settle releases funds."""
        from aitbc_chain.cross_chain.settlement import CrossChainSettlementService

        svc = CrossChainSettlementService("ait-hub")
        create_result = await svc.create_escrow(
            trade_id="trade_2",
            source_chain="ait-hub",
            dest_chain="ait-island-1",
            sender="alice",
            recipient="bob",
            amount=2000,
            timeout_seconds=3600,
        )
        escrow_id = create_result["escrow_id"]
        secret = create_result["secret"]

        # Full lifecycle
        await svc.lock_escrow(escrow_id)
        await svc.verify_lock(escrow_id)
        await svc.execute_trade(escrow_id)
        settle_result = await svc.settle(escrow_id, secret)

        assert settle_result["status"] == "completed"

        # Funds should be released to participant (bob)
        contract = mock_session_b4.get(Account, ("ait-hub", HTLC_CONTRACT_ADDRESS))
        assert contract.balance == 0  # all released

        bob = mock_session_b4.get(Account, ("ait-hub", "bob"))
        assert bob.balance == 52000  # 50000 + 2000
