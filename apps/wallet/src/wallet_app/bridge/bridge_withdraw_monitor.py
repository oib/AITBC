"""
AIT→ETH Bridge Withdrawal Monitor

Polls the AITBC chain for confirmed ``BRIDGE_WITHDRAW`` transactions and releases
ETH from the configured bridge wallet to the Ethereum address in the withdrawal
payload. Failed releases are automatically refunded with a ``BRIDGE_REFUND``.
"""

from __future__ import annotations

import asyncio
import json
import os
from decimal import Decimal
from typing import Any, cast

import httpx
from eth_account import Account as EthAccount

from aitbc.aitbc_logging import get_logger
from aitbc.network import SharedHttpClient
from aitbc.utils import ait_to_units, units_to_ait
from aitbc.crypto.signature_recovery import canonical_address

from .bridge_db import (
    get_withdrawal_by_ait_tx_hash,
    init_db,
    insert_withdrawal,
    update_withdrawal_status,
)
from .price_api import calculate_eth_amount

logger = get_logger(__name__)

# Configuration
ETH_RPC_URL = os.getenv("ETH_RPC_URL", "https://eth.llamarpc.com")
ETH_NETWORK = os.getenv("ETH_NETWORK", "sepolia")
ETH_WALLET_ADDRESS = os.getenv("ETH_WALLET_ADDRESS", "")
ETH_WALLET_PRIVATE_KEY = os.getenv("ETH_WALLET_PRIVATE_KEY", "")
BRIDGE_ADMIN_PRIVATE_KEY = os.getenv("BRIDGE_ADMIN_PRIVATE_KEY", "")

BLOCKCHAIN_RPC_URL = os.getenv("BLOCKCHAIN_RPC_URL", "http://localhost:8202")
GENESIS_WALLET_ADDRESS = os.getenv("GENESIS_WALLET_ADDRESS", "")
GENESIS_WALLET_PRIVATE_KEY = os.getenv("GENESIS_WALLET_PRIVATE_KEY", "")

BRIDGE_ENABLED = os.getenv("BRIDGE_ENABLED", "false").lower() == "true"
WITHDRAW_ENABLED = os.getenv("BRIDGE_WITHDRAW_ENABLED", "true").lower() == "true"
WITHDRAW_POLL_INTERVAL = int(os.getenv("BRIDGE_WITHDRAW_POLL_INTERVAL", "30"))
MIN_AIT_WITHDRAW = Decimal(os.getenv("MIN_AIT_WITHDRAW", "0.01"))
ETH_WITHDRAW_GAS = int(os.getenv("ETH_WITHDRAW_GAS", "100000"))
ETH_WITHDRAW_MIN_RESERVE = Decimal(os.getenv("ETH_WITHDRAW_MIN_RESERVE", "0.005"))

_db_initialized = False
_withdraw_polling_enabled: bool = True

_NETWORK_CHAIN_IDS = {
    "mainnet": 1,
    "sepolia": 11155111,
    "goerli": 5,
    "holesky": 17000,
}


def _ensure_db() -> None:
    """Initialize the bridge database exactly once per process."""
    global _db_initialized
    if not _db_initialized:
        init_db()
        _db_initialized = True


def _eth_chain_id() -> int:
    """Return the Ethereum chain id for the configured network."""
    try:
        return int(ETH_NETWORK)
    except Exception:
        return _NETWORK_CHAIN_IDS.get(ETH_NETWORK.lower(), 11155111)


def _release_private_key() -> str:
    """Return the private key that can sign releases for ETH_WALLET_ADDRESS."""
    return ETH_WALLET_PRIVATE_KEY or BRIDGE_ADMIN_PRIVATE_KEY


def _validate_release_key() -> tuple[str, str] | tuple[None, str]:
    """Derive the release address from the configured key and confirm it matches."""
    key = _release_private_key()
    if not key:
        return (None, "No ETH_WALLET_PRIVATE_KEY or BRIDGE_ADMIN_PRIVATE_KEY configured")
    try:
        account = EthAccount.from_key(key)
        derived = account.address
    except Exception as e:
        return (None, f"Failed to derive release address from private key: {e}")
    if canonical_address(derived).lower() != canonical_address(ETH_WALLET_ADDRESS).lower():
        return (None, f"Release key derives to {derived}, expected {ETH_WALLET_ADDRESS}")
    return (key, "")


def _is_valid_eth_address(address: str) -> bool:
    """Return True if ``address`` is a canonical 42-character 0x address."""
    try:
        normalized = canonical_address(address)
    except Exception:
        return False
    return normalized.startswith("0x") and len(normalized) == 42


async def _post_eth_rpc(payload: Any, timeout: float) -> httpx.Response:
    """POST to ETH_RPC_URL, retrying briefly on transient transport errors.

    Mirrors bridge_monitor._post_eth_rpc -- Sepolia/Infura occasionally drops
    a single connection attempt that succeeds again a moment later.
    """
    delays = (0.5, 1.5)
    last_exc: httpx.TransportError | None = None
    for attempt in range(len(delays) + 1):
        try:
            return await SharedHttpClient.post(ETH_RPC_URL, json=payload, timeout=timeout)
        except httpx.TransportError as e:
            last_exc = e
            if attempt < len(delays):
                await asyncio.sleep(delays[attempt])
    assert last_exc is not None
    raise last_exc


async def _eth_rpc(method: str, params: list[Any]) -> Any:
    """Call the Ethereum RPC and return the ``result`` field."""
    payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
    response = await _post_eth_rpc(payload, timeout=10.0)
    response.raise_for_status()
    data = response.json()
    if "error" in data:
        raise RuntimeError(f"{method} error: {data['error']}")
    return data.get("result")


async def _eth_balance(address: str) -> Decimal:
    """Return the ETH balance of ``address`` in ETH (Decimal)."""
    result = await _eth_rpc("eth_getBalance", [address, "latest"])
    return Decimal(int(result, 16)) / Decimal(10**18)


async def _eth_nonce(address: str) -> int:
    """Return the transaction count for ``address``."""
    result = await _eth_rpc("eth_getTransactionCount", [address, "pending"])
    return int(result, 16)


async def _eth_gas_price() -> int:
    """Return the current gas price in wei (integer)."""
    result = await _eth_rpc("eth_gasPrice", [])
    return int(result, 16)


def _pending_eth_reserve() -> Decimal:
    """Sum of ETH currently allocated to pending or insufficient-reserve withdrawals."""
    from .bridge_db import get_pending_withdrawals

    pending = get_pending_withdrawals()
    return Decimal(sum((Decimal(w["amount_eth"]) for w in pending), Decimal("0")))


async def _send_eth(to_address: str, amount_eth: Decimal) -> str:
    """Sign and broadcast an Ethereum transfer, returning the tx hash."""
    key, error = _validate_release_key()
    if not key:
        raise RuntimeError(error)

    account = EthAccount.from_key(key)
    nonce = await _eth_nonce(ETH_WALLET_ADDRESS)
    gas_price = await _eth_gas_price()
    value_wei = int(amount_eth * Decimal(10**18))

    tx = {
        "to": canonical_address(to_address),
        "value": value_wei,
        "gas": ETH_WITHDRAW_GAS,
        "gasPrice": gas_price,
        "nonce": nonce,
        "chainId": _eth_chain_id(),
    }

    signed = account.sign_transaction(tx)
    raw = signed.raw_transaction
    if isinstance(raw, bytes):
        raw = "0x" + raw.hex()
    result = await _eth_rpc("eth_sendRawTransaction", [raw])
    if not result or not isinstance(result, str):
        raise RuntimeError(f"eth_sendRawTransaction returned unexpected result: {result}")
    return result


async def _submit_bridge_refund(recipient: str, amount_ait: Decimal) -> str:
    """Submit a BRIDGE_REFUND transaction to credit AIT back to the user."""
    if not GENESIS_WALLET_ADDRESS or not GENESIS_WALLET_PRIVATE_KEY:
        raise RuntimeError("GENESIS_WALLET_ADDRESS/PRIVATE_KEY not configured")

    async with httpx.AsyncClient(timeout=10.0) as client:
        account_url = f"{BLOCKCHAIN_RPC_URL}/rpc/account/{GENESIS_WALLET_ADDRESS}"
        account_resp = await client.get(account_url)
        account_resp.raise_for_status()
        nonce = account_resp.json().get("nonce", 0)

    from eth_keys import keys as eth_keys
    from eth_utils import keccak

    value = ait_to_units(amount_ait)
    fee = ait_to_units(Decimal("0.01"))

    tx_payload = {
        "type": "BRIDGE_REFUND",
        "chain_id": os.getenv("CHAIN_ID", "ait-hub.aitbc.bubuit.net"),
        "from": canonical_address(GENESIS_WALLET_ADDRESS),
        "to": canonical_address(recipient),
        "amount": value,
        "fee": fee,
        "nonce": nonce,
        "payload": {"amount": value, "reason": "bridge_withdrawal_failed"},
    }

    unsigned = {k: v for k, v in tx_payload.items() if k != "signature"}
    message = json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    private_key_hex = (
        GENESIS_WALLET_PRIVATE_KEY[2:] if GENESIS_WALLET_PRIVATE_KEY.startswith("0x") else GENESIS_WALLET_PRIVATE_KEY
    )
    private_key = eth_keys.PrivateKey(bytes.fromhex(private_key_hex))
    signature = private_key.sign_msg_hash(keccak(message))
    tx_payload["signature"] = signature.to_bytes().hex()

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(f"{BLOCKCHAIN_RPC_URL}/rpc/transaction", json=tx_payload)
        response.raise_for_status()
        result = response.json()
        tx_hash = result.get("transaction_hash") or result.get("tx_hash") or ""
        if not tx_hash:
            raise ValueError(f"No tx hash returned: {result}")
        return tx_hash


async def _refund_withdrawal(ait_tx_hash: str, user: str, gross_ait: Decimal, reason: str) -> None:
    """Issue a BRIDGE_REFUND and update the withdrawal record."""
    try:
        refund_tx_hash = await _submit_bridge_refund(user, gross_ait)
        update_withdrawal_status(ait_tx_hash, "refunded", refund_tx_hash=refund_tx_hash, error=reason)
        logger.info(
            "Refunded %s AIT to %s for failed withdrawal %s (refund tx: %s)", gross_ait, user, ait_tx_hash, refund_tx_hash
        )
    except Exception as e:
        logger.error("Failed to refund withdrawal %s: %s", ait_tx_hash, e)
        update_withdrawal_status(ait_tx_hash, "failed", error=f"refund failed: {e}")


async def _release_eth_for_withdrawal(withdrawal_id: str, ait_tx_hash: str, eth_address: str, amount_eth: Decimal) -> str:
    """Send the ETH release transaction and return the Ethereum tx hash."""
    # Reserve guard: we need the withdrawal amount plus gas cost in ETH.
    gas_price = await _eth_gas_price()
    estimated_gas_cost_eth = Decimal(gas_price * ETH_WITHDRAW_GAS) / Decimal(10**18)
    required = amount_eth + estimated_gas_cost_eth
    available = await _eth_balance(ETH_WALLET_ADDRESS) - _pending_eth_reserve()
    if available < required:
        raise RuntimeError(f"Insufficient ETH reserve: {available} < {required}")

    eth_tx_hash = await _send_eth(eth_address, amount_eth)
    update_withdrawal_status(ait_tx_hash, "completed", eth_tx_hash=eth_tx_hash)
    logger.info(
        "Released %s ETH to %s (ETH tx: %s) for withdrawal %s",
        amount_eth,
        eth_address,
        eth_tx_hash,
        withdrawal_id,
    )
    return eth_tx_hash


async def _process_withdrawal(tx: dict[str, Any]) -> bool:
    """
    Process a single confirmed BRIDGE_WITHDRAW transaction.
    Returns True if a new withdrawal was recorded and release attempted.
    """
    ait_tx_hash = tx.get("tx_hash") or tx.get("hash", "")
    if not ait_tx_hash:
        logger.warning("Skipping withdrawal with no tx hash: %s", tx)
        return False

    if get_withdrawal_by_ait_tx_hash(ait_tx_hash):
        return False

    sender = tx.get("sender") or tx.get("from", "")
    payload = tx.get("payload") or {}
    eth_address = payload.get("eth_address") or ""
    value = int(tx.get("value", 0) or 0)

    if not _is_valid_eth_address(eth_address):
        logger.warning("Skipping withdrawal %s with invalid eth_address: %s", ait_tx_hash, eth_address)
        return False

    gross_ait = units_to_ait(value)
    if gross_ait < MIN_AIT_WITHDRAW:
        logger.info("Skipping withdrawal %s below minimum: %s AIT", ait_tx_hash, gross_ait)
        return False

    estimate = await calculate_eth_amount(gross_ait)
    if not estimate:
        logger.error("Failed to calculate ETH amount for withdrawal %s", ait_tx_hash)
        return False

    amount_eth = estimate["amount_eth"]
    fee_ait = estimate["fee_ait"]
    net_ait = estimate["net_ait"]

    withdrawal_id = insert_withdrawal(
        ait_tx_hash=ait_tx_hash,
        from_address=sender,
        eth_address=canonical_address(eth_address),
        amount_ait=gross_ait,
        fee_ait=fee_ait,
        net_ait=net_ait,
        amount_eth=amount_eth,
    )
    logger.info(
        "Recorded withdrawal %s: %s AIT -> %s ETH for %s",
        withdrawal_id,
        gross_ait,
        amount_eth,
        eth_address,
    )

    try:
        await _release_eth_for_withdrawal(withdrawal_id, ait_tx_hash, eth_address, amount_eth)
        return True
    except Exception as e:
        logger.error("ETH release failed for withdrawal %s: %s", ait_tx_hash, e)
        update_withdrawal_status(ait_tx_hash, "failed", error=str(e))
        # Refund the AIT so the user is not left with a burned balance.
        await _refund_withdrawal(ait_tx_hash, sender, gross_ait, str(e))
        return True


async def get_bridge_withdraw_transactions() -> list[dict[str, Any]]:
    """Fetch recent confirmed BRIDGE_WITHDRAW transactions from the AITBC hub."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        url = f"{BLOCKCHAIN_RPC_URL}/rpc/transactions"
        params: dict[str, str | int] = {
            "transaction_type": "BRIDGE_WITHDRAW",
            "limit": 50,
        }
        response = await client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict):
            return cast(list[dict[str, Any]], data.get("transactions", []))
        if isinstance(data, list):
            return cast(list[dict[str, Any]], data)
        return []


async def poll_withdrawals_once() -> dict[str, Any]:
    """Run a single withdrawal poll cycle."""
    if not BRIDGE_ENABLED or not WITHDRAW_ENABLED:
        return {"scanned": 0, "recorded": 0, "skipped": True, "reason": "bridge/withdraw not enabled"}
    if not ETH_WALLET_ADDRESS:
        return {"scanned": 0, "recorded": 0, "skipped": True, "reason": "ETH_WALLET_ADDRESS not set"}

    _ensure_db()

    key, error = _validate_release_key()
    if not key:
        logger.error("Withdrawal monitor disabled: %s", error)
        return {"scanned": 0, "recorded": 0, "skipped": True, "reason": error}

    transactions = await get_bridge_withdraw_transactions()
    recorded = 0
    for tx in transactions:
        try:
            if await _process_withdrawal(tx):
                recorded += 1
        except Exception as e:
            logger.error("Error processing withdrawal tx %s: %s", tx.get("tx_hash", ""), e)

    return {"scanned": len(transactions), "recorded": recorded, "skipped": False}


async def withdrawal_monitor_loop() -> None:
    """Main loop for the AIT->ETH withdrawal monitor."""
    if not BRIDGE_ENABLED or not WITHDRAW_ENABLED:
        logger.info("Withdrawal monitoring disabled")
        return
    if not ETH_WALLET_ADDRESS:
        logger.info("Withdrawal monitoring disabled (ETH_WALLET_ADDRESS not set)")
        return

    _ensure_db()
    logger.info("Starting AIT->ETH withdrawal monitor")
    logger.info("Withdrawal poll interval: %ss", WITHDRAW_POLL_INTERVAL)

    while True:
        if not _withdraw_polling_enabled:
            logger.info("Withdrawal auto-poll disabled, sleeping")
            await asyncio.sleep(1)
            continue

        try:
            summary = await poll_withdrawals_once()
            if not summary.get("skipped"):
                logger.info("Withdrawal poll completed: %s", summary)
        except Exception as e:
            logger.error("Error in withdrawal monitor loop: %s", e)

        for _ in range(WITHDRAW_POLL_INTERVAL):
            if not _withdraw_polling_enabled:
                break  # type: ignore[unreachable]
            await asyncio.sleep(1)


def start_withdrawal_monitoring() -> asyncio.Task[None] | None:
    """Start the withdrawal monitor as an asyncio task."""
    if not BRIDGE_ENABLED or not WITHDRAW_ENABLED:
        return None

    try:
        task = asyncio.create_task(withdrawal_monitor_loop())
        return task
    except RuntimeError:
        logger.debug("No event loop running; starting withdrawal monitor in a thread", exc_info=True)
        import threading

        def _run_sync() -> None:
            asyncio.run(withdrawal_monitor_loop())

        monitor_thread = threading.Thread(target=_run_sync, daemon=True)
        monitor_thread.start()
        return None


def set_withdraw_polling_enabled(enabled: bool) -> None:
    global _withdraw_polling_enabled
    _withdraw_polling_enabled = enabled
