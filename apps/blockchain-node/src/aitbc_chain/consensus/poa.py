import asyncio
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Callable, ContextManager, Optional

from sqlmodel import Session, select

from ..logger import get_logger
from ..metrics import metrics_registry
from ..config import ProposerConfig
from ..models import Block, Account
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
        await self._ensure_genesis_block()
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
                await self._propose_block()
            except Exception as exc:  # pragma: no cover - defensive logging
                self._logger.exception("Failed to propose block", extra={"error": str(exc)})

    async def _wait_until_next_slot(self) -> None:
        head = self._fetch_chain_head()
        if head is None:
            return
        now = datetime.utcnow()
        elapsed = (now - head.timestamp).total_seconds()
        sleep_for = max(self._config.interval_seconds - elapsed, 0.1)
        if sleep_for <= 0:
            sleep_for = 0.1
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=sleep_for)
        except asyncio.TimeoutError:
            return

    async def _propose_block(self) -> None:
        # Check internal mempool and include transactions
        from ..mempool import get_mempool
        from ..models import Transaction, Account
        mempool = get_mempool()
        
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
            
            # Pull transactions from mempool
            max_txs = self._config.max_txs_per_block
            max_bytes = self._config.max_block_size_bytes
            pending_txs = mempool.drain(max_txs, max_bytes, 'ait-mainnet')
            self._logger.info(f"[PROPOSE] drained {len(pending_txs)} txs from mempool, chain={self._config.chain_id}")

            # Process transactions and update balances
            processed_txs = []
            for tx in pending_txs:
                try:
                    # Parse transaction data
                    tx_data = tx.content
                    sender = tx_data.get("sender")
                    recipient = tx_data.get("payload", {}).get("to")
                    value = tx_data.get("payload", {}).get("value", 0)
                    fee = tx_data.get("fee", 0)
                    
                    if not sender or not recipient:
                        continue
                    
                    # Get sender account
                    sender_account = session.get(Account, (self._config.chain_id, sender))
                    if not sender_account:
                        continue
                    
                    # Check sufficient balance
                    total_cost = value + fee
                    if sender_account.balance < total_cost:
                        continue
                    
                    # Get or create recipient account
                    recipient_account = session.get(Account, (self._config.chain_id, recipient))
                    if not recipient_account:
                        recipient_account = Account(chain_id=self._config.chain_id, address=recipient, balance=0, nonce=0)
                        session.add(recipient_account)
                        session.flush()
                    
                    # Update balances
                    sender_account.balance -= total_cost
                    sender_account.nonce += 1
                    recipient_account.balance += value
                    
                    # Create transaction record
                    transaction = Transaction(
                        chain_id=self._config.chain_id,
                        tx_hash=tx.tx_hash,
                        sender=sender,
                        recipient=recipient,
                        payload=tx_data,
                        value=value,
                        fee=fee,
                        nonce=sender_account.nonce - 1,
                        timestamp=timestamp,
                        block_height=next_height,
                        status="confirmed"
                    )
                    session.add(transaction)
                    processed_txs.append(tx)
                    
                except Exception as e:
                    self._logger.warning(f"Failed to process transaction {tx.tx_hash}: {e}")
                    continue
            
            # Compute block hash with transaction data
            block_hash = self._compute_block_hash(next_height, parent_hash, timestamp, processed_txs)

            block = Block(
                chain_id=self._config.chain_id,
                height=next_height,
                hash=block_hash,
                parent_hash=parent_hash,
                proposer=self._config.proposer_id,
                timestamp=timestamp,
                tx_count=len(processed_txs),
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
            tx_list = [tx.content for tx in processed_txs] if processed_txs else []
            await gossip_broker.publish(
                "blocks",
                {
                    "chain_id": self._config.chain_id,
                    "height": block.height,
                    "hash": block.hash,
                    "parent_hash": block.parent_hash,
                    "proposer": block.proposer,
                    "timestamp": block.timestamp.isoformat(),
                    "tx_count": block.tx_count,
                    "state_root": block.state_root,
                    "transactions": tx_list,
                },
            )

    async def _ensure_genesis_block(self) -> None:
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
                proposer=self._config.proposer_id,  # Use configured proposer as genesis proposer
                timestamp=timestamp,
                tx_count=0,
                state_root=None,
            )
            session.add(genesis)
            session.commit()

            # Initialize accounts from genesis allocations file (if present)
            await self._initialize_genesis_allocations(session)

            # Broadcast genesis block for initial sync
            await gossip_broker.publish(
                "blocks",
                {
                    "chain_id": self._config.chain_id,
                    "height": genesis.height,
                    "hash": genesis.hash,
                    "parent_hash": genesis.parent_hash,
                    "proposer": genesis.proposer,
                    "timestamp": genesis.timestamp.isoformat(),
                    "tx_count": genesis.tx_count,
                    "state_root": genesis.state_root,
                }
            )

    async def _initialize_genesis_allocations(self, session: Session) -> None:
        """Create Account entries from the genesis allocations file."""
        # Look for genesis file relative to project root: data/{chain_id}/genesis.json
        # Alternatively, use a path from config (future improvement)
        genesis_path = Path(f"./data/{self._config.chain_id}/genesis.json")
        if not genesis_path.exists():
            self._logger.warning("Genesis allocations file not found; skipping account initialization", extra={"path": str(genesis_path)})
            return

        with open(genesis_path) as f:
            genesis_data = json.load(f)

        allocations = genesis_data.get("allocations", [])
        created = 0
        for alloc in allocations:
            addr = alloc["address"]
            balance = int(alloc["balance"])
            nonce = int(alloc.get("nonce", 0))
            # Check if account already exists (idempotent)
            acct = session.get(Account, (self._config.chain_id, addr))
            if acct is None:
                acct = Account(chain_id=self._config.chain_id, address=addr, balance=balance, nonce=nonce)
                session.add(acct)
                created += 1
        session.commit()
        self._logger.info("Initialized genesis accounts", extra={"count": created, "total": len(allocations)})

    def _fetch_chain_head(self) -> Optional[Block]:
        with self._session_factory() as session:
            return session.exec(select(Block).order_by(Block.height.desc()).limit(1)).first()

    def _compute_block_hash(self, height: int, parent_hash: str, timestamp: datetime, transactions: list = None) -> str:
        # Include transaction hashes in block hash computation
        tx_hashes = []
        if transactions:
            tx_hashes = [tx.tx_hash for tx in transactions]
        
        payload = f"{self._config.chain_id}|{height}|{parent_hash}|{timestamp.isoformat()}|{'|'.join(sorted(tx_hashes))}".encode()
        return "0x" + hashlib.sha256(payload).hexdigest()
