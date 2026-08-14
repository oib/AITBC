"""Test suite for Proof-of-Authority consensus mechanism."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from aitbc_chain.config import ProposerConfig
from aitbc_chain.consensus import CircuitBreaker
from aitbc_chain.consensus.poa import PoAProposer
from aitbc.exceptions import CircuitBreakerOpenError
from aitbc_chain.mempool import InMemoryMempool
from aitbc_chain.models import Block
from sqlmodel import Session, create_engine
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


def _allow_request(breaker: CircuitBreaker) -> bool:
    """Helper: return True if the circuit breaker allows a request."""
    try:
        breaker.check()
        return True
    except CircuitBreakerOpenError:
        return False


class TestCircuitBreaker:
    """Test circuit breaker functionality."""

    def test_initial_state(self) -> None:
        """Test circuit breaker starts in closed state."""
        breaker = CircuitBreaker(threshold=5, timeout=60)
        assert breaker.get_state()["state"] == "closed"
        assert _allow_request(breaker) is True

    def test_failure_threshold_opens_circuit(self) -> None:
        """Test that exceeding failure threshold opens circuit."""
        breaker = CircuitBreaker(threshold=3, timeout=60)

        # Record failures up to threshold
        for _ in range(3):
            breaker.record_failure()

        assert breaker.get_state()["state"] == "open"
        assert _allow_request(breaker) is False

    def test_timeout_transitions_to_half_open(self) -> None:
        """Test that timeout transitions circuit to half-open."""
        breaker = CircuitBreaker(threshold=1, timeout=0.1)

        # Trigger open state
        breaker.record_failure()
        assert breaker.get_state()["state"] == "open"

        # Wait for timeout
        import time

        time.sleep(0.2)

        # check() transitions open → half_open on first call
        breaker.check()
        assert breaker.get_state()["state"] == "half_open"

    def test_success_resets_circuit(self) -> None:
        """Test that success resets circuit to closed (from half-open)."""
        breaker = CircuitBreaker(threshold=2, timeout=0.1)

        # Trigger open state
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.get_state()["state"] == "open"

        # Wait for timeout, then check() transitions to half-open
        import time

        time.sleep(0.15)
        breaker.check()
        assert breaker.get_state()["state"] == "half_open"

        # Record success in half-open state → closes the circuit
        breaker.record_success()
        assert breaker.get_state()["state"] == "closed"
        assert _allow_request(breaker) is True

    def test_half_open_allows_request(self) -> None:
        """Test that half-open state allows a probe request."""
        breaker = CircuitBreaker(threshold=1, timeout=0.1)

        # Trigger open then wait for timeout
        breaker.record_failure()
        import time

        time.sleep(0.2)

        # check() transitions open → half_open and allows the probe call
        breaker.check()
        assert breaker.get_state()["state"] == "half_open"


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
