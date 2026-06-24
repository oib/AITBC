"""Test suite for Proof-of-Authority consensus mechanism."""

from __future__ import annotations

import asyncio
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest
from aitbc_chain.config import ProposerConfig
from aitbc_chain.consensus.poa import CircuitBreaker, PoAProposer
from aitbc_chain.mempool import InMemoryMempool
from aitbc_chain.models import Account, Block, Transaction
from sqlmodel import Session, create_engine, select
from sqlmodel.pool import StaticPool


@pytest.fixture
def test_db() -> Generator[Session]:
    """Create a test database session."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Block.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def proposer_config() -> ProposerConfig:
    """Create a test proposer configuration."""
    return ProposerConfig(
        chain_id="test-chain",
        proposer_id="test-proposer",
        interval_seconds=1.0,
        max_txs_per_block=10,
        max_block_size_bytes=1_000_000,
    )


@pytest.fixture
def mock_session_factory(test_db: Session) -> Generator[callable]:
    """Create a mock session factory."""

    def factory():
        return test_db

    yield factory


@pytest.fixture
def mock_mempool() -> Mock:
    """Create a mock mempool."""
    mempool = Mock(spec=InMemoryMempool)
    mempool.drain.return_value = []
    return mempool


class TestCircuitBreaker:
    """Test circuit breaker functionality."""

    def test_initial_state(self) -> None:
        """Test circuit breaker starts in closed state."""
        breaker = CircuitBreaker(threshold=5, timeout=60)
        assert breaker.state == "closed"
        assert breaker.allow_request() is True

    def test_failure_threshold_opens_circuit(self) -> None:
        """Test that exceeding failure threshold opens circuit."""
        breaker = CircuitBreaker(threshold=3, timeout=60)

        # Record failures up to threshold
        for _ in range(3):
            breaker.record_failure()

        assert breaker.state == "open"
        assert breaker.allow_request() is False

    def test_timeout_transitions_to_half_open(self) -> None:
        """Test that timeout transitions circuit to half-open."""
        breaker = CircuitBreaker(threshold=1, timeout=0.1)

        # Trigger open state
        breaker.record_failure()
        assert breaker.state == "open"

        # Wait for timeout
        import time

        time.sleep(0.2)

        assert breaker.state == "half-open"
        assert breaker.allow_request() is True

    def test_success_resets_circuit(self) -> None:
        """Test that success resets circuit to closed."""
        breaker = CircuitBreaker(threshold=2, timeout=60)

        # Trigger open state
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state == "open"

        # Record success
        breaker.record_success()
        assert breaker.state == "closed"
        assert breaker.allow_request() is True

    def test_half_open_allows_request(self) -> None:
        """Test that half-open state allows requests."""
        breaker = CircuitBreaker(threshold=1, timeout=0.1)

        # Trigger open then wait for timeout
        breaker.record_failure()
        import time

        time.sleep(0.2)

        assert breaker.state == "half-open"
        assert breaker.allow_request() is True


class TestPoAProposer:
    """Test Proof-of-Authority proposer functionality."""

    @pytest.fixture
    def proposer(self, proposer_config: ProposerConfig, mock_session_factory: callable) -> PoAProposer:
        """Create a PoA proposer instance."""
        return PoAProposer(config=proposer_config, session_factory=mock_session_factory)

    def test_proposer_initialization(self, proposer: PoAProposer, proposer_config: ProposerConfig) -> None:
        """Test proposer initialization."""
        assert proposer._config == proposer_config
        assert proposer._task is None
        assert not proposer._stop_event.is_set()

    @pytest.mark.asyncio
    async def test_start_stop_proposer(self, proposer: PoAProposer) -> None:
        """Test starting and stopping the proposer."""
        # Start proposer
        await proposer.start()
        assert proposer._task is not None
        assert not proposer._stop_event.is_set()

        # Stop proposer
        await proposer.stop()
        assert proposer._task is None
        assert proposer._stop_event.is_set()

    @pytest.mark.asyncio
    async def test_start_already_running(self, proposer: PoAProposer) -> None:
        """Test that starting an already running proposer doesn't create duplicate tasks."""
        await proposer.start()
        original_task = proposer._task

        # Try to start again
        await proposer.start()

        assert proposer._task is original_task
        await proposer.stop()

    @pytest.mark.asyncio
    async def test_stop_not_running(self, proposer: PoAProposer) -> None:
        """Test stopping a proposer that isn't running."""
        # Should not raise an exception
        await proposer.stop()
        assert proposer._task is None

    @pytest.mark.asyncio
    async def test_propose_block_genesis(self, proposer: PoAProposer, test_db: Session, mock_mempool: Mock) -> None:
        """Test proposing a genesis block."""
        with patch("aitbc_chain.mempool.get_mempool", return_value=mock_mempool):
            with patch("aitbc_chain.consensus.poa.gossip_broker", new=AsyncMock()):
                await proposer._propose_block()

                # Verify genesis block was created
                block = test_db.exec(select(Block).where(Block.chain_id == proposer._config.chain_id)).first()
                assert block is not None
                assert block.height == 0
                assert block.parent_hash == "0x00"
                assert block.proposer == proposer._config.proposer_id
                assert block.tx_count == 0

    @pytest.mark.asyncio
    async def test_propose_block_with_parent(self, proposer: PoAProposer, test_db: Session, mock_mempool: Mock) -> None:
        """Test proposing a block with a parent block."""
        # Create parent block
        parent = Block(
            chain_id=proposer._config.chain_id,
            height=0,
            hash="0xparent",
            parent_hash="0x00",
            proposer="previous-proposer",
            timestamp=datetime.now(UTC),
            tx_count=0,
        )
        test_db.add(parent)
        test_db.commit()

        # Mock mempool with transactions
        mock_tx = Mock()
        mock_tx.tx_hash = "0xtx"
        mock_tx.content = {"sender": "alice", "recipient": "bob", "amount": 100}
        mock_mempool.drain.return_value = [mock_tx]

        with patch("aitbc_chain.mempool.get_mempool", return_value=mock_mempool):
            with patch("aitbc_chain.consensus.poa.gossip_broker", new=AsyncMock()):
                await proposer._propose_block()

                # Verify new block was created
                block = test_db.exec(
                    select(Block).where(Block.chain_id == proposer._config.chain_id).order_by(Block.height.desc())
                ).first()
                assert block is not None
                assert block.height == 1
                assert block.parent_hash == "0xparent"
                assert block.proposer == proposer._config.proposer_id

    @pytest.mark.asyncio
    async def test_wait_until_next_slot_no_head(self, proposer: PoAProposer) -> None:
        """Test waiting for next slot when no head exists."""
        # Should return immediately when no head
        await proposer._wait_until_next_slot()

    @pytest.mark.asyncio
    async def test_wait_until_next_slot_with_head(self, proposer: PoAProposer, test_db: Session) -> None:
        """Test waiting for next slot with existing head."""
        # Create recent head block
        head = Block(
            chain_id=proposer._config.chain_id,
            height=0,
            hash="0xhead",
            parent_hash="0x00",
            proposer="test-proposer",
            timestamp=datetime.now(UTC),
            tx_count=0,
        )
        test_db.add(head)
        test_db.commit()

        # Should wait for the configured interval
        start_time = datetime.now(UTC)
        await proposer._wait_until_next_slot()
        elapsed = (datetime.now(UTC) - start_time).total_seconds()

        # Should wait at least some time (but less than full interval since block is recent)
        assert elapsed >= 0.1

    @pytest.mark.asyncio
    async def test_wait_until_next_slot_stop_event(self, proposer: PoAProposer, test_db: Session) -> None:
        """Test that stop event interrupts slot waiting."""
        # Create old head block to ensure waiting
        head = Block(
            chain_id=proposer._config.chain_id,
            height=0,
            hash="0xhead",
            parent_hash="0x00",
            proposer="test-proposer",
            timestamp=datetime.now(UTC) - timedelta(seconds=10),
            tx_count=0,
        )
        test_db.add(head)
        test_db.commit()

        # Set stop event and wait
        proposer._stop_event.set()
        start_time = datetime.now(UTC)
        await proposer._wait_until_next_slot()
        elapsed = (datetime.now(UTC) - start_time).total_seconds()

        # Should return immediately due to stop event
        assert elapsed < 0.1

    @pytest.mark.asyncio
    async def test_run_loop_stops_on_event(self, proposer: PoAProposer, mock_mempool: Mock) -> None:
        """Test that run loop stops when stop event is set."""
        with patch("aitbc_chain.mempool.get_mempool", return_value=mock_mempool):
            with patch("aitbc_chain.consensus.poa.gossip_broker", new=AsyncMock()):
                # Start the loop
                proposer._stop_event.clear()
                task = asyncio.create_task(proposer._run_loop())

                # Let it run briefly then stop
                await asyncio.sleep(0.1)
                proposer._stop_event.set()

                # Wait for task to complete
                await task

    def test_compute_block_hash(self, proposer: PoAProposer) -> None:
        """Test block hash computation."""
        height = 1
        parent_hash = "0xparent"
        timestamp = datetime.now(UTC)
        processed_txs = []

        block_hash = proposer._compute_block_hash(height, parent_hash, timestamp, processed_txs)

        assert isinstance(block_hash, str)
        assert block_hash.startswith("0x")
        assert len(block_hash) == 66  # 0x + 64 hex chars

    def test_compute_block_hash_with_transactions(self, proposer: PoAProposer) -> None:
        """Test block hash computation with transactions."""
        height = 1
        parent_hash = "0xparent"
        timestamp = datetime.now(UTC)

        mock_tx = Mock()
        mock_tx.tx_hash = "0xtx"
        processed_txs = [mock_tx]

        block_hash = proposer._compute_block_hash(height, parent_hash, timestamp, processed_txs)

        assert isinstance(block_hash, str)
        assert block_hash.startswith("0x")
        assert len(block_hash) == 66

    def test_ensure_genesis_block_existing(self, proposer: PoAProposer, test_db: Session) -> None:
        """Test genesis block creation when block already exists."""
        # Create existing block
        block = Block(
            chain_id=proposer._config.chain_id,
            height=0,
            hash="0xexisting",
            parent_hash="0x00",
            proposer="test-proposer",
            timestamp=datetime.now(UTC),
            tx_count=0,
        )
        test_db.add(block)
        test_db.commit()

        # Should not create duplicate
        proposer._ensure_genesis_block()
        blocks = test_db.exec(select(Block).where(Block.chain_id == proposer._config.chain_id)).all()
        assert len(blocks) == 1
        assert blocks[0].hash == "0xexisting"

    def test_sanitize_metric_suffix(self) -> None:
        """Test metric suffix sanitization."""
        from aitbc_chain.consensus.poa import _sanitize_metric_suffix

        # Test normal string
        assert _sanitize_metric_suffix("normal") == "normal"

        # Test with special characters
        assert _sanitize_metric_suffix("test@#$") == "test"

        # Test empty string
        assert _sanitize_metric_suffix("") == "unknown"

        # Test only special characters
        assert _sanitize_metric_suffix("@#$") == "unknown"

    @pytest.mark.asyncio
    async def test_propose_block_partial_failure(self, proposer: PoAProposer, test_db: Session) -> None:
        """Test that valid txs survive when an invalid tx is in the same batch.

        Injects 3 valid + 1 invalid tx (insufficient balance) and verifies
        that the 3 valid txs' state changes are preserved via savepoints,
        while only the invalid tx is dropped.
        """
        from aitbc_chain.state.state_transition import get_state_transition

        # Reset the global state transition singleton to avoid cross-test contamination
        st = get_state_transition()
        st._processed_tx_hashes.clear()
        st._processed_nonces.clear()

        # Set up sender account with enough balance for 3 txs but not the 4th
        sender = "alice"
        recipient = "bob"
        chain_id = proposer._config.chain_id

        sender_account = Account(chain_id=chain_id, address=sender, balance=400, nonce=0)
        recipient_account = Account(chain_id=chain_id, address=recipient, balance=0, nonce=0)
        test_db.add(sender_account)
        test_db.add(recipient_account)
        test_db.commit()

        # Create 3 valid txs (100 each) + 1 invalid tx (100, but only 100 left after 3 txs = 0 balance, 4th needs 100+fee)
        def make_tx(tx_hash: str, amount: int) -> Mock:
            mock_tx = Mock()
            mock_tx.tx_hash = tx_hash
            mock_tx.content = {"from": sender, "to": recipient, "amount": amount, "fee": 0, "type": "TRANSFER"}
            return mock_tx

        valid_txs = [make_tx("0x" + "a" * 62 + str(i), 100) for i in range(3)]
        invalid_tx = make_tx("0x" + "b" * 63, 100)
        invalid_tx.content["chain_id"] = "wrong-chain"  # Fail inside apply_transaction via chain isolation check
        all_txs = valid_txs + [invalid_tx]

        mock_mempool = Mock(spec=InMemoryMempool)
        mock_mempool.drain.return_value = all_txs

        with patch("aitbc_chain.mempool.get_mempool", return_value=mock_mempool):
            with patch("aitbc_chain.consensus.poa.gossip_broker", new=AsyncMock()):
                result = await proposer._propose_block()

                assert result is True

                # Verify block was proposed with 3 txs (the valid ones)
                block = test_db.exec(select(Block).where(Block.chain_id == chain_id).order_by(Block.height.desc())).first()
                assert block is not None
                assert block.tx_count == 3

                # Verify 3 valid transactions were committed
                txs = test_db.exec(
                    select(Transaction).where(Transaction.chain_id == chain_id).order_by(Transaction.nonce)
                ).all()
                assert len(txs) == 3
                for tx in txs:
                    assert tx.status == "confirmed"

                # Verify sender balance was reduced by 300 (3 * 100)
                updated_sender = test_db.get(Account, (chain_id, sender))
                assert updated_sender is not None
                assert updated_sender.balance == 100  # 400 - 300 = 100

                # Verify recipient balance was increased by 300
                updated_recipient = test_db.get(Account, (chain_id, recipient))
                assert updated_recipient is not None
                assert updated_recipient.balance == 300

                # Verify sender nonce advanced by 3
                assert updated_sender.nonce == 3

    @pytest.mark.asyncio
    async def test_propose_block_unexpected_exception_aborts_proposal(self, proposer_config: ProposerConfig) -> None:
        """Test that an unexpected exception aborts the entire proposal.

        Injects 2 valid txs followed by a tx that triggers a RuntimeError
        (unexpected, not a validation failure). The fix changed the outer
        except block from session.rollback()+continue to return False,
        so the entire proposal should be aborted and no block committed.

        The key assertion is that no Block row is committed — the
        session.commit() at the end of _propose_block() is never reached
        when return False short-circuits the proposal.
        """
        import tempfile

        from sqlalchemy.pool import NullPool

        from aitbc_chain.state.state_transition import get_state_transition

        # Reset the global state transition singleton
        st = get_state_transition()
        st._processed_tx_hashes.clear()
        st._processed_nonces.clear()

        # Use a file-based database with NullPool so each session gets
        # its own connection — matching production behavior.
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            engine = create_engine(
                f"sqlite:///{db_path}",
                connect_args={"check_same_thread": False},
                poolclass=NullPool,
            )
            Block.metadata.create_all(engine)

            def session_factory():
                return Session(engine)

            proposer = PoAProposer(config=proposer_config, session_factory=session_factory)

            # Set up sender account using a separate session
            sender = "alice"
            recipient = "bob"
            chain_id = proposer._config.chain_id

            with Session(engine) as setup_session:
                sender_account = Account(chain_id=chain_id, address=sender, balance=1000, nonce=0)
                recipient_account = Account(chain_id=chain_id, address=recipient, balance=0, nonce=0)
                setup_session.add(sender_account)
                setup_session.add(recipient_account)
                setup_session.commit()

            def make_tx(tx_hash: str, amount: int) -> Mock:
                mock_tx = Mock()
                mock_tx.tx_hash = tx_hash
                mock_tx.content = {"from": sender, "to": recipient, "amount": amount, "fee": 0, "type": "TRANSFER"}
                return mock_tx

            # 2 valid txs + 1 tx that will cause an unexpected RuntimeError
            valid_txs = [make_tx("0x" + "a" * 62 + str(i), 100) for i in range(2)]
            bad_tx = make_tx("0x" + "c" * 63, 100)
            all_txs = valid_txs + [bad_tx]

            mock_mempool = Mock(spec=InMemoryMempool)
            mock_mempool.drain.return_value = all_txs

            # Patch state_transition to raise RuntimeError on the 3rd tx
            original_apply = st.apply_transaction
            call_count = {"n": 0}

            def apply_with_injected_failure(session, cid, tx_data, tx_hash):
                call_count["n"] += 1
                if call_count["n"] == 3:
                    raise RuntimeError("Injected unexpected failure")
                return original_apply(session, cid, tx_data, tx_hash)

            with patch("aitbc_chain.mempool.get_mempool", return_value=mock_mempool):
                with patch("aitbc_chain.consensus.poa.gossip_broker", new=AsyncMock()):
                    with patch.object(st, "apply_transaction", side_effect=apply_with_injected_failure):
                        result = await proposer._propose_block()

                        # Proposal should be aborted
                        assert result is False

            # Verify with a fresh session that no block was committed.
            # The session.commit() at the end of _propose_block() commits
            # the Block row — if return False short-circuits, that commit
            # never happens and no block exists in the database.
            with Session(engine) as verify_session:
                blocks = verify_session.exec(select(Block).where(Block.chain_id == chain_id)).all()
                assert len(blocks) == 0
