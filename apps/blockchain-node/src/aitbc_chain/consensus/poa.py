import asyncio
import hashlib
import re
from datetime import datetime
from typing import Callable, ContextManager, Optional

from sqlmodel import Session, select

from ..logger import get_logger
from ..metrics import metrics_registry
from ..config import ProposerConfig
from ..models import Block
from ..gossip import gossip_broker

_METRIC_KEY_SANITIZE = re.compile(r"[^a-zA-Z0-9_]")


def _sanitize_metric_suffix(value: str) -> str:
    sanitized = _METRIC_KEY_SANITIZE.sub("_", value).strip("_")
    return sanitized or "unknown"



import time

class CircuitBreaker:
    def __init__(self, threshold: int, timeout: int):
        self._threshold = threshold
        self._timeout = timeout
        self._failures = 0
        self._last_failure_time = 0.0
        self._state = "closed"

    @property
    def state(self) -> str:
        if self._state == "open":
            if time.time() - self._last_failure_time > self._timeout:
                self._state = "half-open"
        return self._state

    def allow_request(self) -> bool:
        state = self.state
        if state == "closed":
            return True
        if state == "half-open":
            return True
        return False

    def record_failure(self) -> None:
        self._failures += 1
        self._last_failure_time = time.time()
        if self._failures >= self._threshold:
            self._state = "open"

    def record_success(self) -> None:
        self._failures = 0
        self._state = "closed"

class PoAProposer:
    """Proof-of-Authority block proposer.

    Responsible for periodically proposing blocks if this node is configured as a proposer.
    In the real implementation, this would involve checking the mempool, validating transactions,
    and signing the block.
    """

    def __init__(
        self,
        *,
        config: ProposerConfig,
        session_factory: Callable[[], ContextManager[Session]],
    ) -> None:
        self._config = config
        self._session_factory = session_factory
        self._logger = get_logger(__name__)
        self._stop_event = asyncio.Event()
        self._task: Optional[asyncio.Task[None]] = None
        self._last_proposer_id: Optional[str] = None

    async def start(self) -> None:
        if self._task is not None:
            return
        self._logger.info("Starting PoA proposer loop", extra={"interval": self._config.interval_seconds})
        self._ensure_genesis_block()
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._logger.info("Stopping PoA proposer loop")
        self._stop_event.set()
        await self._task
        self._task = None

    async def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            await self._wait_until_next_slot()
            if self._stop_event.is_set():
                break
            try:
                self._propose_block()
            except Exception as exc:  # pragma: no cover - defensive logging
                self._logger.exception("Failed to propose block", extra={"error": str(exc)})

    async def _wait_until_next_slot(self) -> None:
        head = self._fetch_chain_head()
        if head is None:
            return
        now = datetime.utcnow()
        elapsed = (now - head.timestamp).total_seconds()
        sleep_for = max(self._config.interval_seconds - elapsed, 0)
        if sleep_for <= 0:
            return
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=sleep_for)
        except asyncio.TimeoutError:
            return

    def _propose_block(self) -> None:
        # Check internal mempool
        from ..mempool import get_mempool
        if get_mempool().size(self._config.chain_id) == 0:
            return

        with self._session_factory() as session:
            head = session.exec(select(Block).where(Block.chain_id == self._config.chain_id).order_by(Block.height.desc()).limit(1)).first()
            next_height = 0
            parent_hash = "0x00"
            interval_seconds: Optional[float] = None
            if head is not None:
                next_height = head.height + 1
                parent_hash = head.hash
                interval_seconds = (datetime.utcnow() - head.timestamp).total_seconds()

            timestamp = datetime.utcnow()
            block_hash = self._compute_block_hash(next_height, parent_hash, timestamp)

            block = Block(
                chain_id=self._config.chain_id,
                height=next_height,
                hash=block_hash,
                parent_hash=parent_hash,
                proposer=self._config.proposer_id,
                timestamp=timestamp,
                tx_count=0,
                state_root=None,
            )
            session.add(block)
            session.commit()

            metrics_registry.increment("blocks_proposed_total")
            metrics_registry.set_gauge("chain_head_height", float(next_height))
            if interval_seconds is not None and interval_seconds >= 0:
                metrics_registry.observe("block_interval_seconds", interval_seconds)
                metrics_registry.set_gauge("poa_last_block_interval_seconds", float(interval_seconds))

            proposer_suffix = _sanitize_metric_suffix(self._config.proposer_id)
            metrics_registry.increment(f"poa_blocks_proposed_total_{proposer_suffix}")
            if self._last_proposer_id is not None and self._last_proposer_id != self._config.proposer_id:
                metrics_registry.increment("poa_proposer_switches_total")
            self._last_proposer_id = self._config.proposer_id

            self._logger.info(
                "Proposed block",
                extra={
                    "height": block.height,
                    "hash": block.hash,
                    "proposer": block.proposer,
                },
            )
            
            # Broadcast the new block
            gossip_broker.publish(
                "blocks",
                {
                    "height": block.height,
                    "hash": block.hash,
                    "parent_hash": block.parent_hash,
                    "proposer": block.proposer,
                    "timestamp": block.timestamp.isoformat(),
                    "tx_count": block.tx_count,
                    "state_root": block.state_root,
                }
            )

    def _ensure_genesis_block(self) -> None:
        with self._session_factory() as session:
            head = session.exec(select(Block).where(Block.chain_id == self._config.chain_id).order_by(Block.height.desc()).limit(1)).first()
            if head is not None:
                return

            # Use a deterministic genesis timestamp so all nodes agree on the genesis block hash
            timestamp = datetime(2025, 1, 1, 0, 0, 0)
            block_hash = self._compute_block_hash(0, "0x00", timestamp)
            genesis = Block(
                chain_id=self._config.chain_id,
                height=0,
                hash=block_hash,
                parent_hash="0x00",
                proposer="genesis",
                timestamp=timestamp,
                tx_count=0,
                state_root=None,
            )
            session.add(genesis)
            session.commit()
            
            # Broadcast genesis block for initial sync
            gossip_broker.publish(
                "blocks",
                {
                    "height": genesis.height,
                    "hash": genesis.hash,
                    "parent_hash": genesis.parent_hash,
                    "proposer": genesis.proposer,
                    "timestamp": genesis.timestamp.isoformat(),
                    "tx_count": genesis.tx_count,
                    "state_root": genesis.state_root,
                }
            )

    def _fetch_chain_head(self) -> Optional[Block]:
        with self._session_factory() as session:
            return session.exec(select(Block).order_by(Block.height.desc()).limit(1)).first()

    def _compute_block_hash(self, height: int, parent_hash: str, timestamp: datetime) -> str:
        payload = f"{self._config.chain_id}|{height}|{parent_hash}|{timestamp.isoformat()}".encode()
        return "0x" + hashlib.sha256(payload).hexdigest()
