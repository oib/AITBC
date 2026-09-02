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
from aitbc.utils import ait_to_units

from aitbc.crypto.signature_recovery import canonical_address

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
ETH_WALLET_PRIVATE_KEY = os.getenv("ETH_WALLET_PRIVATE_KEY", "")
BRIDGE_ADMIN_PRIVATE_KEY = os.getenv("BRIDGE_ADMIN_PRIVATE_KEY", "")
POLL_INTERVAL = int(os.getenv("BRIDGE_POLL_INTERVAL", "30"))  # seconds
BRIDGE_ENABLED = os.getenv("BRIDGE_ENABLED", "false").lower() == "true"
WITHDRAW_ENABLED = os.getenv("BRIDGE_WITHDRAW_ENABLED", "true").lower() == "true"
WITHDRAW_POLL_INTERVAL = int(os.getenv("BRIDGE_WITHDRAW_POLL_INTERVAL", "30"))  # seconds

BLOCKCHAIN_RPC_URL = os.getenv("BLOCKCHAIN_RPC_URL", "http://localhost:8202")
GENESIS_WALLET_ADDRESS = os.getenv("GENESIS_WALLET_ADDRESS", "")
GENESIS_WALLET_PRIVATE_KEY = os.getenv("GENESIS_WALLET_PRIVATE_KEY", "")
DEFAULT_RECIPIENT = os.getenv("WALLET_ADDRESS", "")
MIN_ETH_DEPOSIT = Decimal(os.getenv("MIN_ETH_DEPOSIT", "0.001"))
MIN_AIT_WITHDRAW = Decimal(os.getenv("MIN_AIT_WITHDRAW", "0.01"))
ETH_WITHDRAW_GAS = int(os.getenv("ETH_WITHDRAW_GAS", "100000"))
ETH_WITHDRAW_MIN_RESERVE = Decimal(os.getenv("ETH_WITHDRAW_MIN_RESERVE", "0.005"))

_db_initialized = False
_bridge_polling_enabled: bool = True
_LAST_SCANNED_BLOCK: int | None = None


def _ensure_db() -> None:
    """Initialize the bridge database exactly once per process."""
    global _db_initialized
    if not _db_initialized:
        init_db()
        _db_initialized = True


def is_bridge_polling_enabled() -> bool:
    """Return whether the automatic bridge polling loop is enabled."""
    return _bridge_polling_enabled


def set_bridge_polling_enabled(enabled: bool) -> bool:
    """Enable or disable the automatic bridge polling loop at runtime."""
    global _bridge_polling_enabled
    _bridge_polling_enabled = enabled
    logger.info("Bridge auto-poll %s", "enabled" if enabled else "disabled")
    return _bridge_polling_enabled


def _canonical_address(address: str) -> str | None:
    """Normalize a 0x address to its canonical EIP-55 form.

    Legacy ait1/aitbc1 spellings are rejected.
    """
    if not address:
        return None
    normalized = canonical_address(address)
    if normalized.startswith("0x") and len(normalized) == 42:
        return normalized
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
                return canonical
    except UnicodeDecodeError:
        pass

    # Fallback: raw 20 bytes (40 hex chars)
    if len(decoded_bytes) == 20:
        return "0x" + decoded_bytes.hex()

    return None


def _hex_quantity(value: int) -> str:
    """Return a positive integer as a 0x-prefixed hex quantity."""
    return hex(value)


def _normalize_eth_tx(tx: dict[str, Any]) -> dict[str, Any]:
    """Ensure the fields the bridge monitor uses are plain hex strings."""

    def _to_hex(v: Any) -> str:
        if isinstance(v, bytes):
            return "0x" + v.hex()
        if isinstance(v, int):
            return hex(v)
        return str(v)

    return {
        "hash": _to_hex(tx.get("hash")),
        "from": _to_hex(tx.get("from")),
        "to": _to_hex(tx.get("to")),
        "value": _to_hex(tx.get("value")),
        "input": _to_hex(tx.get("input") or tx.get("data")),
    }


async def _rpc(method: str, params: list[Any], req_id: int = 1) -> Any:
    """Send a single JSON-RPC request and return the ``result`` field."""
    payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": req_id}
    response = await SharedHttpClient.post(ETH_RPC_URL, json=payload, timeout=10.0)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise RuntimeError(f"Unexpected response for {method}: {data!r}")
    if "error" in data:
        raise RuntimeError(f"{method} error: {data['error']}")
    return data.get("result")


async def _rpc_batch(payloads: list[dict[str, Any]]) -> dict[int, Any]:
    """Send a JSON-RPC batch and map responses by request ``id``."""
    response = await SharedHttpClient.post(ETH_RPC_URL, json=payloads, timeout=30.0)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list):
        raise RuntimeError(f"Expected JSON-RPC batch response list, got {type(data)}")

    results: dict[int, Any] = {}
    for item in data:
        if not isinstance(item, dict):
            continue
        req_id = item.get("id")
        if req_id is None:
            continue
        results[req_id] = item
    return results


async def get_eth_transactions(address: str) -> list[dict[str, Any]]:
    """
    Fetch recent transactions for an Ethereum address using RPC.

    Uses a JSON-RPC batch to fetch the block range in a single HTTP POST, and
    only scans blocks newer than the last successful poll (plus a small reorg
    margin). This avoids the previous one-request-per-block burst every cycle.
    """
    global _LAST_SCANNED_BLOCK

    lookback = int(os.getenv("BRIDGE_ETH_LOOKBACK_BLOCKS", "10"))
    if lookback < 1:
        lookback = 1
    reorg_margin = int(os.getenv("BRIDGE_ETH_REORG_MARGIN", "2"))
    if reorg_margin < 0:
        reorg_margin = 0

    try:
        latest_hex = await _rpc("eth_blockNumber", [], req_id=0)
        latest = int(latest_hex, 16)

        # Cold start / recovery: use the configured lookback window.
        # Steady state: scan only new blocks, overlapping by reorg_margin so a
        # short reorg does not let a deposit slip past us.
        if _LAST_SCANNED_BLOCK is None:
            start = max(0, latest - lookback + 1)
        else:
            start = max(0, _LAST_SCANNED_BLOCK - reorg_margin + 1)

        # If the monitor fell behind (long pause, error, etc.) do not scan more
        # than the configured lookback.
        start = max(start, latest - lookback + 1)

        target = address.lower()
        relevant_txs: list[dict[str, Any]] = []
        block_numbers = list(range(start, latest + 1))

        if not block_numbers:
            _LAST_SCANNED_BLOCK = latest
            return relevant_txs

        batch_payloads = [
            {
                "jsonrpc": "2.0",
                "method": "eth_getBlockByNumber",
                "params": [_hex_quantity(bn), True],
                "id": bn,
            }
            for bn in block_numbers
        ]

        batch_results = await _rpc_batch(batch_payloads)
        any_error = False

        for bn in block_numbers:
            item = batch_results.get(bn, {})
            if not isinstance(item, dict):
                any_error = True
                logger.warning("Missing block response for block %s", bn)
                continue
            if "error" in item:
                any_error = True
                logger.error("eth_getBlockByNumber(%s) error: %s", bn, item["error"])
                continue

            block_data = item.get("result")
            if not block_data:
                continue

            transactions = block_data.get("transactions") or []
            for tx in transactions:
                if not isinstance(tx, dict):
                    continue
                to_address = tx.get("to") or ""
                if str(to_address).lower() == target:
                    relevant_txs.append(_normalize_eth_tx(tx))

        if not any_error:
            _LAST_SCANNED_BLOCK = latest

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
            recipient = _canonical_address(DEFAULT_RECIPIENT)
            if not recipient:
                logger.error("Default WALLET_ADDRESS is not a valid 0x address: %s", DEFAULT_RECIPIENT)
                return False
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
    if _canonical_address(GENESIS_WALLET_ADDRESS) and GENESIS_WALLET_PRIVATE_KEY:
        try:
            await _mint_deposit(deposit_id, recipient, amount_ait)
        except Exception as e:
            logger.error("Auto-mint failed for deposit %s: %s", deposit_id, e)
    else:
        logger.info("Auto-mint skipped: GENESIS_WALLET_ADDRESS/PRIVATE_KEY not configured")

    return True


async def _mint_deposit(deposit_id: str, recipient: str, amount_ait: Decimal) -> None:
    """Verify, sign, submit AIT transfer, and mark deposit completed."""
    genesis_address = _canonical_address(GENESIS_WALLET_ADDRESS)
    if not genesis_address:
        logger.error("GENESIS_WALLET_ADDRESS is not a valid 0x address: %s", GENESIS_WALLET_ADDRESS)
        update_deposit_status(deposit_id, "pending")
        return

    # 1. Verify
    update_deposit_status(deposit_id, "verified")

    # 2. Get nonce
    try:
        account_resp = await SharedHttpClient.get(f"{BLOCKCHAIN_RPC_URL}/rpc/account/{genesis_address}", timeout=10.0)
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

        amount_seconds = ait_to_units(amount_ait)
        fee_seconds = ait_to_units(Decimal("0.01"))

        tx_payload = {
            "type": "TRANSFER",
            "chain_id": os.getenv("CHAIN_ID", "ait-hub.aitbc.bubuit.net"),
            "from": genesis_address,
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


async def poll_once() -> dict[str, Any]:
    """
    Run a single bridge poll cycle.

    Returns a summary of the poll, including how many transactions were
    scanned and how many new deposits were recorded.
    """
    if not BRIDGE_ENABLED:
        return {
            "scanned": 0,
            "recorded": 0,
            "skipped": True,
            "reason": "BRIDGE_ENABLED=false",
        }

    if not ETH_WALLET_ADDRESS:
        return {
            "scanned": 0,
            "recorded": 0,
            "skipped": True,
            "reason": "ETH_WALLET_ADDRESS not set",
        }

    _ensure_db()

    transactions = await get_eth_transactions(ETH_WALLET_ADDRESS)
    recorded = 0
    for tx in transactions:
        try:
            if await process_transaction(tx):
                recorded += 1
        except Exception as e:
            logger.error("Error processing tx %s: %s", tx.get("hash", ""), e)

    return {
        "scanned": len(transactions),
        "recorded": recorded,
        "skipped": False,
        "address": ETH_WALLET_ADDRESS,
    }


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

    _ensure_db()

    while True:
        if not _bridge_polling_enabled:
            logger.info("Bridge auto-poll disabled, sleeping")
            await asyncio.sleep(1)
            continue

        try:
            summary = await poll_once()
            if not summary.get("skipped"):
                logger.info("Bridge poll completed: %s", summary)
        except Exception as e:
            logger.error("Error in monitor loop: %s", e)

        for _ in range(POLL_INTERVAL):
            if not _bridge_polling_enabled:
                break  # type: ignore[unreachable]
            await asyncio.sleep(1)


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
