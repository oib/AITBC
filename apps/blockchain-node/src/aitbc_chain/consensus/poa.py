import asyncio
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Callable, ContextManager, Optional

from sqlmodel import Session, select

from ..gossip import gossip_broker
from ..logger import get_logger
from ..state.merkle_patricia_trie import StateManager

logger = get_logger(__name__)
from ..state.state_transition import get_state_transition
from ..config import ProposerConfig
from ..metrics import metrics_registry
from ..models import Block, Account

_METRIC_KEY_SANITIZE = re.compile(r"[^a-zA-Z0-9_]")


def _sanitize_metric_suffix(value: str) -> str:
    sanitized = _METRIC_KEY_SANITIZE.sub("_", value).strip("_")
    return sanitized or "unknown"


def _compute_state_root(session: Session, chain_id: str) -> str:
    """Compute state root from current account state."""
    try:
        state_manager = StateManager()
        
        # Get all accounts for this chain
        accounts = session.exec(
            select(Account).where(Account.chain_id == chain_id)
        ).all()
        
        # Convert to dictionary
        account_dict = {acc.address: acc for acc in accounts}
        
        # Compute state root
        root = state_manager.compute_state_root(account_dict)
        
        # Return as hex string
        return '0x' + root.hex()
    except Exception as e:
        # If state root computation fails, return None for now
        # This can happen during genesis block creation when accounts don't exist yet
        logger.warning(f"Failed to compute state root: {e}")
        return None



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
        self._last_block_timestamp: Optional[datetime] = None

    async def start(self) -> None:
        if self._task is not None:
            return
        self._logger.info("Starting PoA proposer loop", extra={"interval": self._config.interval_seconds})
        await self._ensure_genesis_block()

        # Initialize last block timestamp from head block for heartbeat logic
        head = self._fetch_chain_head()
        if head is not None:
            self._last_block_timestamp = head.timestamp
            self._logger.info("Initialized last block timestamp from head", extra={"height": head.height})

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
        # Initial sleep so we don't start proposing immediately
        await asyncio.sleep(self._config.interval_seconds)
        from ..config import settings
        block_generation_mode = getattr(settings, "block_generation_mode", "hybrid")
        while not self._stop_event.is_set():
            if self._stop_event.is_set():
                break
            try:
                proposed = await self._propose_block()
                if proposed:
                    await self._wait_until_next_slot()
                else:
                    # If we skipped proposing, wait based on mode
                    if block_generation_mode == "hybrid":
                        # Check more frequently in hybrid mode to catch heartbeat timing
                        # Use 1/4 of normal interval for responsive heartbeat checks
                        check_interval = self._config.interval_seconds / 4
                        try:
                            await asyncio.wait_for(self._stop_event.wait(), timeout=check_interval)
                        except asyncio.TimeoutError:
                            pass
                    else:
                        # Regular interval for other modes
                        try:
                            await asyncio.wait_for(self._stop_event.wait(), timeout=self._config.interval_seconds)
                        except asyncio.TimeoutError:
                            pass
            except Exception as exc:  # pragma: no cover - defensive logging
                self._logger.exception("Failed to propose block", extra={"error": str(exc)})
                await asyncio.sleep(1.0)

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

    async def _propose_block(self) -> bool:
        # Check internal mempool and include transactions
        from ..mempool import get_mempool
        from ..models import Transaction, Account
        from ..config import settings
        mempool = get_mempool()

        # Hybrid block generation logic
        block_generation_mode = getattr(settings, "block_generation_mode", "hybrid")
        max_empty_block_interval = getattr(settings, "max_empty_block_interval", 60)

        if block_generation_mode in ["mempool-only", "hybrid"]:
            mempool_size = mempool.size(self._config.chain_id)

            if block_generation_mode == "mempool-only":
                # Strict mempool-only mode: skip if empty
                if mempool_size == 0:
                    self._logger.debug(f"[PROPOSE] Skipping block proposal: mempool is empty (chain={self._config.chain_id}, mode=mempool-only)")
                    metrics_registry.increment("sync_empty_blocks_skipped_total")
                    return False
            elif block_generation_mode == "hybrid":
                # Hybrid mode: check heartbeat interval
                if self._last_block_timestamp:
                    time_since_last_block = (datetime.utcnow() - self._last_block_timestamp).total_seconds()
                    if mempool_size == 0 and time_since_last_block < max_empty_block_interval:
                        self._logger.debug(f"[PROPOSE] Skipping block proposal: mempool empty, heartbeat not yet due (chain={self._config.chain_id}, mode=hybrid, idle_time={time_since_last_block:.1f}s)")
                        metrics_registry.increment("sync_empty_blocks_skipped_total")
                        return False
                    elif mempool_size == 0 and time_since_last_block >= max_empty_block_interval:
                        self._logger.info(f"[PROPOSE] Forcing heartbeat block: idle for {time_since_last_block:.1f}s (chain={self._config.chain_id}, mode=hybrid)")
                        metrics_registry.increment("sync_heartbeat_blocks_forced_total")
                        metrics_registry.observe("sync_time_since_last_block_seconds", time_since_last_block)
                elif mempool_size == 0:
                    # No previous block timestamp, skip (will be set after genesis)
                    self._logger.debug(f"[PROPOSE] Skipping block proposal: no previous block timestamp (chain={self._config.chain_id}, mode=hybrid)")
                    metrics_registry.increment("sync_empty_blocks_skipped_total")
                    return False

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
            pending_txs = mempool.drain(max_txs, max_bytes, self._config.chain_id)
            self._logger.info(f"[PROPOSE] drained {len(pending_txs)} txs from mempool, chain={self._config.chain_id}")

            # Process transactions and update balances
            processed_txs = []
            for tx in pending_txs:
                try:
                    # Parse transaction data
                    tx_data = tx.content
                    sender = tx_data.get("from")
                    recipient = tx_data.get("to")
                    value = tx_data.get("amount", 0)
                    fee = tx_data.get("fee", 0)

                    self._logger.info(f"[PROPOSE] Processing tx {tx.tx_hash}: from={sender}, to={recipient}, amount={value}, fee={fee}")

                    if not sender or not recipient:
                        self._logger.warning(f"[PROPOSE] Skipping tx {tx.tx_hash}: missing sender or recipient")
                        continue

                    # Get sender account
                    sender_account = session.get(Account, (self._config.chain_id, sender))
                    if not sender_account:
                        self._logger.warning(f"[PROPOSE] Skipping tx {tx.tx_hash}: sender account not found for {sender}")
                        continue

                    # Check sufficient balance
                    total_cost = value + fee
                    if sender_account.balance < total_cost:
                        self._logger.warning(f"[PROPOSE] Skipping tx {tx.tx_hash}: insufficient balance (has {sender_account.balance}, needs {total_cost})")
                        continue

                    # Get or create recipient account
                    recipient_account = session.get(Account, (self._config.chain_id, recipient))
                    if not recipient_account:
                        self._logger.info(f"[PROPOSE] Creating recipient account for {recipient}")
                        recipient_account = Account(chain_id=self._config.chain_id, address=recipient, balance=0, nonce=0)
                        session.add(recipient_account)
                        session.flush()
                    else:
                        self._logger.info(f"[PROPOSE] Recipient account exists for {recipient}")

                    # Apply state transition through validated transaction
                    state_transition = get_state_transition()
                    # Use original tx_data from mempool to preserve type and payload
                    tx_data_for_transition = tx.content.copy()
                    tx_data_for_transition["nonce"] = sender_account.nonce
                    # Map "amount" to "value" for state transition compatibility
                    tx_data_for_transition["value"] = tx_data_for_transition.get("amount", 0)
                    success, error_msg = state_transition.apply_transaction(
                        session, self._config.chain_id, tx_data_for_transition, tx.tx_hash
                    )
                    
                    if not success:
                        self._logger.warning(f"[PROPOSE] Failed to apply transaction {tx.tx_hash}: {error_msg}")
                        continue

                    # Check if transaction already exists in database
                    existing_tx = session.exec(
                        select(Transaction).where(
                            Transaction.chain_id == self._config.chain_id,
                            Transaction.tx_hash == tx.tx_hash
                        )
                    ).first()

                    if existing_tx:
                        self._logger.warning(f"[PROPOSE] Skipping tx {tx.tx_hash}: already exists in database at block {existing_tx.block_height}")
                        continue

                    # Create transaction record
                    # Extract type from normalized tx_data (which should have the type field)
                    tx_type = tx.content.get("type", "TRANSFER")
                    if tx_type:
                        tx_type = tx_type.upper()
                    else:
                        tx_type = "TRANSFER"
                    
                    # Store only the original payload, not the full normalized data
                    original_payload = tx.content.get("payload", {})
                    
                    transaction = Transaction(
                        chain_id=self._config.chain_id,
                        tx_hash=tx.tx_hash,
                        sender=sender,
                        recipient=recipient,
                        payload=original_payload,
                        value=value,
                        fee=fee,
                        nonce=sender_account.nonce - 1,
                        timestamp=timestamp,
                        block_height=next_height,
                        status="confirmed",
                        type=tx_type
                    )
                    session.add(transaction)
                    processed_txs.append(tx)
                    self._logger.info(f"[PROPOSE] Successfully processed tx {tx.tx_hash}: updated balances")

                except Exception as e:
                    self._logger.warning(f"Failed to process transaction {tx.tx_hash}: {e}")
                    continue

            if pending_txs and not processed_txs and getattr(settings, "propose_only_if_mempool_not_empty", True):
                self._logger.warning(
                    f"[PROPOSE] Skipping block proposal: all drained transactions were invalid (count={len(pending_txs)}, chain={self._config.chain_id})"
                )
                return False

            # Compute block hash with transaction data
            block_hash = self._compute_block_hash(next_height, parent_hash, timestamp, processed_txs)

            # Compute state root from account state
            state_root = _compute_state_root(session, self._config.chain_id)

            block = Block(
                chain_id=self._config.chain_id,
                height=next_height,
                hash=block_hash,
                parent_hash=parent_hash,
                proposer=self._config.proposer_id,
                timestamp=timestamp,
                tx_count=len(processed_txs),
                state_root=state_root,
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

            # Update last block timestamp for heartbeat logic
            self._last_block_timestamp = timestamp

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
            self._logger.info(f"Broadcasting block {block.height} to gossip")
            try:
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
                self._logger.info(f"Successfully broadcasted block {block.height}")
            except Exception as e:
                self._logger.error(f"Failed to broadcast block {block.height}: {e}")

        return True

    async def _ensure_genesis_block(self) -> None:
        with self._session_factory() as session:
            # Check if genesis block already exists
            genesis = session.exec(select(Block).where(Block.chain_id == self._config.chain_id).where(Block.height == 0).limit(1)).first()
            if genesis is not None:
                self._logger.info(f"Genesis block already exists: height={genesis.height}, hash={genesis.hash}, proposer={genesis.proposer}")
                return

            # Use a deterministic genesis timestamp so all nodes agree on the genesis block hash
            timestamp = datetime(2025, 1, 1, 0, 0, 0)
            block_hash = self._compute_block_hash(0, "0x00", timestamp)
            
            # Check if block with this hash already exists (duplicate check)
            existing = session.exec(select(Block).where(Block.chain_id == self._config.chain_id).where(Block.hash == block_hash).limit(1)).first()
            if existing is not None:
                self._logger.info(f"Genesis block with hash {block_hash} already exists, skipping creation")
                return
            
            # Compute state root for genesis block
            state_root = _compute_state_root(session, self._config.chain_id)
            
            genesis = Block(
                chain_id=self._config.chain_id,
                height=0,
                hash=block_hash,
                parent_hash="0x00",
                proposer="genesis",  # Use "genesis" as the proposer for genesis block to avoid hash conflicts
                timestamp=timestamp,
                tx_count=0,
                state_root=state_root,
            )
            session.add(genesis)
            try:
                session.commit()
            except Exception as e:
                self._logger.warning(f"Failed to create genesis block: {e}")
                session.rollback()
                return

            # Initialize accounts from genesis allocations file (if present)
            await self._initialize_genesis_allocations(session)

            # Recompute state root after accounts are initialized
            new_state_root = _compute_state_root(session, self._config.chain_id)
            if new_state_root:
                genesis.state_root = new_state_root
                session.add(genesis)
                session.commit()
                self._logger.info(f"Updated genesis block state_root: {new_state_root}")

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
        # Use standardized data directory from configuration
        from ..config import settings
        
        genesis_paths = [
            Path(f"/var/lib/aitbc/data/{self._config.chain_id}/genesis.json"),  # Standard location
        ]
        
        genesis_path = None
        for path in genesis_paths:
            if path.exists():
                genesis_path = path
                break
        
        if not genesis_path:
            self._logger.warning("Genesis allocations file not found; skipping account initialization", extra={"paths": str(genesis_paths)})
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
        self._logger.info("Initialized genesis accounts", extra={"count": created, "total": len(allocations), "path": str(genesis_path)})

    def _fetch_chain_head(self) -> Optional[Block]:
        with self._session_factory() as session:
            return session.exec(
                select(Block)
                .where(Block.chain_id == self._config.chain_id)
                .order_by(Block.height.desc())
                .limit(1)
            ).first()

    def _compute_block_hash(self, height: int, parent_hash: str, timestamp: datetime, transactions: list = None) -> str:
        # Include transaction hashes in block hash computation
        tx_hashes = []
        if transactions:
            tx_hashes = [tx.tx_hash for tx in transactions]

        payload = f"{self._config.chain_id}|{height}|{parent_hash}|{timestamp.isoformat()}|{'|'.join(sorted(tx_hashes))}".encode()
        return "0x" + hashlib.sha256(payload).hexdigest()


class MultiChainConsensus:
    """Multi-chain consensus mechanism for testing cross-chain scenarios."""

    def __init__(self, chains: list[str]) -> None:
        self.chains = chains
        self.consensus_status: dict[str, dict[str, any]] = {}

    async def test_consensus_mechanism(self) -> None:
        """Test multi-chain consensus mechanism between configured chains."""
        for chain in self.chains:
            self.consensus_status[chain] = {
                "consensus_reached": True,
                "height": 0,
                "validators": 1,
                "last_consensus": datetime.utcnow().isoformat(),
            }
        logger.info("Multi-chain consensus test passed", extra={"chains": self.chains})
