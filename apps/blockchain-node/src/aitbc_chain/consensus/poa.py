import asyncio
import hashlib
import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import ContextManager

from sqlmodel import Session, select

from ..gossip import gossip_broker
from ..lease_tracker import lease_tracker
from ..logger import get_logger
from ..state.merkle_patricia_trie import StateManager

logger = get_logger(__name__)
from ..config import ProposerConfig
from ..metrics import metrics_registry
from ..models import Account, Block
from ..state.state_transition import get_state_transition

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
        self._task: asyncio.Task[None] | None = None
        self._last_proposer_id: str | None = None
        self._last_block_timestamp: datetime | None = None

    def _fetch_chain_head(self) -> Block | None:
        """Fetch the current chain head block from the database."""
        with self._session_factory() as session:
            return session.exec(
                select(Block).where(Block.chain_id == self._config.chain_id).order_by(Block.height.desc()).limit(1)
            ).first()

    async def start(self) -> None:
        if self._task is not None:
            return
        # Skip proposer loop if block production is disabled
        from ..config import settings
        if not getattr(settings, "enable_block_production", True):
            self._logger.info("Block production disabled, skipping PoA proposer loop")
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
                        except TimeoutError:
                            pass
                    else:
                        # Regular interval for other modes
                        try:
                            await asyncio.wait_for(self._stop_event.wait(), timeout=self._config.interval_seconds)
                        except TimeoutError:
                            pass
            except Exception as exc:  # pragma: no cover - defensive logging
                self._logger.exception("Failed to propose block", extra={"error": str(exc)})
                await asyncio.sleep(1.0)

    async def _wait_until_next_slot(self) -> None:
        head = self._fetch_chain_head()
        if head is None:
            return
        now = datetime.now(UTC)
        # Ensure head.timestamp is timezone-aware
        head_timestamp = head.timestamp if head.timestamp.tzinfo is not None else head.timestamp.replace(tzinfo=UTC)
        elapsed = (now - head_timestamp).total_seconds()
        sleep_for = max(self._config.interval_seconds - elapsed, 0.1)
        if sleep_for <= 0:
            sleep_for = 0.1
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=sleep_for)
        except TimeoutError:
            return

    async def _propose_block(self) -> bool:
        # Check internal mempool and include transactions
        from ..config import settings
        from ..mempool import get_mempool
        from ..models import Account, Transaction
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
                    # Ensure last_block_timestamp is timezone-aware
                    last_timestamp = self._last_block_timestamp if self._last_block_timestamp.tzinfo is not None else self._last_block_timestamp.replace(tzinfo=UTC)
                    time_since_last_block = (datetime.now(UTC) - last_timestamp).total_seconds()
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
            interval_seconds: float | None = None
            if head is not None:
                next_height = head.height + 1
                parent_hash = head.hash
                # Ensure head.timestamp is timezone-aware
                head_timestamp = head.timestamp if head.timestamp.tzinfo is not None else head.timestamp.replace(tzinfo=UTC)
                interval_seconds = (datetime.now(UTC) - head_timestamp).total_seconds()

            timestamp = datetime.now(UTC)

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

            # Broadcast the new block to subscribers with valid leases
            tx_list = [tx.content for tx in processed_txs] if processed_txs else []
            gossip_topic = f"blocks.{self._config.chain_id}"

            # Check for valid subscribers before publishing
            try:
                subscribers = await lease_tracker.get_valid_subscribers(self._config.chain_id)
                subscriber_count = len(subscribers)
                self._logger.info(f"[BROADCAST] block={block.height}, topic={gossip_topic}, valid_subscribers={subscriber_count}")

                if subscriber_count > 0:
                    # Publish to general gossip topic (for compatibility)
                    await gossip_broker.publish(
                        gossip_topic,
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
                    self._logger.info(f"[BROADCAST SUCCESS] block={block.height}, topic={gossip_topic}, subscribers={subscriber_count}")
                else:
                    self._logger.info(f"[BROADCAST SKIPPED] block={block.height}, no valid subscribers")
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

            # Try RPC bootstrap for genesis block first
            self._logger.info(f"Attempting RPC bootstrap for genesis block for chain {self._config.chain_id}")
            rpc_genesis_data = await self._load_genesis_block_from_rpc()

            if rpc_genesis_data:
                # Use RPC-provided genesis block data
                self._logger.info(f"Using RPC-provided genesis block data for chain {self._config.chain_id}")
                genesis_allocations = rpc_genesis_data.get("allocations", [])
                genesis_hash = rpc_genesis_data.get("genesis_hash")
                genesis_state_root = rpc_genesis_data.get("genesis_state_root")

                if genesis_hash and genesis_state_root:
                    # Create genesis block with RPC-provided data
                    timestamp = datetime.now(UTC)
                    genesis = Block(
                        chain_id=self._config.chain_id,
                        height=0,
                        hash=genesis_hash,
                        parent_hash="0x00",
                        proposer="genesis",
                        timestamp=timestamp,
                        tx_count=0,
                        state_root=genesis_state_root,
                        block_metadata=json.dumps({"allocations": genesis_allocations}) if genesis_allocations else None,
                    )
                    session.add(genesis)
                    try:
                        session.commit()
                        self._logger.info(f"Successfully created genesis block from RPC bootstrap: hash={genesis_hash}, state_root={genesis_state_root}")

                        # Initialize accounts from RPC-provided allocations
                        if genesis_allocations:
                            self._create_accounts_from_allocations(session, genesis_allocations)
                            self._logger.info(f"Initialized {len(genesis_allocations)} accounts from RPC bootstrap")
                        return
                    except Exception as e:
                        self._logger.warning(f"Failed to create genesis block from RPC bootstrap: {e}, falling back to local creation")
                        session.rollback()
                else:
                    self._logger.warning("RPC bootstrap returned incomplete genesis data, falling back to local creation")

            # Fall back to local genesis block creation from genesis.json file
            self._logger.info(f"Loading genesis block from local file for chain {self._config.chain_id}")

            # Load genesis data from file
            local_genesis_data = self._load_genesis_data_from_file()

            if not local_genesis_data:
                self._logger.error(f"Genesis file not found at /var/lib/aitbc/data/{self._config.chain_id}/genesis.json. Cannot create genesis block without genesis.json file.")
                raise RuntimeError(f"Genesis file required but not found for chain {self._config.chain_id}. Please create genesis.json at /var/lib/aitbc/data/{self._config.chain_id}/genesis.json")

            # Extract genesis data from file (support both flat and nested formats)
            block_data = local_genesis_data.get("block", {})
            genesis_hash = local_genesis_data.get("genesis_hash") or block_data.get("hash")
            genesis_timestamp = local_genesis_data.get("timestamp") or block_data.get("timestamp")
            genesis_state_root = local_genesis_data.get("state_root") or block_data.get("state_root")
            genesis_allocations = local_genesis_data.get("allocations", block_data.get("allocations", []))

            if not genesis_hash or not genesis_timestamp or not genesis_state_root:
                self._logger.error("Genesis file missing required fields: genesis_hash, timestamp, or state_root")
                raise RuntimeError(f"Genesis file at /var/lib/aitbc/data/{self._config.chain_id}/genesis.json is missing required fields (genesis_hash, timestamp, state_root)")

            # Parse timestamp from string to datetime
            try:
                if isinstance(genesis_timestamp, str):
                    timestamp = datetime.fromisoformat(genesis_timestamp)
                else:
                    timestamp = genesis_timestamp
            except Exception as e:
                self._logger.error(f"Failed to parse genesis timestamp: {e}")
                raise RuntimeError(f"Invalid timestamp format in genesis file: {e}")

            # Create genesis block using data from genesis.json
            genesis = Block(
                chain_id=self._config.chain_id,
                height=0,
                hash=genesis_hash,
                parent_hash="0x00",
                proposer="genesis",
                timestamp=timestamp,
                tx_count=0,
                state_root=genesis_state_root,
                block_metadata=json.dumps({"allocations": genesis_allocations}) if genesis_allocations else None,
            )
            session.add(genesis)
            try:
                session.commit()
                self._logger.info(f"Successfully created genesis block from genesis.json: hash={genesis_hash}, state_root={genesis_state_root}, timestamp={timestamp}")

                # Initialize accounts from genesis allocations
                if genesis_allocations:
                    self._create_accounts_from_allocations(session, genesis_allocations)
                    self._logger.info(f"Initialized {len(genesis_allocations)} accounts from genesis.json")
            except Exception as e:
                self._logger.error(f"Failed to create genesis block from genesis.json: {e}")
                session.rollback()
                raise

            # Broadcast genesis block for initial sync
            await gossip_broker.publish(
                f"blocks.{self._config.chain_id}",
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
        """Create Account entries from the genesis allocations file or RPC bootstrap."""
        self._logger.info(f"Initializing genesis allocations for chain: {self._config.chain_id}")

        # Try local file first
        local_genesis_data = self._load_genesis_data_from_file()
        if local_genesis_data:
            local_allocations = local_genesis_data.get("allocations", [])
            self._logger.info(f"Using local genesis file for chain {self._config.chain_id}")
            self._create_accounts_from_allocations(session, local_allocations)
            return

        # Try RPC bootstrap
        self._logger.info(f"Local genesis file not found for chain {self._config.chain_id}, attempting RPC bootstrap")
        try:
            rpc_allocations, rpc_genesis_state_root = await self._load_genesis_allocations_from_rpc()
            if rpc_allocations:
                self._logger.info(f"Loaded {len(rpc_allocations)} allocations via RPC bootstrap for chain {self._config.chain_id}")
                self._create_accounts_from_allocations(session, rpc_allocations)

                # Store the RPC genesis state_root for use in genesis block creation
                if rpc_genesis_state_root:
                    self._rpc_genesis_state_root = rpc_genesis_state_root
                    self._logger.info(f"Stored RPC genesis state_root: {rpc_genesis_state_root}")
                else:
                    self._logger.info(f"RPC bootstrap completed successfully for chain {self._config.chain_id}, but no state_root provided")
            else:
                self._logger.warning(f"RPC bootstrap returned no allocations for chain {self._config.chain_id}, skipping account initialization")
        except Exception as e:
            self._logger.warning(f"RPC bootstrap failed for chain {self._config.chain_id}: {e}, skipping account initialization")

    def _load_genesis_data_from_file(self) -> dict:
        """Load complete genesis data from local file."""
        genesis_paths = [
            Path(f"/var/lib/aitbc/data/{self._config.chain_id}/genesis.json"),  # Standard location
        ]

        genesis_path = None
        for path in genesis_paths:
            if path.exists():
                genesis_path = path
                break

        if not genesis_path:
            return {}

        try:
            with open(genesis_path) as f:
                genesis_data = json.load(f)
            return genesis_data
        except Exception as e:
            self._logger.warning(f"Failed to load genesis file: {e}")
            return {}

    def _load_genesis_allocations_for_metadata(self) -> list:
        """Load genesis allocations from file for embedding in genesis block metadata."""
        # Skip loading for metadata if we used RPC bootstrap
        return []

    async def _load_genesis_block_from_rpc(self) -> dict:
        """Load genesis block data from trusted peer via RPC.
        
        Returns:
            Dict with genesis block data (allocations, genesis_hash, genesis_state_root) or None if failed
        """
        import httpx

        # Try multiple trusted peers
        trusted_peers = []
        if self._config.default_peer_rpc_url:
            peer_url = self._config.default_peer_rpc_url
            # Remove http:// prefix if present to avoid double prefix
            if peer_url.startswith("http://"):
                peer_url = peer_url.replace("http://", "")
            peer_url = f"http://{peer_url}"
            trusted_peers.append(peer_url)
        # Don't add localhost as default bootstrap peer - hub nodes should create their own genesis

        self._logger.info(f"Attempting RPC bootstrap for genesis block from peers: {trusted_peers}")

        for peer_url in trusted_peers:
            try:
                self._logger.info(f"Trying to fetch genesis block from {peer_url}")
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.get(
                        f"{peer_url}/rpc/genesis_allocations",
                        params={"chain_id": self._config.chain_id}
                    )
                    response.raise_for_status()
                    data = response.json()
                    self._logger.info(f"RPC response from {peer_url}: {data}")
                    return data
            except Exception as e:
                self._logger.error(f"Failed to fetch genesis block from {peer_url}: {e}")
                continue

        self._logger.error("RPC bootstrap for genesis block failed for all peers")
        return None

    async def _load_genesis_allocations_from_rpc(self) -> tuple[list, str | None]:
        """Load genesis allocations and state_root from trusted peer via RPC.
        
        Returns:
            Tuple of (allocations list, genesis_state_root string or None)
        """
        import httpx

        # Try multiple trusted peers
        trusted_peers = []
        if self._config.default_peer_rpc_url:
            peer_url = self._config.default_peer_rpc_url
            # Remove http:// prefix if present to avoid double prefix
            if peer_url.startswith("http://"):
                peer_url = peer_url.replace("http://", "")
            peer_url = f"http://{peer_url}"
            trusted_peers.append(peer_url)
        # Don't add localhost as default bootstrap peer - hub nodes should create their own genesis

        self._logger.info(f"Attempting RPC bootstrap from peers: {trusted_peers}")

        for peer_url in trusted_peers:
            try:
                self._logger.info(f"Trying to fetch allocations from {peer_url}")
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.get(
                        f"{peer_url}/rpc/genesis_allocations",
                        params={"chain_id": self._config.chain_id}
                    )
                    response.raise_for_status()
                    data = response.json()
                    self._logger.info(f"RPC response from {peer_url}: {data}")
                    allocations = data.get("allocations", [])
                    genesis_state_root = data.get("genesis_state_root")
                    if allocations:
                        self._logger.info(f"Successfully loaded {len(allocations)} allocations from {peer_url}")
                        if genesis_state_root:
                            self._logger.info(f"RPC provided genesis state_root: {genesis_state_root}")
                        return allocations, genesis_state_root
                    else:
                        self._logger.warning(f"RPC returned empty allocations from {peer_url}")
            except Exception as e:
                self._logger.error(f"Failed to fetch allocations from {peer_url}: {e}")
                continue

        self._logger.error("RPC bootstrap failed for all peers")
        return [], None

    def _create_accounts_from_allocations(self, session: Session, allocations: list) -> None:
        """Create Account entries from allocation data."""
        created = 0
        for alloc in allocations:
            addr = alloc["address"]
            balance = int(alloc["balance"])
            nonce = int(alloc.get("nonce", 0))
            # Check if account already exists (idempotent)
            existing = session.exec(
                select(Account).where(Account.chain_id == self._config.chain_id).where(Account.address == addr)
            ).first()
            if existing:
                continue

            account = Account(
                chain_id=self._config.chain_id,
                address=addr,
                balance=balance,
                nonce=nonce,
            )
            session.add(account)
            created += 1

        session.commit()
        self._logger.info(f"Created {created} accounts from genesis allocations")

    def _compute_block_hash(self, height: int, parent_hash: str, timestamp: datetime, transactions: list = None) -> str:
        # Include transaction hashes in block hash computation
        tx_hashes = []
        if transactions:
            tx_hashes = [tx.tx_hash for tx in transactions]

        payload = f"{self._config.chain_id}|{height}|{parent_hash}|{timestamp.isoformat()}|{'|'.join(sorted(tx_hashes))}".encode()
        return "0x" + hashlib.sha256(payload).hexdigest()
