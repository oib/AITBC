"""
AIT→ETH Bridge Withdrawal Monitor

Polls the AITBC chain for confirmed ``BRIDGE_WITHDRAW`` transactions and releases
ETH from the configured bridge wallet to the Ethereum address in the withdrawal
payload. Failed releases are automatically refunded by an on-chain transfer
from the funding wallet.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
from datetime import datetime
from decimal import Decimal
from typing import Any, cast

import httpx
from eth_account import Account as EthAccount

from aitbc.aitbc_logging import get_logger
from aitbc.network import SharedHttpClient
from aitbc.utils import ait_to_units, units_to_ait
from aitbc.crypto.signature_recovery import canonical_address

from .bridge_db import (
    get_resumable_withdrawals,
    get_withdrawal_by_ait_tx_hash,
    init_db,
    insert_withdrawal,
    update_withdrawal_status,
)
from .price_api import calculate_eth_amount
from .url_redact import redact_text

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
# ETH-14: release gas comes from eth_estimateGas — never a static value.
# Post-Glamsterdam (Sepolia 2026-10-06, EIP-8037 state-gas) a transfer to a
# previously unseen address costs ~207k units; the old fixed 100k guaranteed
# an out-of-gas revert that the ledger still recorded 'completed'.
# ETH_WITHDRAW_GAS is now an *explicit override only* (operator escape
# hatch); unset means estimate. Margin/floor/cap bound the estimate path;
# an estimate error or an over-cap result fails closed before signing.
ETH_WITHDRAW_GAS = os.getenv("ETH_WITHDRAW_GAS", "")
ETH_WITHDRAW_GAS_MARGIN = Decimal(os.getenv("ETH_WITHDRAW_GAS_MARGIN", "1.25"))
ETH_WITHDRAW_GAS_MAX = int(os.getenv("ETH_WITHDRAW_GAS_MAX", "300000"))
_ETH_GAS_FLOOR = 21_000
# Grace window for an *absence-only* outcome on a just-broadcast release.
# Receipt verification now runs on the happy path ~one poll after the
# send, and a lagging / load-balanced RPC can report "no tx, no receipt,
# nonce not pending" while the transaction is still in flight. Refunding
# on that view would double-pay once it seals — so within the grace
# window an absence-only result reports 'unknown' (re-checked next poll)
# instead of 'not_sent'. A status-0 receipt is never ambiguous and keeps
# returning 'not_sent' at any age.
ETH_RELEASE_ABSENCE_GRACE_SECONDS = int(os.getenv("ETH_RELEASE_ABSENCE_GRACE_SECONDS", "600"))
ETH_WITHDRAW_MIN_RESERVE = Decimal(os.getenv("ETH_WITHDRAW_MIN_RESERVE", "0.005"))
# ETH nonce serialization across the three release lanes (withdraw, sell
# escrow, exchange settlement): the nonce comes from
# eth_getTransactionCount(pending), so two lanes racing fetch→sign→broadcast
# can read the same count and collide — the loser then parks in
# needs_review. One shared lock keeps a lane's whole nonce→sign→broadcast
# section atomic; the second lane's pending-count then sees the first's tx.
ETH_RELEASE_NONCE_LOCK = asyncio.Lock()
# Confirmation depth a release receipt must reach before it counts as proof.
# Defaults to the deposit-side BRIDGE_CONFIRMATIONS (3) so both directions
# agree on finality.
ETH_RELEASE_CONFIRMATIONS = int(os.getenv("BRIDGE_RELEASE_CONFIRMATIONS", os.getenv("BRIDGE_CONFIRMATIONS", "3")))

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
    try:
        response = await _post_eth_rpc(payload, timeout=10.0)
        response.raise_for_status()
    except httpx.HTTPError as e:
        # httpx error text embeds the full request URL — redact it (ETH-15).
        raise RuntimeError(f"{method} request failed: {redact_text(str(e))}") from e
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


async def _eth_estimate_gas(to_address: str, value_wei: int) -> int:
    """eth_estimateGas for the exact release call from the bridge wallet."""
    result = await _eth_rpc(
        "eth_estimateGas",
        [
            {
                "from": canonical_address(ETH_WALLET_ADDRESS),
                "to": canonical_address(to_address),
                "value": hex(value_wei),
            },
            "latest",
        ],
    )
    return int(result, 16)


async def _release_gas_limit(to_address: str, amount_eth: Decimal) -> int:
    """Gas limit for a release tx: estimate x margin, floored, hard-capped.

    Fail closed: an RPC error or an over-cap estimate raises before any
    signing or intent write — a release is never sent with unverified gas.
    A set ETH_WITHDRAW_GAS overrides the estimate entirely (documented
    escape hatch — a stale static value is exactly how ETH-14 happened).
    """
    if ETH_WITHDRAW_GAS:
        limit = int(ETH_WITHDRAW_GAS)
        if limit <= 0 or limit > ETH_WITHDRAW_GAS_MAX:
            raise RuntimeError(f"ETH_WITHDRAW_GAS={limit} outside (0, {ETH_WITHDRAW_GAS_MAX}]")
        logger.warning("ETH_WITHDRAW_GAS=%d override in use — estimate skipped", limit)
        return limit
    estimate = await _eth_estimate_gas(to_address, int(amount_eth * Decimal(10**18)))
    limit = max(_ETH_GAS_FLOOR, math.ceil(Decimal(estimate) * ETH_WITHDRAW_GAS_MARGIN))
    if limit > ETH_WITHDRAW_GAS_MAX:
        raise RuntimeError(
            f"release gas estimate {estimate} (x{ETH_WITHDRAW_GAS_MARGIN} = {limit}) "
            f"exceeds ETH_WITHDRAW_GAS_MAX={ETH_WITHDRAW_GAS_MAX}"
        )
    return limit


def _pending_eth_reserve() -> Decimal:
    """Sum of ETH currently allocated to pending or insufficient-reserve withdrawals.

    Includes pending sell-escrow locks (ETH-10) and open exchange
    settlements (ETH-8 phase 3): all three lanes draw from the same
    bridge-wallet float, so each side's reserve check must see the others'
    in-flight rows. The sell-side sum excludes 'failed' rows.
    """
    from .bridge_db import get_exchange_pending_eth_reserve, get_pending_withdrawals, get_sell_pending_eth_reserve

    pending = get_pending_withdrawals()
    withdraw_sum = Decimal(sum((Decimal(w["amount_eth"]) for w in pending), Decimal("0")))
    try:
        sell_sum = get_sell_pending_eth_reserve()
    except Exception:  # noqa: BLE001 - pre-ETH-10 databases lack the sell tables — reserve must not depend on them
        # Pre-ETH-10 databases lack the sell tables; withdraw reserve must not
        # depend on them existing.
        sell_sum = Decimal("0")
    try:
        exchange_sum = get_exchange_pending_eth_reserve()
    except Exception:  # noqa: BLE001 - same fail-open: a pre-phase-3 database may lack the table
        # Same fail-open as the sell term: a pre-phase-3 database may lack
        # the table; reserve must not depend on it existing.
        exchange_sum = Decimal("0")
    return withdraw_sum + sell_sum + exchange_sum


def _sign_release_tx(
    account: Any,
    to_address: str,
    amount_eth: Decimal,
    nonce: int,
    gas_price: int,
    gas_limit: int,
) -> tuple[str, str]:
    """Build and sign the release transaction, returning (raw_tx, tx_hash).

    The hash is deterministic for the signed payload, so it is known
    *before* broadcast — the monitor persists it as the send id so a
    crash between broadcast and status write can still identify the
    transaction on-chain. ``gas_limit`` comes from _release_gas_limit.
    """
    value_wei = int(amount_eth * Decimal(10**18))
    tx = {
        "to": canonical_address(to_address),
        "value": value_wei,
        "gas": gas_limit,
        "gasPrice": gas_price,
        "nonce": nonce,
        "chainId": _eth_chain_id(),
    }
    signed = account.sign_transaction(tx)
    raw = signed.raw_transaction
    if isinstance(raw, bytes):
        raw = "0x" + raw.hex()
    tx_hash = signed.hash.hex()
    if not tx_hash.startswith("0x"):
        tx_hash = "0x" + tx_hash
    return raw, tx_hash


async def _broadcast_release_tx(raw: str) -> str:
    """Broadcast a signed raw transaction, returning the tx hash the node reports."""
    result = await _eth_rpc("eth_sendRawTransaction", [raw])
    if not result or not isinstance(result, str):
        raise RuntimeError(f"eth_sendRawTransaction returned unexpected result: {result}")
    return result


async def _send_eth(to_address: str, amount_eth: Decimal) -> str:
    """Sign and broadcast an Ethereum transfer, returning the tx hash.

    Broadcast only — a returned hash is NOT proof of payment. The caller
    owns receipt verification (_release_receipt_outcome); never record a
    send as complete on the broadcast echo alone (ETH-14).
    """
    key, error = _validate_release_key()
    if not key:
        raise RuntimeError(error)

    account = EthAccount.from_key(key)
    gas_price = await _eth_gas_price()
    gas_limit = await _release_gas_limit(to_address, amount_eth)
    async with ETH_RELEASE_NONCE_LOCK:
        nonce = await _eth_nonce(ETH_WALLET_ADDRESS)
        raw, eth_tx_hash = _sign_release_tx(account, to_address, amount_eth, nonce, gas_price, gas_limit)
        sent = await _broadcast_release_tx(raw)
    if sent.lower() != eth_tx_hash.lower():
        logger.warning("eth_sendRawTransaction returned %s, expected signed hash %s", sent, eth_tx_hash)
    return eth_tx_hash


async def _submit_bridge_refund(recipient: str, amount_ait: Decimal) -> str:
    """Submit the refund transaction returning AIT to the user."""
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
        # An ordinary spend out of the funding wallet: TRANSFER debits it and
        # credits the user. The BRIDGE_* credit types are issued inside the
        # node and are refused at public transaction intake.
        "type": "TRANSFER",
        "chain_id": os.getenv("CHAIN_ID", "ait-localnet"),
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
    """Issue the AIT refund and update the withdrawal record."""
    try:
        refund_tx_hash = await _submit_bridge_refund(user, gross_ait)
        update_withdrawal_status(ait_tx_hash, "refunded", refund_tx_hash=refund_tx_hash, error=reason)
        logger.info(
            "Refunded %s AIT to %s for failed withdrawal %s (refund tx: %s)", gross_ait, user, ait_tx_hash, refund_tx_hash
        )
    except Exception as e:
        logger.error("Failed to refund withdrawal %s: %s", ait_tx_hash, e)
        update_withdrawal_status(ait_tx_hash, "failed", error=f"refund failed: {e}")


_STATUS_PERSIST_ATTEMPTS = 3
_STATUS_PERSIST_DELAYS = (0.5, 1.5)


async def _update_status_with_retry(
    ait_tx_hash: str,
    status: str,
    *,
    eth_tx_hash: str | None = None,
    refund_tx_hash: str | None = None,
    release_nonce: int | None = None,
    error: str | None = None,
) -> bool:
    """Persist a withdrawal status, retrying transient DB errors.

    A status write that fails after an ETH send must never be allowed to
    fall through to a refund path: the caller either persists or raises,
    and the caller's except branch verifies on-chain before doing anything.
    """
    last_exc: Exception | None = None
    for attempt in range(_STATUS_PERSIST_ATTEMPTS):
        try:
            return update_withdrawal_status(
                ait_tx_hash,
                status,
                eth_tx_hash=eth_tx_hash,
                refund_tx_hash=refund_tx_hash,
                error=error,
                release_nonce=release_nonce,
            )
        except Exception as e:  # noqa: BLE001 - persist retry — any store failure alike
            last_exc = e
            logger.error(
                "Failed to persist withdrawal %s status %s (attempt %d/%d): %s",
                ait_tx_hash,
                status,
                attempt + 1,
                _STATUS_PERSIST_ATTEMPTS,
                e,
            )
            if attempt < _STATUS_PERSIST_ATTEMPTS - 1:
                await asyncio.sleep(_STATUS_PERSIST_DELAYS[attempt])
    raise RuntimeError(f"could not persist withdrawal {ait_tx_hash} status {status}: {last_exc}")


async def _release_eth_for_withdrawal(
    withdrawal_id: str,
    ait_tx_hash: str,
    eth_address: str,
    amount_eth: Decimal,
    *,
    intent_status: str = "releasing",
    nonce: int | None = None,
) -> str:
    """Send the ETH release transaction and return the Ethereum tx hash.

    Ordering guarantees (ETH-9/ETH-14): the intent (``intent_status`` +
    nonce + deterministic tx hash) is persisted BEFORE broadcast, and the
    row stays there — 'completed' is written only by the verified-outcome
    paths (_resume_unfinished_releases / _resolve_release_failure / the
    release-retry command), never right after broadcast. A reverted or
    dropped release can never again be recorded as paid.

    ``intent_status`` is 'releasing_retry' for operator-driven re-releases
    so the resume pass parks a failed retry ('needs_review_release')
    instead of auto-refunding — the refund decision stays with the
    operator. ``nonce`` overrides the pending-count nonce (used to reuse a
    provably free nonce when a prior broadcast never sealed).
    """
    # Reserve guard: we need the withdrawal amount plus gas cost in ETH.
    gas_price = await _eth_gas_price()
    gas_limit = await _release_gas_limit(eth_address, amount_eth)
    estimated_gas_cost_eth = Decimal(gas_price * gas_limit) / Decimal(10**18)
    required = amount_eth + estimated_gas_cost_eth
    available = await _eth_balance(ETH_WALLET_ADDRESS) - _pending_eth_reserve()
    if available < required:
        raise RuntimeError(f"Insufficient ETH reserve: {available} < {required}")

    key, error = _validate_release_key()
    if not key:
        raise RuntimeError(error)
    account = EthAccount.from_key(key)
    async with ETH_RELEASE_NONCE_LOCK:
        if nonce is None:
            nonce = await _eth_nonce(ETH_WALLET_ADDRESS)
        raw, eth_tx_hash = _sign_release_tx(account, eth_address, amount_eth, nonce, gas_price, gas_limit)

        # Persist intent BEFORE broadcast: a crash after this line leaves
        # evidence (nonce + deterministic hash) the resume check can verify.
        await _update_status_with_retry(ait_tx_hash, intent_status, eth_tx_hash=eth_tx_hash, release_nonce=nonce)

        sent = await _broadcast_release_tx(raw)
    if sent.lower() != eth_tx_hash.lower():
        logger.warning("Broadcast reported %s; keeping signed hash %s", sent, eth_tx_hash)

    logger.info(
        "Broadcast release %s ETH to %s (ETH tx: %s, gas %d) for withdrawal %s — awaiting receipt proof",
        amount_eth,
        eth_address,
        eth_tx_hash,
        gas_limit,
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
        # Never refund blind: a DB error after the broadcast can land us here
        # with the ETH already gone. Verify against the chain first.
        await _resolve_release_failure(ait_tx_hash, sender, gross_ait, e)
        return True


def _receipt_status(receipt: dict[str, Any]) -> int:
    """Normalize an eth_getTransactionReceipt status (hex string or int) to int."""
    status = receipt.get("status")
    return int(status, 16) if isinstance(status, str) else int(status or 0)


async def _release_receipt_outcome(eth_tx_hash: str) -> str | None:
    """Outcome for the recorded hash: 'sent'/'not_sent'/'unknown', or None
    when the hash is absent from the chain entirely (fall back to nonce)."""
    tx = await _eth_rpc("eth_getTransactionByHash", [eth_tx_hash])
    receipt = await _eth_rpc("eth_getTransactionReceipt", [eth_tx_hash])
    if receipt is not None:
        if _receipt_status(receipt) != 1:
            # Reverted send: ETH never moved, nonce burned by our tx.
            return "not_sent"
        latest_block = int(await _eth_rpc("eth_blockNumber", []), 16)
        receipt_block = int(receipt.get("blockNumber") or "0x0", 16)
        if receipt_block and latest_block - receipt_block + 1 >= ETH_RELEASE_CONFIRMATIONS:
            return "sent"
        # Confirmed but below the required depth — re-checked next poll.
        return "unknown"
    if tx is not None:
        # Broadcast reached a node but is not mined yet — undecidable.
        return "unknown"
    return None


async def _release_nonce_outcome(row: dict[str, Any]) -> tuple[str | None, str | None]:
    """(outcome, reason) from the recorded nonce, or (None, None) when the
    nonce view cannot decide.

    'nonce_consumed' — the latest nonce passed the recorded release nonce
    without a qualifying receipt for the recorded hash: a manual send or
    replacement may have taken the nonce while the recorded release never
    landed. A real anomaly, never routine lag.
    'nonce_pending' — the recorded nonce is still visible in the pending
    pool: the broadcast reached the chain and awaits mining. Routine.
    """
    nonce = row.get("release_nonce")
    if nonce is None:
        return None, None
    latest = int(await _eth_rpc("eth_getTransactionCount", [ETH_WALLET_ADDRESS, "latest"]), 16)
    pending = int(await _eth_rpc("eth_getTransactionCount", [ETH_WALLET_ADDRESS, "pending"]), 16)
    if latest > nonce:
        logger.error(
            "Withdrawal %s: release nonce %d consumed but no qualifying receipt for recorded hash %s (latest=%d, pending=%d)",
            row.get("ait_tx_hash"),
            nonce,
            row.get("eth_tx_hash"),
            latest,
            pending,
        )
        return "unknown", "nonce_consumed"
    if pending > nonce:
        return "unknown", "nonce_pending"
    return None, None


def _release_intent_age_seconds(row: dict[str, Any]) -> float:
    """Seconds since the release intent was persisted for this row.

    ``released_at`` is refreshed by every non-terminal status write on both
    withdrawal rows and sell locks — for an in-flight row it is the moment
    the 'releasing'/'releasing_retry' intent (nonce + deterministic hash)
    was written, i.e. the broadcast time. A missing or unparseable value
    means infinitely old — no grace — so crash-recovery rows keep their
    previous resolution.
    """
    raw = row.get("released_at")
    if not raw:
        return float("inf")
    try:
        return (datetime.now() - datetime.fromisoformat(str(raw))).total_seconds()
    except (TypeError, ValueError):
        return float("inf")


async def _compose_release_outcome_detail(row: dict[str, Any]) -> tuple[str, str]:
    """(outcome, reason) — the _compose_release_outcome contract plus *why*
    'unknown' was returned, so a caller can log an in-grace absence quietly
    and anything genuinely unverifiable loudly (ETH-15).

    reason is one of: 'chain_view' (a receipt or mempool view decided),
    'nonce_consumed'/'nonce_pending' (the nonce view — see
    _release_nonce_outcome), 'absent_in_grace' (nothing visible, still
    young — normal propagation lag), 'absent_expired', or 'verify_error'.
    """
    try:
        eth_tx_hash = row.get("eth_tx_hash")
        if eth_tx_hash:
            outcome = await _release_receipt_outcome(eth_tx_hash)
            if outcome is not None:
                return outcome, "chain_view"
        nonce_outcome, nonce_reason = await _release_nonce_outcome(row)
        if nonce_outcome is not None:
            return nonce_outcome, nonce_reason or "nonce_view"
        # Absence-only view: no receipt, no tx, nonce not visibly pending.
        # A lagging endpoint can report this for a tx still in flight —
        # within ETH_RELEASE_ABSENCE_GRACE_SECONDS it is 'unknown', never
        # a refund trigger (a proven revert above already returned).
        if _release_intent_age_seconds(row) < ETH_RELEASE_ABSENCE_GRACE_SECONDS:
            return "unknown", "absent_in_grace"
        return "not_sent", "absent_expired"
    except Exception as e:  # noqa: BLE001 - verify containment — an unverifiable outcome is unknown, never guessed
        logger.error("Release outcome verification failed for %s: %s", row.get("ait_tx_hash"), e)
        return "unknown", "verify_error"


async def _compose_release_outcome(row: dict[str, Any]) -> str:
    """Verify a persisted release row's ETH outcome: 'sent'/'not_sent'/'unknown'.

    Shared by the withdrawal and sell-escrow monitors — the single
    implementation of "is the ETH out?". The row dict must carry
    ``eth_tx_hash``, ``release_nonce`` and ``ait_tx_hash`` (log context).
    """
    outcome, _reason = await _compose_release_outcome_detail(row)
    return outcome


async def _verify_release_outcome_detail(ait_tx_hash: str) -> tuple[str, str]:
    """_verify_release_outcome plus the 'unknown' reason — see
    _compose_release_outcome_detail for the reason vocabulary."""
    try:
        row = get_withdrawal_by_ait_tx_hash(ait_tx_hash)
    except Exception as e:  # noqa: BLE001 - verify containment — row unreadable means outcome unknown
        logger.error("Could not read withdrawal %s for release verification: %s", ait_tx_hash, e)
        return "unknown", "verify_error"
    if not row:
        # A missing row proves nothing about the chain.
        return "unknown", "verify_error"

    return await _compose_release_outcome_detail(row)


async def _verify_release_outcome(ait_tx_hash: str) -> str:
    """Return 'sent', 'not_sent' or 'unknown' for a withdrawal's ETH release.

    'sent' requires a successful receipt for the *recorded* tx hash at
    ``ETH_RELEASE_CONFIRMATIONS`` depth. A consumed nonce alone is never
    proof — a manual send from the bridge wallet can consume it while the
    recorded release never landed. 'not_sent' is only returned on positive
    proof — failed receipt, or neither the hash nor the nonce ever appeared
    on-chain. Anything ambiguous, including a missing row or RPC failures,
    is 'unknown' so the caller never refunds blind.
    """
    outcome, _reason = await _verify_release_outcome_detail(ait_tx_hash)
    return outcome


async def _resolve_release_failure(ait_tx_hash: str, sender: str, gross_ait: Decimal, exc: Exception) -> None:
    """Decide what a failed release attempt means — refund only on proof.

    'sent'  -> the ETH did leave; completing the row is the only safe end.
    'not_sent' -> proven never released; mark failed and refund the AIT.
    'unknown' -> do not refund; mark needs_review for the operator.
    """
    outcome = await _verify_release_outcome(ait_tx_hash)
    if outcome == "sent":
        logger.warning(
            "ETH release for withdrawal %s succeeded despite error (%s); completing the row",
            ait_tx_hash,
            exc,
        )
        try:
            await _update_status_with_retry(ait_tx_hash, "completed")
        except Exception as persist_err:  # noqa: BLE001 - persist best-effort inside the confirmed-error path
            logger.error("Could not persist completion for %s: %s", ait_tx_hash, persist_err)
    elif outcome == "not_sent":
        update_withdrawal_status(ait_tx_hash, "failed", error=str(exc))
        # Refund the AIT so the user is not left with a burned balance.
        await _refund_withdrawal(ait_tx_hash, sender, gross_ait, str(exc))
    else:
        update_withdrawal_status(
            ait_tx_hash,
            "needs_review",
            error=f"release outcome unverifiable: {exc}",
        )
        logger.error(
            "Withdrawal %s marked needs_review — ETH release outcome unverifiable: %s",
            ait_tx_hash,
            exc,
        )


async def _resume_unfinished_releases() -> dict[str, int]:
    """Re-verify 'releasing'/'needs_review' rows against the chain.

    Runs every poll and covers restart-after-crash: the persisted nonce
    and deterministic tx hash let the check prove what already happened.
    Proven-sent rows complete; proven-unsent rows fail and refund;
    unknown rows stay open for the operator.
    """
    resolved = {"completed": 0, "failed": 0, "parked": 0, "still_open": 0}
    for row in get_resumable_withdrawals():
        try:
            outcome, reason = await _verify_release_outcome_detail(row["ait_tx_hash"])
            if outcome == "sent":
                await _update_status_with_retry(row["ait_tx_hash"], "completed")
                resolved["completed"] += 1
                logger.info("Resumed withdrawal %s: ETH release confirmed on chain", row["ait_tx_hash"])
            elif outcome == "not_sent":
                if row["status"] == "releasing_retry":
                    # Operator-driven retry: park, never auto-refund — the
                    # refund path is the operator's deliberate fallback
                    # (mark-review), not an automatic outcome (ETH-14).
                    update_withdrawal_status(
                        row["ait_tx_hash"],
                        "needs_review_release",
                        error="release retry reverted or never landed — operator decision required",
                    )
                    resolved["parked"] += 1
                    logger.error(
                        "Withdrawal %s: release retry proven unsent — parked needs_review_release",
                        row["ait_tx_hash"],
                    )
                else:
                    update_withdrawal_status(row["ait_tx_hash"], "failed", error="release never reached the chain")
                    await _refund_withdrawal(
                        row["ait_tx_hash"],
                        row["from_address"],
                        Decimal(str(row["amount_ait"])),
                        "release never reached the chain",
                    )
                    resolved["failed"] += 1
            else:
                resolved["still_open"] += 1
                age = _release_intent_age_seconds(row)
                age_txt = f"{int(age)}s" if age != float("inf") else "unknown"
                if reason == "absent_in_grace":
                    # Normal propagation lag on a just-broadcast send —
                    # routine, not an incident (ETH-15).
                    logger.info(
                        "Withdrawal %s (%s) not yet visible on-chain — inside absence grace; rechecking (age=%s)",
                        row["ait_tx_hash"],
                        row["status"],
                        age_txt,
                    )
                elif reason in ("chain_view", "nonce_pending") and age < ETH_RELEASE_ABSENCE_GRACE_SECONDS:
                    # Just-broadcast release whose chain view is merely
                    # pending or below confirmation depth — a normal
                    # delay, not an incident (ETH-18). verify_error and a
                    # consumed nonce keep ERROR regardless of age.
                    logger.info(
                        "Withdrawal %s (%s) not yet confirmed on-chain — reason=%s, age=%s (grace %ds); rechecking",
                        row["ait_tx_hash"],
                        row["status"],
                        reason,
                        age_txt,
                        ETH_RELEASE_ABSENCE_GRACE_SECONDS,
                    )
                else:
                    logger.error(
                        "Withdrawal %s (%s) still unverifiable — needs review (reason=%s, age=%s)",
                        row["ait_tx_hash"],
                        row["status"],
                        reason,
                        age_txt,
                    )
        except Exception as e:  # noqa: BLE001 - row containment — a failed resume check must not kill the pass
            resolved["still_open"] += 1
            logger.error("Resume check failed for withdrawal %s: %s", row.get("ait_tx_hash"), e)
    return resolved


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

    # Re-verify rows left mid-flight by a crash or restart before scanning
    # for new withdrawals — the same on-chain checks decide their fate.
    try:
        resume = await _resume_unfinished_releases()
        if any(resume.values()):
            logger.info("Release resume pass: %s", resume)
    except Exception as e:  # noqa: BLE001 - resume pass containment — logged, retried next poll
        logger.error("Release resume pass failed: %s", e)

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
