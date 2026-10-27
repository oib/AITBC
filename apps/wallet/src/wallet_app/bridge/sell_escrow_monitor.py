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
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, cast

import httpx

from aitbc.aitbc_logging import get_logger
from aitbc.utils import ait_to_units, units_to_ait
from aitbc.utils.units import DEFAULT_TX_FEE_AIT
from aitbc.crypto.signature_recovery import canonical_address

from . import bridge_withdraw_monitor as wdm
from .bridge_db import (
    get_open_sell_locks,
    get_sell_eth_committed_since,
    get_sell_inflight_sweep,
    get_sell_lock_by_ait_tx_hash,
    get_sell_lock_by_quote_id,
    get_sell_pending_eth_reserve,
    get_sell_quote,
    get_sell_quotes_by_status,
    init_db,
    insert_sell_lock,
    update_sell_lock_status,
    update_sell_quote_status,
)
from .price_api import apply_bridge_fee, calculate_eth_amount, get_eth_prices_fresh

logger = get_logger(__name__)

_db_initialized = False
_sell_polling_enabled: bool = True

# Sibling-lock statuses that consume a quote — everything still live or
# ambiguous. 'orphaned'/'refunded'/'failed'/'settled' siblings do not block.
_SELL_BINDING_STATUSES = (
    "locked",
    "releasing",
    "released",
    "settling",
    "refunding",
    "refund_pending",
    "stale_price",
    "queued_reserve",
    "queued_fee_settle",
    "queued_fee_refund",
    "needs_review",
    "needs_review_sweep",
)

# A row in one of these statuses holds a persisted sweep intent (escrow
# nonce + signed blob). Sweep serialization: at most one may exist; a new
# sweep waits until it is sealed or resolved.
_INFLIGHT_SWEEP_STATUSES = ("settling", "refunding")

# Marker tail on a fee-parked row's ``error`` — the write in ``_escrow_sweep``
# and the reason split in ``_parked_refund_reason`` share this exact string so
# a re-parked row recovers its original reason instead of accumulating
# deficit text.
_FEE_FLOAT_DEFICIT_MARK = "; escrow fee float deficit"

# Warned-once fee-float deficits: (ait_tx_hash, deficit, park_status). A
# parked row retries every poll — the WARNING must fire once per deficit
# state, not per cycle (journal noise feeds JournalErrors). A deficit that
# changes is a new state and warns again.
_fee_float_warned: set[tuple[str, str, str]] = set()


def _sweep_fee_ait() -> Decimal:
    """Each escrow sweep spends the standard transfer fee on top of the
    moved amount — the escrow needs a seed balance for exactly this."""
    return Decimal(str(DEFAULT_TX_FEE_AIT))


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
        proc = subprocess.run(argv, capture_output=True, timeout=10.0, check=False)
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


async def compute_sell_quote(ait_amount: Decimal) -> dict[str, Any] | None:
    """Compute the quote payload for an AIT sell amount.

    Returns None when the feed is unavailable or stale — callers must not
    price off a dead feed (route 503s, monitor parks the lock).
    """
    meta = await get_eth_prices_fresh()
    if meta is None:
        return None
    estimate = await calculate_eth_amount(ait_amount, eth_price_usd=meta["usd"])
    if not estimate:
        return None
    return {
        "eth_amount": estimate["amount_eth"],
        "fee_ait": estimate["fee_ait"],
        "net_ait": estimate["net_ait"],
        "rate_eth_usd": meta["usd"],
        "ait_usd": estimate["ait_usd"],
        "feed_age_seconds": Decimal(str(meta["feed_age_seconds"])),
    }


def _eth_for_lock_at_quote(amount_ait: Decimal, quote: dict[str, Any]) -> Decimal:
    """ETH owed for a lock at the rates frozen on its quote row."""
    if Decimal(str(amount_ait)) == Decimal(str(quote["ait_amount"])):
        return Decimal(str(quote["eth_amount"]))
    fee_ait, net_ait = apply_bridge_fee(Decimal(str(amount_ait)))
    eth_usd = Decimal(str(quote["rate_eth_usd"]))
    ait_usd = Decimal(str(quote["ait_usd"]))
    return (Decimal(str(net_ait)) * ait_usd / eth_usd).quantize(Decimal("0.00000001"))


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


def _exchange_inflight_sweep() -> bool:
    """An exchange settlement row holds the escrow's one in-flight sweep —
    shared nonce space, so this lane defers while it resolves."""
    if os.getenv("EXCHANGE_SETTLEMENT_ENABLED", "false").lower() != "true":
        return False
    try:
        from .bridge_db import get_exchange_inflight_sweep

        return get_exchange_inflight_sweep() is not None
    except Exception:  # noqa: BLE001 - inflight probe defaults to not-in-flight on failure
        return False


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
        if tx.get("block_height") is None:
            continue  # not sealed yet
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


# ---------------------------------------------------------------------------
# Escrow-leg signing (AIT side) — settle to treasury / refund to shop
# ---------------------------------------------------------------------------


async def _sign_escrow_transfer(
    cfg: SellConfig, to_address: str, amount_ait: Decimal, payload_extra: dict[str, Any], nonce: int
) -> dict[str, Any]:
    """Build and sign an escrow-account TRANSFER at the given nonce."""
    from eth_utils import keccak

    value = ait_to_units(amount_ait)
    tx_payload = {
        "type": "TRANSFER",
        "chain_id": cfg.chain_id,
        "from": cfg.escrow_address,
        "to": canonical_address(to_address),
        "amount": value,
        "fee": ait_to_units(_sweep_fee_ait()),
        "nonce": nonce,
        "payload": {"amount": value, **payload_extra},
    }
    unsigned = {k: v for k, v in tx_payload.items() if k != "signature"}
    message = json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    private_key = _load_escrow_key(cfg)
    signature = private_key.sign_msg_hash(keccak(message))
    tx_payload["signature"] = signature.to_bytes().hex()
    return tx_payload


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


async def _update_lock_status_with_retry(ait_tx_hash: str, status: str, **fields: Any) -> bool:
    """Persist a sell-lock status with the ETH-9 retry discipline: a write
    that fails after a broadcast must never fall through to a second send."""
    last_exc: Exception | None = None
    for attempt in range(wdm._STATUS_PERSIST_ATTEMPTS):
        try:
            return update_sell_lock_status(ait_tx_hash, status, **fields)
        except Exception as e:  # noqa: BLE001 - persist retry — any store failure alike
            last_exc = e
            logger.error(
                "Failed to persist sell lock %s status %s (attempt %d/%d): %s",
                ait_tx_hash,
                status,
                attempt + 1,
                wdm._STATUS_PERSIST_ATTEMPTS,
                e,
            )
            if attempt < wdm._STATUS_PERSIST_ATTEMPTS - 1:
                await asyncio.sleep(wdm._STATUS_PERSIST_DELAYS[attempt])
    raise RuntimeError(f"could not persist sell lock {ait_tx_hash} status {status}: {last_exc}")


def _expected_sweep(cfg: SellConfig, row: dict[str, Any], lane: str | None = None) -> tuple[str, int, str]:
    """(recipient, amount_units, sell_ref) the row's escrow outflow must
    match — derived from the row, the same values the stored blob carries.

    ``lane`` is "settle" or "refund"; when omitted it is read from the
    row's current status (the monitor's resolver sees only
    'settling'/'refunding' rows). sell_admin passes the lane it recovered
    from the persisted intent, since a 'needs_review_sweep' status no
    longer says which lane the sweep was in."""
    if lane is None:
        lane = "settle" if row["status"] in ("settling", "queued_fee_settle") else "refund"
    to_address = cfg.treasury_address if lane == "settle" else str(row["shop_ait_address"])
    return canonical_address(to_address), ait_to_units(Decimal(str(row["amount_ait"]))), str(row["ait_tx_hash"])


async def _find_escrow_outflow(
    cfg: SellConfig, nonce: int, to_address: str, amount_units: int, sell_ref: str
) -> dict[str, Any] | None:
    """Find the escrow's SEALED outbound TRANSFER that this row's recorded
    intent produced — matched on nonce AND recipient AND amount AND
    ``payload.sell_ref``, so a different transaction at the same nonce (a
    manual send, another row's sweep) can never be credited to this row.
    Mempool-pending txs (no ``block_height``) do not count as sealed."""
    txs = await _fetch_transfers(cfg.escrow_address)
    for tx in txs:
        if tx.get("block_height") is None:
            continue
        sender = (tx.get("sender") or tx.get("from") or "").lower()
        if sender != cfg.escrow_address.lower():
            continue
        tx_nonce = tx.get("nonce")
        if tx_nonce is None or int(tx_nonce) != nonce:
            continue
        recipient = (tx.get("recipient") or tx.get("to") or "").lower()
        payload = tx.get("payload") or {}
        if (
            recipient == to_address.lower()
            and int(tx.get("value") or 0) == amount_units
            and payload.get("sell_ref") == sell_ref
        ):
            return tx
    return None


async def _escrow_sweep(
    cfg: SellConfig,
    row: dict[str, Any],
    to_address: str,
    reason: str,
    intent_status: str,
    fee_park_status: str,
) -> str:
    """Start an escrow → ``to_address`` sweep, serialized and float-checked.

    Serialization: at most one sweep (``settling``/``refunding``) is in
    flight at a time — while one is, this returns ``"deferred"`` and the row
    keeps its caller status to retry on a later poll.

    Fee float: the escrow pays ``amount + 0.01 AIT`` (the transfer fee). A
    short balance parks the row in ``fee_park_status`` with the deficit —
    never an exception, never a failed sign.

    On send, the nonce AND signed blob are persisted *before* broadcast and
    the row goes to ``intent_status`` — and stays there until the outflow is
    found *sealed* (see ``_resolve_escrow_sweep``). A broadcast returning a
    hash is not proof of seal, so terminal status is never written here.
    """
    if get_sell_inflight_sweep() or _exchange_inflight_sweep():
        logger.info(
            "Sell lock %s: escrow sweep %s deferred — another sweep is in flight",
            row["ait_tx_hash"],
            reason,
        )
        return "deferred"

    amount_ait = Decimal(str(row["amount_ait"]))
    nonce, balance = await _account_view(cfg.escrow_address)
    required = amount_ait + _sweep_fee_ait()
    if balance < required:
        deficit = required - balance
        update_sell_lock_status(
            row["ait_tx_hash"],
            fee_park_status,
            error=f"{reason}{_FEE_FLOAT_DEFICIT_MARK} {deficit} AIT (need {required} AIT, have {balance})",
        )
        warn_key = (str(row["ait_tx_hash"]), str(deficit), fee_park_status)
        if warn_key not in _fee_float_warned:
            _fee_float_warned.add(warn_key)
            logger.warning(
                "Sell lock %s: escrow fee float short %s AIT (balance %s, need %s) — parked %s",
                row["ait_tx_hash"],
                deficit,
                balance,
                required,
                fee_park_status,
            )
        return "fee_parked"

    payload_extra = {"sell_ref": row["ait_tx_hash"], "reason": reason}
    signed_tx = await _sign_escrow_transfer(cfg, to_address, amount_ait, payload_extra, nonce)
    await _update_lock_status_with_retry(
        row["ait_tx_hash"], intent_status, escrow_out_nonce=nonce, escrow_out_tx=json.dumps(signed_tx)
    )
    tx_hash = await _broadcast_ait_tx(signed_tx)
    logger.info(
        "Sell lock %s: escrow sweep %s broadcast (%s AIT -> %s, nonce %d, tx %s) — awaiting seal",
        row["ait_tx_hash"],
        reason,
        amount_ait,
        to_address,
        nonce,
        tx_hash,
    )
    return "sent"


async def _resolve_escrow_sweep(cfg: SellConfig, row: dict[str, Any]) -> None:
    """Resolve an in-flight 'settling'/'refunding' row.

    Terminal status comes only from the chain: the sealed outflow matching
    nonce+recipient+amount+``sell_ref`` writes 'settled'/'refunded' with its
    real hash. If the recorded nonce is still unconsumed, the stored signed
    blob is re-broadcast — identical signature at the same nonce, which the
    chain dedups, so a resume can never produce a second payment. If the
    nonce was consumed by a *different* transaction (a manual send), the row
    goes to 'needs_review_sweep' — the ETH-9b rule, never a blind re-send.
    """
    nonce = row.get("escrow_out_nonce")
    if nonce is None:
        # Intent persisted but nonce missing — undecidable, needs a human.
        update_sell_lock_status(row["ait_tx_hash"], "needs_review_sweep", error="escrow sweep nonce missing")
        return
    final_status = "settled" if row["status"] == "settling" else "refunded"
    hash_field = "settle_tx_hash" if final_status == "settled" else "refund_tx_hash"
    to_address, amount_units, sell_ref = _expected_sweep(cfg, row)
    outflow = await _find_escrow_outflow(cfg, int(nonce), to_address, amount_units, sell_ref)
    if outflow is not None:
        await _update_lock_status_with_retry(
            row["ait_tx_hash"], final_status, **{hash_field: outflow.get("tx_hash") or outflow.get("hash")}
        )
        logger.info("Sell lock %s: %s sealed at escrow nonce %d", row["ait_tx_hash"], final_status, nonce)
        return
    account_nonce, _balance = await _account_view(cfg.escrow_address)
    if account_nonce > int(nonce):
        # The nonce was consumed by a transaction that does NOT match this
        # row's intent — a manual send or foreign sweep. Never auto-resolve.
        update_sell_lock_status(
            row["ait_tx_hash"],
            "needs_review_sweep",
            error=f"escrow nonce {nonce} consumed by an unmatched transaction",
        )
        logger.error(
            "Sell lock %s: escrow nonce %d sealed to an unmatched tx — needs review",
            row["ait_tx_hash"],
            nonce,
        )
        return
    # The nonce is still free — the original broadcast never sealed.
    # Re-broadcast the stored signed blob: identical signature at the same
    # nonce — a fresh signature could double-pay, this cannot.
    stored = row.get("escrow_out_tx")
    if not stored:
        update_sell_lock_status(row["ait_tx_hash"], "needs_review_sweep", error="escrow sweep blob missing")
        return
    signed_tx = json.loads(stored)
    tx_hash = await _broadcast_ait_tx(signed_tx)
    logger.info(
        "Sell lock %s: re-broadcast stored %s blob (tx %s) — still in flight until sealed",
        row["ait_tx_hash"],
        row["status"],
        tx_hash,
    )


async def _settle_lock(cfg: SellConfig, row: dict[str, Any]) -> None:
    """Settle escrowed AIT to the hub treasury (the sell's AIT leg)."""
    await _escrow_sweep(cfg, row, cfg.treasury_address, "sell_settle", "settling", "queued_fee_settle")


async def _refund_lock(cfg: SellConfig, row: dict[str, Any], reason: str) -> None:
    """Refund escrowed AIT to the shop.

    Deferred/parked outcomes leave the row in a retriable status. A failure
    before the 'refunding' intent persisted leaves the row untouched — the
    next healthy poll retries it, so an outage can never burn a refundable
    row. Once the intent + signed blob are persisted, the row is in flight
    and ``_resolve_escrow_sweep`` owns it: sealed → 'refunded'; nonce spent
    by a foreign tx → 'needs_review_sweep'; never a second blind refund.
    """
    try:
        await _escrow_sweep(cfg, row, row["shop_ait_address"], reason, "refunding", "queued_fee_refund")
        return
    except Exception as e:  # noqa: BLE001 - refund sweep failure resolved by the resolver
        logger.error("Refund sweep errored for sell lock %s: %s", row["ait_tx_hash"], e)
    fresh = get_sell_lock_by_ait_tx_hash(row["ait_tx_hash"]) or {}
    if fresh.get("status") == "refunding":
        logger.error(
            "Sell lock %s: refund broadcast threw post-intent — the resolver will prove the outcome by nonce",
            row["ait_tx_hash"],
        )
    # else: pre-intent failure — the row keeps its status and retries next poll


# ---------------------------------------------------------------------------
# ETH release — ETH-9/9b machinery reused, no second "is the ETH out?"
# ---------------------------------------------------------------------------


async def _verify_sell_release_outcome(row: dict[str, Any]) -> tuple[str, str]:
    """(outcome, reason) for a sell lock's ETH release — the shared
    ETH-9b compose (deep receipt wins; nonce alone is never proof). The
    reason distinguishes an in-grace absence from a genuine verification
    problem so callers can pick the log level (ETH-15)."""
    fresh = get_sell_lock_by_ait_tx_hash(row["ait_tx_hash"])
    if not fresh:
        return "unknown", "verify_error"
    return await wdm._compose_release_outcome_detail(fresh)


async def _release_eth_for_lock(cfg: SellConfig, row: dict[str, Any], amount_eth: Decimal) -> None:
    """Send the ETH release for a sell lock (intent persisted pre-broadcast).

    ``amount_eth`` is the admission-priced amount — the caller's freshly
    computed value, since ``row`` may be a pre-update snapshot.
    """
    eth_address = row.get("shop_eth_address") or ""
    if amount_eth <= 0:
        raise RuntimeError(f"Sell lock {row['ait_tx_hash']} has no ETH amount to release")
    if not wdm._is_valid_eth_address(eth_address):
        raise RuntimeError(f"Sell lock {row['ait_tx_hash']} has no valid shop ETH address")

    gas_price = await wdm._eth_gas_price()
    gas_limit = await wdm._release_gas_limit(eth_address, amount_eth)
    gas_cost = Decimal(gas_price * gas_limit) / Decimal(10**18)
    required = amount_eth + gas_cost
    balance = await wdm._eth_balance(wdm.ETH_WALLET_ADDRESS)
    available = balance - wdm._pending_eth_reserve()
    # The stricter of SELL_MAX_ETH_PER_TX and BRIDGE_MAX_PAYOUT_FRACTION binds
    # (the fraction shrinks as the float drains — operator decision (c)).
    fraction_cap = balance * cfg.max_payout_fraction
    if amount_eth > fraction_cap:
        update_sell_lock_status(
            row["ait_tx_hash"],
            "queued_reserve",
            error=f"{amount_eth} ETH exceeds BRIDGE_MAX_PAYOUT_FRACTION={cfg.max_payout_fraction} of float {balance}",
        )
        return
    if available - required < cfg.min_reserve_eth:
        deficit = required + cfg.min_reserve_eth - available
        update_sell_lock_status(
            row["ait_tx_hash"],
            "queued_reserve",
            error=f"deficit {deficit} ETH — need {required} + {cfg.min_reserve_eth} reserve, have {available}",
        )
        return

    from eth_account import Account as EthAccount

    key, error = wdm._validate_release_key()
    if not key:
        raise RuntimeError(error)
    account = EthAccount.from_key(key)
    async with wdm.ETH_RELEASE_NONCE_LOCK:
        nonce = await wdm._eth_nonce(wdm.ETH_WALLET_ADDRESS)
        raw, eth_tx_hash = wdm._sign_release_tx(account, eth_address, amount_eth, nonce, gas_price, gas_limit)

        await _update_lock_status_with_retry(row["ait_tx_hash"], "releasing", eth_tx_hash=eth_tx_hash, release_nonce=nonce)
        sent = await wdm._broadcast_release_tx(raw)
    if sent.lower() != eth_tx_hash.lower():
        logger.warning("Broadcast reported %s; keeping signed hash %s", sent, eth_tx_hash)
    # ETH-14: 'released' is written only on a verified receipt — the
    # inflight handler proves the outcome next poll; a reverted or dropped
    # release can never again be recorded as sent here.
    logger.info(
        "Sell lock %s: broadcast %s ETH to %s (tx %s, gas %d) — awaiting receipt proof",
        row["ait_tx_hash"],
        amount_eth,
        eth_address,
        eth_tx_hash,
        gas_limit,
    )


async def _resolve_lock_release_failure(cfg: SellConfig, row: dict[str, Any], exc: Exception) -> None:
    """Same rule as withdrawals: refund only on positive proof of no send."""
    outcome, _reason = await _verify_sell_release_outcome(row)
    if outcome == "sent":
        logger.warning("Sell lock %s: ETH release confirmed despite error (%s)", row["ait_tx_hash"], exc)
        try:
            await _update_lock_status_with_retry(row["ait_tx_hash"], "released")
        except Exception as persist_err:  # noqa: BLE001 - persist best-effort inside the confirmed-error path
            logger.error("Could not persist released for %s: %s", row["ait_tx_hash"], persist_err)
    elif outcome == "not_sent":
        # Release provably never landed — the row owes a refund but stays
        # open in 'refund_pending' so a deferred/failed sweep retries.
        update_sell_lock_status(row["ait_tx_hash"], "refund_pending", error=f"release failed: {exc}")
        await _refund_lock(cfg, row, f"release failed: {exc}")
    else:
        update_sell_lock_status(row["ait_tx_hash"], "needs_review", error=f"release outcome unverifiable: {exc}")
        logger.error("Sell lock %s marked needs_review — release outcome unverifiable: %s", row["ait_tx_hash"], exc)


# ---------------------------------------------------------------------------
# Per-status handlers
# ---------------------------------------------------------------------------


def _lock_age_seconds(row: dict[str, Any]) -> float:
    locked_at = row.get("locked_at") or row.get("created_at")
    try:
        return (datetime.now() - datetime.fromisoformat(str(locked_at))).total_seconds()
    except (TypeError, ValueError):
        return 0.0


def _quote_admits_lock(row: dict[str, Any], quote: dict[str, Any]) -> bool:
    """Whether this row's quote admits it: 'expired' quotes still admit their
    lock — at the re-quoted live rate. A 'locked' quote is already bound:
    admission only when the bound lock IS this row (a queued_reserve/
    stale_price re-entry). Otherwise the earliest live sibling wins; a later
    'locked' sibling never blocks."""
    quote_id = str(quote["id"])
    bound_lock = get_sell_lock_by_quote_id(quote_id, statuses=_SELL_BINDING_STATUSES)
    bound_is_self = bool(bound_lock and bound_lock["ait_tx_hash"] == row["ait_tx_hash"])
    quote_ok = quote.get("status") in ("quoted", "expired") or (quote.get("status") == "locked" and bound_is_self)
    if quote_ok and quote.get("status") != "locked":
        live_sibling = get_sell_lock_by_quote_id(
            quote_id,
            exclude_ait_tx_hash=row["ait_tx_hash"],
            statuses=_SELL_BINDING_STATUSES,
            before_created_at=str(row.get("created_at") or ""),
        )
        quote_ok = not live_sibling
    return quote_ok


async def _price_lock_eth_amount(cfg: SellConfig, row: dict[str, Any], quote: dict[str, Any], quote_id: str) -> Decimal | None:
    """Persist the lock's ETH amount — quote rate or live re-quote for an
    expired quote. Returns ``None`` when the row was parked (stale feed)."""
    eth_amount = row.get("eth_amount")
    if eth_amount is not None:
        return Decimal(str(eth_amount))
    expired = True
    try:
        expired = datetime.now() > datetime.fromisoformat(str(quote.get("expires_at") or ""))
    except (TypeError, ValueError):
        pass
    if expired:
        # Late lock on an expired quote: re-quote at the live feed.
        recomputed = await compute_sell_quote(Decimal(str(row["amount_ait"])))
        if recomputed is None:
            update_sell_lock_status(row["ait_tx_hash"], "stale_price", error="expired quote and feed unavailable")
            return None
        eth_amount = recomputed["eth_amount"]
        update_sell_quote_status(quote_id, "expired")
        update_sell_lock_status(row["ait_tx_hash"], "locked", eth_amount=eth_amount, requoted=1, error="requoted after expiry")
    else:
        eth_amount = _eth_for_lock_at_quote(Decimal(str(row["amount_ait"])), quote)
        update_sell_lock_status(row["ait_tx_hash"], "locked", eth_amount=eth_amount)
        update_sell_quote_status(quote_id, "locked")
    return Decimal(str(eth_amount))


async def _handle_locked(cfg: SellConfig, row: dict[str, Any]) -> None:
    """Admission path for a recorded lock: quote match → deadline →
    expiry/requote → feed freshness → caps → release."""
    quote = get_sell_quote(str(row["quote_id"])) if row.get("quote_id") else None
    if quote is None or not _quote_admits_lock(row, quote):
        # No live quote — unmatched locks are orphan-refunded after the
        # window, never held. A second lock reusing an already-bound quote
        # lands here too.
        update_sell_lock_status(row["ait_tx_hash"], "orphaned", error="no live quote for lock")
        return
    quote_id = str(quote["id"])

    if _lock_age_seconds(row) > cfg.release_deadline_seconds:
        await _refund_lock(cfg, row, "release deadline passed")
        return

    eth_amount = await _price_lock_eth_amount(cfg, row, quote, quote_id)
    if eth_amount is None:
        return

    # Re-check feed freshness immediately before spending ETH.
    if await get_eth_prices_fresh() is None:
        update_sell_lock_status(row["ait_tx_hash"], "stale_price", error="price feed stale at release check")
        return

    amount_eth = Decimal(str(eth_amount))
    if amount_eth > cfg.max_eth_per_tx:
        update_sell_lock_status(
            row["ait_tx_hash"],
            "queued_reserve",
            error=f"{amount_eth} ETH exceeds SELL_MAX_ETH_PER_TX={cfg.max_eth_per_tx}",
        )
        return
    since = (datetime.now() - timedelta(hours=24)).isoformat()
    if get_sell_eth_committed_since(since) + amount_eth > cfg.max_eth_per_day:
        update_sell_lock_status(row["ait_tx_hash"], "queued_reserve", error="daily sell release cap reached")
        return

    try:
        await _release_eth_for_lock(cfg, row, amount_eth)
    except Exception as e:  # noqa: BLE001 - release failure resolved in-place, never raised into the poll
        logger.error("ETH release failed for sell lock %s: %s", row["ait_tx_hash"], e)
        await _resolve_lock_release_failure(cfg, row, e)


async def _handle_orphaned(cfg: SellConfig, row: dict[str, Any]) -> None:
    """Orphan lock (no live quote): refund once the chain has moved past the
    configured orphan window."""
    locked_height = row.get("locked_height")
    if locked_height is None:
        return
    try:
        height = await _chain_height()
    except Exception as e:  # noqa: BLE001 - height probe containment — orphan check skipped
        logger.error("Could not read chain height for orphan check on %s: %s", row["ait_tx_hash"], e)
        return
    if height - int(locked_height) >= cfg.orphan_blocks:
        await _refund_lock(cfg, row, "orphan lock — no matching quote")


async def _handle_inflight(cfg: SellConfig, row: dict[str, Any]) -> None:
    """'releasing'/'needs_review': the ETH-9b resume check — sent → released,
    proven unsent → refund_pending + refund sweep, unknown → stays."""
    outcome, reason = await _verify_sell_release_outcome(row)
    if outcome == "sent":
        await _update_lock_status_with_retry(row["ait_tx_hash"], "released")
        logger.info("Sell lock %s: ETH release confirmed on chain", row["ait_tx_hash"])
    elif outcome == "not_sent":
        update_sell_lock_status(row["ait_tx_hash"], "refund_pending", error="release never reached the chain")
        await _refund_lock(cfg, row, "release never reached the chain")
    else:
        if row["status"] != "needs_review":
            update_sell_lock_status(row["ait_tx_hash"], "needs_review", error="release outcome unverifiable")
        age = wdm._release_intent_age_seconds(row)
        age_txt = f"{int(age)}s" if age != float("inf") else "unknown"
        if reason == "absent_in_grace":
            # Invisible-but-young is routine propagation lag, not an
            # incident — the parked row still surfaces at WARNING (ETH-15).
            logger.warning(
                "Sell lock %s (%s) not yet visible on-chain — inside absence grace; parked needs_review (age=%s)",
                row["ait_tx_hash"],
                row["status"],
                age_txt,
            )
        elif reason in ("chain_view", "nonce_pending") and age < wdm.ETH_RELEASE_ABSENCE_GRACE_SECONDS:
            # Pending/below-depth view on a just-broadcast release — a
            # normal delay (ETH-18). The row did change status, so it
            # still surfaces at WARNING; verify_error and a consumed
            # nonce keep ERROR regardless of age.
            logger.warning(
                "Sell lock %s (%s) not yet confirmed on-chain — reason=%s, age=%s (grace %ds); parked needs_review",
                row["ait_tx_hash"],
                row["status"],
                reason,
                age_txt,
                wdm.ETH_RELEASE_ABSENCE_GRACE_SECONDS,
            )
        else:
            logger.error(
                "Sell lock %s (%s) still unverifiable — needs review (reason=%s, age=%s)",
                row["ait_tx_hash"],
                row["status"],
                reason,
                age_txt,
            )


async def _handle_released(cfg: SellConfig, row: dict[str, Any]) -> None:
    """'released': re-verify the receipt each poll; on 'sent' settle the
    escrowed AIT to treasury; on 'not_sent' (reorg/dropped tx) refund."""
    outcome, _reason = await _verify_sell_release_outcome(row)
    if outcome == "sent":
        await _settle_lock(cfg, row)
    elif outcome == "not_sent":
        update_sell_lock_status(row["ait_tx_hash"], "refund_pending", error="release transaction dropped or reverted")
        await _refund_lock(cfg, row, "release transaction dropped or reverted")
    # 'unknown' keeps the row 'released' — re-checked next poll.


def _parked_refund_reason(row: dict[str, Any]) -> str:
    """The refund reason stored ahead of the parked fee-deficit marker."""
    error = str(row.get("error") or "")
    reason = error.split(_FEE_FLOAT_DEFICIT_MARK)[0].strip()
    return reason or "refund"


async def _handle_stale_price(cfg: SellConfig, row: dict[str, Any]) -> None:
    """Feed-stale park: re-admit at the live rate once the feed recovers;
    deadline still refunds while parked."""
    if await get_eth_prices_fresh() is not None:
        update_sell_lock_status(row["ait_tx_hash"], "locked", error="feed recovered")
        await _handle_locked(cfg, {**row, "status": "locked"})
    elif _lock_age_seconds(row) > cfg.release_deadline_seconds:
        await _refund_lock(cfg, row, "release deadline passed while feed stale")


async def _refund_pending_lock(cfg: SellConfig, row: dict[str, Any]) -> None:
    await _refund_lock(cfg, row, str(row.get("error") or "refund"))


async def _refund_queued_fee_lock(cfg: SellConfig, row: dict[str, Any]) -> None:
    await _refund_lock(cfg, row, _parked_refund_reason(row))


# Binding the function objects at import time is safe here: every handler is a
# module-level function defined above this line, nothing ever rebinds the
# module names (tests stub the DB/RPC seams, not the handlers), and the table
# is read-only after construction. _SELL_STATUS_HANDLERS must cover every
# _SELL_OPEN_STATUSES member except needs_review_sweep (deliberately terminal
# for the machine) — a test pins that.
_SELL_STATUS_HANDLERS: dict[str, Callable[[SellConfig, dict[str, Any]], Awaitable[None]]] = {
    "locked": _handle_locked,
    "queued_reserve": _handle_locked,
    "stale_price": _handle_stale_price,
    "orphaned": _handle_orphaned,
    "refund_pending": _refund_pending_lock,
    "queued_fee_settle": _settle_lock,
    "queued_fee_refund": _refund_queued_fee_lock,
    "releasing": _handle_inflight,
    "needs_review": _handle_inflight,
    "released": _handle_released,
    "settling": _resolve_escrow_sweep,
    "refunding": _resolve_escrow_sweep,
}


async def _process_sell_lock(cfg: SellConfig, row: dict[str, Any]) -> None:
    status = str(row.get("status"))
    if status == "needs_review_sweep":
        # Sweep-path review rows are terminal for the machine: the recorded
        # intent is undecidable (nonce consumed by a foreign tx, nonce or
        # signed blob missing), so only an explicit operator action may move
        # the row — routing it into the ETH-release check could re-release
        # or re-refund funds. See docs/ops/sell-escrow-runbook.md.
        return
    handler = _SELL_STATUS_HANDLERS.get(status)
    if handler is not None:
        await handler(cfg, row)


def _expire_stale_quotes() -> int:
    """Mark 'quoted' rows past their expiry 'expired' — bookkeeping only."""
    expired = 0
    for quote in get_sell_quotes_by_status(("quoted",)):
        try:
            if datetime.now() > datetime.fromisoformat(str(quote.get("expires_at"))):
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
        task = asyncio.create_task(sell_monitor_loop())
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
