"""Exchange integration commands for AITBC CLI"""

import json
from datetime import UTC, datetime
from pathlib import Path

import click

from ..config import get_config
from ..utils import error, output, success, warning

# Import shared modules
from ..utils.http_client import AITBCHTTPClient, NetworkError, get_logger

# Initialize logger
logger = get_logger(__name__)


def _load_module_from_path(module_name: str, file_path: Path) -> object:
    """Load a module from a file path using importlib."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module {module_name} from {file_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


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
def register_local(ctx, name: str, api_key: str, secret_key: str | None, sandbox: bool, description: str | None):
    """Register a new exchange integration (local storage)"""
    # Create exchange configuration
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

    # Store exchange configuration
    exchanges_file = Path.home() / ".aitbc" / "exchanges.json"
    exchanges_file.parent.mkdir(parents=True, exist_ok=True)

    # Load existing exchanges
    exchanges = {}
    if exchanges_file.exists():
        with open(exchanges_file) as f:
            exchanges = json.load(f)

    # Add new exchange
    exchanges[name.lower()] = exchange_config

    # Save exchanges
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
def create_pair_local(
    ctx, base_asset: str, quote_asset: str, exchange: str, min_order_size: float, price_precision: int, quantity_precision: int
):
    """Create a new trading pair (local storage)"""
    pair_symbol = f"{base_asset}/{quote_asset}"

    # Load exchanges
    exchanges_file = Path.home() / ".aitbc" / "exchanges.json"
    if not exchanges_file.exists():
        error("No exchanges registered. Use 'aitbc exchange register' first.")
        return

    with open(exchanges_file) as f:
        exchanges = json.load(f)

    if exchange.lower() not in exchanges:
        error(f"Exchange '{exchange}' not registered.")
        return

    # Create trading pair configuration
    pair_config = {
        "symbol": pair_symbol,
        "base_asset": base_asset,
        "quote_asset": quote_asset,
        "exchange": exchange,
        "min_order_size": min_order_size,
        "price_precision": price_precision,
        "quantity_precision": quantity_precision,
        "status": "active",
        "created_at": datetime.now(UTC).isoformat(),
        "trading_enabled": False,
    }

    # Update exchange with new pair
    exchanges[exchange.lower()]["trading_pairs"].append(pair_config)

    # Save exchanges
    with open(exchanges_file, "w") as f:
        json.dump(exchanges, f, indent=2)

    success(f"Trading pair '{pair_symbol}' created on {exchange}")
    output(
        {
            "pair": pair_symbol,
            "exchange": exchange,
            "status": "created",
            "min_order_size": min_order_size,
            "created_at": pair_config["created_at"],
        }
    )


@exchange.command()
@click.option("--pair", required=True, help="Trading pair symbol (e.g., AITBC/BTC)")
@click.option("--price", type=float, help="Initial price for the pair")
@click.option("--base-liquidity", type=float, default=10000, help="Base asset liquidity amount")
@click.option("--quote-liquidity", type=float, default=10000, help="Quote asset liquidity amount")
@click.option("--exchange", help="Exchange name (if not specified, uses first available)")
@click.pass_context
def start_trading_local(
    ctx, pair: str, price: float | None, base_liquidity: float, quote_liquidity: float, exchange: str | None
):
    """Start trading for a specific pair (local storage)"""

    # Load exchanges
    exchanges_file = Path.home() / ".aitbc" / "exchanges.json"
    if not exchanges_file.exists():
        error("No exchanges registered. Use 'aitbc exchange register' first.")
        return

    with open(exchanges_file) as f:
        exchanges = json.load(f)

    # Find the pair
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

    # Update pair to enable trading
    target_pair["trading_enabled"] = True
    target_pair["started_at"] = datetime.now(UTC).isoformat()
    target_pair["initial_price"] = price or 0.00001  # Default price for AITBC
    target_pair["base_liquidity"] = base_liquidity
    target_pair["quote_liquidity"] = quote_liquidity

    # Save exchanges
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

    # Load exchanges
    exchanges_file = Path.home() / ".aitbc" / "exchanges.json"
    if not exchanges_file.exists():
        error("No exchanges registered. Use 'aitbc exchange register' first.")
        return

    with open(exchanges_file) as f:
        exchanges = json.load(f)

    # Filter exchanges and pairs
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

    # Display monitoring data
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
        # Note: In a real implementation, this would start a background monitoring process


@exchange.command()
@click.option("--pair", required=True, help="Trading pair symbol (e.g., AITBC/BTC)")
@click.option("--amount", type=float, required=True, help="Liquidity amount")
@click.option("--side", type=click.Choice(["buy", "sell"]), default="both", help="Side to provide liquidity")
@click.option("--exchange", help="Exchange name")
@click.pass_context
def add_liquidity(ctx, pair: str, amount: float, side: str, exchange: str | None):
    """Add liquidity to a trading pair"""

    # Load exchanges
    exchanges_file = Path.home() / ".aitbc" / "exchanges.json"
    if not exchanges_file.exists():
        error("No exchanges registered. Use 'aitbc exchange register' first.")
        return

    with open(exchanges_file) as f:
        exchanges = json.load(f)

    # Find the pair
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

    # Add liquidity
    if side == "buy" or side == "both":
        target_pair["quote_liquidity"] = target_pair.get("quote_liquidity", 0) + amount
    if side == "sell" or side == "both":
        target_pair["base_liquidity"] = target_pair.get("base_liquidity", 0) + amount

    target_pair["liquidity_updated_at"] = datetime.now(UTC).isoformat()

    # Save exchanges
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

    # Load exchanges
    exchanges_file = Path.home() / ".aitbc" / "exchanges.json"
    if not exchanges_file.exists():
        warning("No exchanges registered.")
        return

    with open(exchanges_file) as f:
        exchanges = json.load(f)

    # Format output
    exchange_list = []
    for _exchange_name, exchange_data in exchanges.items():
        exchange_info = {
            "name": exchange_data["name"],
            "status": exchange_data["status"],
            "sandbox": exchange_data.get("sandbox", False),
            "trading_pairs": len(exchange_data.get("trading_pairs", [])),
            "created_at": exchange_data["created_at"],
        }
        exchange_list.append(exchange_info)

    output(
        {
            "exchanges": exchange_list,
            "total_exchanges": len(exchange_list),
            "total_pairs": sum(ex["trading_pairs"] for ex in exchange_list),
        }
    )


@exchange.command()
@click.argument("exchange_name")
@click.pass_context
def status_local(ctx, exchange_name: str):
    """Get detailed status of a specific exchange (local storage)"""

    # Load exchanges
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

    output(
        {
            "exchange": exchange_data["name"],
            "status": exchange_data["status"],
            "sandbox": exchange_data.get("sandbox", False),
            "description": exchange_data.get("description"),
            "created_at": exchange_data["created_at"],
            "trading_pairs": exchange_data.get("trading_pairs", []),
            "last_sync": exchange_data.get("last_sync"),
        }
    )
    config = ctx.obj["config"]

    try:
        http_client = AITBCHTTPClient(base_url=config.exchange_service_url, timeout=10)
        rates_data = http_client.get("/exchange/rates")
        success("Current exchange rates:")
        output(rates_data, ctx.obj["output_format"])
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error: {e}")


@exchange.command()
@click.option("--aitbc-amount", type=float, help="Amount of AITBC to buy")
@click.option("--btc-amount", type=float, help="Amount of BTC to spend")
@click.option("--user-id", help="User ID for the payment")
@click.option("--notes", help="Additional notes for the payment")
@click.pass_context
def create_payment(ctx, aitbc_amount: float | None, btc_amount: float | None, user_id: str | None, notes: str | None):
    """Create a Bitcoin payment request for AITBC purchase"""
    config = ctx.obj["config"]

    # Validate input
    if aitbc_amount is not None and aitbc_amount <= 0:
        error("AITBC amount must be greater than 0")
        return

    if btc_amount is not None and btc_amount <= 0:
        error("BTC amount must be greater than 0")
        return

    if not aitbc_amount and not btc_amount:
        error("Either --aitbc-amount or --btc-amount must be specified")
        return

    # Get exchange rates to calculate missing amount
    try:
        http_client = AITBCHTTPClient(base_url=config.exchange_service_url, timeout=10)
        rates = http_client.get("/exchange/rates")
        btc_to_aitbc = rates.get("btc_to_aitbc", 100000)

        # Calculate missing amount
        if aitbc_amount and not btc_amount:
            btc_amount = aitbc_amount / btc_to_aitbc
        elif btc_amount and not aitbc_amount:
            aitbc_amount = btc_amount * btc_to_aitbc

        # Prepare payment request
        payment_data = {"user_id": user_id or "cli_user", "aitbc_amount": aitbc_amount, "btc_amount": btc_amount}

        if notes:
            payment_data["notes"] = notes

        # Create payment
        payment = http_client.post("/exchange/create-payment", json=payment_data)
        success(f"Payment created: {payment.get('payment_id')}")
        success(f"Send {btc_amount:.8f} BTC to: {payment.get('payment_address')}")
        success(f"Expires at: {payment.get('expires_at')}")
        output(payment, ctx.obj["output_format"])
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error: {e}")


@exchange.command()
@click.option("--payment-id", required=True, help="Payment ID to check")
@click.pass_context
def payment_status(ctx, payment_id: str):
    """Check payment confirmation status"""
    config = ctx.obj["config"]

    try:
        http_client = AITBCHTTPClient(base_url=config.exchange_service_url, timeout=10)
        status_data = http_client.get(f"/exchange/payment-status/{payment_id}")
        status = status_data.get("status", "unknown")

        if status == "confirmed":
            success(f"Payment {payment_id} is confirmed!")
            success(f"AITBC amount: {status_data.get('aitbc_amount', 0)}")
        elif status == "pending":
            success(f"Payment {payment_id} is pending confirmation")
        elif status == "expired":
            error(f"Payment {payment_id} has expired")
        else:
            success(f"Payment {payment_id} status: {status}")

        output(status_data, ctx.obj["output_format"])
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error: {e}")


@exchange.command()
@click.pass_context
def market_stats(ctx):
    """Get exchange market statistics"""
    config = ctx.obj["config"]

    try:
        http_client = AITBCHTTPClient(base_url=config.exchange_service_url, timeout=10)
        stats = http_client.get("/exchange/market-stats")
        success("Exchange market statistics:")
        output(stats, ctx.obj["output_format"])
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error: {e}")


@exchange.group()
def wallet():
    """Bitcoin wallet operations"""
    pass


@wallet.command()
@click.pass_context
def wallet_balance(ctx):
    """Get Bitcoin wallet balance"""
    config = ctx.obj["config"]

    try:
        http_client = AITBCHTTPClient(base_url=config.exchange_service_url, timeout=10)
        balance_data = http_client.get("/exchange/wallet/balance")
        success("Bitcoin wallet balance:")
        output(balance_data, ctx.obj["output_format"])
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error: {e}")


@wallet.command()
@click.pass_context
def info(ctx):
    """Get comprehensive Bitcoin wallet information"""
    config = ctx.obj["config"]

    try:
        http_client = AITBCHTTPClient(base_url=config.exchange_service_url, timeout=10)
        wallet_info = http_client.get("/exchange/wallet/info")
        success("Bitcoin wallet information:")
        output(wallet_info, ctx.obj["output_format"])
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error: {e}")


@exchange.command()
@click.option("--name", required=True, help="Exchange name (e.g., Binance, Coinbase)")
@click.option("--api-key", required=True, help="API key for exchange integration")
@click.option("--api-secret", help="API secret for exchange integration")
@click.option("--sandbox", is_flag=True, default=False, help="Use sandbox/testnet environment")
@click.pass_context
def register_remote(ctx, name: str, api_key: str, api_secret: str | None, sandbox: bool):
    """Register a new exchange integration (remote service)"""
    config = ctx.obj["config"]

    exchange_data = {"name": name, "api_key": api_key, "sandbox": sandbox}

    if api_secret:
        exchange_data["api_secret"] = api_secret

    try:
        http_client = AITBCHTTPClient(base_url=config.exchange_service_url, timeout=10)
        result = http_client.post("/exchange/register", json=exchange_data)
        success(f"Exchange '{name}' registered successfully!")
        success(f"Exchange ID: {result.get('exchange_id')}")
        output(result, ctx.obj["output_format"])
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error: {e}")


@exchange.command()
@click.option("--pair", required=True, help="Trading pair (e.g., AITBC/BTC, AITBC/ETH)")
@click.option("--base-asset", required=True, help="Base asset symbol")
@click.option("--quote-asset", required=True, help="Quote asset symbol")
@click.option("--min-order-size", type=float, help="Minimum order size")
@click.option("--max-order-size", type=float, help="Maximum order size")
@click.option("--price-precision", type=int, default=8, help="Price decimal precision")
@click.option("--size-precision", type=int, default=8, help="Size decimal precision")
@click.pass_context
def create_pair_remote(
    ctx,
    pair: str,
    base_asset: str,
    quote_asset: str,
    min_order_size: float | None,
    max_order_size: float | None,
    price_precision: int,
    size_precision: int,
):
    """Create a new trading pair"""
    config = ctx.obj["config"]

    pair_data = {
        "pair": pair,
        "base_asset": base_asset,
        "quote_asset": quote_asset,
        "price_precision": price_precision,
        "size_precision": size_precision,
    }

    if min_order_size is not None:
        pair_data["min_order_size"] = min_order_size
    if max_order_size is not None:
        pair_data["max_order_size"] = max_order_size

    try:
        http_client = AITBCHTTPClient(base_url=config.exchange_service_url, timeout=10)
        result = http_client.post("/exchange/create-pair", json=pair_data)
        success(f"Trading pair '{pair}' created successfully!")
        success(f"Pair ID: {result.get('pair_id')}")
        output(result, ctx.obj["output_format"])
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error: {e}")


@exchange.command()
@click.option("--pair", required=True, help="Trading pair to start trading")
@click.option("--exchange", help="Specific exchange to enable")
@click.option(
    "--order-type", multiple=True, default=["limit", "market"], help="Order types to enable (limit, market, stop_limit)"
)
@click.pass_context
def start_trading_remote(ctx, pair: str, exchange: str | None, order_type: tuple):
    """Start trading for a specific pair (remote service)"""
    config = ctx.obj["config"]

    trading_data = {"pair": pair, "order_types": list(order_type)}

    if exchange:
        trading_data["exchange"] = exchange

    try:
        http_client = AITBCHTTPClient(base_url=config.exchange_service_url, timeout=10)
        result = http_client.post("/exchange/start-trading", json=trading_data)
        success(f"Trading started for pair '{pair}'!")
        success(f"Order types: {', '.join(order_type)}")
        output(result, ctx.obj["output_format"])
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error: {e}")


@exchange.command()
@click.option("--pair", help="Filter by trading pair")
@click.option("--exchange", help="Filter by exchange")
@click.option("--status", help="Filter by status (active, inactive, suspended)")
@click.pass_context
def list_pairs(ctx, pair: str | None, exchange: str | None, status: str | None):
    """List all trading pairs"""
    config = ctx.obj["config"]

    params = {}
    if pair:
        params["pair"] = pair
    if exchange:
        params["exchange"] = exchange
    if status:
        params["status"] = status

    try:
        http_client = AITBCHTTPClient(base_url=config.exchange_service_url, timeout=10)
        pairs = http_client.get("/exchange/pairs", params=params)
        success("Trading pairs:")
        output(pairs, ctx.obj["output_format"])
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error: {e}")


@exchange.command()
@click.option("--exchange", required=True, help="Exchange name (binance, coinbasepro, kraken)")
@click.option("--api-key", required=True, help="API key for exchange")
@click.option("--secret", required=True, help="API secret for exchange")
@click.option("--sandbox", is_flag=True, default=True, help="Use sandbox/testnet environment")
@click.option("--passphrase", help="API passphrase (for Coinbase)")
@click.pass_context
def connect(ctx, exchange: str, api_key: str, secret: str, sandbox: bool, passphrase: str | None):
    """Connect to a real exchange API"""
    try:
        # Import the real exchange integration
        import asyncio

        _exchange_mod = _load_module_from_path(
            "real_exchange_integration",
            Path(__file__).resolve().parent.parent.parent.parent / "apps" / "exchange" / "real_exchange_integration.py",
        )
        connect_to_exchange = _exchange_mod.connect_to_exchange

        success = asyncio.run(connect_to_exchange(exchange, api_key, secret, sandbox, passphrase))

        if success:
            success(f"✅ Successfully connected to {exchange}")
            if sandbox:
                success("🧪 Using sandbox/testnet environment")
        else:
            error(f"❌ Failed to connect to {exchange}")

    except ImportError:
        error("❌ Real exchange integration not available. Install ccxt library.")
    except Exception as e:
        error(f"❌ Connection error: {e}")


@exchange.command()
@click.option("--exchange", help="Check specific exchange (default: all)")
@click.pass_context
def status_remote(ctx, exchange: str | None):
    """Check exchange connection status (remote service)"""
    try:
        # Import the real exchange integration
        import asyncio

        _exchange_mod = _load_module_from_path(
            "real_exchange_integration",
            Path(__file__).resolve().parent.parent.parent.parent / "apps" / "exchange" / "real_exchange_integration.py",
        )
        get_exchange_status = _exchange_mod.get_exchange_status

        status_data = asyncio.run(get_exchange_status(exchange))

        # Display status
        for exchange_name, health in status_data.items():
            status_icon = "🟢" if health.status.value == "connected" else "🔴" if health.status.value == "error" else "🟡"

            success(f"{status_icon} {exchange_name.upper()}")
            success(f"   Status: {health.status.value}")
            success(f"   Latency: {health.latency_ms:.2f}ms")
            success(f"   Last Check: {health.last_check.strftime('%H:%M:%S')}")

            if health.error_message:
                error(f"   Error: {health.error_message}")
            click.echo("")

    except ImportError:
        error("❌ Real exchange integration not available. Install ccxt library.")
    except Exception as e:
        error(f"❌ Status check error: {e}")


@exchange.command()
@click.option("--exchange", required=True, help="Exchange name to disconnect")
@click.pass_context
def disconnect(ctx, exchange: str):
    """Disconnect from an exchange"""
    try:
        # Import the real exchange integration
        import asyncio

        _exchange_mod = _load_module_from_path(
            "real_exchange_integration",
            Path(__file__).resolve().parent.parent.parent.parent / "apps" / "exchange" / "real_exchange_integration.py",
        )
        disconnect_from_exchange = _exchange_mod.disconnect_from_exchange

        success = asyncio.run(disconnect_from_exchange(exchange))

        if success:
            success(f"🔌 Disconnected from {exchange}")
        else:
            error(f"❌ Failed to disconnect from {exchange}")

    except ImportError:
        error("❌ Real exchange integration not available. Install ccxt library.")
    except Exception as e:
        error(f"❌ Disconnection error: {e}")


@exchange.command()
@click.option("--exchange", required=True, help="Exchange name")
@click.option("--symbol", required=True, help="Trading symbol (e.g., BTC/USDT)")
@click.option("--limit", type=int, default=20, help="Order book depth")
@click.pass_context
def orderbook(ctx, exchange: str, symbol: str, limit: int):
    """Get order book from exchange"""
    try:
        # Import the real exchange integration
        import asyncio

        _exchange_mod = _load_module_from_path(
            "real_exchange_integration",
            Path(__file__).resolve().parent.parent.parent.parent / "apps" / "exchange" / "real_exchange_integration.py",
        )
        exchange_manager = _exchange_mod.exchange_manager

        orderbook = asyncio.run(exchange_manager.get_order_book(exchange, symbol, limit))

        # Display order book
        success(f"📊 Order Book for {symbol} on {exchange.upper()}")

        # Display bids (buy orders)
        if "bids" in orderbook and orderbook["bids"]:
            success("\n🟢 Bids (Buy Orders):")
            for i, bid in enumerate(orderbook["bids"][:10]):
                price, amount = bid
                success(f"  {i + 1}. ${price:.8f} x {amount:.6f}")

        # Display asks (sell orders)
        if "asks" in orderbook and orderbook["asks"]:
            success("\n🔴 Asks (Sell Orders):")
            for i, ask in enumerate(orderbook["asks"][:10]):
                price, amount = ask
                success(f"  {i + 1}. ${price:.8f} x {amount:.6f}")

        # Spread
        if "bids" in orderbook and "asks" in orderbook and orderbook["bids"] and orderbook["asks"]:
            best_bid = orderbook["bids"][0][0]
            best_ask = orderbook["asks"][0][0]
            spread = best_ask - best_bid
            spread_pct = (spread / best_bid) * 100

            success(f"\n📈 Spread: ${spread:.8f} ({spread_pct:.4f}%)")
            success(f"🎯 Best Bid: ${best_bid:.8f}")
            success(f"🎯 Best Ask: ${best_ask:.8f}")

    except ImportError:
        error("❌ Real exchange integration not available. Install ccxt library.")
    except Exception as e:
        error(f"❌ Order book error: {e}")


@exchange.command()
@click.option("--exchange", required=True, help="Exchange name")
@click.pass_context
def exchange_balance(ctx, exchange: str):
    """Get account balance from exchange"""
    try:
        # Import the real exchange integration
        import asyncio

        _exchange_mod = _load_module_from_path(
            "real_exchange_integration",
            Path(__file__).resolve().parent.parent.parent.parent / "apps" / "exchange" / "real_exchange_integration.py",
        )
        exchange_manager = _exchange_mod.exchange_manager

        balance_data = asyncio.run(exchange_manager.get_balance(exchange))

        # Display balance
        success(f"💰 Account Balance on {exchange.upper()}")

        if "total" in balance_data:
            for asset, amount in balance_data["total"].items():
                if amount > 0:
                    available = balance_data.get("free", {}).get(asset, 0)
                    used = balance_data.get("used", {}).get(asset, 0)

                    success(f"\n{asset}:")
                    success(f"  Total: {amount:.8f}")
                    success(f"  Available: {available:.8f}")
                    success(f"  In Orders: {used:.8f}")
        else:
            warning("No balance data available")

    except ImportError:
        error("❌ Real exchange integration not available. Install ccxt library.")
    except Exception as e:
        error(f"❌ Balance error: {e}")


@exchange.command()
@click.option("--exchange", required=True, help="Exchange name")
@click.pass_context
def pairs(ctx, exchange: str):
    """List supported trading pairs"""
    try:
        # Import the real exchange integration
        import asyncio

        _exchange_mod = _load_module_from_path(
            "real_exchange_integration",
            Path(__file__).resolve().parent.parent.parent.parent / "apps" / "exchange" / "real_exchange_integration.py",
        )
        exchange_manager = _exchange_mod.exchange_manager

        pairs = asyncio.run(exchange_manager.get_supported_pairs(exchange))

        # Display pairs
        success(f"📋 Supported Trading Pairs on {exchange.upper()}")
        success(f"Found {len(pairs)} trading pairs:\n")

        # Group by base currency
        base_currencies = {}
        for pair in pairs:
            base = pair.split("/")[0] if "/" in pair else pair.split("-")[0]
            if base not in base_currencies:
                base_currencies[base] = []
            base_currencies[base].append(pair)

        # Display organized pairs
        for base in sorted(base_currencies.keys()):
            success(f"\n🔹 {base}:")
            for pair in sorted(base_currencies[base][:10]):  # Show first 10 per base
                success(f"  • {pair}")

            if len(base_currencies[base]) > 10:
                success(f"  ... and {len(base_currencies[base]) - 10} more")
    except Exception as e:
        error(f"Error fetching pairs: {e}")


@exchange.command()
@click.argument("order_id")
@click.pass_context
def order(ctx, order_id: str):
    """Get specific order details from exchange-service"""
    config = get_config()

    try:
        http_client = AITBCHTTPClient(base_url=config.exchange_service_url, timeout=10)
        order_data = http_client.get(f"/exchange/order/{order_id}")
        success(f"Order {order_id}:")
        output(order_data, ctx.obj.get("output_format", "table"))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error fetching order: {e}")


@exchange.command()
@click.option("--pair", help="Filter by trading pair")
@click.option("--status", help="Filter by status")
@click.option("--limit", type=int, default=20, help="Number of orders to return")
@click.pass_context
def orders(ctx, pair: str | None, status: str | None, limit: int):
    """List orders from exchange-service"""
    config = get_config()

    try:
        http_client = AITBCHTTPClient(base_url=config.exchange_service_url, timeout=10)
        params = {"limit": limit}
        if pair:
            params["pair"] = pair
        if status:
            params["status"] = status

        orders_data = http_client.get("/exchange/orders", params=params)
        success("Orders:")
        output(orders_data, ctx.obj.get("output_format", "table"))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error fetching orders: {e}")


@exchange.command()
@click.option("--pair", required=True, help="Trading pair (e.g., AITBC/BTC)")
@click.option("--limit", type=int, default=20, help="Order book depth")
@click.pass_context
def book(ctx, pair: str, limit: int):
    """Get order book from exchange-service"""
    config = get_config()

    try:
        http_client = AITBCHTTPClient(base_url=config.exchange_service_url, timeout=10)
        book_data = http_client.get("/exchange/orderbook", params={"pair": pair, "limit": limit})
        success(f"Order Book for {pair}:")
        output(book_data, ctx.obj.get("output_format", "table"))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error fetching order book: {e}")


@exchange.command()
@click.option("--pair", help="Filter by trading pair")
@click.option("--limit", type=int, default=50, help="Number of history entries")
@click.pass_context
def history(ctx, pair: str | None, limit: int):
    """Get trade history from exchange-service"""
    config = get_config()

    try:
        http_client = AITBCHTTPClient(base_url=config.exchange_service_url, timeout=10)
        params = {"limit": limit}
        if pair:
            params["pair"] = pair

        history_data = http_client.get("/exchange/history", params=params)
        success("Trade History:")
        output(history_data, ctx.obj.get("output_format", "table"))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error fetching trade history: {e}")


@exchange.command()
@click.pass_context
def list_exchanges(ctx):
    """List all supported exchanges"""
    try:
        # Import the real exchange integration
        _exchange_mod = _load_module_from_path(
            "real_exchange_integration",
            Path(__file__).resolve().parent.parent.parent.parent / "apps" / "exchange" / "real_exchange_integration.py",
        )
        exchange_manager = _exchange_mod.exchange_manager

        success("🏢 Supported Exchanges:")
        for exchange in exchange_manager.supported_exchanges:
            success(f"  • {exchange.title()}")

        success("\n📝 Usage:")
        success("  aitbc exchange connect --exchange binance --api-key <key> --secret <secret>")
        success("  aitbc exchange status --exchange binance")
        success("  aitbc exchange orderbook --exchange binance --symbol BTC/USDT")

    except ImportError:
        error("❌ Real exchange integration not available. Install ccxt library.")
    except Exception as e:
        error(f"❌ Error: {e}")


# ── Bridge / Oracle commands ──────────────────────────────────────────────────


@exchange.command()
@click.argument("base", default="ETH")
@click.argument("quote", default="USD")
@click.pass_context
def price(ctx, base: str, quote: str):
    """Get oracle price for a token pair (e.g. aitbc exchange price ETH USD)"""
    try:
        from aitbc.oracles.price_oracle import get_price_oracle

        oracle = get_price_oracle()
        result = oracle.get_price(base.upper(), quote.upper())
        if result:
            success(f"{result.base}/{result.quote} = {result.price:.4f} (source: {result.source})")
        else:
            error(f"No price available for {base}/{quote}")
    except Exception as e:
        error(f"Oracle error: {e}")


@exchange.command()
@click.option("--amount", required=True, type=float, help="Amount of ETH to deposit")
@click.option("--ait-address", required=True, help="AITBC wallet address to receive AIT tokens")
@click.option("--dry-run", is_flag=True, help="Estimate only, do not submit transaction")
@click.pass_context
def deposit(ctx, amount: float, ait_address: str, dry_run: bool):
    """Deposit ETH → receive AIT via bridge (requires ETH_RPC_URL + PRIVATE_KEY env vars)"""
    try:
        from aitbc.oracles.price_oracle import get_price_oracle

        oracle = get_price_oracle()
        eth_price = oracle.get_price("ETH", "USD")
        price_str = f"(~${eth_price.price * amount:.2f} USD)" if eth_price else ""

        if dry_run:
            success(f"[DRY RUN] Would deposit {amount} ETH {price_str} → AIT to {ait_address}")
            success(f"Bridge fee: {amount * 0.005:.6f} ETH (0.5%)")
            success(f"Net deposit: {amount * 0.995:.6f} ETH")
            return

        bridge_url = "http://localhost:8106/v1/bridge/deposit"
        import json
        import urllib.request

        payload = json.dumps(
            {
                "eth_amount": amount,
                "ait_address": ait_address,
            }
        ).encode()
        req = urllib.request.Request(bridge_url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        success(f"Deposit submitted: {data}")
    except Exception as e:
        error(f"Deposit error: {e}")


@exchange.command()
@click.option("--amount", required=True, type=float, help="Amount of AIT to withdraw")
@click.option("--eth-address", required=True, help="Ethereum wallet address to receive ETH")
@click.option("--dry-run", is_flag=True, help="Estimate only, do not submit transaction")
@click.pass_context
def withdraw(ctx, amount: float, eth_address: str, dry_run: bool):
    """Withdraw AIT → receive ETH via bridge"""
    try:
        from aitbc.oracles.price_oracle import get_price_oracle

        oracle = get_price_oracle()
        eth_price = oracle.get_price("ETH", "USD")

        if dry_run:
            success(f"[DRY RUN] Would withdraw {amount} AIT → ETH to {eth_address}")
            success(f"Bridge fee: {amount * 0.005:.4f} AIT (0.5%)")
            if eth_price:
                success(f"ETH/USD rate: ${eth_price.price:.2f} (source: {eth_price.source})")
            return

        bridge_url = "http://localhost:8106/v1/bridge/withdraw"
        import json
        import urllib.request

        payload = json.dumps(
            {
                "ait_amount": amount,
                "eth_address": eth_address,
            }
        ).encode()
        req = urllib.request.Request(bridge_url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        success(f"Withdrawal submitted: {data}")
    except Exception as e:
        error(f"Withdrawal error: {e}")


@exchange.command()
@click.option("--from-token", required=True, help="Token to swap from (e.g. ETH)")
@click.option("--to-token", required=True, help="Token to swap to (e.g. AIT)")
@click.option("--amount", required=True, type=float, help="Amount to swap")
@click.option("--slippage", default=0.5, type=float, help="Max slippage % (default: 0.5)")
@click.pass_context
def swap(ctx, from_token: str, to_token: str, amount: float, slippage: float):
    """Swap tokens via bridge oracle pricing (dry-run estimate)"""
    try:
        from aitbc.oracles.price_oracle import get_price_oracle

        oracle = get_price_oracle()

        from_price = oracle.get_price(from_token.upper(), "USD")
        to_price = oracle.get_price(to_token.upper(), "USD")

        if not from_price:
            error(f"No price available for {from_token}")
            return
        if not to_price:
            error(f"No price available for {to_token}")
            return

        from_usd = amount * from_price.price
        to_amount = from_usd / to_price.price
        fee = to_amount * 0.005
        net_to = to_amount - fee

        success(f"Swap estimate: {amount} {from_token.upper()} → {net_to:.6f} {to_token.upper()}")
        success(f"  Rate:     1 {from_token.upper()} = {from_price.price / to_price.price:.6f} {to_token.upper()}")
        success(f"  Fee:      {fee:.6f} {to_token.upper()} (0.5%)")
        success(f"  Slippage: ±{slippage}%")
        success(f"  Min out:  {net_to * (1 - slippage / 100):.6f} {to_token.upper()}")
        success(f"  Sources:  {from_token}: {from_price.source}, {to_token}: {to_price.source}")
    except Exception as e:
        error(f"Swap error: {e}")


@exchange.command("bridge-status")
@click.option("--tx-id", help="Bridge transaction ID to check")
@click.pass_context
def bridge_status_check(ctx, tx_id: str | None):
    """Check bridge status or list recent bridge transactions"""
    try:
        import json
        import urllib.request

        if tx_id:
            url = f"http://localhost:8106/v1/bridge/status/{tx_id}"
        else:
            url = "http://localhost:8106/v1/bridge/status"
        req = urllib.request.Request(url, headers={"User-Agent": "aitbc-cli/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        output(data, ctx.obj.get("output_format", "json"))
    except Exception:
        # Bridge may not be configured — show oracle health instead
        from aitbc.oracles.price_oracle import get_price_oracle

        h = get_price_oracle().health_check()
        success("Bridge endpoint not available. Oracle status:")
        for src, info in h.items():
            success(f"  {src}: {info['status']}" + (f" (ETH/USD: ${info['eth_usd']:.2f})" if info["eth_usd"] else ""))


@exchange.command()
@click.option("--status", help="Filter by status (pending, processing, completed, failed)")
@click.option("--limit", default=10, help="Number of deposits to show")
def bridge_deposits(status, limit):
    """List ETH-to-AIT bridge deposits."""
    _bridge_mod = _load_module_from_path(
        "bridge_monitor.storage",
        Path(__file__).resolve().parent.parent.parent.parent
        / "apps"
        / "bridge-monitor"
        / "src"
        / "bridge_monitor"
        / "storage.py",
    )
    BridgeDepositStatus = _bridge_mod.BridgeDepositStatus
    count_deposits = _bridge_mod.count_deposits
    get_deposits = _bridge_mod.get_deposits

    status_filter = None
    if status:
        try:
            status_filter = BridgeDepositStatus(status)
        except ValueError:
            error(f"Invalid status: {status}")
            return

    deposits = get_deposits(status=status_filter, limit=limit)
    total = count_deposits(status=status_filter)

    if not deposits:
        info("No deposits found")
        return

    success(f"Showing {len(deposits)} of {total} deposits")
    for d in deposits:
        status_emoji = {"pending": "⏳", "processing": "🔄", "completed": "✅", "failed": "❌"}.get(d["status"], "❓")
        success(
            f"{status_emoji} {d['eth_tx_hash'][:10]}... | {d['eth_amount']} ETH → {d['ait_amount'] or '?'} AIT | {d['ait_recipient'] or 'N/A'} | {d['status']}"
        )


@exchange.command()
@click.option("--eth-amount", type=float, required=True, help="ETH amount to estimate")
def bridge_estimate(eth_amount):
    """Estimate AIT amount for ETH deposit."""
    from aitbc.oracles.price_oracle import get_price_oracle

    oracle = get_price_oracle()
    eth_usd = oracle.get_price("ETH", "USD")
    ait_usd = oracle.get_price("AIT", "USD")

    if not eth_usd or not ait_usd or ait_usd == 0:
        error("Cannot get oracle prices")
        return

    ait_amount = (eth_amount * eth_usd) / ait_usd

    success(f"ETH Amount: {eth_amount} ETH")
    success(f"ETH/USD: ${eth_usd:.2f}")
    success(f"AIT/USD: ${ait_usd:.2f}")
    success(f"Estimated AIT: {ait_amount:.6f} AIT")
    success(f"Exchange Rate: 1 ETH = {ait_amount / eth_amount:.2f} AIT")


@exchange.command()
def bridge_status():
    """Show bridge monitor status."""
    _bridge_mod = _load_module_from_path(
        "bridge_monitor.storage",
        Path(__file__).resolve().parent.parent.parent.parent
        / "apps"
        / "bridge-monitor"
        / "src"
        / "bridge_monitor"
        / "storage.py",
    )
    BridgeDepositStatus = _bridge_mod.BridgeDepositStatus
    count_deposits = _bridge_mod.count_deposits

    pending = count_deposits(BridgeDepositStatus.PENDING)
    processing = count_deposits(BridgeDepositStatus.PROCESSING)
    completed = count_deposits(BridgeDepositStatus.COMPLETED)
    failed = count_deposits(BridgeDepositStatus.FAILED)

    success("Bridge Monitor Status:")
    success(f"  ⏳ Pending: {pending}")
    success(f"  🔄 Processing: {processing}")
    success(f"  ✅ Completed: {completed}")
    success(f"  ❌ Failed: {failed}")
    success(f"  📊 Total: {pending + processing + completed + failed}")

    import os

    bridge_addr = os.getenv("BRIDGE_ETH_ADDRESS", "0x818018F30d8F5FB7AE7a64f25895F15110923748")
    success(f"  📍 Bridge Address: {bridge_addr}")
