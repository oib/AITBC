from __future__ import annotations

import asyncio
import hashlib
import time
from dataclasses import dataclass
from datetime import datetime
import re
from typing import Callable, ContextManager, Optional

from sqlmodel import Session, select

from ..logger import get_logger
from ..metrics import metrics_registry
from ..models import Block, Transaction
from ..gossip import gossip_broker
from ..mempool import get_mempool


_METRIC_KEY_SANITIZE = re.compile(r"[^0-9a-zA-Z]+")


def _sanitize_metric_suffix(value: str) -> str:
    sanitized = _METRIC_KEY_SANITIZE.sub("_", value).strip("_")
    return sanitized or "unknown"


@dataclass
class ProposerConfig:
    chain_id: str
    proposer_id: str
    interval_seconds: int
    max_block_size_bytes: int = 1_000_000
    max_txs_per_block: int = 500


class CircuitBreaker:
    """Circuit breaker for graceful degradation on repeated failures."""

    def __init__(self, threshold: int = 5, timeout: int = 30) -> None:
        self._threshold = threshold
        self._timeout = timeout
        self._failure_count = 0
        self._last_failure_time: float = 0
        self._state = "closed"  # closed, open, half-open

    @property
    def state(self) -> str:
        if self._state == "open":
            if time.time() - self._last_failure_time >= self._timeout:
                self._state = "half-open"
        return self._state

    def record_success(self) -> None:
        self._failure_count = 0
        self._state = "closed"
        metrics_registry.set_gauge("circuit_breaker_state", 0.0)

    def record_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.time()
        if self._failure_count >= self._threshold:
            self._state = "open"
            metrics_registry.set_gauge("circuit_breaker_state", 1.0)
            metrics_registry.increment("circuit_breaker_trips_total")

    def allow_request(self) -> bool:
        state = self.state
        if state == "closed":
            return True
        if state == "half-open":
            return True
        return False


class PoAProposer:
    def __init__(
        self,
        *,
        config: ProposerConfig,
        session_factory: Callable[[], ContextManager[Session]],
        circuit_breaker: Optional[CircuitBreaker] = None,
    ) -> None:
        self._config = config
        self._session_factory = session_factory
        self._logger = get_logger(__name__)
        self._stop_event = asyncio.Event()
        self._task: Optional[asyncio.Task[None]] = None
        self._last_proposer_id: Optional[str] = None
        self._circuit_breaker = circuit_breaker or CircuitBreaker()

    async def start(self) -> None:
        if self._task is not None:
            return
        self._logger.info("Starting PoA proposer loop", extra={"interval": self._config.interval_seconds})
        self._ensure_genesis_block()
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_loop(), name="poa-proposer-loop")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._logger.info("Stopping PoA proposer loop")
        self._stop_event.set()
        await self._task
        self._task = None

    @property
    def is_healthy(self) -> bool:
        return self._circuit_breaker.state != "open"

    async def _run_loop(self) -> None:
        metrics_registry.set_gauge("poa_proposer_running", 1.0)
        try:
            while not self._stop_event.is_set():
                await self._wait_until_next_slot()
                if self._stop_event.is_set():
                    break
                if not self._circuit_breaker.allow_request():
                    self._logger.warning("Circuit breaker open, skipping block proposal")
                    metrics_registry.increment("blocks_skipped_circuit_breaker_total")
                    continue
                try:
                    self._propose_block()
                    self._circuit_breaker.record_success()
                except Exception as exc:
                    self._circuit_breaker.record_failure()
                    self._logger.exception("Failed to propose block", extra={"error": str(exc)})
                    metrics_registry.increment("poa_propose_errors_total")
        finally:
            metrics_registry.set_gauge("poa_proposer_running", 0.0)
            self._logger.info("PoA proposer loop exited")

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
        start_time = time.perf_counter()
        with self._session_factory() as session:
            head = session.exec(select(Block).order_by(Block.height.desc()).limit(1)).first()
            next_height = 0
            parent_hash = "0x00"
            interval_seconds: Optional[float] = None
            if head is not None:
                next_height = head.height + 1
                parent_hash = head.hash
                interval_seconds = (datetime.utcnow() - head.timestamp).total_seconds()

            # Drain transactions from mempool
            mempool = get_mempool()
            pending_txs = mempool.drain(
                max_count=self._config.max_txs_per_block,
                max_bytes=self._config.max_block_size_bytes,
            )

            timestamp = datetime.utcnow()
            block_hash = self._compute_block_hash(next_height, parent_hash, timestamp)

            block = Block(
                height=next_height,
                hash=block_hash,
                parent_hash=parent_hash,
                proposer=self._config.proposer_id,
                timestamp=timestamp,
                tx_count=len(pending_txs),
                state_root=None,
            )
            session.add(block)

            # Batch-insert transactions into the block
            total_fees = 0
            for ptx in pending_txs:
                tx = Transaction(
                    tx_hash=ptx.tx_hash,
                    block_height=next_height,
                    sender=ptx.content.get("sender", ""),
                    recipient=ptx.content.get("recipient", ptx.content.get("payload", {}).get("recipient", "")),
                    payload=ptx.content,
                )
                session.add(tx)
                total_fees += ptx.fee

            session.commit()

            # Metrics
            build_duration = time.perf_counter() - start_time
            metrics_registry.increment("blocks_proposed_total")
            metrics_registry.set_gauge("chain_head_height", float(next_height))
            metrics_registry.set_gauge("last_block_tx_count", float(len(pending_txs)))
            metrics_registry.set_gauge("last_block_total_fees", float(total_fees))
            metrics_registry.observe("block_build_duration_seconds", build_duration)
            if interval_seconds is not None and interval_seconds >= 0:
                metrics_registry.observe("block_interval_seconds", interval_seconds)
                metrics_registry.set_gauge("poa_last_block_interval_seconds", float(interval_seconds))

            proposer_suffix = _sanitize_metric_suffix(self._config.proposer_id)
            metrics_registry.increment(f"poa_blocks_proposed_total_{proposer_suffix}")
            if self._last_proposer_id is not None and self._last_proposer_id != self._config.proposer_id:
                metrics_registry.increment("poa_proposer_rotations_total")
            self._last_proposer_id = self._config.proposer_id

            asyncio.create_task(
                gossip_broker.publish(
                    "blocks",
                    {
                        "height": block.height,
                        "hash": block.hash,
                        "parent_hash": block.parent_hash,
                        "timestamp": block.timestamp.isoformat(),
                        "tx_count": block.tx_count,
                    },
                )
            )

            self._logger.info(
                "Proposed block",
                extra={
                    "height": next_height,
                    "hash": block_hash,
                    "parent_hash": parent_hash,
                    "timestamp": timestamp.isoformat(),
                    "tx_count": len(pending_txs),
                    "total_fees": total_fees,
                    "build_ms": round(build_duration * 1000, 2),
                },
            )

    def _ensure_genesis_block(self) -> None:
        with self._session_factory() as session:
            head = session.exec(select(Block).order_by(Block.height.desc()).limit(1)).first()
            if head is not None:
                return

            timestamp = datetime.utcnow()
            genesis_hash = self._compute_block_hash(0, "0x00", timestamp)
            genesis = Block(
                height=0,
                hash=genesis_hash,
                parent_hash="0x00",
                proposer=self._config.proposer_id,
                timestamp=timestamp,
                tx_count=0,
                state_root=None,
            )
            session.add(genesis)
            session.commit()
            asyncio.create_task(
                gossip_broker.publish(
                    "blocks",
                    {
                        "height": genesis.height,
                        "hash": genesis.hash,
                        "parent_hash": genesis.parent_hash,
                        "timestamp": genesis.timestamp.isoformat(),
                        "tx_count": genesis.tx_count,
                    },
                )
            )

            self._logger.info("Created genesis block", extra={"hash": genesis_hash})

    def _fetch_chain_head(self) -> Optional[Block]:
        for attempt in range(3):
            try:
                with self._session_factory() as session:
                    return session.exec(select(Block).order_by(Block.height.desc()).limit(1)).first()
            except Exception as exc:
                if attempt == 2:
                    self._logger.error("Failed to fetch chain head after 3 attempts", extra={"error": str(exc)})
                    metrics_registry.increment("poa_db_errors_total")
                    return None
                time.sleep(0.1 * (attempt + 1))

    def _compute_block_hash(self, height: int, parent_hash: str, timestamp: datetime) -> str:
        payload = f"{self._config.chain_id}|{height}|{parent_hash}|{timestamp.isoformat()}".encode()
        return "0x" + hashlib.sha256(payload).hexdigest()
