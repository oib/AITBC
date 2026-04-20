from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from .config import settings
from .consensus import PoAProposer, ProposerConfig, CircuitBreaker
from .database import init_db, session_scope
from .logger import get_logger
from .gossip import gossip_broker, create_backend
from .sync import ChainSync
from .mempool import init_mempool

logger = get_logger(__name__)

def _load_keystore_password() -> str:
    """Load keystore password from file or environment."""
    pwd_file = settings.keystore_password_file
    if pwd_file.exists():
        return pwd_file.read_text().strip()
    env_pwd = os.getenv("KEYSTORE_PASSWORD")
    if env_pwd:
        return env_pwd
    raise RuntimeError(f"Keystore password not found. Set in {pwd_file} or KEYSTORE_PASSWORD env.")

def _load_private_key_from_keystore(keystore_dir: Path, password: str, target_address: Optional[str] = None) -> Optional[bytes]:
    """Load an ed25519 private key from the keystore.
    If target_address is given, find the keystore file with matching address.
    Otherwise, return the first key found.
    """
    if not keystore_dir.exists():
        return None
    for kf in keystore_dir.glob("*.json"):
        try:
            with open(kf) as f:
                data = json.load(f)
            addr = data.get("address")
            if target_address and addr != target_address:
                continue
            # Decrypt
            from cryptography.hazmat.primitives.asymmetric import ed25519
            from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            from cryptography.hazmat.backends import default_backend

            crypto = data["crypto"]
            kdfparams = crypto["kdfparams"]
            salt = bytes.fromhex(kdfparams["salt"])
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=kdfparams["c"],
                backend=default_backend()
            )
            key = kdf.derive(password.encode('utf-8'))
            nonce = bytes.fromhex(crypto["cipherparams"]["nonce"])
            ciphertext = bytes.fromhex(crypto["ciphertext"])
            aesgcm = AESGCM(key)
            private_bytes = aesgcm.decrypt(nonce, ciphertext, None)
            # Verify it's ed25519
            priv_key = ed25519.Ed25519PrivateKey.from_private_bytes(private_bytes)
            return private_bytes
        except Exception:
            continue
    return None

# Attempt to load proposer private key from keystore if not set
if not settings.proposer_key:
    try:
        pwd = _load_keystore_password()
        key_bytes = _load_private_key_from_keystore(settings.keystore_path, pwd, target_address=settings.proposer_id)
        if key_bytes:
            # Encode as hex for easy storage; not yet used for signing
            settings.proposer_key = key_bytes.hex()
            logger.info("Loaded proposer private key from keystore", extra={"proposer_id": settings.proposer_id})
        else:
            logger.warning("Proposer private key not found in keystore; block signing disabled", extra={"proposer_id": settings.proposer_id})
    except Exception as e:
        logger.warning("Failed to load proposer key from keystore", extra={"error": str(e)})


class BlockchainNode:
    def __init__(self) -> None:
        self._stop_event = asyncio.Event()
        self._proposers: dict[str, PoAProposer] = {}

    async def _setup_gossip_subscribers(self) -> None:
        logger.info("Setting up gossip subscribers")
        # Transactions
        try:
            tx_sub = await gossip_broker.subscribe("transactions")
            logger.info("Successfully subscribed to transactions topic")
        except Exception as e:
            logger.error(f"Failed to subscribe to transactions: {e}")
            return
        
        async def process_txs():
            from .mempool import get_mempool
            mempool = get_mempool()
            while True:
                try:
                    tx_data = await tx_sub.queue.get()
                    if isinstance(tx_data, str):
                        import json
                        tx_data = json.loads(tx_data)
                    chain_id = tx_data.get("chain_id", settings.chain_id)
                    mempool.add(tx_data, chain_id=chain_id)
                except Exception as exc:
                    logger.error(f"Error processing transaction from gossip: {exc}")
                    
        asyncio.create_task(process_txs())

        # Blocks
        try:
            block_sub = await gossip_broker.subscribe("blocks")
            logger.info("Successfully subscribed to blocks topic")
        except Exception as e:
            logger.error(f"Failed to subscribe to blocks: {e}")
            return
        
        async def process_blocks():
            last_bulk_sync_time = 0
            while True:
                try:
                    block_data = await block_sub.queue.get()
                    logger.info(f"Received block from gossip")
                    if isinstance(block_data, str):
                        import json
                        block_data = json.loads(block_data)
                    chain_id = block_data.get("chain_id", settings.chain_id)
                    logger.info(f"Importing block for chain {chain_id}: {block_data.get('height')}")
                    sync = ChainSync(session_factory=session_scope, chain_id=chain_id)
                    res = sync.import_block(block_data, transactions=block_data.get("transactions"))
                    logger.info(f"Import result: accepted={res.accepted}, reason={res.reason}")
                    
                    # Automatic bulk sync on gap detection
                    if not res.accepted and "Gap detected" in res.reason and settings.auto_sync_enabled:
                        # Parse gap size from reason string
                        try:
                            reason_parts = res.reason.split(":")
                            our_height = int(reason_parts[1].strip().split(",")[0].replace("our height: ", ""))
                            received_height = int(reason_parts[2].strip().replace("received: ", "").replace(")", ""))
                            gap_size = received_height - our_height
                            
                            if gap_size > settings.auto_sync_threshold:
                                current_time = asyncio.get_event_loop().time()
                                time_since_last_sync = current_time - last_bulk_sync_time
                                
                                if time_since_last_sync >= settings.min_bulk_sync_interval:
                                    logger.warning(f"Gap detected: {gap_size} blocks, triggering automatic bulk sync")
                                    
                                    # Get source URL from block metadata if available
                                    source_url = block_data.get("source_url")
                                    if not source_url:
                                        # Fallback to default peer RPC URL
                                        source_url = settings.default_peer_rpc_url
                                    
                                    if source_url:
                                        try:
                                            imported = await sync.bulk_import_from(source_url)
                                            logger.info(f"Bulk sync completed: {imported} blocks imported")
                                            last_bulk_sync_time = current_time
                                            
                                            # Retry block import after bulk sync
                                            res = sync.import_block(block_data, transactions=block_data.get("transactions"))
                                            logger.info(f"Retry import result: accepted={res.accepted}, reason={res.reason}")
                                        except Exception as sync_exc:
                                            logger.error(f"Automatic bulk sync failed: {sync_exc}")
                                    else:
                                        logger.warning("No source URL available for bulk sync")
                                else:
                                    logger.info(f"Skipping bulk sync, too recent ({time_since_last_sync:.0f}s ago)")
                        except (ValueError, IndexError) as parse_exc:
                            logger.error(f"Failed to parse gap size from reason: {res.reason}, error: {parse_exc}")
                except Exception as exc:
                    logger.error(f"Error processing block from gossip: {exc}")
                    
        asyncio.create_task(process_blocks())
        logger.info("Gossip subscribers setup completed")

    async def start(self) -> None:
        logger.info("Starting blockchain node", extra={"supported_chains": getattr(settings, 'supported_chains', settings.chain_id)})
        
        # Initialize Gossip Backend
        backend = create_backend(
            settings.gossip_backend,
            broadcast_url=settings.gossip_broadcast_url,
        )
        logger.info(f"Initializing gossip backend: {settings.gossip_backend}, url: {settings.gossip_broadcast_url}")
        await gossip_broker.set_backend(backend)
        logger.info("Gossip backend initialized successfully")
        
        init_db()
        init_mempool(
            backend=settings.mempool_backend,
            db_path=str(settings.db_path.parent / "mempool.db"),
            max_size=settings.mempool_max_size,
            min_fee=settings.min_fee,
        )
        # Start proposers only if enabled (followers set enable_block_production=False)
        if getattr(settings, "enable_block_production", True):
            self._start_proposers()
        else:
            logger.info("Block production disabled on this node", extra={"proposer_id": settings.proposer_id})
        await self._setup_gossip_subscribers()
        try:
            await self._stop_event.wait()
        finally:
            await self._shutdown()

    async def stop(self) -> None:
        logger.info("Stopping blockchain node")
        self._stop_event.set()
        await self._shutdown()

    def _start_proposers(self) -> None:
        chains_str = getattr(settings, 'supported_chains', settings.chain_id)
        chains = [c.strip() for c in chains_str.split(",") if c.strip()]
        for chain_id in chains:
            if chain_id in self._proposers:
                continue

            proposer_config = ProposerConfig(
                chain_id=chain_id,
                proposer_id=settings.proposer_id,
                interval_seconds=settings.block_time_seconds,
                max_block_size_bytes=settings.max_block_size_bytes,
                max_txs_per_block=settings.max_txs_per_block,
            )
            
            proposer = PoAProposer(config=proposer_config, session_factory=session_scope)
            self._proposers[chain_id] = proposer
            asyncio.create_task(proposer.start())

    async def _shutdown(self) -> None:
        for chain_id, proposer in list(self._proposers.items()):
            await proposer.stop()
        self._proposers.clear()
        await gossip_broker.shutdown()


@asynccontextmanager
async def node_app() -> asyncio.AbstractAsyncContextManager[BlockchainNode]:  # type: ignore[override]
    node = BlockchainNode()
    try:
        yield node
    finally:
        await node.stop()


def run() -> None:
    asyncio.run(_run())


async def _run() -> None:
    async with node_app() as node:
        await node.start()


if __name__ == "__main__":  # pragma: no cover
    run()
