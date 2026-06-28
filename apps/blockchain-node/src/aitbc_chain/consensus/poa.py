import asyncio
import hashlib
import json
import re
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlmodel import Session, select

from aitbc.network import SharedHttpClient
from aitbc.parallel import DependencyGraph, ParallelExecutor

from ..config import ProposerConfig, settings
from ..gossip import gossip_broker
from ..lease_tracker import lease_tracker
from ..logger import get_logger
from ..metrics import metrics_registry
from ..models import Account, Block
from ..models import Transaction
from ..state.pure_state_transition import (
    StateDelta,
    apply_delta_to_map,
    apply_deltas_to_db,
    compute_state_delta,
    extract_read_write_sets,
)
from ..state.state_root_utils import (
    compute_state_root_full as _compute_state_root,
    compute_state_root_incremental as _compute_state_root_incremental,
)
from ..state.state_transition import get_state_transition

logger = get_logger(__name__)

_METRIC_KEY_SANITIZE = re.compile("[^a-zA-Z0-9_]")


def _sanitize_metric_suffix(value: str) -> str:
    sanitized = _METRIC_KEY_SANITIZE.sub("_", value).strip("_")
    return sanitized or "unknown"


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

    def __init__(self, *, config: ProposerConfig, session_factory: Callable[[], AbstractContextManager[Session]]) -> None:
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
                select(Block).where(Block.chain_id == self._config.chain_id).order_by(text("height DESC")).limit(1)
            ).first()

    async def start(self) -> None:
        if self._task is not None:
            return
        from ..config import settings

        if not getattr(settings, "enable_block_production", True):
            self._logger.info("Block production disabled, skipping PoA proposer loop")
            return
        self._logger.info("Starting PoA proposer loop", extra={"interval": self._config.interval_seconds})
        await self._ensure_genesis_block()
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
                elif block_generation_mode == "hybrid":
                    check_interval = self._config.interval_seconds / 4
                    try:
                        await asyncio.wait_for(self._stop_event.wait(), timeout=check_interval)
                    except TimeoutError:
                        pass
                else:
                    try:
                        await asyncio.wait_for(self._stop_event.wait(), timeout=self._config.interval_seconds)
                    except TimeoutError:
                        pass
            except Exception as exc:
                self._logger.exception("Failed to propose block", extra={"error": str(exc)})
                await asyncio.sleep(1.0)

    async def _wait_until_next_slot(self) -> None:
        head = self._fetch_chain_head()
        if head is None:
            return
        now = datetime.now(UTC)
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
        from ..config import settings
        from ..mempool import get_mempool as get_mempool_instance
        from ..models import Account, Transaction

        mempool = get_mempool_instance()
        block_generation_mode = getattr(settings, "block_generation_mode", "hybrid")
        max_empty_block_interval = getattr(settings, "max_empty_block_interval", 60)
        if block_generation_mode in ["mempool-only", "hybrid"]:
            mempool_size = mempool.size(self._config.chain_id)
            if block_generation_mode == "mempool-only":
                if mempool_size == 0:
                    self._logger.debug(
                        "[PROPOSE] Skipping block proposal: mempool is empty (chain=%s, mode=mempool-only)",
                        self._config.chain_id,
                    )
                    metrics_registry.increment("sync_empty_blocks_skipped_total")
                    return False
            elif block_generation_mode == "hybrid":
                if self._last_block_timestamp:
                    last_timestamp = (
                        self._last_block_timestamp
                        if self._last_block_timestamp.tzinfo is not None
                        else self._last_block_timestamp.replace(tzinfo=UTC)
                    )
                    time_since_last_block = (datetime.now(UTC) - last_timestamp).total_seconds()
                    if mempool_size == 0 and time_since_last_block < max_empty_block_interval:
                        self._logger.debug(
                            "[PROPOSE] Skipping block proposal: mempool empty, heartbeat not yet due (chain=%s, mode=hybrid, idle_time=%ss)",
                            self._config.chain_id,
                            time_since_last_block,
                        )
                        metrics_registry.increment("sync_empty_blocks_skipped_total")
                        return False
                    elif mempool_size == 0 and time_since_last_block >= max_empty_block_interval:
                        self._logger.info(
                            "[PROPOSE] Forcing heartbeat block: idle for %ss (chain=%s, mode=hybrid)",
                            time_since_last_block,
                            self._config.chain_id,
                        )
                        metrics_registry.increment("sync_heartbeat_blocks_forced_total")
                        metrics_registry.observe("sync_time_since_last_block_seconds", time_since_last_block)
                elif mempool_size == 0:
                    self._logger.debug(
                        "[PROPOSE] Skipping block proposal: no previous block timestamp (chain=%s, mode=hybrid)",
                        self._config.chain_id,
                    )
                    metrics_registry.increment("sync_empty_blocks_skipped_total")
                    return False
        with self._session_factory() as session:
            head = session.exec(
                select(Block).where(Block.chain_id == self._config.chain_id).order_by(text("height DESC")).limit(1)
            ).first()
            next_height = 0
            parent_hash = "0x00"
            interval_seconds: float | None = None
            if head is not None:
                next_height = head.height + 1
                parent_hash = head.hash
                head_timestamp = head.timestamp if head.timestamp.tzinfo is not None else head.timestamp.replace(tzinfo=UTC)
                interval_seconds = (datetime.now(UTC) - head_timestamp).total_seconds()
            timestamp = datetime.now(UTC)
            max_txs = self._config.max_txs_per_block
            max_bytes = self._config.max_block_size_bytes
            pending_txs = mempool.drain(max_txs, max_bytes, self._config.chain_id)
            self._logger.info("[PROPOSE] drained %s txs from mempool, chain=%s", len(pending_txs), self._config.chain_id)
            # Batch-fetch all unique sender and recipient accounts in one query
            # (eliminates the per-tx session.get() round-trips).
            unique_addresses: set[str] = set()
            for tx in pending_txs:
                tx_data = tx.content
                sender = tx_data.get("from")
                recipient = tx_data.get("to")
                if sender:
                    unique_addresses.add(sender)
                if recipient:
                    unique_addresses.add(recipient)
            account_map: dict[str, Account] = {}
            if unique_addresses:
                existing_accounts = session.exec(
                    select(Account).where(
                        Account.chain_id == self._config.chain_id,
                        Account.address.in_(unique_addresses),
                    )
                ).all()
                account_map = {acc.address: acc for acc in existing_accounts}
            # Batch-fetch duplicate tx hashes in one query (eliminates the
            # per-tx duplicate-check DB round-trip).
            existing_tx_map: dict[str, int] = {}
            if pending_txs:
                existing_tx_rows = session.execute(
                    select(Transaction.tx_hash, Transaction.block_height).where(
                        Transaction.chain_id == self._config.chain_id,
                        Transaction.tx_hash.in_([tx.tx_hash for tx in pending_txs]),
                    )
                ).all()
                existing_tx_map = {row[0]: row[1] for row in existing_tx_rows}
            processed_txs = []
            changed_addresses: set[str] = set()  # tracks accounts modified during the tx loop
            # Feature flag: parallel tx validation (v0.6.1). Default off for safety.
            use_parallel = getattr(settings, "parallel_tx_validation", False) and len(pending_txs) > 1
            if use_parallel:
                processed_txs, changed_addresses, ok = self._process_txs_parallel(
                    session, pending_txs, account_map, existing_tx_map, next_height, timestamp
                )
                if not ok:
                    return False
                # If parallel returned nothing (e.g. conflict rate exceeded threshold),
                # fall back to sequential processing.
                use_parallel = bool(processed_txs) or not pending_txs
            if not use_parallel:
                for tx in pending_txs:
                    nested = None
                    try:
                        tx_data = tx.content
                        sender = tx_data.get("from")
                        recipient = tx_data.get("to")
                        value = tx_data.get("amount", 0)
                        fee = tx_data.get("fee", 0)
                        self._logger.info(
                            "[PROPOSE] Processing tx %s: from=%s, to=%s, amount=%s, fee=%s",
                            tx.tx_hash,
                            sender,
                            recipient,
                            value,
                            fee,
                        )
                        if not sender or not recipient:
                            self._logger.warning("[PROPOSE] Skipping tx %s: missing sender or recipient", tx.tx_hash)
                            continue
                        sender_account = account_map.get(sender)
                        if not sender_account:
                            self._logger.warning(
                                "[PROPOSE] Skipping tx %s: sender account not found for %s", tx.tx_hash, sender
                            )
                            continue
                        total_cost = value + fee
                        if sender_account.balance < total_cost:
                            self._logger.warning(
                                "[PROPOSE] Skipping tx %s: insufficient balance (has %s, needs %s)",
                                tx.tx_hash,
                                sender_account.balance,
                                total_cost,
                            )
                            continue
                        nested = session.begin_nested()
                        recipient_account = account_map.get(recipient)
                        if not recipient_account:
                            self._logger.info("[PROPOSE] Creating recipient account for %s", recipient)
                            recipient_account = Account(chain_id=self._config.chain_id, address=recipient, balance=0, nonce=0)
                            session.add(recipient_account)
                            session.flush()
                            account_map[recipient] = recipient_account
                        else:
                            self._logger.info("[PROPOSE] Recipient account exists for %s", recipient)
                        state_transition = get_state_transition()
                        tx_data_for_transition = tx.content.copy()
                        tx_data_for_transition["nonce"] = sender_account.nonce
                        tx_data_for_transition["value"] = tx_data_for_transition.get("amount", 0)
                        success, error_msg = state_transition.apply_transaction(
                            session, self._config.chain_id, tx_data_for_transition, tx.tx_hash
                        )
                        if not success:
                            nested.rollback()
                            self._logger.warning("[PROPOSE] Failed to apply transaction %s: %s", tx.tx_hash, error_msg)
                            continue
                        existing_block_height = existing_tx_map.get(tx.tx_hash)
                        if existing_block_height is not None:
                            nested.rollback()
                            self._logger.warning(
                                "[PROPOSE] Skipping tx %s: already exists in database at block %s",
                                tx.tx_hash,
                                existing_block_height,
                            )
                            continue
                        tx_type = tx.content.get("type", "TRANSFER")
                        if tx_type:
                            tx_type = tx_type.upper()
                        else:
                            tx_type = "TRANSFER"
                        original_payload = tx.content.get("payload", {})
                        transaction = Transaction(
                            chain_id=self._config.chain_id,
                            tx_hash=tx.tx_hash,
                            sender=sender,
                            recipient=recipient,
                            payload=original_payload,
                            value=value,
                            fee=fee,
                            nonce=tx_data_for_transition["nonce"],
                            timestamp=timestamp,
                            block_height=next_height,
                            status="confirmed",
                            type=tx_type,
                        )
                        session.add(transaction)
                        nested.commit()
                        # Track changed addresses for incremental state root computation
                        changed_addresses.add(sender)
                        changed_addresses.add(recipient)
                        # Track the newly committed tx hash so subsequent iterations
                        # in this loop detect it as a duplicate without another DB query.
                        existing_tx_map[tx.tx_hash] = next_height
                        processed_txs.append(tx)
                        self._logger.info("[PROPOSE] Successfully processed tx %s: updated balances", tx.tx_hash)
                    except Exception as e:
                        if nested is not None:
                            nested.rollback()
                        self._logger.warning("Failed to process transaction %s: %s", tx.tx_hash, e)
                        return False
            if pending_txs and (not processed_txs) and getattr(settings, "propose_only_if_mempool_not_empty", True):
                self._logger.warning(
                    "[PROPOSE] Skipping block proposal: all drained transactions were invalid (count=%s, chain=%s)",
                    len(pending_txs),
                    self._config.chain_id,
                )
                return False
            block_hash = self._compute_block_hash(next_height, parent_hash, timestamp, processed_txs)
            # Compute state root incrementally — only re-read changed accounts
            # instead of loading ALL accounts from the DB.
            if changed_addresses:
                state_root = _compute_state_root_incremental(session, self._config.chain_id, account_map, changed_addresses)
            else:
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
            # Invalidate the in-process block header cache for the new block
            # so stale entries are not served by rpc/blocks.py.
            from ..block_cache import get_block_header_cache

            get_block_header_cache().invalidate(self._config.chain_id, height=next_height, hash=block_hash)
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
            self._last_block_timestamp = timestamp
            self._logger.info("Proposed block", extra={"height": block.height, "hash": block.hash, "proposer": block.proposer})
            tx_list = [tx.content for tx in processed_txs] if processed_txs else []
            gossip_topic = f"blocks.{self._config.chain_id}"
            try:
                subscribers = await lease_tracker.get_valid_subscribers(self._config.chain_id)
                subscriber_count = len(subscribers)
                self._logger.info(
                    "[BROADCAST] block=%s, topic=%s, valid_subscribers=%s", block.height, gossip_topic, subscriber_count
                )
                if subscriber_count > 0:
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
                    self._logger.info(
                        "[BROADCAST SUCCESS] block=%s, topic=%s, subscribers=%s", block.height, gossip_topic, subscriber_count
                    )
                else:
                    self._logger.info("[BROADCAST SKIPPED] block=%s, no valid subscribers", block.height)
            except Exception as e:
                self._logger.error("Failed to broadcast block %s: %s", block.height, e)
        return True

    async def _ensure_genesis_block(self) -> None:
        with self._session_factory() as session:
            genesis = session.exec(
                select(Block).where(Block.chain_id == self._config.chain_id).where(Block.height == 0).limit(1)
            ).first()
            if genesis is not None:
                self._logger.info(
                    "Genesis block already exists: height=%s, hash=%s, proposer=%s",
                    genesis.height,
                    genesis.hash,
                    genesis.proposer,
                )
                return
            self._logger.info("Attempting RPC bootstrap for genesis block for chain %s", self._config.chain_id)
            rpc_genesis_data = await self._load_genesis_block_from_rpc()
            if rpc_genesis_data:
                self._logger.info("Using RPC-provided genesis block data for chain %s", self._config.chain_id)
                genesis_allocations = rpc_genesis_data.get("allocations", [])
                genesis_hash = rpc_genesis_data.get("genesis_hash")
                genesis_state_root = rpc_genesis_data.get("genesis_state_root")
                if genesis_hash and genesis_state_root:
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
                        self._logger.info(
                            "Successfully created genesis block from RPC bootstrap: hash=%s, state_root=%s",
                            genesis_hash,
                            genesis_state_root,
                        )
                        if genesis_allocations:
                            self._create_accounts_from_allocations(session, genesis_allocations)
                            self._logger.info("Initialized %s accounts from RPC bootstrap", len(genesis_allocations))
                        return
                    except Exception as e:
                        self._logger.warning(
                            "Failed to create genesis block from RPC bootstrap: %s, falling back to local creation", e
                        )
                        session.rollback()
                else:
                    self._logger.warning("RPC bootstrap returned incomplete genesis data, falling back to local creation")
            self._logger.info("Loading genesis block from local file for chain %s", self._config.chain_id)
            local_genesis_data = self._load_genesis_data_from_file()
            if not local_genesis_data:
                self._logger.error(
                    "Genesis file not found at /var/lib/aitbc/data/%s/genesis.json. Cannot create genesis block without genesis.json file.",
                    self._config.chain_id,
                )
                raise RuntimeError(
                    f"Genesis file required but not found for chain {self._config.chain_id}. Please create genesis.json at /var/lib/aitbc/data/{self._config.chain_id}/genesis.json"
                )
            block_data = local_genesis_data.get("block", {})
            genesis_hash = local_genesis_data.get("genesis_hash") or block_data.get("hash")
            genesis_timestamp = local_genesis_data.get("timestamp") or block_data.get("timestamp")
            genesis_state_root = local_genesis_data.get("state_root") or block_data.get("state_root")
            genesis_allocations = local_genesis_data.get("allocations", block_data.get("allocations", []))
            if not genesis_hash or not genesis_timestamp or (not genesis_state_root):
                self._logger.error("Genesis file missing required fields: genesis_hash, timestamp, or state_root")
                raise RuntimeError(
                    f"Genesis file at /var/lib/aitbc/data/{self._config.chain_id}/genesis.json is missing required fields (genesis_hash, timestamp, state_root)"
                )
            try:
                if isinstance(genesis_timestamp, str):
                    timestamp = datetime.fromisoformat(genesis_timestamp)
                else:
                    timestamp = genesis_timestamp
            except Exception as e:
                self._logger.error("Failed to parse genesis timestamp: %s", e)
                raise RuntimeError(f"Invalid timestamp format in genesis file: {e}") from e
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
                self._logger.info(
                    "Successfully created genesis block from genesis.json: hash=%s, state_root=%s, timestamp=%s",
                    genesis_hash,
                    genesis_state_root,
                    timestamp,
                )
                if genesis_allocations:
                    self._create_accounts_from_allocations(session, genesis_allocations)
                    self._logger.info("Initialized %s accounts from genesis.json", len(genesis_allocations))
            except Exception as e:
                self._logger.error("Failed to create genesis block from genesis.json: %s", e)
                session.rollback()
                raise
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
                },
            )

    async def _initialize_genesis_allocations(self, session: Session) -> None:
        """Create Account entries from the genesis allocations file or RPC bootstrap."""
        self._logger.info("Initializing genesis allocations for chain: %s", self._config.chain_id)
        local_genesis_data = self._load_genesis_data_from_file()
        if local_genesis_data:
            local_allocations = local_genesis_data.get("allocations", [])
            self._logger.info("Using local genesis file for chain %s", self._config.chain_id)
            self._create_accounts_from_allocations(session, local_allocations)
            return
        self._logger.info("Local genesis file not found for chain %s, attempting RPC bootstrap", self._config.chain_id)
        try:
            rpc_allocations, rpc_genesis_state_root = await self._load_genesis_allocations_from_rpc()
            if rpc_allocations:
                self._logger.info(
                    "Loaded %s allocations via RPC bootstrap for chain %s", len(rpc_allocations), self._config.chain_id
                )
                self._create_accounts_from_allocations(session, rpc_allocations)
                if rpc_genesis_state_root:
                    self._rpc_genesis_state_root = rpc_genesis_state_root
                    self._logger.info("Stored RPC genesis state_root: %s", rpc_genesis_state_root)
                else:
                    self._logger.info(
                        "RPC bootstrap completed successfully for chain %s, but no state_root provided", self._config.chain_id
                    )
            else:
                self._logger.warning(
                    "RPC bootstrap returned no allocations for chain %s, skipping account initialization",
                    self._config.chain_id,
                )
        except Exception as e:
            self._logger.warning(
                "RPC bootstrap failed for chain %s: %s, skipping account initialization", self._config.chain_id, e
            )

    def _load_genesis_data_from_file(self) -> dict[str, Any]:
        """Load complete genesis data from local file."""
        genesis_paths = [Path(f"/var/lib/aitbc/data/{self._config.chain_id}/genesis.json")]
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
            return genesis_data  # type: ignore[no-any-return]
        except Exception as e:
            self._logger.warning("Failed to load genesis file: %s", e)
            return {}

    def _load_genesis_allocations_for_metadata(self) -> list[Any]:
        """Load genesis allocations from file for embedding in genesis block metadata."""
        return []

    async def _load_genesis_block_from_rpc(self) -> dict[str, Any] | None:
        """Load genesis block data from trusted peer via RPC.

        Returns:
            Dict with genesis block data (allocations, genesis_hash, genesis_state_root) or None if failed
        """
        trusted_peers = []
        if self._config.default_peer_rpc_url:
            peer_url = self._config.default_peer_rpc_url
            if peer_url.startswith("http://"):
                peer_url = peer_url.replace("http://", "")
            peer_url = f"http://{peer_url}"
            trusted_peers.append(peer_url)
        self._logger.info("Attempting RPC bootstrap for genesis block from peers: %s", trusted_peers)
        for peer_url in trusted_peers:
            try:
                self._logger.info("Trying to fetch genesis block from %s", peer_url)
                response = await SharedHttpClient.get(
                    f"{peer_url}/rpc/genesis_allocations", params={"chain_id": self._config.chain_id}, timeout=5.0
                )
                response.raise_for_status()
                data = response.json()
                self._logger.info("RPC response from %s: %s", peer_url, data)
                return data  # type: ignore[no-any-return]
            except Exception as e:
                self._logger.error("Failed to fetch genesis block from %s: %s", peer_url, e)
                continue
        self._logger.error("RPC bootstrap for genesis block failed for all peers")
        return None

    async def _load_genesis_allocations_from_rpc(self) -> tuple[list[Any], str | None]:
        """Load genesis allocations and state_root from trusted peer via RPC.

        Returns:
            Tuple of (allocations list, genesis_state_root string or None)
        """
        trusted_peers = []
        if self._config.default_peer_rpc_url:
            peer_url = self._config.default_peer_rpc_url
            if peer_url.startswith("http://"):
                peer_url = peer_url.replace("http://", "")
            peer_url = f"http://{peer_url}"
            trusted_peers.append(peer_url)
        self._logger.info("Attempting RPC bootstrap from peers: %s", trusted_peers)
        for peer_url in trusted_peers:
            try:
                self._logger.info("Trying to fetch allocations from %s", peer_url)
                response = await SharedHttpClient.get(
                    f"{peer_url}/rpc/genesis_allocations", params={"chain_id": self._config.chain_id}, timeout=5.0
                )
                response.raise_for_status()
                data = response.json()
                self._logger.info("RPC response from %s: %s", peer_url, data)
                allocations = data.get("allocations", [])
                genesis_state_root = data.get("genesis_state_root")
                if allocations:
                    self._logger.info("Successfully loaded %s allocations from %s", len(allocations), peer_url)
                    if genesis_state_root:
                        self._logger.info("RPC provided genesis state_root: %s", genesis_state_root)
                    return (allocations, genesis_state_root)
                else:
                    self._logger.warning("RPC returned empty allocations from %s", peer_url)
            except Exception as e:
                self._logger.error("Failed to fetch allocations from %s: %s", peer_url, e)
                continue
        self._logger.error("RPC bootstrap failed for all peers")
        return ([], None)

    def _create_accounts_from_allocations(self, session: Session, allocations: list[Any]) -> None:
        """Create Account entries from allocation data."""
        created = 0
        for alloc in allocations:
            addr = alloc["address"]
            balance = int(alloc["balance"])
            nonce = int(alloc.get("nonce", 0))
            existing = session.exec(
                select(Account).where(Account.chain_id == self._config.chain_id).where(Account.address == addr)
            ).first()
            if existing:
                continue
            account = Account(chain_id=self._config.chain_id, address=addr, balance=balance, nonce=nonce)
            session.add(account)
            created += 1
        session.commit()
        self._logger.info("Created %s accounts from genesis allocations", created)

    def _process_txs_parallel(
        self,
        session: Session,
        pending_txs: list[Any],
        account_map: dict[str, Account],
        existing_tx_map: dict[str, int],
        next_height: int,
        timestamp: datetime,
    ) -> tuple[list[Any], set[str], bool]:
        """Process transactions in parallel using dependency analysis.

        Returns (processed_txs, changed_addresses, success).
        Falls back to sequential if conflict rate exceeds threshold.
        """
        chain_id = self._config.chain_id
        # Build dependency graph from tx read/write sets
        graph = DependencyGraph()
        tx_by_hash: dict[str, Any] = {}
        for idx, tx in enumerate(pending_txs):
            read_set, write_set = extract_read_write_sets(tx.content)
            graph.add_transaction(tx.tx_hash, read_set, write_set, index=idx)
            tx_by_hash[tx.tx_hash] = tx

        # Check conflict rate — fall back to sequential if too many conflicts
        conflict_rate = graph.conflict_rate()
        threshold = getattr(settings, "conflict_threshold", 0.5)
        if conflict_rate > threshold:
            self._logger.info(
                "[PROPOSE-PARALLEL] Conflict rate %.2f exceeds threshold %.2f — falling back to sequential",
                conflict_rate,
                threshold,
            )
            return [], set(), True  # signal: no parallel processing, caller continues sequential

        groups = graph.get_conflict_groups()
        self._logger.info(
            "[PROPOSE-PARALLEL] %d txs → %d groups (conflict_rate=%.2f)",
            len(pending_txs),
            len(groups),
            conflict_rate,
        )

        # Prepare tx_data for each tx (with nonce set from account_map)
        tx_data_map: dict[str, dict[str, Any]] = {}
        for tx in pending_txs:
            tx_data = tx.content.copy()
            sender = tx_data.get("from", "")
            sender_account = account_map.get(sender)
            tx_data["nonce"] = sender_account.nonce if sender_account else 0
            tx_data["value"] = tx_data.get("amount", 0)
            tx_data_map[tx.tx_hash] = tx_data

        # Track processed tx hashes for duplicate detection
        processed_tx_hashes: set[str] = set()

        # Execute groups in parallel — within each group, txs are independent
        max_workers = getattr(settings, "parallel_workers", 4)
        executor = ParallelExecutor(max_workers=max_workers)
        try:
            all_deltas: list[tuple[int, StateDelta, Any]] = []  # (index, delta, tx)
            for group in groups:
                # Update nonces from account_map before processing each group
                # (conflicting txs in later groups need updated nonces from earlier groups)
                for tx_hash in group:
                    tx_data = tx_data_map[tx_hash]
                    sender = tx_data.get("from", "")
                    sender_account = account_map.get(sender)
                    if sender_account:
                        tx_data["nonce"] = sender_account.nonce

                # Build the list of (tx_hash, tx_data) for this group
                group_items = [(tx_hash, tx_data_map[tx_hash]) for tx_hash in group]

                def compute_fn(item: tuple[str, dict[str, Any]]) -> StateDelta:
                    tx_hash, tx_data = item
                    return compute_state_delta(account_map, tx_data, chain_id, tx_hash, processed_tx_hashes)

                results = executor.execute_groups([group_items], compute_fn)
                group_deltas = results[0] if results else []

                # Apply successful deltas to account_map immediately (within group,
                # txs don't conflict, so order within group doesn't matter for state)
                for i, (tx_hash, _) in enumerate(group_items):
                    delta = group_deltas[i]
                    tx = tx_by_hash[tx_hash]
                    if delta.success:
                        # Check for duplicate tx in DB
                        if existing_tx_map.get(tx_hash) is not None:
                            self._logger.warning(
                                "[PROPOSE-PARALLEL] Skipping tx %s: already exists in database at block %s",
                                tx_hash,
                                existing_tx_map[tx_hash],
                            )
                            continue
                        apply_delta_to_map(account_map, delta, chain_id)
                        processed_tx_hashes.add(tx_hash)
                        all_deltas.append((i, delta, tx))
                    else:
                        self._logger.warning("[PROPOSE-PARALLEL] Failed to validate tx %s: %s", tx_hash, delta.error)
        finally:
            executor.close()

        # Sort deltas by original tx index for deterministic ordering
        all_deltas.sort(key=lambda x: x[0])

        # Write all deltas to DB in a single batch
        successful_deltas = [d for _, d, _ in all_deltas]
        if successful_deltas:
            apply_deltas_to_db(session, successful_deltas, chain_id)

        # Create Transaction records and track changed addresses
        processed_txs: list[Any] = []
        changed_addresses: set[str] = set()
        for _idx, delta, tx in all_deltas:
            sender = delta.sender
            recipient = delta.recipient
            tx_type = delta.tx_type
            tx_data = tx.content
            value = tx_data.get("amount", 0)
            fee = tx_data.get("fee", 0)
            original_payload = tx_data.get("payload", {})
            transaction = Transaction(
                chain_id=chain_id,
                tx_hash=tx.tx_hash,
                sender=sender,
                recipient=recipient,
                payload=original_payload,
                value=value,
                fee=fee,
                nonce=tx_data_map[tx.tx_hash].get("nonce", 0),
                timestamp=timestamp,
                block_height=next_height,
                status="confirmed",
                type=tx_type,
            )
            session.add(transaction)
            changed_addresses.add(sender)
            if recipient:
                changed_addresses.add(recipient)
            existing_tx_map[tx.tx_hash] = next_height
            processed_txs.append(tx)
            self._logger.info("[PROPOSE-PARALLEL] Successfully processed tx %s", tx.tx_hash)

        self._logger.info(
            "[PROPOSE-PARALLEL] Processed %d/%d txs in parallel",
            len(processed_txs),
            len(pending_txs),
        )
        return processed_txs, changed_addresses, True

    def _compute_block_hash(
        self, height: int, parent_hash: str, timestamp: datetime, transactions: list[Any] | None = None
    ) -> str:
        tx_hashes = []
        if transactions:
            tx_hashes = [tx.tx_hash for tx in transactions]
        payload = (
            f"{self._config.chain_id}|{height}|{parent_hash}|{timestamp.isoformat()}|{'|'.join(sorted(tx_hashes))}".encode()
        )
        return "0x" + hashlib.sha256(payload).hexdigest()
