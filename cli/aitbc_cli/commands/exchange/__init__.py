"""
Exchange integration commands for AITBC CLI
"""

import click

from .main import exchange

__all__ = ["exchange"]


# Attach payment commands
@exchange.command()
@click.option("--aitbc-amount", type=float, help="Amount of AITBC to buy")
@click.option("--btc-amount", type=float, help="Amount of BTC to spend")
@click.option("--user-id", help="User ID for the payment")
@click.option("--notes", help="Additional notes for the payment")
@click.pass_context
def create_payment(ctx, aitbc_amount: float | None, btc_amount: float | None, user_id: str | None, notes: str | None):
    """Create a Bitcoin payment request for AITBC purchase"""
    create_payment_command(ctx, aitbc_amount, btc_amount, user_id, notes)


@exchange.command()
@click.option("--payment-id", required=True, help="Payment ID to check")
@click.pass_context
def payment_status(ctx, payment_id: str):
    """Check payment confirmation status"""
    payment_status_command(ctx, payment_id)


@exchange.command()
@click.pass_context
def market_stats(ctx):
    """Get exchange market statistics"""
    market_stats_command(ctx)


# Attach wallet commands
@exchange.group()
def wallet():
    """Wallet management for exchange operations"""
    pass


@wallet.command()
@click.pass_context
def balance(ctx):
    """Check wallet balance"""
    balance_command(ctx)


@wallet.command()
@click.pass_context
def info(ctx):
    """Get wallet information"""
    info_command(ctx)


# Attach trading commands
@exchange.command()
@click.option("--name", help="Exchange name")
@click.option("--api-key", help="Exchange API key")
@click.option("--api-secret", help="Exchange API secret")
@click.option("--sandbox", is_flag=True, help="Use sandbox environment")
@click.pass_context
def register(ctx, name: str, api_key: str, api_secret: str | None, sandbox: bool):
    """Register with external exchange"""
    register_command(ctx, name, api_key, api_secret, sandbox)


@exchange.command()
@click.option("--pair", help="Trading pair symbol")
@click.option("--base-asset", help="Base asset")
@click.option("--quote-asset", help="Quote asset")
@click.option("--min-order-size", type=float, help="Minimum order size")
@click.option("--price-precision", type=int, help="Price precision")
@click.option("--quantity-precision", type=int, help="Quantity precision")
@click.pass_context
def create_pair(
    ctx, pair: str, base_asset: str, quote_asset: str, min_order_size: float, price_precision: int, quantity_precision: int
):
    """Create trading pair on external exchange"""
    create_pair_command(ctx, pair, base_asset, quote_asset, min_order_size, price_precision, quantity_precision)


@exchange.command()
@click.option("--pair", help="Trading pair symbol")
@click.option("--exchange", help="Exchange name")
@click.option("--order-type", multiple=True, help="Order types")
@click.pass_context
def start_trading(ctx, pair: str, exchange: str | None, order_type: tuple):
    """Start trading on external exchange"""
    start_trading_command(ctx, pair, exchange, order_type)


@exchange.command()
@click.option("--pair", help="Trading pair symbol")
@click.option("--exchange", help="Exchange name")
@click.option("--status", help="Filter by status")
@click.pass_context
def list_pairs(ctx, pair: str | None, exchange: str | None, status: str | None):
    """List trading pairs on external exchange"""
    list_pairs_command(ctx, pair, exchange, status)


@exchange.command()
@click.option("--exchange", help="Exchange name")
@click.option("--api-key", help="API key")
@click.option("--secret", help="API secret")
@click.option("--sandbox", is_flag=True, help="Use sandbox")
@click.option("--passphrase", help="API passphrase")
@click.pass_context
def connect(ctx, exchange: str, api_key: str, secret: str, sandbox: bool, passphrase: str | None):
    """Connect to external exchange"""
    connect_command(ctx, exchange, api_key, secret, sandbox, passphrase)


@exchange.command()
@click.option("--exchange", help="Exchange name")
@click.pass_context
def status(ctx, exchange: str | None):
    """Get external exchange status"""
    status_command(ctx, exchange)


@exchange.command()
@click.argument("exchange")
@click.pass_context
def disconnect(ctx, exchange: str):
    """Disconnect from external exchange"""
    disconnect_command(ctx, exchange)


@exchange.command()
@click.option("--exchange", help="Exchange name")
@click.option("--symbol", help="Trading symbol")
@click.option("--limit", type=int, default=10, help="Limit results")
@click.pass_context
def orderbook(ctx, exchange: str, symbol: str, limit: int):
    """Get order book from external exchange"""
    orderbook_command(ctx, exchange, symbol, limit)


@exchange.command()
@click.option("--exchange", help="Exchange name")
@click.pass_context
def exchange_balance(ctx, exchange: str):
    """Get balance from external exchange"""
    trading_balance_command(ctx, exchange)


@exchange.command()
@click.option("--exchange", help="Exchange name")
@click.pass_context
def pairs(ctx, exchange: str):
    """List pairs from external exchange"""
    pairs_command(ctx, exchange)


@exchange.command()
@click.argument("order_id")
@click.pass_context
def order(ctx, order_id: str):
    """Get order details from external exchange"""
    order_command(ctx, order_id)


@exchange.command()
@click.option("--pair", help="Trading pair")
@click.option("--status", help="Filter by status")
@click.option("--limit", type=int, default=10, help="Limit results")
@click.pass_context
def orders(ctx, pair: str | None, status: str | None, limit: int):
    """List orders from external exchange"""
    orders_command(ctx, pair, status, limit)


@exchange.command()
@click.option("--pair", help="Trading pair")
@click.option("--limit", type=int, default=10, help="Limit results")
@click.pass_context
def book(ctx, pair: str, limit: int):
    """Get order book for pair"""
    book_command(ctx, pair, limit)


@exchange.command()
@click.option("--pair", help="Trading pair")
@click.option("--limit", type=int, default=10, help="Limit results")
@click.pass_context
def history(ctx, pair: str | None, limit: int):
    """Get trade history"""
    history_command(ctx, pair, limit)


@exchange.command()
@click.pass_context
def list_exchanges(ctx):
    """List supported external exchanges"""
    list_exchanges_command(ctx)


@exchange.command()
@click.option("--base", help="Base asset")
@click.option("--quote", help="Quote asset")
@click.pass_context
def price(ctx, base: str, quote: str):
    """Get price for trading pair"""
    price_command(ctx, base, quote)


@exchange.command()
@click.option("--amount", type=float, help="Amount to deposit")
@click.option("--ait-address", help="AITBC address")
@click.option("--dry-run", is_flag=True, help="Dry run")
@click.pass_context
def deposit(ctx, amount: float, ait_address: str, dry_run: bool):
    """Deposit to external exchange"""
    deposit_command(ctx, amount, ait_address, dry_run)


@exchange.command()
@click.option("--amount", type=float, help="Amount to withdraw")
@click.option("--eth-address", help="ETH address")
@click.option("--dry-run", is_flag=True, help="Dry run")
@click.pass_context
def withdraw(ctx, amount: float, eth_address: str, dry_run: bool):
    """Withdraw from external exchange"""
    withdraw_command(ctx, amount, eth_address, dry_run)


@exchange.command()
@click.option("--from-token", help="From token")
@click.option("--to-token", help="To token")
@click.option("--amount", type=float, help="Amount")
@click.option("--slippage", type=float, default=0.5, help="Slippage tolerance")
@click.pass_context
def swap(ctx, from_token: str, to_token: str, amount: float, slippage: float):
    """Swap tokens on external exchange"""
    swap_command(ctx, from_token, to_token, amount, slippage)


# Attach bridge commands
@exchange.command("bridge-status")
@click.option("--tx-id", help="Transaction ID")
@click.pass_context
def bridge_status(ctx, tx_id: str | None):
    """Check bridge status"""
    bridge_status_command(ctx, tx_id)


@exchange.command()
@click.option("--status", help="Filter by status")
@click.option("--limit", type=int, default=10, help="Limit results")
@click.pass_context
def bridge_deposits(status, limit):
    """List bridge deposits"""
    bridge_deposits_command(status, limit)


@exchange.command()
@click.argument("eth-amount", type=float)
@click.pass_context
def bridge_estimate(eth_amount):
    """Estimate bridge fee"""
    bridge_estimate_command(eth_amount)


__all__ = ["exchange"]
