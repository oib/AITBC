"""Staking wallet commands"""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import click

from aitbc_agent_core import get_active_brand

from aitbc.utils.units import ait_to_seconds, seconds_to_ait

from ...config import get_config
from ...utils import DECIMAL, error, output, success
from ...utils.crypto_utils import bech32_to_hex
from ...utils.http_client import AITBCHTTPClient
from ...utils.money import wallet_amount as _wallet_amount
from . import _get_wallet_password, _load_wallet, _save_wallet, wallet

_brand = get_active_brand()


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

        return os.getenv("CHAIN_ID", "ait-hub.aitbc.bubuit.net")


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


@wallet.command()
@click.argument("amount", type=DECIMAL)
@click.option("--duration", type=int, default=30, help="Staking duration in days")
@click.pass_context
def stake(ctx, amount: Decimal, duration: int):
    """Stake tokens on blockchain"""
    wallet_name = ctx.obj["wallet_name"]
    wallet_path = ctx.obj["wallet_path"]

    if not wallet_path.exists():
        error(f"Wallet '{wallet_name}' not found")
        return

    wallet_data = _load_wallet(wallet_path, wallet_name)
    sender_address = wallet_data["address"]

    hex_address = bech32_to_hex(sender_address)
    rpc_url = _get_rpc_url(ctx)
    chain_id = _get_chain_id(rpc_url)

    amount_seconds = ait_to_seconds(amount)
    sign_data = {
        "address": hex_address.lower().strip(),
        "amount": amount_seconds,
        "chain_id": chain_id,
        "action": "stake",
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
        "signature": signature,
    }

    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
        result = http_client.post("/rpc/staking/stake", json=stake_data)

        success(f"Staked {amount} AITBC for {duration} days")
        output(
            {
                "wallet": wallet_name,
                "stake_id": result.get("stake_id"),
                "amount": str(amount),
                "duration_days": duration,
                "locked_until": result.get("locked_until"),
                "remaining_balance": str(seconds_to_ait(result.get("remaining_balance", 0))),
                "chain_id": chain_id,
            },
            ctx.obj.get("output_format", "table"),
        )
    except Exception as e:
        error(f"Error staking tokens: {e}")
        raise click.Abort() from e


@wallet.command()
@click.argument("stake_id")
@click.pass_context
def unstake(ctx, stake_id: str):
    """Unstake tokens from blockchain"""
    wallet_name = ctx.obj["wallet_name"]
    wallet_path = ctx.obj["wallet_path"]

    if not wallet_path.exists():
        error(f"Wallet '{wallet_name}' not found")
        return

    wallet_data = _load_wallet(wallet_path, wallet_name)
    sender_address = wallet_data["address"]

    hex_address = bech32_to_hex(sender_address)
    rpc_url = _get_rpc_url(ctx)
    chain_id = _get_chain_id(rpc_url)

    stake_id_int = int(stake_id)
    sign_data = {
        "address": hex_address.lower().strip(),
        "stake_id": stake_id_int,
        "chain_id": chain_id,
        "action": "unstake",
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
        "signature": signature,
    }

    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
        result = http_client.post("/rpc/staking/unstake", json=unstake_data)

        success(f"Unstaked tokens from stake {stake_id}")
        output(
            {
                "wallet": wallet_name,
                "stake_id": stake_id,
                "amount": str(seconds_to_ait(result.get("amount", 0))),
                "new_balance": str(seconds_to_ait(result.get("new_balance", 0))),
                "status": result.get("status"),
                "chain_id": chain_id,
            },
            ctx.obj.get("output_format", "table"),
        )
    except Exception as e:
        error(f"Error unstaking tokens: {e}")
        raise click.Abort() from e


@wallet.command(name="staking-info")
@click.pass_context
def staking_info(ctx):
    """Show staking information from blockchain"""
    wallet_name = ctx.obj["wallet_name"]
    wallet_path = ctx.obj["wallet_path"]

    if not wallet_path.exists():
        error(f"Wallet '{wallet_name}' not found")
        return

    wallet_data = _load_wallet(wallet_path, wallet_name)
    sender_address = wallet_data["address"]

    hex_address = bech32_to_hex(sender_address)
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
                "total_staked": str(seconds_to_ait(result.get("total_staked", 0))),
                "active_stake_count": result.get("active_stake_count"),
                "active_stakes": [
                    {**s, "amount": str(seconds_to_ait(s.get("amount", 0)))} for s in result.get("active_stakes", [])
                ],
            },
            ctx.obj.get("output_format", "table"),
        )
    except Exception as e:
        error(f"Error fetching staking info: {e}")
        raise click.Abort() from e


@wallet.command(name="liquidity-stake")
@click.argument("amount", type=DECIMAL)
@click.option("--pool", default="main", help="Liquidity pool name")
@click.option("--lock-days", type=int, default=0, help="Lock period in days (higher APY)")
@click.pass_context
def liquidity_stake(ctx, amount: Decimal, pool: str, lock_days: int):
    """Stake tokens into a liquidity pool"""
    wallet_name = ctx.obj["wallet_name"]
    wallet_path = ctx.obj.get("wallet_path")
    if not wallet_path or not Path(wallet_path).exists():
        error("Wallet not found")
        ctx.exit(1)
        return

    wallet_data = _load_wallet(Path(wallet_path), wallet_name)

    balance = _wallet_amount(wallet_data.get("balance", 0))
    if balance < amount:
        error(f"Insufficient balance. Available: {balance}, Required: {amount}")
        ctx.exit(1)
        return

    # APY tiers based on lock period
    if lock_days >= 90:
        apy = 12.0
        tier = "platinum"
    elif lock_days >= 30:
        apy = 8.0
        tier = "gold"
    elif lock_days >= 7:
        apy = 5.0
        tier = "silver"
    else:
        apy = 3.0
        tier = "bronze"

    import secrets

    stake_id = f"liq_{secrets.token_hex(6)}"
    now = datetime.now(UTC)

    liq_record = {
        "stake_id": stake_id,
        "pool": pool,
        "amount": str(amount),
        "apy": apy,
        "tier": tier,
        "lock_days": lock_days,
        "start_date": now.isoformat(),
        "unlock_date": (now + timedelta(days=lock_days)).isoformat() if lock_days > 0 else None,
        "status": "active",
    }

    wallet_data.setdefault("liquidity", []).append(liq_record)
    wallet_data["balance"] = str(balance - amount)

    wallet_data["transactions"].append(
        {
            "type": "liquidity_stake",
            "amount": str(-amount),
            "pool": pool,
            "stake_id": stake_id,
            "timestamp": now.isoformat(),
        }
    )

    # Save wallet with encryption
    password = None
    if wallet_data.get("encrypted"):
        password = _get_wallet_password(wallet_name)
    _save_wallet(Path(wallet_path), wallet_data, password if password else None)

    success(f"Staked {amount} AITBC into '{pool}' pool ({tier} tier, {apy}% APY)")
    output(
        {
            "stake_id": stake_id,
            "pool": pool,
            "amount": str(amount),
            "apy": apy,
            "tier": tier,
            "lock_days": lock_days,
            "new_balance": wallet_data["balance"],
        },
        ctx.obj.get("output_format", "table"),
    )


@wallet.command(name="liquidity-unstake")
@click.argument("stake_id")
@click.pass_context
def liquidity_unstake(ctx, stake_id: str):
    """Withdraw from a liquidity pool with rewards"""
    wallet_name = ctx.obj["wallet_name"]
    wallet_path = ctx.obj.get("wallet_path")
    if not wallet_path or not Path(wallet_path).exists():
        error("Wallet not found")
        ctx.exit(1)
        return

    wallet_data = _load_wallet(Path(wallet_path), wallet_name)

    liquidity = wallet_data.get("liquidity", [])
    record = next(
        (r for r in liquidity if r["stake_id"] == stake_id and r["status"] == "active"),
        None,
    )

    if not record:
        error(f"Active liquidity stake '{stake_id}' not found")
        ctx.exit(1)
        return

    # Check lock period
    if record.get("unlock_date"):
        unlock = datetime.fromisoformat(record["unlock_date"])
        if datetime.now() < unlock:
            error(f"Stake is locked until {record['unlock_date']}")
            ctx.exit(1)
            return

    # Calculate rewards
    start = datetime.fromisoformat(record["start_date"])
    days_staked = max((datetime.now(UTC) - start.replace(tzinfo=UTC)).total_seconds() / 86400, 0.001)
    principal = _wallet_amount(record["amount"])
    rewards = principal * (Decimal(str(record["apy"])) / 100) * (Decimal(str(days_staked)) / 365)
    total = principal + rewards

    record["status"] = "completed"
    record["end_date"] = datetime.now(UTC).isoformat()
    record["rewards"] = str(round(rewards, 6))

    wallet_data["balance"] = str(_wallet_amount(wallet_data.get("balance", 0)) + total)

    wallet_data["transactions"].append(
        {
            "type": "liquidity_unstake",
            "amount": str(total),
            "principal": str(principal),
            "rewards": str(round(rewards, 6)),
            "pool": record["pool"],
            "stake_id": stake_id,
            "timestamp": datetime.now(UTC).isoformat(),
        }
    )

    # Save wallet with encryption
    password = None
    if wallet_data.get("encrypted"):
        password = _get_wallet_password(wallet_name)
    _save_wallet(Path(wallet_path), wallet_data, password if password else None)

    success(f"Withdrawn {total:.6f} AITBC (principal: {principal}, rewards: {rewards:.6f})")
    output(
        {
            "stake_id": stake_id,
            "pool": record["pool"],
            "principal": str(principal),
            "rewards": str(round(rewards, 6)),
            "total_returned": str(round(total, 6)),
            "days_staked": round(days_staked, 2),
            "apy": record["apy"],
            "new_balance": str(round(_wallet_amount(wallet_data["balance"]), 6)),
        },
        ctx.obj.get("output_format", "table"),
    )
