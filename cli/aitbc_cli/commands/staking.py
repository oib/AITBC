"""Top-level staking commands — real, wallet-signed, on-chain paths.

``aitbc stake``, ``aitbc unstake``, and ``aitbc liquidity-stake`` delegate to
the ``aitbc wallet`` staking implementations (signed ``/rpc/staking/*``
requests that queue STAKE_LOCK/STAKE_RELEASE protocol transfers, and signed
``LIQUIDITY_*`` transactions submitted to ``/rpc/transaction``), so the
scenario surface works without the ``wallet`` group prefix.

Wallet resolution matches ``aitbc wallet``: ``--wallet-path`` >
``--wallet-name`` > ``AITBC_DEFAULT_WALLET`` > ``~/.aitbc/config.yaml``
``active_wallet`` > ``default``.
"""

from decimal import Decimal

import click

from ..utils import DECIMAL
from .wallet import wallet as _wallet_group
from .wallet.staking import liquidity_stake as _wallet_liquidity_stake
from .wallet.staking import stake as _wallet_stake
from .wallet.staking import unstake as _wallet_unstake


def _bind_wallet(
    ctx: click.Context,
    wallet_name: str | None,
    wallet_path: str | None,
    rpc_url: str | None,
) -> None:
    """Populate ``ctx.obj`` exactly like the ``wallet`` group callback.

    Runs the wallet group's own resolution so delegated staking commands see
    the same ``wallet_name``/``wallet_path``/``chain_id`` values a real
    ``aitbc wallet ...`` invocation would compute.
    """
    ctx.ensure_object(dict)
    if rpc_url:
        ctx.obj["rpc_url"] = rpc_url
    ctx.invoke(
        _wallet_group,
        wallet_name=wallet_name,
        wallet_path=wallet_path,
        use_daemon=True,
        chain_id=ctx.obj.get("chain_id"),
    )


@click.command(
    epilog="""Examples:

  aitbc stake --amount 100 --duration 30

  aitbc stake --wallet-name staker --amount 50 --duration 90 --rpc-url http://localhost:8202

See also: `aitbc wallet staking-info` lists active stakes and their IDs."""
)
@click.option("--wallet-name", "wallet_name", help="Name of the wallet to stake from")
@click.option("--wallet-path", "wallet_path", help="Direct path to wallet file (overrides --wallet-name)")
@click.option("--rpc-url", "rpc_url", help="Blockchain RPC URL (overrides config)")
@click.option("--amount", "amount", required=True, type=DECIMAL, help="Amount of AIT.")
@click.option("--duration", type=int, default=30, help="Staking duration in days")
@click.pass_context
def stake(ctx, wallet_name: str | None, wallet_path: str | None, rpc_url: str | None, amount: Decimal, duration: int):
    """Stake AITBC tokens on-chain for a configurable lock duration."""
    _bind_wallet(ctx, wallet_name, wallet_path, rpc_url)
    return ctx.invoke(_wallet_stake, amount=amount, duration=duration)


@click.command(
    epilog="""Examples:

  aitbc unstake --stake-id 7

  aitbc unstake --wallet-name staker --stake-id 7

Use `aitbc wallet staking-info` to find the stake IDs of your active stakes."""
)
@click.option("--wallet-name", "wallet_name", help="Name of the wallet to unstake into")
@click.option("--wallet-path", "wallet_path", help="Direct path to wallet file (overrides --wallet-name)")
@click.option("--rpc-url", "rpc_url", help="Blockchain RPC URL (overrides config)")
@click.option("--stake-id", "stake_id", required=True, help="Numeric stake ID returned by 'stake'.")
@click.pass_context
def unstake(ctx, wallet_name: str | None, wallet_path: str | None, rpc_url: str | None, stake_id: str):
    """Unstake tokens once the lock period ends and withdraw the principal."""
    _bind_wallet(ctx, wallet_name, wallet_path, rpc_url)
    return ctx.invoke(_wallet_unstake, stake_id=stake_id)


@click.command(
    name="liquidity-stake",
    epilog="""Examples:

  aitbc liquidity-stake --amount 50 --pool main --lock-days 7

  aitbc liquidity-stake --wallet-name staker --amount 25 --fee 0.01

See also: `aitbc wallet liquidity-unstake` and `aitbc wallet liquidity-claim`.""",
)
@click.option("--wallet-name", "wallet_name", help="Name of the wallet to stake from")
@click.option("--wallet-path", "wallet_path", help="Direct path to wallet file (overrides --wallet-name)")
@click.option("--rpc-url", "rpc_url", help="Blockchain RPC URL (overrides config)")
@click.option("--amount", "amount", required=True, type=DECIMAL, help="Amount of AIT.")
@click.option("--pool", default="main", help="Liquidity pool name")
@click.option("--lock-days", type=int, default=0, help="Lock period in days (higher APY)")
@click.option("--fee", type=DECIMAL, default="0.01", help="Transaction fee in AIT")
@click.pass_context
def liquidity_stake(
    ctx,
    wallet_name: str | None,
    wallet_path: str | None,
    rpc_url: str | None,
    amount: Decimal,
    pool: str,
    lock_days: int,
    fee: Decimal,
):
    """Stake tokens into an on-chain liquidity pool to earn rewards."""
    _bind_wallet(ctx, wallet_name, wallet_path, rpc_url)
    return ctx.invoke(_wallet_liquidity_stake, amount=amount, pool=pool, lock_days=lock_days, fee=fee)
