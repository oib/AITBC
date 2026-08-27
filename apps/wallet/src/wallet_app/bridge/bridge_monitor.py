"""
ETH-AIT Bridge Monitor
Polls Ethereum RPC for incoming ETH transactions to the bridge wallet address.
"""

import asyncio
import os
from decimal import Decimal
from typing import Any

from aitbc.aitbc_logging import get_logger
from aitbc.network import SharedHttpClient

from .bridge_db import get_deposit_by_tx_hash, init_db, insert_deposit
from .price_api import calculate_ait_amount

logger = get_logger(__name__)

# Configuration
ETH_RPC_URL = os.getenv("ETH_RPC_URL", "https://eth.llamarpc.com")
ETH_WALLET_ADDRESS = os.getenv("ETH_WALLET_ADDRESS", "")
POLL_INTERVAL = int(os.getenv("BRIDGE_POLL_INTERVAL", "30"))  # seconds
BRIDGE_ENABLED = os.getenv("BRIDGE_ENABLED", "false").lower() == "true"


async def get_eth_transactions(address: str) -> list[dict[str, Any]]:
    """
    Fetch recent transactions for an Ethereum address using RPC.
    Returns list of transaction objects.
    """
    try:
        # Use etherscan-like API or RPC to get transactions
        # For MVP, we'll use a simple RPC call to get latest block and filter
        # In production, use proper block explorer API or indexer

        payload = {"jsonrpc": "2.0", "method": "eth_getBlockByNumber", "params": ["latest", True], "id": 1}

        response = await SharedHttpClient.post(ETH_RPC_URL, json=payload, timeout=10.0)
        response.raise_for_status()

        block_data = response.json()
        if "result" not in block_data:
            return []

        transactions = block_data["result"].get("transactions", [])

        # Filter transactions to our wallet address
        relevant_txs = []
        for tx in transactions:
            if not isinstance(tx, dict):
                continue
            to_address = tx.get("to") or ""
            if to_address and to_address.lower() == address.lower():
                relevant_txs.append(tx)

        return relevant_txs
    except Exception as e:
        logger.error("Error fetching ETH transactions: %s", e)
        return []


async def process_transaction(tx: dict[str, Any]) -> bool:
    """
    Process a single ETH transaction and record it as a deposit.
    Returns True if deposit was recorded, False if already exists.
    """
    tx_hash = tx.get("hash", "")
    from_address = tx.get("from") or ""

    # Parse ETH amount (hex wei to ETH)
    value_hex = tx.get("value") or "0x0"
    value_wei = int(value_hex, 16)
    amount_eth = Decimal(value_wei) / Decimal(10**18)  # Convert wei to ETH

    if amount_eth <= 0:
        return False

    # Check if already recorded
    existing = get_deposit_by_tx_hash(tx_hash)
    if existing:
        return False

    # Calculate AIT amount
    amount_ait = await calculate_ait_amount(amount_eth)
    if amount_ait is None:
        logger.error("Failed to calculate AIT amount for tx %s", tx_hash)
        return False

    # Record deposit
    try:
        deposit_id = insert_deposit(tx_hash, from_address, amount_eth, amount_ait)
        logger.info("Recorded deposit %s: %s ETH → %s AIT (tx: %s)", deposit_id, amount_eth, amount_ait, tx_hash)
        return True
    except ValueError as e:
        logger.warning("Deposit already exists: %s", e)
        return False
    except Exception as e:
        logger.error("Error recording deposit: %s", e)
        return False


async def monitor_loop() -> None:
    """
    Main monitoring loop that polls for new transactions.
    """
    if not BRIDGE_ENABLED:
        logger.info("Bridge monitoring disabled (BRIDGE_ENABLED=false)")
        return

    if not ETH_WALLET_ADDRESS:
        logger.info("Bridge monitoring disabled (ETH_WALLET_ADDRESS not set)")
        return

    logger.info("Starting bridge monitor for address %s", ETH_WALLET_ADDRESS)
    logger.info("Polling interval: %ss", POLL_INTERVAL)

    init_db()

    while True:
        try:
            transactions = await get_eth_transactions(ETH_WALLET_ADDRESS)

            for tx in transactions:
                await process_transaction(tx)

        except Exception as e:
            logger.error("Error in monitor loop: %s", e)

        await asyncio.sleep(POLL_INTERVAL)


def start_monitoring() -> asyncio.Task[None] | None:
    """
    Start the bridge monitoring as an asyncio task.

    Returns the task if bridge monitoring is enabled, None otherwise.
    The caller is responsible for running an event loop.
    """
    if not BRIDGE_ENABLED:
        return None

    try:
        task = asyncio.create_task(monitor_loop())
        return task
    except RuntimeError:
        # No event loop running — fall back to running in a thread
        logger.debug("No event loop running; starting bridge monitor in a thread", exc_info=True)
        import threading

        def _run_sync() -> None:
            asyncio.run(monitor_loop())

        monitor_thread = threading.Thread(target=_run_sync, daemon=True)
        monitor_thread.start()
        return None


if __name__ == "__main__":
    # For testing
    logger.info("Testing bridge monitor...")
    asyncio.run(monitor_loop())
