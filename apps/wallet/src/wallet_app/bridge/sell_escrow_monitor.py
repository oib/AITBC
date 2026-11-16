"""
Escrowed AIT→ETH sell monitor (ETH-10 phase 1, Sepolia only).

Polls the AITBC chain for TRANSFERs sent to the dedicated ``AIT_SELL_ESCROW``
address carrying ``payload.sell_quote``. A matched quote lets the hub release
ETH from its own bridge wallet; the escrowed AIT then settles to the hub
treasury. Locks with no live quote, expired deadlines or failed releases are
refunded escrow → shop. The escrow key is hub custody infrastructure — it can
move only the AIT shops locked in, never a node wallet.

Fail closed: ``SELL_ESCROW_ENABLED`` defaults to false, and without
``AIT_SELL_ESCROW`` (address) + ``SELL_ESCROW_WALLET_PATH`` /
``SELL_ESCROW_CREDENTIAL_FILE`` (the escrow key slot, custodied like an
ops-signer entry: encrypted wallet JSON + sealed credential) +
``SELL_TREASURY_ADDRESS`` the monitor and quote routes stay disabled; nothing
falls back to the bridge payout key or the treasury key. Key material is read
from the slot at signing time only — never from an env value, never logged.
ETH release and outcome verification reuse the ETH-9/ETH-9b machinery in
``bridge_withdraw_monitor`` — there is no second "is the ETH out?" here.

Escrow sweeps (settle → treasury, refund → shop) are serialized: at most one
is in flight at a time, and a row leaves ``settling``/``refunding`` only when
its outflow is found *sealed* — matched on nonce + recipient + amount +
``payload.sell_ref`` — or resolved to ``needs_review_sweep``. Each sweep spends the
moved amount plus the standard 0.01 AIT fee; the escrow needs a small seed
AIT balance for those fees (see docs/ops/sell-escrow-runbook.md).
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass

from wallet_app.utc_time import parse_stored, utc_now
from decimal import Decimal
from typing import Any, cast

import httpx

from aitbc.aitbc_logging import get_logger
from aitbc.async_tasks import create_task_with_logging
from aitbc.utils import units_to_ait
from aitbc.utils.env import subprocess_env
from aitbc.crypto.signature_recovery import canonical_address

from . import bridge_withdraw_monitor as wdm
from .bridge_db import (
    get_open_sell_locks,
    get_sell_lock_by_ait_tx_hash,
    get_sell_pending_eth_reserve,
    get_sell_quote,
    get_sell_quotes_by_status,
    init_db,
    insert_sell_lock,
    update_sell_lock_status as update_sell_lock_status,
    update_sell_quote_status,
)

# Re-exported so tests' ``sellmon.get_eth_prices_fresh`` patches and the
# settlement module's deferred delegates keep resolving at call time.
from .price_api import get_eth_prices_fresh as get_eth_prices_fresh
from .sell_escrow_settlement import (
    AIT_ESCROW_SWEEP_LOCK as AIT_ESCROW_SWEEP_LOCK,
    _FEE_FLOAT_DEFICIT_MARK as _FEE_FLOAT_DEFICIT_MARK,
    _SELL_BINDING_STATUSES as _SELL_BINDING_STATUSES,
    _SELL_STATUS_HANDLERS as _SELL_STATUS_HANDLERS,
    _eth_for_lock_at_quote as _eth_for_lock_at_quote,
    _escrow_sweep as _escrow_sweep,
    _exchange_inflight_sweep as _exchange_inflight_sweep,
    _expected_sweep as _expected_sweep,
    _fee_float_warned as _fee_float_warned,
    _find_escrow_outflow as _find_escrow_outflow,
    _handle_inflight as _handle_inflight,
    _handle_locked as _handle_locked,
    _handle_orphaned as _handle_orphaned,
    _handle_released as _handle_released,
    _handle_stale_price as _handle_stale_price,
    _parked_refund_reason as _parked_refund_reason,
    _price_lock_eth_amount as _price_lock_eth_amount,
    _process_sell_lock as _process_sell_lock,
    _quote_admits_lock as _quote_admits_lock,
    _refund_lock as _refund_lock,
    _refund_pending_lock as _refund_pending_lock,
    _refund_queued_fee_lock as _refund_queued_fee_lock,
    _release_eth_for_lock as _release_eth_for_lock,
    _resolve_escrow_sweep as _resolve_escrow_sweep,
    _resolve_lock_release_failure as _resolve_lock_release_failure,
    _settle_lock as _settle_lock,
    _sign_escrow_transfer as _sign_escrow_transfer,
    _sweep_fee_ait as _sweep_fee_ait,
    _update_lock_status_with_retry as _update_lock_status_with_retry,
    _verify_sell_release_outcome as _verify_sell_release_outcome,
    compute_sell_quote as compute_sell_quote,
)

logger = get_logger(__name__)

_db_initialized = False
_sell_polling_enabled: bool = True


# A row in one of these statuses holds a persisted sweep intent (escrow
# nonce + signed blob). Sweep serialization: at most one may exist; a new
# sweep waits until it is sealed or resolved.
_INFLIGHT_SWEEP_STATUSES = ("settling", "refunding")


@dataclass(frozen=True)
class SellConfig:
    """Validated sell-escrow configuration. Carries only the key *slot*
    locations (wallet JSON + sealed credential paths) — key material is
    loaded inside the signing call frame and never stored here."""

    escrow_address: str
    escrow_wallet_path: str
    escrow_credential_file: str
    escrow_credential_name: str
    treasury_address: str
    chain_id: str
    max_eth_per_tx: Decimal
    max_eth_per_day: Decimal
    min_reserve_eth: Decimal
    max_payout_fraction: Decimal
    release_deadline_seconds: int
    orphan_blocks: int
    sell_seal_depth: int
    quote_expiry_seconds: int
    poll_interval: int


def _decimal_env(env: str, default: str) -> Decimal:
    raw = os.getenv(env, default)
    try:
        value = Decimal(raw)
    except (ArithmeticError, TypeError, ValueError) as e:
        raise ValueError(f"{env}={raw!r} is not a number") from e
    if value <= 0:
        raise ValueError(f"{env}={raw!r} must be positive")
    return value


def _positive_int_env(env: str, default: str) -> int:
    raw = os.getenv(env, default)
    try:
        value = int(raw)
    except (TypeError, ValueError) as e:
        raise ValueError(f"{env}={raw!r} is not an integer") from e
    if value <= 0:
        raise ValueError(f"{env}={raw!r} must be positive")
    return value


def _sell_config() -> SellConfig:
    """Parse and validate sell-escrow env config.

    Missing cap/reserve/deadline keys use the documented defaults; an invalid
    value raises ValueError so the monitor refuses to start while the
    withdraw monitor keeps running. Missing escrow/signer/treasury raises —
    there is no fallback key.
    """
    escrow_address = os.getenv("AIT_SELL_ESCROW", "")
    wallet_path = os.getenv("SELL_ESCROW_WALLET_PATH", "/var/lib/aitbc/wallets/ait-sell-escrow.json")
    credential_file = os.getenv("SELL_ESCROW_CREDENTIAL_FILE", "/etc/aitbc/credentials/sell-escrow-pass")
    credential_name = os.getenv("SELL_ESCROW_CREDENTIAL_NAME", "sell-escrow-pass")
    treasury = os.getenv("SELL_TREASURY_ADDRESS", "")
    if not escrow_address:
        raise ValueError("AIT_SELL_ESCROW (escrow address) not configured")
    if not wallet_path:
        raise ValueError("SELL_ESCROW_WALLET_PATH (escrow key slot) not configured")
    if not credential_file:
        raise ValueError("SELL_ESCROW_CREDENTIAL_FILE (escrow key slot) not configured")
    if not treasury:
        raise ValueError("SELL_TREASURY_ADDRESS (settle target) not configured")
    # No default: signing a sweep on the wrong chain id is how replayed or
    # rejected transactions happen. Missing env = refuse to sign.
    chain_id = os.getenv("CHAIN_ID", "")
    if not chain_id:
        raise ValueError("CHAIN_ID not configured — refusing to sign escrow sweeps")

    return SellConfig(
        escrow_address=canonical_address(escrow_address),
        escrow_wallet_path=wallet_path,
        escrow_credential_file=credential_file,
        escrow_credential_name=credential_name,
        treasury_address=canonical_address(treasury),
        chain_id=chain_id,
        max_eth_per_tx=_decimal_env("SELL_MAX_ETH_PER_TX", "0.01"),
        max_eth_per_day=_decimal_env("SELL_MAX_ETH_PER_DAY", "0.03"),
        min_reserve_eth=_decimal_env("ETH_WITHDRAW_MIN_RESERVE", "0.005"),
        max_payout_fraction=_decimal_env("BRIDGE_MAX_PAYOUT_FRACTION", "0.5"),
        release_deadline_seconds=_positive_int_env("SELL_RELEASE_DEADLINE", "3600"),
        orphan_blocks=_positive_int_env("SELL_LOCK_ORPHAN_BLOCKS", "150"),
        # #1269: AIT-side seal depth a sell lock must reach before the monitor
        # spends anything on it (ETH release or AIT refund). Same convention as
        # bridge_withdraw_monitor.WITHDRAW_SEAL_DEPTH: defaults to the
        # deposit-side BRIDGE_CONFIRMATIONS (3); a tip-height lock can still
        # reorg out, which would leave ETH released against un-sealed AIT.
        sell_seal_depth=int(os.getenv("SELL_SEAL_DEPTH", os.getenv("BRIDGE_CONFIRMATIONS", "3"))),
        quote_expiry_seconds=_positive_int_env("SELL_QUOTE_EXPIRY_SECONDS", "900"),
        poll_interval=_positive_int_env("SELL_POLL_INTERVAL", "30"),
    )


def sell_feature_enabled() -> bool:
    """Master switch: BRIDGE_ENABLED + SELL_ESCROW_ENABLED (default off)."""
    return wdm.BRIDGE_ENABLED and os.getenv("SELL_ESCROW_ENABLED", "false").lower() == "true"


def sell_config_status() -> tuple[bool, str]:
    """(enabled, reason) — the fail-closed gate routes and the monitor share."""
    if os.getenv("SELL_ESCROW_ENABLED", "false").lower() != "true":
        return (False, "sell escrow disabled")
    if not wdm.BRIDGE_ENABLED:
        return (False, "bridge disabled")
    try:
        _sell_config()
    except ValueError as e:
        return (False, str(e))
    return (True, "")


def sell_status_document() -> dict[str, Any]:
    """Non-secret sell-lane status document (CLI-5).

    One shape for the admin route and the sell_admin status verb: the
    fail-closed (enabled, reason) pair, the feature flags, and the parsed
    config minus every secret-bearing field — key-slot paths and credential
    names appear only as configured booleans, never their contents.
    """
    enabled, reason = sell_config_status()
    doc: dict[str, Any] = {
        "enabled": enabled,
        "reason": reason,
        "feature_enabled": sell_feature_enabled(),
        "flags": {
            "bridge_enabled": bool(wdm.BRIDGE_ENABLED),
            "sell_escrow_enabled": os.getenv("SELL_ESCROW_ENABLED", "false").lower() == "true",
        },
        "config": None,
    }
    try:
        cfg = _sell_config()
    except ValueError:
        return doc
    doc["config"] = {
        "chain_id": cfg.chain_id,
        "escrow_address": cfg.escrow_address,
        "treasury_address": cfg.treasury_address,
        "max_eth_per_tx": str(cfg.max_eth_per_tx),
        "max_eth_per_day": str(cfg.max_eth_per_day),
        "min_reserve_eth": str(cfg.min_reserve_eth),
        "max_payout_fraction": str(cfg.max_payout_fraction),
        "release_deadline_seconds": cfg.release_deadline_seconds,
        "orphan_blocks": cfg.orphan_blocks,
        "quote_expiry_seconds": cfg.quote_expiry_seconds,
        "poll_interval": cfg.poll_interval,
        "escrow_wallet_configured": bool(cfg.escrow_wallet_path),
        "escrow_credential_configured": bool(cfg.escrow_credential_file and cfg.escrow_credential_name),
    }
    return doc


# ---------------------------------------------------------------------------
# Escrow key slot — the ops-signer custody mechanism
#
# The escrow key lives in an encrypted wallet JSON file (same format the CLI
# and ops-signer read), with the wallet password sealed by systemd-creds and
# reached either through $CREDENTIALS_DIRECTORY/<name> (systemd
# LoadCredentialEncrypted) or `systemd-creds decrypt` on the credential file
# (LXC hosts, where credential mounts yield nothing — the ops-signer
# fallback). No key material or password ever appears in env values, argv,
# logs or this process's config.
# ---------------------------------------------------------------------------


class _CredentialMissing(Exception):
    """The escrow credential is absent/unreadable — refuse to sign."""


def _check_credential_file(path: Any) -> None:
    import stat
    from pathlib import Path

    path = Path(path)
    if not path.is_absolute():
        raise _CredentialMissing("escrow credential path not absolute")
    try:
        st = path.stat()
    except OSError:
        raise _CredentialMissing("escrow credential file missing or unreadable") from None
    # The sealed credential must be 0600 and owned by root or the service
    # account itself (aitbc-wallet runs as User=aitbc — unlike the root-owned
    # ops-signer). Anything world-readable or group-writable refuses.
    if st.st_uid not in (0, os.geteuid()):
        raise _CredentialMissing("escrow credential file not owned by root or the service user")
    if stat.S_IMODE(st.st_mode) != 0o600:
        raise _CredentialMissing("escrow credential file mode not 0600")


def _credential_from_dir(cfg: SellConfig) -> str | None:
    """The systemd credential dir copy of the wallet password, if mounted."""
    from pathlib import Path

    cred_dir = os.environ.get("CREDENTIALS_DIRECTORY")
    if not cred_dir:
        return None
    path = Path(cred_dir) / cfg.escrow_credential_name
    try:
        password = path.read_text().rstrip("\n")
    except OSError:
        return None
    if not password:
        raise _CredentialMissing(f"{path} is empty")
    return password


def _credential_via_systemd_creds(cfg: SellConfig) -> str:
    """Decrypt the sealed credential file with systemd-creds (LXC path)."""
    import subprocess
    from pathlib import Path

    credential_file = Path(cfg.escrow_credential_file)
    _check_credential_file(credential_file)
    argv = [
        "systemd-creds",
        "decrypt",
        f"--name={cfg.escrow_credential_name}",
        str(credential_file),
        "-",
    ]
    try:
        proc = subprocess.run(argv, capture_output=True, timeout=10.0, check=False, env=subprocess_env())
    except subprocess.TimeoutExpired:
        raise _CredentialMissing("systemd-creds decrypt timed out") from None
    except OSError:
        raise _CredentialMissing("systemd-creds not available") from None
    if proc.returncode != 0:
        raise _CredentialMissing(f"systemd-creds decrypt failed rc={proc.returncode}")
    try:
        password = proc.stdout.decode()
    except UnicodeDecodeError:
        raise _CredentialMissing("systemd-creds output undecodable") from None
    if password.endswith("\n"):
        password = password[:-1]
    if not password:
        raise _CredentialMissing("systemd-creds decrypt produced empty secret")
    return password


def _escrow_credential_password(cfg: SellConfig) -> str:
    """Wallet password from the systemd credential, or sealed-file decrypt."""
    password = _credential_from_dir(cfg)
    if password is not None:
        return password
    return _credential_via_systemd_creds(cfg)


def _load_escrow_key(cfg: SellConfig) -> Any:
    """Decrypt the escrow key slot and return the private key object.

    Mirrors aitbc_ops_signer.signer._load_wallet/_private_key: wallet JSON
    carries ``address`` + ``private_key`` (``decrypt_value``-sealed dict or
    hex). The key exists only inside the caller's frame.
    """
    from pathlib import Path

    from aitbc.security.encryption import decrypt_value
    from eth_keys import keys as eth_keys

    data: dict[str, Any] = json.loads(Path(cfg.escrow_wallet_path).read_text())
    priv = data.get("private_key")
    if isinstance(priv, dict):
        priv = decrypt_value(priv, _escrow_credential_password(cfg))
    if not isinstance(priv, str):
        raise ValueError("escrow wallet carries no private_key")
    hexkey = priv[2:] if priv.startswith("0x") else priv
    key = eth_keys.PrivateKey(bytes.fromhex(hexkey))
    derived = key.public_key.to_checksum_address()
    if canonical_address(derived).lower() != cfg.escrow_address.lower():
        raise ValueError("escrow key slot does not derive to AIT_SELL_ESCROW")
    return key


def _validate_escrow_key(cfg: SellConfig) -> str | None:
    """Confirm the key slot loads and derives to AIT_SELL_ESCROW."""
    try:
        _load_escrow_key(cfg)
    except Exception as e:  # noqa: BLE001 - probe containment — unusable key reported, never raised
        return f"escrow key slot unusable: {e}"
    return None


def _ensure_db() -> None:
    global _db_initialized
    if not _db_initialized:
        init_db()
        _db_initialized = True


async def _chain_height() -> int:
    """Current sealed chain height from the AITBC RPC."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{wdm.BLOCKCHAIN_RPC_URL}/rpc/height")
        resp.raise_for_status()
        data = resp.json()
    return int(data.get("height", 0))


async def _fetch_transfers(address: str, limit: int = 0) -> list[dict[str, Any]]:
    """TRANSFERs touching ``address`` (sender or recipient), newest first.

    ``/rpc/transactions`` has no offset/cursor pagination; its ``limit`` is
    applied as ``results[:limit]`` guarded by ``if limit:`` — so ``limit=0``
    deliberately disables truncation and returns the *complete* history for
    the address. The escrow scan relies on that: every poll sees every lock
    ever sent to the escrow, so a busy window with more than a page of new
    transfers can never silently drop a lock (dedupe is by tx hash). Escrow
    traffic is low-volume, so the unbounded read stays small.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{wdm.BLOCKCHAIN_RPC_URL}/rpc/transactions",
            params={"transaction_type": "TRANSFER", "address": address, "limit": limit},
        )
        resp.raise_for_status()
        data = resp.json()
    txs = data.get("transactions", data) if isinstance(data, dict) else data
    return cast(list[dict[str, Any]], txs) if isinstance(txs, list) else []


async def _account_view(address: str) -> tuple[int, Decimal]:
    """(nonce, balance in AIT) from the AITBC RPC in one call. A 404 (the
    account has no on-chain record yet) reads as zero."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{wdm.BLOCKCHAIN_RPC_URL}/rpc/account/{address}")
        if resp.status_code == 404:
            return 0, Decimal("0")
        resp.raise_for_status()
        data = resp.json()
    return int(data.get("nonce", 0)), units_to_ait(int(data.get("balance", 0) or 0))


# ---------------------------------------------------------------------------
# Lock scan
# ---------------------------------------------------------------------------


def _funding_sources() -> set[str]:
    """AIT addresses whose sends to the escrow are float top-ups (seed for
    sweep fees / operating balance), never sell locks. Comma-separated,
    case-insensitive — mirrors BRIDGE_FUNDING_SOURCES on the ETH side."""
    raw = os.getenv("SELL_ESCROW_FUNDING_SOURCES", "")
    return {a.strip().lower() for a in raw.split(",") if a.strip()}


def _exchange_lock_lane(quote_value: Any) -> bool:
    """True when ``payload.sell_quote`` names an exchange order — an int or
    an all-digit string (ETH-7 quote ids are ``sellq_<hex>``). Only applies
    while the exchange settlement flag is on; flag-off the value falls
    through to the quote lookup like before."""
    if os.getenv("EXCHANGE_SETTLEMENT_ENABLED", "false").lower() != "true":
        return False
    if isinstance(quote_value, bool):
        return False
    if isinstance(quote_value, int):
        return True
    return isinstance(quote_value, str) and quote_value.isdigit()


async def _scan_escrow_locks(cfg: SellConfig) -> dict[str, int]:
    """Record confirmed TRANSFERs to the escrow address as sell locks.

    The fetch is deliberately unbounded (``limit=0`` — see
    ``_fetch_transfers``): the scan sees the complete escrow history every
    poll, so a burst of any size cannot hide a lock behind a page limit.
    """
    txs = await _fetch_transfers(cfg.escrow_address, limit=0)
    funding = _funding_sources()
    scanned = 0
    recorded = 0
    for tx in txs:
        recipient = tx.get("recipient") or tx.get("to") or ""
        if recipient.lower() != cfg.escrow_address.lower():
            continue
        if not wdm.tx_sealed_confirmed(tx):
            continue  # not sealed, or sealed-but-failed — no value moved (#1916)
        ait_tx_hash = tx.get("tx_hash") or tx.get("hash") or ""
        if not ait_tx_hash:
            continue
        sender = tx.get("sender") or tx.get("from") or ""
        if sender.lower() in funding:
            continue  # operator seed/float top-up — not a sell lock
        scanned += 1
        if get_sell_lock_by_ait_tx_hash(ait_tx_hash):
            continue

        amount_ait = units_to_ait(int(tx.get("value", 0) or 0))
        payload = tx.get("payload") or {}
        if payload.get("sell_float"):
            # Operator float top-up marked in-band — never a sell lock,
            # regardless of sender (complements the funding-source allowlist).
            continue
        quote_id = payload.get("sell_quote")
        if _exchange_lock_lane(quote_id):
            # An int order id in sell_quote belongs to the exchange
            # settlement lane (ETH-8 phase 3) — this lane owns sellq_* only.
            continue
        quote = get_sell_quote(str(quote_id)) if quote_id else None
        error = None
        if quote and sender.lower() != str(quote.get("shop_ait_address") or "").lower():
            # A lock is bound to the quoting shop: anyone else paying into a
            # live quote id gets the orphan path — refunded to the *actual*
            # sender, never releasing against somebody else's quote.
            quote = None
            error = "lock sender does not match quote's shop_ait_address"
        status = "locked" if quote else "orphaned"
        insert_sell_lock(
            ait_tx_hash=ait_tx_hash,
            shop_ait_address=sender,
            shop_eth_address=(quote or {}).get("shop_eth_address"),
            amount_ait=amount_ait,
            quote_id=str(quote_id) if quote_id else None,
            status=status,
            locked_height=int(tx["block_height"]),
            error=error,
        )
        recorded += 1
        logger.info(
            "Recorded sell lock %s: %s AIT from %s (quote %s)",
            ait_tx_hash,
            amount_ait,
            sender,
            quote_id or "none — orphaned",
        )
    return {"scanned": scanned, "recorded": recorded}


async def _broadcast_ait_tx(signed_tx: dict[str, Any]) -> str:
    """Submit a signed AIT transaction and return its chain tx hash."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(f"{wdm.BLOCKCHAIN_RPC_URL}/rpc/transaction", json=signed_tx)
        response.raise_for_status()
        result = response.json()
    tx_hash = result.get("transaction_hash") or result.get("tx_hash") or ""
    if not tx_hash:
        raise ValueError(f"No tx hash returned: {result}")
    return str(tx_hash)


# ---------------------------------------------------------------------------
# Per-status handlers
# ---------------------------------------------------------------------------


def _lock_age_seconds(row: dict[str, Any]) -> float:
    locked_at = row.get("locked_at") or row.get("created_at")
    try:
        return (utc_now() - parse_stored(locked_at)).total_seconds()
    except (TypeError, ValueError):
        return 0.0


def _expire_stale_quotes() -> int:
    """Mark 'quoted' rows past their expiry 'expired' — bookkeeping only."""
    expired = 0
    for quote in get_sell_quotes_by_status(("quoted",)):
        try:
            if utc_now() > parse_stored(quote.get("expires_at")):
                update_sell_quote_status(str(quote["id"]), "expired")
                expired += 1
        except Exception:  # noqa: BLE001 - bad quote row skipped — expired count stays accurate
            continue
    return expired


async def poll_sells_once() -> dict[str, Any]:
    """Run a single sell-escrow poll cycle."""
    enabled, reason = sell_config_status()
    if not enabled:
        return {"scanned": 0, "recorded": 0, "processed": 0, "skipped": True, "reason": reason}

    try:
        cfg = _sell_config()
    except ValueError as e:
        return {"scanned": 0, "recorded": 0, "processed": 0, "skipped": True, "reason": str(e)}

    key_error = _validate_escrow_key(cfg)
    if key_error:
        return {"scanned": 0, "recorded": 0, "processed": 0, "skipped": True, "reason": key_error}
    if not wdm.ETH_WALLET_ADDRESS:
        return {"scanned": 0, "recorded": 0, "processed": 0, "skipped": True, "reason": "ETH_WALLET_ADDRESS not set"}

    _ensure_db()
    _expire_stale_quotes()

    try:
        scanned = await _scan_escrow_locks(cfg)
    except Exception as e:  # noqa: BLE001 - failed scan skips the poll — RPC outage never drives a refund
        # A failed scan means the chain view is unverifiable this poll —
        # process nothing. Deadline/orphan/refund decisions only ever run
        # on successful polls; an RPC outage can never drive a refund.
        logger.error("Sell lock scan failed — skipping poll: %s", e)
        return {"scanned": 0, "recorded": 0, "processed": 0, "skipped": True, "reason": f"scan failed: {e}"}

    # In-flight sweeps resolve first: a sealed outflow frees the serialized
    # slot before any new sweep initiation is attempted this poll.
    open_rows = get_open_sell_locks()
    worklist = [r for r in open_rows if r["status"] in _INFLIGHT_SWEEP_STATUSES]
    worklist += [r for r in open_rows if r["status"] not in _INFLIGHT_SWEEP_STATUSES]
    processed = 0
    for row in worklist:
        try:
            await _process_sell_lock(cfg, row)
            processed += 1
        except Exception as e:  # noqa: BLE001 - row containment — one bad lock must not kill the drain
            logger.error("Error processing sell lock %s: %s", row.get("ait_tx_hash"), e)

    return {"scanned": scanned["scanned"], "recorded": scanned["recorded"], "processed": processed, "skipped": False}


async def sell_monitor_loop() -> None:
    """Main loop for the escrowed sell monitor."""
    enabled, reason = sell_config_status()
    if not enabled:
        logger.info("Sell escrow monitor disabled: %s", reason)
        return
    try:
        cfg = _sell_config()
    except ValueError as e:
        logger.error("Sell escrow monitor refused to start: %s", e)
        return

    key_error = _validate_escrow_key(cfg)
    if key_error:
        logger.error("Sell escrow monitor disabled: %s", key_error)
        return

    _ensure_db()
    logger.info("Starting AIT->ETH sell escrow monitor (escrow %s)", cfg.escrow_address)
    logger.info("Sell poll interval: %ss", cfg.poll_interval)

    while True:
        if not _sell_polling_enabled:
            logger.info("Sell auto-poll disabled, sleeping")
            await asyncio.sleep(1)
            continue
        try:
            summary = await poll_sells_once()
            if not summary.get("skipped"):
                did_work = summary.get("recorded", 0) > 0 or summary.get("processed", 0) > 0
                log = logger.info if did_work else logger.debug
                log("Sell poll completed: %s", summary)
        except Exception as e:  # noqa: BLE001 - poll containment — a failed pass must not end the monitor loop
            logger.error("Error in sell monitor loop: %s", e)
        for _ in range(cfg.poll_interval):
            if not _sell_polling_enabled:
                break  # type: ignore[unreachable]
            await asyncio.sleep(1)


def start_sell_monitoring() -> asyncio.Task[None] | None:
    """Start the sell monitor as an asyncio task — or log one clear disabled
    line and return None when unconfigured/misconfigured. Never falls back to
    another key."""
    enabled, reason = sell_config_status()
    if not enabled:
        logger.info("Sell escrow monitor disabled: %s", reason)
        return None
    try:
        _sell_config()
    except ValueError as e:
        logger.error("Sell escrow monitor refused to start: %s", e)
        return None

    try:
        task = create_task_with_logging(sell_monitor_loop(), name="sell_escrow_monitor")
        return task
    except RuntimeError:
        logger.debug("No event loop running; starting sell monitor in a thread", exc_info=True)
        import threading

        def _run_sync() -> None:
            asyncio.run(sell_monitor_loop())

        monitor_thread = threading.Thread(target=_run_sync, daemon=True)
        monitor_thread.start()
        return None


def set_sell_polling_enabled(enabled: bool) -> None:
    global _sell_polling_enabled
    _sell_polling_enabled = enabled


def pending_sell_eth_reserve() -> Decimal:
    """ETH reserved by open sell locks — exposed for status endpoints."""
    return get_sell_pending_eth_reserve()
