"""Staking wallet commands"""

import json
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import click

from aitbc.utils.units import ait_to_units, units_to_ait

from aitbc.crypto.signature_recovery import canonical_address
from aitbc.utils.validation import validate_address

from ...config import get_config
from ...utils import DECIMAL, error, output, success
from ...utils.http_client import AITBCHTTPClient, http_error_detail
from ...utils.money import wallet_amount as _wallet_amount
from . import _get_wallet_password, _load_wallet, _save_wallet, wallet


LIQUIDITY_FEE_DEFAULT_AIT = Decimal("0.01")


def _brand_token_symbol() -> str:
    """Return the active brand token symbol, falling back to the default."""
    try:
        from aitbc_agent_core import get_active_brand

        return get_active_brand().token_symbol
    except Exception:
        return "AITBC"


def _get_rpc_url(ctx: click.Context) -> str:
    """Resolve the blockchain RPC URL, preferring the wallet command override."""
    rpc_url = ctx.obj.get("rpc_url") if ctx.obj else None
    if not rpc_url:
        config = get_config()
        rpc_url = getattr(config, "blockchain_rpc_url", None) or "http://localhost:8202"
    return rpc_url


def _get_chain_id(rpc_url: str) -> str:
    """Resolve chain_id, falling back to the environment default."""
    try:
        from ...utils.chain_id import get_chain_id

        return get_chain_id(rpc_url, override=None, timeout=5)
    except Exception:
        import os

        return os.getenv("CHAIN_ID", "ait-localnet")


def _get_account_nonce(http_client: AITBCHTTPClient, address: str, chain_id: str) -> int:
    """Fetch the on-chain nonce for an address."""
    try:
        account = http_client.get(f"/rpc/account/{address}?chain_id={chain_id}")
        return int(account.get("nonce", 0))
    except Exception:
        return 0


def _sign_transaction(wallet_data: dict[str, Any], tx: dict[str, Any]) -> str:
    """Sign a transaction dict with the wallet's private key."""
    from eth_keys import keys
    from eth_utils import keccak

    private_key = wallet_data.get("private_key")
    if not private_key:
        raise click.ClickException("Wallet private key is not available")

    if private_key.startswith("0x"):
        private_key = private_key[2:]
    pk = keys.PrivateKey(bytes.fromhex(private_key))

    signed = {k: v for k, v in tx.items() if k != "signature"}
    message = json.dumps(signed, sort_keys=True, separators=(",", ":")).encode()
    signature = pk.sign_msg_hash(keccak(message))
    return signature.to_bytes().hex()


def _submit_liquidity_transaction(
    ctx: click.Context,
    wallet_data: dict[str, Any],
    tx: dict[str, Any],
) -> str:
    """Sign and submit a LIQUIDITY_* transaction, returning the tx hash."""

    rpc_url = _get_rpc_url(ctx)
    chain_id = _get_chain_id(rpc_url)
    address = canonical_address(wallet_data["address"])

    http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
    tx["nonce"] = _get_account_nonce(http_client, address, chain_id)
    tx["chain_id"] = chain_id
    tx["signature"] = _sign_transaction(wallet_data, tx)

    result = http_client.post("/rpc/transaction", json=tx)
    tx_hash = result.get("transaction_hash")
    if not tx_hash:
        raise click.ClickException(f"Transaction submission failed: {result}")
    return str(tx_hash)


def _sign_staking_message(wallet_data: dict[str, Any], sign_data: dict[str, Any]) -> str:
    """Sign the canonical JSON of sign_data with the wallet's private key."""
    from aitbc.crypto.crypto import sign_transaction_hash
    from eth_utils import keccak

    private_key = wallet_data.get("private_key")
    if not private_key:
        raise click.ClickException("Wallet private key is not available")

    message = json.dumps(sign_data, sort_keys=True, separators=(",", ":")).encode()
    message_hash = keccak(message).hex()
    return sign_transaction_hash(message_hash, str(private_key))


def _http_error_detail(exc: BaseException) -> str | None:
    """Extract the FastAPI ``detail`` message from a wrapped HTTP error.

    Delegates to the shared helper; kept as a thin wrapper so existing call
    sites read ``detail or e`` without a new import name.
    """
    return http_error_detail(exc)


def _stake_release_preflight(
    http_client: AITBCHTTPClient, address: str, chain_id: str, stake_id: int
) -> tuple[str | None, str | None]:
    """Pre-flight an on-chain unstake before submitting the release.

    Returns ``(error, locked_until)``: ``error`` is a human-readable reason
    the release cannot proceed (the stake is absent/inactive or still inside
    its lock window); ``locked_until`` is the stake's lock expiry when the
    node reports it. On any lookup failure both are None so the write path
    stays authoritative — the node still rejects an invalid release itself.
    """
    try:
        info = http_client.get(f"/rpc/staking/{address}?chain_id={chain_id}")
    except Exception:
        return None, None
    active: dict[int, dict[str, Any]] = {}
    for s in info.get("active_stakes") or []:
        try:
            active[int(s.get("stake_id"))] = s
        except (TypeError, ValueError):
            continue
    entry = active.get(stake_id)
    if entry is None:
        return (
            f"no active stake {stake_id} found for this wallet on {chain_id} (already withdrawn or unknown to this node)",
            None,
        )
    locked_until = entry.get("locked_until")
    if locked_until:
        try:
            expiry = datetime.fromisoformat(str(locked_until))
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=UTC)
            if expiry > datetime.now(UTC):
                return (
                    f"stake {stake_id} is still locked until {locked_until} — the lock (unbonding) period has not expired",
                    str(locked_until),
                )
        except (TypeError, ValueError):
            pass  # unparsable timestamp — let the node decide
    return None, str(locked_until) if locked_until else None


@wallet.command(
    epilog="""Examples:

  aitbc wallet stake --amount 100 --duration 30"""
)
@click.option("--amount", "amount", required=True, type=DECIMAL, help="Amount of AIT.")
@click.option("--duration", type=int, default=30, help="Staking duration in days")
@click.pass_context
def stake(ctx, amount: Decimal, duration: int):
    """Stake AITBC tokens on the blockchain for a configurable duration."""
    wallet_name = ctx.obj["wallet_name"]
    wallet_path = ctx.obj["wallet_path"]

    if not wallet_path.exists():
        error(f"Wallet '{wallet_name}' not found")
        return

    wallet_data = _load_wallet(wallet_path, wallet_name)
    sender_address = wallet_data["address"]

    hex_address = canonical_address(sender_address)
    if not validate_address(hex_address):
        error(f"Invalid sender address: {sender_address}")
        return
    rpc_url = _get_rpc_url(ctx)
    chain_id = _get_chain_id(rpc_url)

    http_client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
    amount_seconds = ait_to_units(amount)
    # The node requires the signed message to carry the account nonce and a
    # fresh timestamp so a captured signature cannot be replayed later.
    nonce = _get_account_nonce(http_client, hex_address, chain_id)
    timestamp = int(time.time())
    sign_data = {
        "address": hex_address.lower().strip(),
        "amount": amount_seconds,
        "chain_id": chain_id,
        "action": "stake",
        "nonce": nonce,
        "timestamp": timestamp,
    }

    try:
        signature = _sign_staking_message(wallet_data, sign_data)
    except click.ClickException as e:
        error(str(e))
        return

    stake_data = {
        "address": hex_address,
        "amount": amount_seconds,
        "lock_days": duration,
        "chain_id": chain_id,
        "nonce": nonce,
        "timestamp": timestamp,
        "signature": signature,
    }

    try:
        result = http_client.post("/rpc/staking/stake", json=stake_data)

        success(f"Submitted a stake of {amount} {_brand_token_symbol()} for {duration} days")
        # The node no longer debits the balance in the request. It queues a
        # STAKE_LOCK transfer that is applied when the next block includes it,
        # so there is no post-stake balance to report here -- show the
        # transaction to follow instead.
        remaining = result.get("remaining_balance") or 0
        output(
            {
                "wallet": wallet_name,
                "stake_id": result.get("stake_id"),
                "amount": str(amount),
                "remaining_balance": str(units_to_ait(remaining)),
                "duration_days": duration,
                "locked_until": result.get("locked_until"),
                "transaction_hash": result.get("transaction_hash"),
                "chain_id": chain_id,
            },
            ctx.obj.get("output_format", "table"),
        )
    except Exception as e:
        detail = _http_error_detail(e)
        error(f"Error staking tokens: {detail or e}")
        raise click.Abort() from e


@wallet.command(
    epilog="""Examples:

  aitbc wallet unstake --stake-id 42"""
)
@click.option("--stake-id", "stake_id", required=True, help="Numeric stake ID returned by 'stake'.")
@click.pass_context
def unstake(ctx, stake_id: str):
    """Unstake tokens and withdraw the principal for the given stake ID."""
    wallet_name = ctx.obj["wallet_name"]
    wallet_path = ctx.obj["wallet_path"]

    if not wallet_path.exists():
        error(f"Wallet '{wallet_name}' not found")
        return

    wallet_data = _load_wallet(wallet_path, wallet_name)
    sender_address = wallet_data["address"]

    hex_address = canonical_address(sender_address)
    if not validate_address(hex_address):
        error(f"Invalid sender address: {sender_address}")
        return
    rpc_url = _get_rpc_url(ctx)
    chain_id = _get_chain_id(rpc_url)

    try:
        stake_id_int = int(stake_id)
    except ValueError:
        error(f"Invalid stake ID '{stake_id}': expected the numeric stake_id returned by 'stake'")
        raise click.Abort() from None
    http_client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
    nonce = _get_account_nonce(http_client, hex_address, chain_id)
    timestamp = int(time.time())
    sign_data = {
        "address": hex_address.lower().strip(),
        "stake_id": stake_id_int,
        "chain_id": chain_id,
        "action": "unstake",
        "nonce": nonce,
        "timestamp": timestamp,
    }

    try:
        signature = _sign_staking_message(wallet_data, sign_data)
    except click.ClickException as e:
        error(str(e))
        return

    unstake_data = {
        "address": hex_address,
        "stake_id": stake_id_int,
        "chain_id": chain_id,
        "nonce": nonce,
        "timestamp": timestamp,
        "signature": signature,
    }

    try:
        locked_until = None
        block_reason, locked_until = _stake_release_preflight(http_client, hex_address, chain_id, stake_id_int)
        if block_reason:
            error(f"Cannot unstake: {block_reason}")
            raise click.Abort()
        result = http_client.post("/rpc/staking/unstake", json=unstake_data)

        success(f"Submitted an unstake of stake {stake_id}")
        # As with staking, the credit lands when the STAKE_RELEASE transfer is
        # included in a block, so report the transaction rather than a balance.
        result_out = {
            "wallet": wallet_name,
            "stake_id": stake_id,
            "amount": str(units_to_ait(result.get("amount", 0))),
            "transaction_hash": result.get("transaction_hash"),
            "status": result.get("status"),
            "chain_id": chain_id,
        }
        if locked_until:
            result_out["locked_until"] = locked_until
        output(result_out, ctx.obj.get("output_format", "table"))
    except click.Abort:
        raise
    except Exception as e:
        detail = _http_error_detail(e)
        error(f"Error unstaking tokens: {detail or e}")
        raise click.Abort() from e


@wallet.command(
    name="staking-info",
    epilog="""Examples:

  aitbc wallet staking-info

  aitbc wallet staking-info --address 0x1234...""",
)
@click.option("--address", "address_override", default=None, help="Query this address instead of the active wallet")
@click.pass_context
def staking_info(ctx, address_override: str | None):
    """Show current staking information and rewards from the blockchain RPC."""
    wallet_name = ctx.obj["wallet_name"]
    wallet_path = ctx.obj["wallet_path"]

    if address_override:
        sender_address = address_override
        wallet_name = "(by address)"
    else:
        if not wallet_path.exists():
            error(f"Wallet '{wallet_name}' not found")
            return

        wallet_data = _load_wallet(wallet_path, wallet_name)
        sender_address = wallet_data["address"]

    hex_address = canonical_address(sender_address)
    if not validate_address(hex_address):
        error(f"Invalid sender address: {sender_address}")
        return
    rpc_url = _get_rpc_url(ctx)
    chain_id = _get_chain_id(rpc_url)

    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
        result = http_client.get(f"/rpc/staking/{hex_address}?chain_id={chain_id}")

        output(
            {
                "wallet": wallet_name,
                "address": sender_address,
                "chain_id": chain_id,
                "total_staked": str(units_to_ait(result.get("total_staked", 0))),
                "active_stake_count": result.get("active_stake_count"),
                "active_stakes": [
                    {**s, "amount": str(units_to_ait(s.get("amount", 0)))} for s in result.get("active_stakes", [])
                ],
            },
            ctx.obj.get("output_format", "table"),
        )
    except Exception as e:
        detail = _http_error_detail(e)
        error(f"Error fetching staking info: {detail or e}")
        raise click.Abort() from e


@wallet.command(
    name="liquidity-stake",
    epilog="""Examples:

  aitbc wallet liquidity-stake --amount 50 --pool main --lock-days 7""",
)
@click.option("--amount", "amount", required=True, type=DECIMAL, help="Amount of AIT.")
@click.option("--pool", default="main", help="Liquidity pool name")
@click.option("--lock-days", type=int, default=0, help="Lock period in days (higher APY)")
@click.option("--fee", type=DECIMAL, default="0.01", help="Transaction fee in AIT")
@click.pass_context
def liquidity_stake(ctx, amount: Decimal, pool: str, lock_days: int, fee: Decimal):
    """Stake tokens into an on-chain liquidity pool to earn rewards."""
    wallet_name = ctx.obj["wallet_name"]
    wallet_path = ctx.obj.get("wallet_path")
    if not wallet_path or not Path(wallet_path).exists():
        error("Wallet not found")
        ctx.exit(1)
        return

    wallet_data = _load_wallet(Path(wallet_path), wallet_name)
    balance = _wallet_amount(wallet_data.get("balance", 0))
    if balance < amount + fee:
        error(f"Insufficient balance. Available: {balance}, Required: {amount + fee}")
        ctx.exit(1)
        return

    hex_address = canonical_address(wallet_data["address"])
    amount_seconds = int(ait_to_units(amount))
    fee_seconds = int(ait_to_units(fee))

    tx = {
        "type": "LIQUIDITY_DEPOSIT",
        "from": hex_address,
        "to": _pool_main_address(),
        "amount": amount_seconds,
        "fee": fee_seconds,
        "payload": {
            "pool_id": pool,
            "lock_days": lock_days,
            "to": _pool_main_address(),
            "amount": amount_seconds,
        },
    }

    try:
        tx_hash = _submit_liquidity_transaction(ctx, wallet_data, tx)
    except click.ClickException as e:
        error(str(e))
        ctx.exit(1)
        return
    except Exception as e:
        detail = _http_error_detail(e)
        error(f"Error submitting liquidity deposit: {detail or e}")
        ctx.exit(1)
        return

    # Keep a local cache entry for convenience, but mark it as on-chain-backed.
    liq_record = {
        "stake_id": None,  # will be set by on-chain state
        "pool": pool,
        "amount": str(amount),
        "lock_days": lock_days,
        "tx_hash": tx_hash,
        "status": "active",
    }
    wallet_data.setdefault("liquidity", []).append(liq_record)
    password = None
    if wallet_data.get("encrypted"):
        password = _get_wallet_password(wallet_name)
    _save_wallet(Path(wallet_path), wallet_data, password if password else None)

    success(f"Submitted liquidity deposit of {amount} AIT to pool '{pool}' (tx={tx_hash})")
    output(
        {
            "transaction_hash": tx_hash,
            "pool": pool,
            "amount": str(amount),
            "lock_days": lock_days,
            "fee": str(fee),
        },
        ctx.obj.get("output_format", "table"),
    )


@wallet.command(
    name="liquidity-claim",
    epilog="""Examples:

  aitbc wallet liquidity-claim --stake-id lstake-5678""",
)
@click.option("--stake-id", "stake_id", required=True, help="Stake ID.")
@click.option("--fee", type=DECIMAL, default="0.01", help="Transaction fee in AIT")
@click.pass_context
def liquidity_claim(ctx, stake_id: str, fee: Decimal):
    """Claim accrued liquidity rewards for the given stake ID."""
    wallet_name = ctx.obj["wallet_name"]
    wallet_path = ctx.obj.get("wallet_path")
    if not wallet_path or not Path(wallet_path).exists():
        error("Wallet not found")
        ctx.exit(1)
        return

    wallet_data = _load_wallet(Path(wallet_path), wallet_name)
    hex_address = canonical_address(wallet_data["address"])
    fee_seconds = int(ait_to_units(fee))

    tx = {
        "type": "LIQUIDITY_CLAIM",
        "from": hex_address,
        "to": hex_address,
        "amount": 0,
        "fee": fee_seconds,
        "payload": {
            "pool_id": "main",
            "stake_id": stake_id,
            "to": hex_address,
            "amount": 0,
        },
    }

    try:
        tx_hash = _submit_liquidity_transaction(ctx, wallet_data, tx)
    except click.ClickException as e:
        error(str(e))
        ctx.exit(1)
        return
    except Exception as e:
        detail = _http_error_detail(e)
        error(f"Error submitting liquidity claim: {detail or e}")
        ctx.exit(1)
        return

    success(f"Submitted liquidity claim for stake {stake_id} (tx={tx_hash})")
    output(
        {"transaction_hash": tx_hash, "stake_id": stake_id, "fee": str(fee)},
        ctx.obj.get("output_format", "table"),
    )


@wallet.command(
    name="liquidity-unstake",
    epilog="""Examples:

  aitbc wallet liquidity-unstake --stake-id lstake-5678""",
)
@click.option("--stake-id", "stake_id", required=True, help="Stake ID.")
@click.option("--fee", type=DECIMAL, default="0.01", help="Transaction fee in AIT")
@click.pass_context
def liquidity_unstake(ctx, stake_id: str, fee: Decimal):
    """Withdraw a liquidity stake and its accumulated rewards."""
    wallet_name = ctx.obj["wallet_name"]
    wallet_path = ctx.obj.get("wallet_path")
    if not wallet_path or not Path(wallet_path).exists():
        error("Wallet not found")
        ctx.exit(1)
        return

    wallet_data = _load_wallet(Path(wallet_path), wallet_name)
    hex_address = canonical_address(wallet_data["address"])
    fee_seconds = int(ait_to_units(fee))

    tx = {
        "type": "LIQUIDITY_WITHDRAW",
        "from": hex_address,
        "to": hex_address,
        "amount": 0,
        "fee": fee_seconds,
        "payload": {
            "pool_id": "main",
            "stake_id": stake_id,
            "to": hex_address,
            "amount": 0,
        },
    }

    try:
        tx_hash = _submit_liquidity_transaction(ctx, wallet_data, tx)
    except click.ClickException as e:
        error(str(e))
        ctx.exit(1)
        return
    except Exception as e:
        detail = _http_error_detail(e)
        error(f"Error submitting liquidity withdraw: {detail or e}")
        ctx.exit(1)
        return

    for rec in wallet_data.get("liquidity", []):
        if rec.get("stake_id") == stake_id and rec.get("status") == "active":
            rec["status"] = "completed"
    password = None
    if wallet_data.get("encrypted"):
        password = _get_wallet_password(wallet_name)
    _save_wallet(Path(wallet_path), wallet_data, password if password else None)

    success(f"Submitted liquidity unstake for stake {stake_id} (tx={tx_hash})")
    output(
        {"transaction_hash": tx_hash, "stake_id": stake_id, "fee": str(fee)},
        ctx.obj.get("output_format", "table"),
    )


def _pool_main_address() -> str:
    """Return the canonical pool main address deterministically."""
    from aitbc.crypto.signature_recovery import canonical_address
    from eth_utils import keccak

    return canonical_address("0x" + keccak(b"aitbc.pool.main").hex()[:40])
