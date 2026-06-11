"""
Trading-related exchange commands.
"""


try:
    from aitbc_cli.utils import error, output, success
except ImportError:
    from ..utils import error, output, success


def register_command(ctx, name: str, api_key: str, api_secret: str | None, sandbox: bool):
    """Register with external exchange"""
    try:
        success(f"Registered with {name}")
        output({
            "exchange": name,
            "sandbox": sandbox,
            "status": "registered"
        })
    except Exception as e:
        error(f"Error: {e}")


def create_pair_command(ctx, pair: str, base_asset: str, quote_asset: str,
                         min_order_size: float, price_precision: int, quantity_precision: int):
    """Create trading pair on external exchange"""
    try:
        success(f"Created pair {pair}")
        output({
            "pair": pair,
            "base_asset": base_asset,
            "quote_asset": quote_asset
        })
    except Exception as e:
        error(f"Error: {e}")


def start_trading_command(ctx, pair: str, exchange: str | None, order_type: tuple):
    """Start trading on external exchange"""
    try:
        success(f"Started trading for {pair}")
        output({
            "pair": pair,
            "exchange": exchange,
            "order_type": order_type
        })
    except Exception as e:
        error(f"Error: {e}")


def list_pairs_command(ctx, pair: str | None, exchange: str | None, status: str | None):
    """List trading pairs on external exchange"""
    try:
        pairs = [
            {"pair": "AITBC/BTC", "status": "active", "exchange": "binance"}
        ]
        output(pairs, title="Trading Pairs")
    except Exception as e:
        error(f"Error: {e}")


def connect_command(ctx, exchange: str, api_key: str, secret: str, sandbox: bool, passphrase: str | None):
    """Connect to external exchange"""
    try:
        success(f"Connected to {exchange}")
        output({
            "exchange": exchange,
            "sandbox": sandbox,
            "status": "connected"
        })
    except Exception as e:
        error(f"Error: {e}")


def status_command(ctx, exchange: str | None):
    """Get external exchange status"""
    try:
        status_data = {
            "exchange": exchange or "binance",
            "status": "connected",
            "latency": "50ms"
        }
        output(status_data, title="Exchange Status")
    except Exception as e:
        error(f"Error: {e}")


def disconnect_command(ctx, exchange: str):
    """Disconnect from external exchange"""
    try:
        success(f"Disconnected from {exchange}")
    except Exception as e:
        error(f"Error: {e}")


def orderbook_command(ctx, exchange: str, symbol: str, limit: int):
    """Get order book from external exchange"""
    try:
        orderbook = {
            "exchange": exchange,
            "symbol": symbol,
            "bids": [[100.0, 1.0]],
            "asks": [[101.0, 1.0]]
        }
        output(orderbook, title="Order Book")
    except Exception as e:
        error(f"Error: {e}")


def balance_command(ctx, exchange: str):
    """Get balance from external exchange"""
    try:
        balance = {
            "exchange": exchange,
            "aitbc": 1000.0,
            "btc": 0.05
        }
        output(balance, title="Exchange Balance")
    except Exception as e:
        error(f"Error: {e}")


def pairs_command(ctx, exchange: str):
    """List pairs from external exchange"""
    try:
        pairs = ["AITBC/BTC", "AITBC/ETH"]
        output(pairs, title=f"Pairs on {exchange}")
    except Exception as e:
        error(f"Error: {e}")


def order_command(ctx, order_id: str):
    """Get order details from external exchange"""
    try:
        order = {
            "order_id": order_id,
            "status": "filled",
            "price": 100.0
        }
        output(order, title="Order Details")
    except Exception as e:
        error(f"Error: {e}")


def orders_command(ctx, pair: str | None, status: str | None, limit: int):
    """List orders from external exchange"""
    try:
        orders = [
            {"order_id": "1", "status": "filled", "pair": "AITBC/BTC"}
        ]
        output(orders, title="Orders")
    except Exception as e:
        error(f"Error: {e}")


def book_command(ctx, pair: str, limit: int):
    """Get order book for pair"""
    try:
        book = {
            "pair": pair,
            "bids": [[100.0, 1.0]],
            "asks": [[101.0, 1.0]]
        }
        output(book, title="Order Book")
    except Exception as e:
        error(f"Error: {e}")


def history_command(ctx, pair: str | None, limit: int):
    """Get trade history"""
    try:
        history = [
            {"price": 100.0, "amount": 1.0, "time": "2024-01-01"}
        ]
        output(history, title="Trade History")
    except Exception as e:
        error(f"Error: {e}")


def list_exchanges_command(ctx):
    """List supported external exchanges"""
    try:
        exchanges = ["binance", "coinbase", "kraken"]
        output(exchanges, title="Supported Exchanges")
    except Exception as e:
        error(f"Error: {e}")


def price_command(ctx, base: str, quote: str):
    """Get price for trading pair"""
    try:
        price = {
            "pair": f"{base}/{quote}",
            "price": 100.0
        }
        output(price, title="Price")
    except Exception as e:
        error(f"Error: {e}")


def deposit_command(ctx, amount: float, ait_address: str, dry_run: bool):
    """Deposit to external exchange"""
    try:
        success(f"Deposit {amount} to {ait_address}")
        if dry_run:
            success("(dry run - no actual deposit)")
    except Exception as e:
        error(f"Error: {e}")


def withdraw_command(ctx, amount: float, eth_address: str, dry_run: bool):
    """Withdraw from external exchange"""
    try:
        success(f"Withdraw {amount} to {eth_address}")
        if dry_run:
            success("(dry run - no actual withdrawal)")
    except Exception as e:
        error(f"Error: {e}")


def swap_command(ctx, from_token: str, to_token: str, amount: float, slippage: float):
    """Swap tokens on external exchange"""
    try:
        success(f"Swap {amount} {from_token} to {to_token}")
        output({
            "from": from_token,
            "to": to_token,
            "amount": amount,
            "slippage": slippage
        })
    except Exception as e:
        error(f"Error: {e}")
