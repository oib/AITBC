"""Staking wallet commands for AITBC CLI"""

from datetime import datetime, timedelta
from pathlib import Path

import click

from ...utils import error, output, success
from ...utils.http_client import AITBCHTTPClient
from . import _get_wallet_password, _load_wallet, _save_wallet, wallet


@wallet.command()
@click.argument("amount", type=float)
@click.option("--duration", type=int, default=30, help="Staking duration in days")
@click.pass_context
def stake(ctx, amount: float, duration: int):
    """Stake AITBC tokens on blockchain"""
    wallet_name = ctx.obj["wallet_name"]
    wallet_path = ctx.obj["wallet_path"]

    if not wallet_path.exists():
        error(f"Wallet '{wallet_name}' not found")
        return

    wallet_data = _load_wallet(wallet_path, wallet_name)
    sender_address = wallet_data["address"]

    # Convert bech32 address to hex for RPC compatibility
    from ...utils.crypto_utils import bech32_to_hex

    hex_address = bech32_to_hex(sender_address)

    # Get RPC URL from config (use hub for cross-node operations)
    from ...config import get_config

    config = get_config()
    rpc_url = getattr(config, "blockchain_rpc_url", "http://localhost:8202")
    # Use hub RPC for cross-node transaction propagation
    rpc_url = rpc_url.replace("localhost", config.hub_discovery_url or "hub.aitbc.bubuit.net")

    # Get chain_id
    try:
        from ...utils.chain_id import get_chain_id

        chain_id = get_chain_id(rpc_url, override=None, timeout=5)
    except Exception:
        import os

        chain_id = os.getenv("CHAIN_ID", "ait-hub.aitbc.bubuit.net")

    # Submit staking request to blockchain RPC
    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
        stake_data = {
            "address": hex_address,
            "amount": int(amount * 10**18),  # Convert to wei
            "lock_days": duration,
            "chain_id": chain_id,
        }
        result = http_client.post("/rpc/staking/stake", json=stake_data)

        success(f"Staked {amount} AITBC for {duration} days")
        output(
            {
                "wallet": wallet_name,
                "stake_id": result.get("stake_id"),
                "amount": amount,
                "duration_days": duration,
                "locked_until": result.get("locked_until"),
                "remaining_balance": result.get("remaining_balance"),
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
    """Unstake AITBC tokens from blockchain"""
    wallet_name = ctx.obj["wallet_name"]
    wallet_path = ctx.obj["wallet_path"]

    if not wallet_path.exists():
        error(f"Wallet '{wallet_name}' not found")
        return

    wallet_data = _load_wallet(wallet_path, wallet_name)
    sender_address = wallet_data["address"]

    # Convert bech32 address to hex for RPC compatibility
    from ...utils.crypto_utils import bech32_to_hex

    hex_address = bech32_to_hex(sender_address)

    # Get RPC URL from config (use hub for cross-node operations)
    from ...config import get_config

    config = get_config()
    rpc_url = getattr(config, "blockchain_rpc_url", "http://localhost:8202")
    # Use hub RPC for cross-node transaction propagation
    rpc_url = rpc_url.replace("localhost", config.hub_discovery_url or "hub.aitbc.bubuit.net")

    # Get chain_id
    try:
        from ...utils.chain_id import get_chain_id

        chain_id = get_chain_id(rpc_url, override=None, timeout=5)
    except Exception:
        import os

        chain_id = os.getenv("CHAIN_ID", "ait-hub.aitbc.bubuit.net")

    # Submit unstaking request to blockchain RPC
    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
        unstake_data = {"address": hex_address, "stake_id": int(stake_id), "chain_id": chain_id}
        result = http_client.post("/rpc/staking/unstake", json=unstake_data)

        success(f"Unstaked tokens from stake {stake_id}")
        output(
            {
                "wallet": wallet_name,
                "stake_id": stake_id,
                "amount": result.get("amount"),
                "new_balance": result.get("new_balance"),
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

    # Convert bech32 address to hex for RPC compatibility
    from ...utils.crypto_utils import bech32_to_hex

    hex_address = bech32_to_hex(sender_address)

    # Get RPC URL from config (use hub for cross-node operations)
    from ...config import get_config

    config = get_config()
    rpc_url = getattr(config, "blockchain_rpc_url", "http://localhost:8202")
    # Use hub RPC for cross-node transaction propagation
    rpc_url = rpc_url.replace("localhost", config.hub_discovery_url or "hub.aitbc.bubuit.net")

    # Get chain_id
    try:
        from ...utils.chain_id import get_chain_id

        chain_id = get_chain_id(rpc_url, override=None, timeout=5)
    except Exception:
        import os

        chain_id = os.getenv("CHAIN_ID", "ait-hub.aitbc.bubuit.net")

    # Query staking info from blockchain RPC
    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
        result = http_client.get(f"/rpc/staking/{hex_address}?chain_id={chain_id}")

        output(
            {
                "wallet": wallet_name,
                "address": sender_address,
                "chain_id": chain_id,
                "total_staked": result.get("total_staked"),
                "active_stake_count": result.get("active_stake_count"),
                "active_stakes": result.get("active_stakes", []),
            },
            ctx.obj.get("output_format", "table"),
        )
    except Exception as e:
        error(f"Error fetching staking info: {e}")
        raise click.Abort() from e


@wallet.command(name="liquidity-stake")
@click.argument("amount", type=float)
@click.option("--pool", default="main", help="Liquidity pool name")
@click.option("--lock-days", type=int, default=0, help="Lock period in days (higher APY)")
@click.pass_context
def liquidity_stake(ctx, amount: float, pool: str, lock_days: int):
    """Stake tokens into a liquidity pool"""
    wallet_name = ctx.obj["wallet_name"]
    wallet_path = ctx.obj.get("wallet_path")
    if not wallet_path or not Path(wallet_path).exists():
        error("Wallet not found")
        ctx.exit(1)
        return

    wallet_data = _load_wallet(Path(wallet_path), wallet_name)

    balance = wallet_data.get("balance", 0)
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
    now = datetime.now()

    liq_record = {
        "stake_id": stake_id,
        "pool": pool,
        "amount": amount,
        "apy": apy,
        "tier": tier,
        "lock_days": lock_days,
        "start_date": now.isoformat(),
        "unlock_date": (now + timedelta(days=lock_days)).isoformat() if lock_days > 0 else None,
        "status": "active",
    }

    wallet_data.setdefault("liquidity", []).append(liq_record)
    wallet_data["balance"] = balance - amount

    wallet_data["transactions"].append(
        {
            "type": "liquidity_stake",
            "amount": -amount,
            "pool": pool,
            "stake_id": stake_id,
            "timestamp": now.isoformat(),
        }
    )

    # Save wallet with encryption
    password = None
    if wallet_data.get("encrypted"):
        password = _get_wallet_password(wallet_name)
    _save_wallet(Path(wallet_path), wallet_data, password)

    success(f"Staked {amount} AITBC into '{pool}' pool ({tier} tier, {apy}% APY)")
    output(
        {
            "stake_id": stake_id,
            "pool": pool,
            "amount": amount,
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
    days_staked = max((datetime.now() - start).total_seconds() / 86400, 0.001)
    rewards = record["amount"] * (record["apy"] / 100) * (days_staked / 365)
    total = record["amount"] + rewards

    record["status"] = "completed"
    record["end_date"] = datetime.now().isoformat()
    record["rewards"] = round(rewards, 6)

    wallet_data["balance"] = wallet_data.get("balance", 0) + total

    wallet_data["transactions"].append(
        {
            "type": "liquidity_unstake",
            "amount": total,
            "principal": record["amount"],
            "rewards": round(rewards, 6),
            "pool": record["pool"],
            "stake_id": stake_id,
            "timestamp": datetime.now().isoformat(),
        }
    )

    # Save wallet with encryption
    password = None
    if wallet_data.get("encrypted"):
        password = _get_wallet_password(wallet_name)
    _save_wallet(Path(wallet_path), wallet_data, password)

    success(f"Withdrawn {total:.6f} AITBC (principal: {record['amount']}, rewards: {rewards:.6f})")
    output(
        {
            "stake_id": stake_id,
            "pool": record["pool"],
            "principal": record["amount"],
            "rewards": round(rewards, 6),
            "total_returned": round(total, 6),
            "days_staked": round(days_staked, 2),
            "apy": record["apy"],
            "new_balance": round(wallet_data["balance"], 6),
        },
        ctx.obj.get("output_format", "table"),
    )
