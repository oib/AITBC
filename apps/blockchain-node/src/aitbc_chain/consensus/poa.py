from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, ContextManager, Optional

from sqlmodel import Session, select

from ..logging import get_logger
from ..metrics import metrics_registry
from ..models import Block


@dataclass
class ProposerConfig:
    chain_id: str
    proposer_id: str
    interval_seconds: int


class PoAProposer:
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
        with self._session_factory() as session:
            head = session.exec(select(Block).order_by(Block.height.desc()).limit(1)).first()
            next_height = 0
            parent_hash = "0x00"
            if head is not None:
                next_height = head.height + 1
                parent_hash = head.hash

            timestamp = datetime.utcnow()
            block_hash = self._compute_block_hash(next_height, parent_hash, timestamp)

            block = Block(
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

            self._logger.info(
                "Proposed block",
                extra={
                    "height": next_height,
                    "hash": block_hash,
                    "parent_hash": parent_hash,
                    "timestamp": timestamp.isoformat(),
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
            self._logger.info("Created genesis block", extra={"hash": genesis_hash})

    def _fetch_chain_head(self) -> Optional[Block]:
        with self._session_factory() as session:
            return session.exec(select(Block).order_by(Block.height.desc()).limit(1)).first()

    def _compute_block_hash(self, height: int, parent_hash: str, timestamp: datetime) -> str:
        payload = f"{self._config.chain_id}|{height}|{parent_hash}|{timestamp.isoformat()}".encode()
        return "0x" + hashlib.sha256(payload).hexdigest()
