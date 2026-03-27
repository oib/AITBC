"""Test suite for Proof-of-Authority consensus mechanism."""

from __future__ import annotations

import asyncio
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch
from typing import Generator

from sqlmodel import Session, create_engine, select
from sqlmodel.pool import StaticPool

from aitbc_chain.consensus.poa import CircuitBreaker, PoAProposer
from aitbc_chain.config import ProposerConfig
from aitbc_chain.models import Block, Account
from aitbc_chain.mempool import InMemoryMempool


@pytest.fixture
def test_db() -> Generator[Session, None, None]:
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
def mock_session_factory(test_db: Session) -> Generator[callable, None, None]:
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
        with patch('aitbc_chain.mempool.get_mempool', return_value=mock_mempool):
            with patch('aitbc_chain.consensus.poa.gossip_broker', new=AsyncMock()):
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
            timestamp=datetime.utcnow(),
            tx_count=0,
        )
        test_db.add(parent)
        test_db.commit()
        
        # Mock mempool with transactions
        mock_tx = Mock()
        mock_tx.tx_hash = "0xtx"
        mock_tx.content = {"sender": "alice", "recipient": "bob", "amount": 100}
        mock_mempool.drain.return_value = [mock_tx]
        
        with patch('aitbc_chain.mempool.get_mempool', return_value=mock_mempool):
            with patch('aitbc_chain.consensus.poa.gossip_broker', new=AsyncMock()):
                await proposer._propose_block()
                
                # Verify new block was created
                block = test_db.exec(select(Block).where(Block.chain_id == proposer._config.chain_id).order_by(Block.height.desc())).first()
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
            timestamp=datetime.utcnow(),
            tx_count=0,
        )
        test_db.add(head)
        test_db.commit()
        
        # Should wait for the configured interval
        start_time = datetime.utcnow()
        await proposer._wait_until_next_slot()
        elapsed = (datetime.utcnow() - start_time).total_seconds()
        
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
            timestamp=datetime.utcnow() - timedelta(seconds=10),
            tx_count=0,
        )
        test_db.add(head)
        test_db.commit()
        
        # Set stop event and wait
        proposer._stop_event.set()
        start_time = datetime.utcnow()
        await proposer._wait_until_next_slot()
        elapsed = (datetime.utcnow() - start_time).total_seconds()
        
        # Should return immediately due to stop event
        assert elapsed < 0.1

    @pytest.mark.asyncio
    async def test_run_loop_stops_on_event(self, proposer: PoAProposer, mock_mempool: Mock) -> None:
        """Test that run loop stops when stop event is set."""
        with patch('aitbc_chain.mempool.get_mempool', return_value=mock_mempool):
            with patch('aitbc_chain.consensus.poa.gossip_broker', new=AsyncMock()):
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
        timestamp = datetime.utcnow()
        processed_txs = []
        
        block_hash = proposer._compute_block_hash(height, parent_hash, timestamp, processed_txs)
        
        assert isinstance(block_hash, str)
        assert block_hash.startswith("0x")
        assert len(block_hash) == 66  # 0x + 64 hex chars

    def test_compute_block_hash_with_transactions(self, proposer: PoAProposer) -> None:
        """Test block hash computation with transactions."""
        height = 1
        parent_hash = "0xparent"
        timestamp = datetime.utcnow()
        
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
            timestamp=datetime.utcnow(),
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
