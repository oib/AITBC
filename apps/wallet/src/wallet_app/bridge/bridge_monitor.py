"""
ETH-AIT Bridge Monitor
Polls Ethereum RPC for incoming ETH transactions to the bridge wallet address.
"""

import asyncio
import json
import os
from decimal import Decimal
from typing import Any

import httpx
from aitbc.aitbc_logging import get_logger
from aitbc.network import SharedHttpClient
from aitbc.utils import ait_to_seconds

from .bridge_db import (
    get_deposit_by_tx_hash,
    init_db,
    insert_deposit,
    update_deposit_status,
    update_deposit_tx_hash,
)
from .price_api import calculate_ait_amount

logger = get_logger(__name__)

# Configuration
ETH_RPC_URL = os.getenv("ETH_RPC_URL", "https://eth.llamarpc.com")
ETH_WALLET_ADDRESS = os.getenv("ETH_WALLET_ADDRESS", "")
POLL_INTERVAL = int(os.getenv("BRIDGE_POLL_INTERVAL", "30"))  # seconds
BRIDGE_ENABLED = os.getenv("BRIDGE_ENABLED", "false").lower() == "true"

BLOCKCHAIN_RPC_URL = os.getenv("BLOCKCHAIN_RPC_URL", "http://localhost:8202")
GENESIS_WALLET_ADDRESS = os.getenv("GENESIS_WALLET_ADDRESS", "")
GENESIS_WALLET_PRIVATE_KEY = os.getenv("GENESIS_WALLET_PRIVATE_KEY", "")
DEFAULT_RECIPIENT = os.getenv("WALLET_ADDRESS", "")
MIN_ETH_DEPOSIT = Decimal(os.getenv("MIN_ETH_DEPOSIT", "0.001"))


def _canonical_address(address: str) -> str | None:
    """Normalize ait1/aitbc1/0x address to 0x... if it is a valid 20-byte address.

    Returns the original string as-is if it cannot be canonicalized, so agents
    can pass any supported spelling.
    """
    if not address:
        return None
    lowered = address.strip().lower()
    if lowered.startswith("0x"):
        body = lowered[2:]
        if len(body) == 40:
            return lowered
    for prefix in ("aitbc1", "ait1"):
        if lowered.startswith(prefix):
            body = lowered[len(prefix) :]
            if len(body) == 40:
                return f"0x{body}"
    return None


def _parse_recipient_from_input(tx_input: str | None) -> str | None:
    """Extract an AIT/EVM address from the transaction input data field."""
    if not tx_input or tx_input == "0x":
        return None
    try:
        data = tx_input[2:] if tx_input.startswith("0x") else tx_input
        if len(data) % 2:
            data = "0" + data
        decoded_bytes = bytes.fromhex(data)
    except ValueError:
        return None

    # First try UTF-8 decoding (website encodes the AIT address as UTF-8 hex).
    try:
        decoded = decoded_bytes.decode("utf-8").strip()
        if decoded:
            canonical = _canonical_address(decoded)
            if canonical:
                return decoded
            # If decoded is already 0x + 40 hex without prefix, return as 0x...
            if len(decoded) == 42 and decoded.startswith("0x"):
                return decoded
    except UnicodeDecodeError:
        pass

    # Fallback: raw 20 bytes (40 hex chars)
    if len(decoded_bytes) == 20:
        return "0x" + decoded_bytes.hex()

    return None


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
    try:
        value_wei = int(value_hex, 16)
    except ValueError:
        logger.warning("Skipping tx %s with non-hex value: %s", tx_hash, value_hex)
        return False
    amount_eth = Decimal(value_wei) / Decimal(10**18)  # Convert wei to ETH

    if amount_eth < MIN_ETH_DEPOSIT:
        logger.info("Skipping tx %s: %s ETH below minimum %s", tx_hash, amount_eth, MIN_ETH_DEPOSIT)
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

    # Resolve recipient: tx data first, then default configured wallet.
    tx_input = tx.get("input") or tx.get("data") or "0x"
    recipient = _parse_recipient_from_input(tx_input)
    if not recipient:
        if DEFAULT_RECIPIENT:
            recipient = DEFAULT_RECIPIENT
            logger.info("No AIT address in tx %s data; using default recipient %s", tx_hash, recipient)
        else:
            logger.error("No AIT recipient for tx %s and no WALLET_ADDRESS configured", tx_hash)
            return False

    # Record deposit
    try:
        deposit_id = insert_deposit(tx_hash, from_address, amount_eth, amount_ait, recipient=recipient)
        logger.info(
            "Recorded deposit %s: %s ETH → %s AIT for %s (tx: %s)",
            deposit_id,
            amount_eth,
            amount_ait,
            recipient,
            tx_hash,
        )
    except ValueError:
        logger.warning("Deposit already exists for tx %s", tx_hash)
        return False
    except Exception as e:
        logger.error("Error recording deposit: %s", e)
        return False

    # Auto-mint if configured
    if GENESIS_WALLET_ADDRESS and GENESIS_WALLET_PRIVATE_KEY:
        try:
            await _mint_deposit(deposit_id, recipient, amount_ait)
        except Exception as e:
            logger.error("Auto-mint failed for deposit %s: %s", deposit_id, e)
    else:
        logger.info("Auto-mint skipped: GENESIS_WALLET_ADDRESS/PRIVATE_KEY not configured")

    return True


async def _mint_deposit(deposit_id: str, recipient: str, amount_ait: Decimal) -> None:
    """Verify, sign, submit AIT transfer, and mark deposit completed."""
    # 1. Verify
    update_deposit_status(deposit_id, "verified")

    # 2. Get nonce
    try:
        account_resp = await SharedHttpClient.get(f"{BLOCKCHAIN_RPC_URL}/rpc/account/{GENESIS_WALLET_ADDRESS}", timeout=10.0)
        account_data = account_resp.json()
        nonce = account_data.get("nonce", 0)
    except Exception as e:
        logger.error("Failed to fetch genesis nonce for auto-mint: %s", e)
        update_deposit_status(deposit_id, "pending")
        return

    # 3. Build and sign transaction
    try:
        from eth_keys import keys as eth_keys
        from eth_utils import keccak

        amount_seconds = ait_to_seconds(amount_ait)
        fee_seconds = ait_to_seconds(Decimal("0.01"))

        tx_payload = {
            "type": "TRANSFER",
            "chain_id": os.getenv("CHAIN_ID", "ait-hub.aitbc.bubuit.net"),
            "from": GENESIS_WALLET_ADDRESS,
            "to": recipient,
            "amount": amount_seconds,
            "fee": fee_seconds,
            "nonce": nonce,
            "payload": {"amount": amount_seconds},
        }

        unsigned = {k: v for k, v in tx_payload.items() if k != "signature"}
        message = json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
        private_key_hex = (
            GENESIS_WALLET_PRIVATE_KEY[2:] if GENESIS_WALLET_PRIVATE_KEY.startswith("0x") else GENESIS_WALLET_PRIVATE_KEY
        )
        private_key = eth_keys.PrivateKey(bytes.fromhex(private_key_hex))
        signature = private_key.sign_msg_hash(keccak(message))
        tx_payload["signature"] = signature.to_bytes().hex()

        # 4. Submit
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{BLOCKCHAIN_RPC_URL}/rpc/transaction", json=tx_payload)
            response.raise_for_status()
            result = response.json()
            tx_hash = result.get("transaction_hash") or result.get("tx_hash") or ""

        if not tx_hash:
            raise ValueError(f"No tx hash returned: {result}")

        # 5. Complete
        update_deposit_status(deposit_id, "completed")
        update_deposit_tx_hash(deposit_id, tx_hash)
        logger.info("Auto-minted %s AIT to %s (tx: %s) for deposit %s", amount_ait, recipient, tx_hash, deposit_id)
    except Exception as e:
        logger.error("Error during auto-mint: %s", e)
        update_deposit_status(deposit_id, "pending")


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
