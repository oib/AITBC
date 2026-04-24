"""Exchange integration commands for AITBC CLI"""

import click
import json
import os
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime
from ..utils import output, error, success, warning
from ..config import get_config

# Import shared modules
from aitbc.aitbc_logging import get_logger
from aitbc.http_client import AITBCHTTPClient
from aitbc.exceptions import NetworkError

# Initialize logger
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
def register(ctx, name: str, api_key: str, secret_key: Optional[str], sandbox: bool, description: Optional[str]):
    """Register a new exchange integration"""
    config = get_config()
    
    # Create exchange configuration
    exchange_config = {
        "name": name,
        "api_key": api_key,
        "secret_key": secret_key or "NOT_SET",
        "sandbox": sandbox,
        "description": description or f"{name} exchange integration",
        "created_at": datetime.utcnow().isoformat(),
        "status": "active",
        "trading_pairs": [],
        "last_sync": None
    }
    
    # Store exchange configuration
    exchanges_file = Path.home() / ".aitbc" / "exchanges.json"
    exchanges_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Load existing exchanges
    exchanges = {}
    if exchanges_file.exists():
        with open(exchanges_file, 'r') as f:
            exchanges = json.load(f)
    
    # Add new exchange
    exchanges[name.lower()] = exchange_config
    
    # Save exchanges
    with open(exchanges_file, 'w') as f:
        json.dump(exchanges, f, indent=2)
    
    success(f"Exchange '{name}' registered successfully")
    output({
        "exchange": name,
        "status": "registered",
        "sandbox": sandbox,
        "created_at": exchange_config["created_at"]
    })


@exchange.command()
@click.option("--base-asset", required=True, help="Base asset symbol (e.g., AITBC)")
@click.option("--quote-asset", required=True, help="Quote asset symbol (e.g., BTC)")
@click.option("--exchange", required=True, help="Exchange name")
@click.option("--min-order-size", type=float, default=0.001, help="Minimum order size")
@click.option("--price-precision", type=int, default=8, help="Price precision")
@click.option("--quantity-precision", type=int, default=8, help="Quantity precision")
@click.pass_context
def create_pair(ctx, base_asset: str, quote_asset: str, exchange: str, min_order_size: float, price_precision: int, quantity_precision: int):
    """Create a new trading pair"""
    pair_symbol = f"{base_asset}/{quote_asset}"
    
    # Load exchanges
    exchanges_file = Path.home() / ".aitbc" / "exchanges.json"
    if not exchanges_file.exists():
        error("No exchanges registered. Use 'aitbc exchange register' first.")
        return
    
    with open(exchanges_file, 'r') as f:
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
        "created_at": datetime.utcnow().isoformat(),
        "trading_enabled": False
    }
    
    # Update exchange with new pair
    exchanges[exchange.lower()]["trading_pairs"].append(pair_config)
    
    # Save exchanges
    with open(exchanges_file, 'w') as f:
        json.dump(exchanges, f, indent=2)
    
    success(f"Trading pair '{pair_symbol}' created on {exchange}")
    output({
        "pair": pair_symbol,
        "exchange": exchange,
        "status": "created",
        "min_order_size": min_order_size,
        "created_at": pair_config["created_at"]
    })


@exchange.command()
@click.option("--pair", required=True, help="Trading pair symbol (e.g., AITBC/BTC)")
@click.option("--price", type=float, help="Initial price for the pair")
@click.option("--base-liquidity", type=float, default=10000, help="Base asset liquidity amount")
@click.option("--quote-liquidity", type=float, default=10000, help="Quote asset liquidity amount")
@click.option("--exchange", help="Exchange name (if not specified, uses first available)")
@click.pass_context
def start_trading(ctx, pair: str, price: Optional[float], base_liquidity: float, quote_liquidity: float, exchange: Optional[str]):
    """Start trading for a specific pair"""
    
    # Load exchanges
    exchanges_file = Path.home() / ".aitbc" / "exchanges.json"
    if not exchanges_file.exists():
        error("No exchanges registered. Use 'aitbc exchange register' first.")
        return
    
    with open(exchanges_file, 'r') as f:
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
    target_pair["started_at"] = datetime.utcnow().isoformat()
    target_pair["initial_price"] = price or 0.00001  # Default price for AITBC
    target_pair["base_liquidity"] = base_liquidity
    target_pair["quote_liquidity"] = quote_liquidity
    
    # Save exchanges
    with open(exchanges_file, 'w') as f:
        json.dump(exchanges, f, indent=2)
    
    success(f"Trading started for pair '{pair}' on {target_exchange}")
    output({
        "pair": pair,
        "exchange": target_exchange,
        "status": "trading_active",
        "initial_price": target_pair["initial_price"],
        "base_liquidity": base_liquidity,
        "quote_liquidity": quote_liquidity,
        "started_at": target_pair["started_at"]
    })


@exchange.command()
@click.option("--pair", help="Trading pair symbol (e.g., AITBC/BTC)")
@click.option("--exchange", help="Exchange name")
@click.option("--real-time", is_flag=True, help="Enable real-time monitoring")
@click.option("--interval", type=int, default=60, help="Update interval in seconds")
@click.pass_context
def monitor(ctx, pair: Optional[str], exchange: Optional[str], real_time: bool, interval: int):
    """Monitor exchange trading activity"""
    
    # Load exchanges
    exchanges_file = Path.home() / ".aitbc" / "exchanges.json"
    if not exchanges_file.exists():
        error("No exchanges registered. Use 'aitbc exchange register' first.")
        return
    
    with open(exchanges_file, 'r') as f:
        exchanges = json.load(f)
    
    # Filter exchanges and pairs
    monitoring_data = []
    
    for exchange_name, exchange_data in exchanges.items():
        if exchange and exchange_name != exchange.lower():
            continue
            
        for pair_config in exchange_data.get("trading_pairs", []):
            if pair and pair_config["symbol"] != pair:
                continue
                
            monitoring_data.append({
                "exchange": exchange_name,
                "pair": pair_config["symbol"],
                "status": "active" if pair_config.get("trading_enabled") else "inactive",
                "created_at": pair_config.get("created_at"),
                "started_at": pair_config.get("started_at"),
                "initial_price": pair_config.get("initial_price"),
                "base_liquidity": pair_config.get("base_liquidity"),
                "quote_liquidity": pair_config.get("quote_liquidity")
            })
    
    if not monitoring_data:
        error("No trading pairs found for monitoring.")
        return
    
    # Display monitoring data
    output({
        "monitoring_active": True,
        "real_time": real_time,
        "interval": interval,
        "pairs": monitoring_data,
        "total_pairs": len(monitoring_data)
    })
    
    if real_time:
        warning(f"Real-time monitoring enabled. Updates every {interval} seconds.")
        # Note: In a real implementation, this would start a background monitoring process


@exchange.command()
@click.option("--pair", required=True, help="Trading pair symbol (e.g., AITBC/BTC)")
@click.option("--amount", type=float, required=True, help="Liquidity amount")
@click.option("--side", type=click.Choice(['buy', 'sell']), default='both', help="Side to provide liquidity")
@click.option("--exchange", help="Exchange name")
@click.pass_context
def add_liquidity(ctx, pair: str, amount: float, side: str, exchange: Optional[str]):
    """Add liquidity to a trading pair"""
    
    # Load exchanges
    exchanges_file = Path.home() / ".aitbc" / "exchanges.json"
    if not exchanges_file.exists():
        error("No exchanges registered. Use 'aitbc exchange register' first.")
        return
    
    with open(exchanges_file, 'r') as f:
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
    if side == 'buy' or side == 'both':
        target_pair["quote_liquidity"] = target_pair.get("quote_liquidity", 0) + amount
    if side == 'sell' or side == 'both':
        target_pair["base_liquidity"] = target_pair.get("base_liquidity", 0) + amount
    
    target_pair["liquidity_updated_at"] = datetime.utcnow().isoformat()
    
    # Save exchanges
    with open(exchanges_file, 'w') as f:
        json.dump(exchanges, f, indent=2)
    
    success(f"Added {amount} liquidity to {pair} on {target_exchange} ({side} side)")
    output({
        "pair": pair,
        "exchange": target_exchange,
        "amount": amount,
        "side": side,
        "base_liquidity": target_pair.get("base_liquidity"),
        "quote_liquidity": target_pair.get("quote_liquidity"),
        "updated_at": target_pair["liquidity_updated_at"]
    })


@exchange.command()
@click.pass_context
def list(ctx):
    """List all registered exchanges and trading pairs"""
    
    # Load exchanges
    exchanges_file = Path.home() / ".aitbc" / "exchanges.json"
    if not exchanges_file.exists():
        warning("No exchanges registered.")
        return
    
    with open(exchanges_file, 'r') as f:
        exchanges = json.load(f)
    
    # Format output
    exchange_list = []
    for exchange_name, exchange_data in exchanges.items():
        exchange_info = {
            "name": exchange_data["name"],
            "status": exchange_data["status"],
            "sandbox": exchange_data.get("sandbox", False),
            "trading_pairs": len(exchange_data.get("trading_pairs", [])),
            "created_at": exchange_data["created_at"]
        }
        exchange_list.append(exchange_info)
    
    output({
        "exchanges": exchange_list,
        "total_exchanges": len(exchange_list),
        "total_pairs": sum(ex["trading_pairs"] for ex in exchange_list)
    })


@exchange.command()
@click.argument("exchange_name")
@click.pass_context
def status(ctx, exchange_name: str):
    """Get detailed status of a specific exchange"""
    
    # Load exchanges
    exchanges_file = Path.home() / ".aitbc" / "exchanges.json"
    if not exchanges_file.exists():
        error("No exchanges registered.")
        return
    
    with open(exchanges_file, 'r') as f:
        exchanges = json.load(f)
    
    if exchange_name.lower() not in exchanges:
        error(f"Exchange '{exchange_name}' not found.")
        return
    
    exchange_data = exchanges[exchange_name.lower()]
    
    output({
        "exchange": exchange_data["name"],
        "status": exchange_data["status"],
        "sandbox": exchange_data.get("sandbox", False),
        "description": exchange_data.get("description"),
        "created_at": exchange_data["created_at"],
        "trading_pairs": exchange_data.get("trading_pairs", []),
        "last_sync": exchange_data.get("last_sync")
    })
    config = ctx.obj['config']
    
    try:
        http_client = AITBCHTTPClient(base_url="http://localhost:8001/api/v1", timeout=10)
        rates_data = http_client.get(f"/exchange/rates")
        success("Current exchange rates:")
        output(rates_data, ctx.obj['output_format'])
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
def create_payment(ctx, aitbc_amount: Optional[float], btc_amount: Optional[float], 
                  user_id: Optional[str], notes: Optional[str]):
    """Create a Bitcoin payment request for AITBC purchase"""
    config = ctx.obj['config']
    
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
        http_client = AITBCHTTPClient(base_url="http://localhost:8001/api/v1", timeout=10)
        rates = http_client.get("/exchange/rates")
        btc_to_aitbc = rates.get('btc_to_aitbc', 100000)
        
        # Calculate missing amount
        if aitbc_amount and not btc_amount:
            btc_amount = aitbc_amount / btc_to_aitbc
        elif btc_amount and not aitbc_amount:
            aitbc_amount = btc_amount * btc_to_aitbc
        
        # Prepare payment request
        payment_data = {
            "user_id": user_id or "cli_user",
            "aitbc_amount": aitbc_amount,
            "btc_amount": btc_amount
        }
        
        if notes:
            payment_data["notes"] = notes
        
        # Create payment
        payment = http_client.post("/exchange/create-payment", json=payment_data)
        success(f"Payment created: {payment.get('payment_id')}")
        success(f"Send {btc_amount:.8f} BTC to: {payment.get('payment_address')}")
        success(f"Expires at: {payment.get('expires_at')}")
        output(payment, ctx.obj['output_format'])
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error: {e}")


@exchange.command()
@click.option("--payment-id", required=True, help="Payment ID to check")
@click.pass_context
def payment_status(ctx, payment_id: str):
    """Check payment confirmation status"""
    config = ctx.obj['config']
    
    try:
        http_client = AITBCHTTPClient(base_url="http://localhost:8001/api/v1", timeout=10)
        status_data = http_client.get(f"/exchange/payment-status/{payment_id}")
        status = status_data.get('status', 'unknown')
        
        if status == 'confirmed':
            success(f"Payment {payment_id} is confirmed!")
            success(f"AITBC amount: {status_data.get('aitbc_amount', 0)}")
        elif status == 'pending':
            success(f"Payment {payment_id} is pending confirmation")
        elif status == 'expired':
            error(f"Payment {payment_id} has expired")
        else:
            success(f"Payment {payment_id} status: {status}")
        
        output(status_data, ctx.obj['output_format'])
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error: {e}")


@exchange.command()
@click.pass_context
def market_stats(ctx):
    """Get exchange market statistics"""
    config = ctx.obj['config']
    
    try:
        http_client = AITBCHTTPClient(base_url="http://localhost:8001/api/v1", timeout=10)
        stats = http_client.get("/exchange/market-stats")
        success("Exchange market statistics:")
        output(stats, ctx.obj['output_format'])
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
def balance(ctx):
    """Get Bitcoin wallet balance"""
    config = ctx.obj['config']
    
    try:
        http_client = AITBCHTTPClient(base_url="http://localhost:8001/api/v1", timeout=10)
        balance_data = http_client.get("/exchange/wallet/balance")
        success("Bitcoin wallet balance:")
        output(balance_data, ctx.obj['output_format'])
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error: {e}")


@wallet.command()
@click.pass_context
def info(ctx):
    """Get comprehensive Bitcoin wallet information"""
    config = ctx.obj['config']
    
    try:
        http_client = AITBCHTTPClient(base_url="http://localhost:8001/api/v1", timeout=10)
        wallet_info = http_client.get("/exchange/wallet/info")
        success("Bitcoin wallet information:")
        output(wallet_info, ctx.obj['output_format'])
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
def register(ctx, name: str, api_key: str, api_secret: Optional[str], sandbox: bool):
    """Register a new exchange integration"""
    config = ctx.obj['config']
    
    exchange_data = {
        "name": name,
        "api_key": api_key,
        "sandbox": sandbox
    }
    
    if api_secret:
        exchange_data["api_secret"] = api_secret
    
    try:
        http_client = AITBCHTTPClient(base_url="http://localhost:8001/api/v1", timeout=10)
        result = http_client.post("/exchange/register", json=exchange_data)
        success(f"Exchange '{name}' registered successfully!")
        success(f"Exchange ID: {result.get('exchange_id')}")
        output(result, ctx.obj['output_format'])
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
def create_pair(ctx, pair: str, base_asset: str, quote_asset: str, 
                min_order_size: Optional[float], max_order_size: Optional[float],
                price_precision: int, size_precision: int):
    """Create a new trading pair"""
    config = ctx.obj['config']
    
    pair_data = {
        "pair": pair,
        "base_asset": base_asset,
        "quote_asset": quote_asset,
        "price_precision": price_precision,
        "size_precision": size_precision
    }
    
    if min_order_size is not None:
        pair_data["min_order_size"] = min_order_size
    if max_order_size is not None:
        pair_data["max_order_size"] = max_order_size
    
    try:
        http_client = AITBCHTTPClient(base_url="http://localhost:8001/api/v1", timeout=10)
            response = http_client.post(
                f"{config.coordinator_url}/v1/exchange/create-pair",
                json=pair_data,
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                success(f"Trading pair '{pair}' created successfully!")
                success(f"Pair ID: {result.get('pair_id')}")
                output(result, ctx.obj['output_format'])
            else:
                error(f"Failed to create trading pair: {response.status_code}")
                if response.text:
                    error(f"Error details: {response.text}")
    except Exception as e:
        error(f"Network error: {e}")


@exchange.command()
@click.option("--pair", required=True, help="Trading pair to start trading")
@click.option("--exchange", help="Specific exchange to enable")
@click.option("--order-type", multiple=True, default=["limit", "market"], 
              help="Order types to enable (limit, market, stop_limit)")
@click.pass_context
def start_trading(ctx, pair: str, exchange: Optional[str], order_type: tuple):
    """Start trading for a specific pair"""
    config = ctx.obj['config']
    
    trading_data = {
        "pair": pair,
        "order_types": list(order_type)
    }
    
    if exchange:
        trading_data["exchange"] = exchange
    
    try:
        http_client = AITBCHTTPClient(base_url="http://localhost:8001/api/v1", timeout=10)
            response = http_client.post(
                f"{config.coordinator_url}/v1/exchange/start-trading",
                json=trading_data,
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                success(f"Trading started for pair '{pair}'!")
                success(f"Order types: {', '.join(order_type)}")
                output(result, ctx.obj['output_format'])
            else:
                error(f"Failed to start trading: {response.status_code}")
                if response.text:
                    error(f"Error details: {response.text}")
    except Exception as e:
        error(f"Network error: {e}")


@exchange.command()
@click.option("--pair", help="Filter by trading pair")
@click.option("--exchange", help="Filter by exchange")
@click.option("--status", help="Filter by status (active, inactive, suspended)")
@click.pass_context
def list_pairs(ctx, pair: Optional[str], exchange: Optional[str], status: Optional[str]):
    """List all trading pairs"""
    config = ctx.obj['config']
    
    params = {}
    if pair:
        params["pair"] = pair
    if exchange:
        params["exchange"] = exchange
    if status:
        params["status"] = status
    
    try:
        http_client = AITBCHTTPClient(base_url="http://localhost:8001/api/v1", timeout=10)
            response = http_client.get(
                f"{config.coordinator_url}/v1/exchange/pairs",
                params=params,
                timeout=10
            )
            
            if response.status_code == 200:
                pairs = response.json()
                success("Trading pairs:")
                output(pairs, ctx.obj['output_format'])
            else:
                error(f"Failed to list trading pairs: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")


@exchange.command()
@click.option("--exchange", required=True, help="Exchange name (binance, coinbasepro, kraken)")
@click.option("--api-key", required=True, help="API key for exchange")
@click.option("--secret", required=True, help="API secret for exchange")
@click.option("--sandbox", is_flag=True, default=True, help="Use sandbox/testnet environment")
@click.option("--passphrase", help="API passphrase (for Coinbase)")
@click.pass_context
def connect(ctx, exchange: str, api_key: str, secret: str, sandbox: bool, passphrase: Optional[str]):
    """Connect to a real exchange API"""
    try:
        # Import the real exchange integration
        import sys
        sys.path.append('/home/oib/windsurf/aitbc/apps/exchange')
        from real_exchange_integration import connect_to_exchange
        
        # Run async connection
        import asyncio
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
def status(ctx, exchange: Optional[str]):
    """Check exchange connection status"""
    try:
        # Import the real exchange integration
        import sys
        sys.path.append('/home/oib/windsurf/aitbc/apps/exchange')
        from real_exchange_integration import get_exchange_status
        
        # Run async status check
        import asyncio
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
            print()
            
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
        import sys
        sys.path.append('/home/oib/windsurf/aitbc/apps/exchange')
        from real_exchange_integration import disconnect_from_exchange
        
        # Run async disconnection
        import asyncio
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
        import sys
        sys.path.append('/home/oib/windsurf/aitbc/apps/exchange')
        from real_exchange_integration import exchange_manager
        
        # Run async order book fetch
        import asyncio
        orderbook = asyncio.run(exchange_manager.get_order_book(exchange, symbol, limit))
        
        # Display order book
        success(f"📊 Order Book for {symbol} on {exchange.upper()}")
        
        # Display bids (buy orders)
        if 'bids' in orderbook and orderbook['bids']:
            success("\n🟢 Bids (Buy Orders):")
            for i, bid in enumerate(orderbook['bids'][:10]):
                price, amount = bid
                success(f"  {i+1}. ${price:.8f} x {amount:.6f}")
        
        # Display asks (sell orders)
        if 'asks' in orderbook and orderbook['asks']:
            success("\n🔴 Asks (Sell Orders):")
            for i, ask in enumerate(orderbook['asks'][:10]):
                price, amount = ask
                success(f"  {i+1}. ${price:.8f} x {amount:.6f}")
        
        # Spread
        if 'bids' in orderbook and 'asks' in orderbook and orderbook['bids'] and orderbook['asks']:
            best_bid = orderbook['bids'][0][0]
            best_ask = orderbook['asks'][0][0]
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
def balance(ctx, exchange: str):
    """Get account balance from exchange"""
    try:
        # Import the real exchange integration
        import sys
        sys.path.append('/home/oib/windsurf/aitbc/apps/exchange')
        from real_exchange_integration import exchange_manager
        
        # Run async balance fetch
        import asyncio
        balance_data = asyncio.run(exchange_manager.get_balance(exchange))
        
        # Display balance
        success(f"💰 Account Balance on {exchange.upper()}")
        
        if 'total' in balance_data:
            for asset, amount in balance_data['total'].items():
                if amount > 0:
                    available = balance_data.get('free', {}).get(asset, 0)
                    used = balance_data.get('used', {}).get(asset, 0)
                    
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
        import sys
        sys.path.append('/home/oib/windsurf/aitbc/apps/exchange')
        from real_exchange_integration import exchange_manager
        
        # Run async pairs fetch
        import asyncio
        pairs = asyncio.run(exchange_manager.get_supported_pairs(exchange))
        
        # Display pairs
        success(f"📋 Supported Trading Pairs on {exchange.upper()}")
        success(f"Found {len(pairs)} trading pairs:\n")
        
        # Group by base currency
        base_currencies = {}
        for pair in pairs:
            base = pair.split('/')[0] if '/' in pair else pair.split('-')[0]
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
            
    except ImportError:
        error("❌ Real exchange integration not available. Install ccxt library.")
    except Exception as e:
        error(f"❌ Pairs error: {e}")


@exchange.command()
@click.pass_context
def list_exchanges(ctx):
    """List all supported exchanges"""
    try:
        # Import the real exchange integration
        import sys
        sys.path.append('/home/oib/windsurf/aitbc/apps/exchange')
        from real_exchange_integration import exchange_manager
        
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
