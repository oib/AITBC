"""
Main exchange integration commands for AITBC CLI.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import click

try:
    from aitbc_cli.config import get_config  # noqa: F401
    from aitbc_cli.utils import error, output, success, warning
    from aitbc_cli.utils.http_client import AITBCHTTPClient, NetworkError, get_logger  # noqa: F401
except ImportError:
    from ..utils import error, output, success, warning
    from ..utils.http_client import get_logger

logger = get_logger(__name__)


@click.group()
def exchange():
    """Exchange integration and trading management commands"""
    pass


@exchange.command()
@click.option("--name", required=True, help="Exchange name (e.g., Binance, Coinbase, Kraken)")
@click.option("--api-key", required=True, help="Exchange API key")
@click.option("--secret-key", help="Exchange API secret key")
@click.option("--sandbox", is_flag=True, help="Use sandbox/testnet environment")
@click.option("--description", help="Exchange description")
@click.pass_context
def register(ctx, name: str, api_key: str, secret_key: str | None, sandbox: bool, description: str | None):
    """Register a new exchange integration"""
    exchange_config = {
        "name": name,
        "api_key": api_key,
        "secret_key": secret_key or "NOT_SET",
        "sandbox": sandbox,
        "description": description or f"{name} exchange integration",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "active",
        "trading_pairs": [],
        "last_sync": None,
    }

    exchanges_file = Path.home() / ".aitbc" / "exchanges.json"
    exchanges_file.parent.mkdir(parents=True, exist_ok=True)

    exchanges = {}
    if exchanges_file.exists():
        with open(exchanges_file) as f:
            exchanges = json.load(f)

    exchanges[name.lower()] = exchange_config

    with open(exchanges_file, "w") as f:
        json.dump(exchanges, f, indent=2)

    success(f"Exchange '{name}' registered successfully")
    output({"exchange": name, "status": "registered", "sandbox": sandbox, "created_at": exchange_config["created_at"]})


@exchange.command()
@click.option("--base-asset", required=True, help="Base asset symbol (e.g., AITBC)")
@click.option("--quote-asset", required=True, help="Quote asset symbol (e.g., BTC)")
@click.option("--exchange", required=True, help="Exchange name")
@click.option("--min-order-size", type=float, default=0.001, help="Minimum order size")
@click.option("--price-precision", type=int, default=8, help="Price precision")
@click.option("--quantity-precision", type=int, default=8, help="Quantity precision")
@click.pass_context
def create_pair(
    ctx, base_asset: str, quote_asset: str, exchange: str, min_order_size: float, price_precision: int, quantity_precision: int
):
    """Create a new trading pair"""
    pair_symbol = f"{base_asset}/{quote_asset}"

    exchanges_file = Path.home() / ".aitbc" / "exchanges.json"
    if not exchanges_file.exists():
        error("No exchanges registered. Use 'aitbc exchange register' first.")
        return

    with open(exchanges_file) as f:
        exchanges = json.load(f)

    if exchange.lower() not in exchanges:
        error(f"Exchange '{exchange}' not registered.")
        return

    pair_config = {
        "symbol": pair_symbol,
        "base_asset": base_asset,
        "quote_asset": quote_asset,
        "min_order_size": min_order_size,
        "price_precision": price_precision,
        "quantity_precision": quantity_precision,
        "trading_enabled": False,
        "created_at": datetime.now(UTC).isoformat(),
    }

    exchanges[exchange.lower()]["trading_pairs"].append(pair_config)

    with open(exchanges_file, "w") as f:
        json.dump(exchanges, f, indent=2)

    success(f"Trading pair '{pair_symbol}' created on {exchange}")
    output(pair_config)


@exchange.command()
@click.option("--pair", required=True, help="Trading pair symbol (e.g., AITBC/BTC)")
@click.option("--price", type=float, help="Initial price for the pair")
@click.option("--base-liquidity", type=float, default=10000, help="Base asset liquidity amount")
@click.option("--quote-liquidity", type=float, default=10000, help="Quote asset liquidity amount")
@click.option("--exchange", help="Exchange name (if not specified, uses first available)")
@click.pass_context
def start_trading(ctx, pair: str, price: float | None, base_liquidity: float, quote_liquidity: float, exchange: str | None):
    """Start trading for a specific pair"""
    exchanges_file = Path.home() / ".aitbc" / "exchanges.json"
    if not exchanges_file.exists():
        error("No exchanges registered. Use 'aitbc exchange register' first.")
        return

    with open(exchanges_file) as f:
        exchanges = json.load(f)

    target_exchange = None
    target_pair = None

    for exchange_name, exchange_data in exchanges.items():
        for pair_config in exchange_data.get("trading_pairs", []):
            if pair_config["symbol"] == pair:
                target_exchange = exchange_name
                target_pair = pair_config
                break
        if target_pair:
            break

    if not target_pair:
        error(f"Trading pair '{pair}' not found. Create it first with 'aitbc exchange create-pair'.")
        return

    target_pair["trading_enabled"] = True
    target_pair["started_at"] = datetime.now(UTC).isoformat()
    target_pair["initial_price"] = price or 0.00001
    target_pair["base_liquidity"] = base_liquidity
    target_pair["quote_liquidity"] = quote_liquidity

    with open(exchanges_file, "w") as f:
        json.dump(exchanges, f, indent=2)

    success(f"Trading started for pair '{pair}' on {target_exchange}")
    output(
        {
            "pair": pair,
            "exchange": target_exchange,
            "status": "trading_active",
            "initial_price": target_pair["initial_price"],
            "base_liquidity": base_liquidity,
            "quote_liquidity": quote_liquidity,
            "started_at": target_pair["started_at"],
        }
    )


@exchange.command()
@click.option("--pair", help="Trading pair symbol (e.g., AITBC/BTC)")
@click.option("--exchange", help="Exchange name")
@click.option("--real-time", is_flag=True, help="Enable real-time monitoring")
@click.option("--interval", type=int, default=60, help="Update interval in seconds")
@click.pass_context
def monitor(ctx, pair: str | None, exchange: str | None, real_time: bool, interval: int):
    """Monitor exchange trading activity"""
    exchanges_file = Path.home() / ".aitbc" / "exchanges.json"
    if not exchanges_file.exists():
        error("No exchanges registered. Use 'aitbc exchange register' first.")
        return

    with open(exchanges_file) as f:
        exchanges = json.load(f)

    monitoring_data = []

    for exchange_name, exchange_data in exchanges.items():
        if exchange and exchange_name != exchange.lower():
            continue

        for pair_config in exchange_data.get("trading_pairs", []):
            if pair and pair_config["symbol"] != pair:
                continue

            monitoring_data.append(
                {
                    "exchange": exchange_name,
                    "pair": pair_config["symbol"],
                    "status": "active" if pair_config.get("trading_enabled") else "inactive",
                    "created_at": pair_config.get("created_at"),
                    "started_at": pair_config.get("started_at"),
                    "initial_price": pair_config.get("initial_price"),
                    "base_liquidity": pair_config.get("base_liquidity"),
                    "quote_liquidity": pair_config.get("quote_liquidity"),
                }
            )

    if not monitoring_data:
        error("No trading pairs found for monitoring.")
        return

    output(
        {
            "monitoring_active": True,
            "real_time": real_time,
            "interval": interval,
            "pairs": monitoring_data,
            "total_pairs": len(monitoring_data),
        }
    )

    if real_time:
        warning(f"Real-time monitoring enabled. Updates every {interval} seconds.")


@exchange.command()
@click.option("--pair", required=True, help="Trading pair symbol (e.g., AITBC/BTC)")
@click.option("--amount", type=float, required=True, help="Liquidity amount")
@click.option("--side", type=click.Choice(["buy", "sell"]), default="both", help="Side to provide liquidity")
@click.option("--exchange", help="Exchange name")
@click.pass_context
def add_liquidity(ctx, pair: str, amount: float, side: str, exchange: str | None):
    """Add liquidity to a trading pair"""
    exchanges_file = Path.home() / ".aitbc" / "exchanges.json"
    if not exchanges_file.exists():
        error("No exchanges registered. Use 'aitbc exchange register' first.")
        return

    with open(exchanges_file) as f:
        exchanges = json.load(f)

    target_exchange = None
    target_pair = None

    for exchange_name, exchange_data in exchanges.items():
        if exchange and exchange_name != exchange.lower():
            continue

        for pair_config in exchange_data.get("trading_pairs", []):
            if pair_config["symbol"] == pair:
                target_exchange = exchange_name
                target_pair = pair_config
                break
        if target_pair:
            break

    if not target_pair:
        error(f"Trading pair '{pair}' not found.")
        return

    if side == "buy" or side == "both":
        target_pair["quote_liquidity"] = target_pair.get("quote_liquidity", 0) + amount
    if side == "sell" or side == "both":
        target_pair["base_liquidity"] = target_pair.get("base_liquidity", 0) + amount

    target_pair["liquidity_updated_at"] = datetime.now(UTC).isoformat()

    with open(exchanges_file, "w") as f:
        json.dump(exchanges, f, indent=2)

    success(f"Added {amount} liquidity to {pair} on {target_exchange} ({side} side)")
    output(
        {
            "pair": pair,
            "exchange": target_exchange,
            "amount": amount,
            "side": side,
            "base_liquidity": target_pair.get("base_liquidity"),
            "quote_liquidity": target_pair.get("quote_liquidity"),
            "updated_at": target_pair["liquidity_updated_at"],
        }
    )


@exchange.command()
@click.pass_context
def list(ctx):
    """List all registered exchanges and trading pairs"""
    exchanges_file = Path.home() / ".aitbc" / "exchanges.json"
    if not exchanges_file.exists():
        warning("No exchanges registered.")
        return

    with open(exchanges_file) as f:
        exchanges = json.load(f)

    exchange_list = []
    for _exchange_name, exchange_data in exchanges.items():
        exchange_info = {
            "name": exchange_data["name"],
            "status": exchange_data["status"],
            "sandbox": exchange_data["sandbox"],
            "trading_pairs": len(exchange_data.get("trading_pairs", [])),
            "created_at": exchange_data["created_at"],
        }
        exchange_list.append(exchange_info)

    output(exchange_list, title="Registered Exchanges")


@exchange.command()
@click.argument("exchange_name")
@click.pass_context
def status(ctx, exchange_name: str):
    """Get status of a specific exchange"""
    exchanges_file = Path.home() / ".aitbc" / "exchanges.json"
    if not exchanges_file.exists():
        error("No exchanges registered.")
        return

    with open(exchanges_file) as f:
        exchanges = json.load(f)

    if exchange_name.lower() not in exchanges:
        error(f"Exchange '{exchange_name}' not found.")
        return

    exchange_data = exchanges[exchange_name.lower()]
    output(exchange_data, title=f"Exchange Status: {exchange_name}")
