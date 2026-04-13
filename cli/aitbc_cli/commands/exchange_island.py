"""
Exchange Island CLI Commands
Commands for trading AIT coin against BTC and ETH on the island exchange
"""

import click
import json
import hashlib
import socket
import os
from datetime import datetime
from decimal import Decimal
from typing import Optional
from ..utils import output, error, success, info, warning
from ..utils.island_credentials import (
    load_island_credentials, get_rpc_endpoint, get_chain_id,
    get_island_id, get_island_name
)


# Supported trading pairs
SUPPORTED_PAIRS = ['AIT/BTC', 'AIT/ETH']


@click.group()
def exchange_island():
    """Exchange commands for trading AIT against BTC and ETH on the island"""
    pass


@exchange_island.command()
@click.argument('ait_amount', type=float)
@click.argument('quote_currency', type=click.Choice(['BTC', 'ETH']))
@click.option('--max-price', type=float, help='Maximum price to pay per AIT')
@click.pass_context
def buy(ctx, ait_amount: float, quote_currency: str, max_price: Optional[float]):
    """Buy AIT with BTC or ETH"""
    try:
        if ait_amount <= 0:
            error("AIT amount must be greater than 0")
            raise click.Abort()

        # Load island credentials
        credentials = load_island_credentials()
        rpc_endpoint = get_rpc_endpoint()
        chain_id = get_chain_id()
        island_id = get_island_id()

        # Get user node ID
        hostname = socket.gethostname()
        local_address = socket.gethostbyname(hostname)
        p2p_port = credentials.get('credentials', {}).get('p2p_port', 8001)
        
        # Get public key for node ID generation
        keystore_path = '/var/lib/aitbc/keystore/validator_keys.json'
        if os.path.exists(keystore_path):
            with open(keystore_path, 'r') as f:
                keys = json.load(f)
                public_key_pem = None
                for key_id, key_data in keys.items():
                    public_key_pem = key_data.get('public_key_pem')
                    break
                if public_key_pem:
                    content = f"{hostname}:{local_address}:{p2p_port}:{public_key_pem}"
                    user_id = hashlib.sha256(content.encode()).hexdigest()
                else:
                    error("No public key found in keystore")
                    raise click.Abort()
        else:
            error(f"Keystore not found at {keystore_path}")
            raise click.Abort()

        pair = f"AIT/{quote_currency}"

        # Generate order ID
        order_id = f"exchange_buy_{datetime.now().strftime('%Y%m%d%H%M%S')}_{hashlib.sha256(f'{user_id}{ait_amount}{quote_currency}'.encode()).hexdigest()[:8]}"

        # Create buy order transaction
        buy_order_data = {
            'type': 'exchange',
            'action': 'buy',
            'order_id': order_id,
            'user_id': user_id,
            'pair': pair,
            'side': 'buy',
            'amount': float(ait_amount),
            'max_price': float(max_price) if max_price else None,
            'status': 'open',
            'island_id': island_id,
            'chain_id': chain_id,
            'created_at': datetime.now().isoformat()
        }

        # Submit transaction to blockchain
        try:
            import httpx
            with httpx.Client() as client:
                response = client.post(
                    f"{rpc_endpoint}/transaction",
                    json=buy_order_data,
                    timeout=10
                )
                
                if response.status_code == 200:
                    result = response.json()
                    success(f"Buy order created successfully!")
                    success(f"Order ID: {order_id}")
                    success(f"Buying {ait_amount} AIT with {quote_currency}")
                    
                    if max_price:
                        success(f"Max price: {max_price:.8f} {quote_currency}/AIT")
                    
                    order_info = {
                        "Order ID": order_id,
                        "Pair": pair,
                        "Side": "BUY",
                        "Amount": f"{ait_amount} AIT",
                        "Max Price": f"{max_price:.8f} {quote_currency}/AIT" if max_price else "Market",
                        "Status": "open",
                        "User": user_id[:16] + "...",
                        "Island": island_id[:16] + "..."
                    }
                    
                    output(order_info, ctx.obj.get('output_format', 'table'))
                else:
                    error(f"Failed to submit transaction: {response.status_code}")
                    if response.text:
                        error(f"Error details: {response.text}")
                    raise click.Abort()
        except Exception as e:
            error(f"Network error submitting transaction: {e}")
            raise click.Abort()

    except Exception as e:
        error(f"Error creating buy order: {str(e)}")
        raise click.Abort()


@exchange_island.command()
@click.argument('ait_amount', type=float)
@click.argument('quote_currency', type=click.Choice(['BTC', 'ETH']))
@click.option('--min-price', type=float, help='Minimum price to accept per AIT')
@click.pass_context
def sell(ctx, ait_amount: float, quote_currency: str, min_price: Optional[float]):
    """Sell AIT for BTC or ETH"""
    try:
        if ait_amount <= 0:
            error("AIT amount must be greater than 0")
            raise click.Abort()

        # Load island credentials
        credentials = load_island_credentials()
        rpc_endpoint = get_rpc_endpoint()
        chain_id = get_chain_id()
        island_id = get_island_id()

        # Get user node ID
        hostname = socket.gethostname()
        local_address = socket.gethostbyname(hostname)
        p2p_port = credentials.get('credentials', {}).get('p2p_port', 8001)
        
        # Get public key for node ID generation
        keystore_path = '/var/lib/aitbc/keystore/validator_keys.json'
        if os.path.exists(keystore_path):
            with open(keystore_path, 'r') as f:
                keys = json.load(f)
                public_key_pem = None
                for key_id, key_data in keys.items():
                    public_key_pem = key_data.get('public_key_pem')
                    break
                if public_key_pem:
                    content = f"{hostname}:{local_address}:{p2p_port}:{public_key_pem}"
                    user_id = hashlib.sha256(content.encode()).hexdigest()
                else:
                    error("No public key found in keystore")
                    raise click.Abort()
        else:
            error(f"Keystore not found at {keystore_path}")
            raise click.Abort()

        pair = f"AIT/{quote_currency}"

        # Generate order ID
        order_id = f"exchange_sell_{datetime.now().strftime('%Y%m%d%H%M%S')}_{hashlib.sha256(f'{user_id}{ait_amount}{quote_currency}'.encode()).hexdigest()[:8]}"

        # Create sell order transaction
        sell_order_data = {
            'type': 'exchange',
            'action': 'sell',
            'order_id': order_id,
            'user_id': user_id,
            'pair': pair,
            'side': 'sell',
            'amount': float(ait_amount),
            'min_price': float(min_price) if min_price else None,
            'status': 'open',
            'island_id': island_id,
            'chain_id': chain_id,
            'created_at': datetime.now().isoformat()
        }

        # Submit transaction to blockchain
        try:
            import httpx
            with httpx.Client() as client:
                response = client.post(
                    f"{rpc_endpoint}/transaction",
                    json=sell_order_data,
                    timeout=10
                )
                
                if response.status_code == 200:
                    result = response.json()
                    success(f"Sell order created successfully!")
                    success(f"Order ID: {order_id}")
                    success(f"Selling {ait_amount} AIT for {quote_currency}")
                    
                    if min_price:
                        success(f"Min price: {min_price:.8f} {quote_currency}/AIT")
                    
                    order_info = {
                        "Order ID": order_id,
                        "Pair": pair,
                        "Side": "SELL",
                        "Amount": f"{ait_amount} AIT",
                        "Min Price": f"{min_price:.8f} {quote_currency}/AIT" if min_price else "Market",
                        "Status": "open",
                        "User": user_id[:16] + "...",
                        "Island": island_id[:16] + "..."
                    }
                    
                    output(order_info, ctx.obj.get('output_format', 'table'))
                else:
                    error(f"Failed to submit transaction: {response.status_code}")
                    if response.text:
                        error(f"Error details: {response.text}")
                    raise click.Abort()
        except Exception as e:
            error(f"Network error submitting transaction: {e}")
            raise click.Abort()

    except Exception as e:
        error(f"Error creating sell order: {str(e)}")
        raise click.Abort()


@exchange_island.command()
@click.argument('pair', type=click.Choice(SUPPORTED_PAIRS))
@click.option('--limit', type=int, default=20, help='Order book depth')
@click.pass_context
def orderbook(ctx, pair: str, limit: int):
    """View the order book for a trading pair"""
    try:
        # Load island credentials
        credentials = load_island_credentials()
        rpc_endpoint = get_rpc_endpoint()
        island_id = get_island_id()

        # Query blockchain for exchange orders
        try:
            import httpx
            params = {
                'transaction_type': 'exchange',
                'island_id': island_id,
                'pair': pair,
                'status': 'open',
                'limit': limit * 2  # Get both buys and sells
            }

            with httpx.Client() as client:
                response = client.get(
                    f"{rpc_endpoint}/transactions",
                    params=params,
                    timeout=10
                )
                
                if response.status_code == 200:
                    orders = response.json()
                    
                    # Separate buy and sell orders
                    buy_orders = []
                    sell_orders = []
                    
                    for order in orders:
                        if order.get('side') == 'buy':
                            buy_orders.append(order)
                        elif order.get('side') == 'sell':
                            sell_orders.append(order)
                    
                    # Sort buy orders by price descending (highest first)
                    buy_orders.sort(key=lambda x: x.get('max_price', 0), reverse=True)
                    # Sort sell orders by price ascending (lowest first)
                    sell_orders.sort(key=lambda x: x.get('min_price', float('inf')))
                    
                    if not buy_orders and not sell_orders:
                        info(f"No open orders for {pair}")
                        return
                    
                    # Display sell orders (asks)
                    if sell_orders:
                        asks_data = []
                        for order in sell_orders[:limit]:
                            asks_data.append({
                                "Price": f"{order.get('min_price', 0):.8f}",
                                "Amount": f"{order.get('amount', 0):.4f} AIT",
                                "Total": f"{order.get('min_price', 0) * order.get('amount', 0):.8f} {pair.split('/')[1]}",
                                "User": order.get('user_id', '')[:16] + "...",
                                "Order": order.get('order_id', '')[:16] + "..."
                            })
                        
                        output(asks_data, ctx.obj.get('output_format', 'table'), title=f"Sell Orders (Asks) - {pair}")
                    
                    # Display buy orders (bids)
                    if buy_orders:
                        bids_data = []
                        for order in buy_orders[:limit]:
                            bids_data.append({
                                "Price": f"{order.get('max_price', 0):.8f}",
                                "Amount": f"{order.get('amount', 0):.4f} AIT",
                                "Total": f"{order.get('max_price', 0) * order.get('amount', 0):.8f} {pair.split('/')[1]}",
                                "User": order.get('user_id', '')[:16] + "...",
                                "Order": order.get('order_id', '')[:16] + "..."
                            })
                        
                        output(bids_data, ctx.obj.get('output_format', 'table'), title=f"Buy Orders (Bids) - {pair}")
                    
                    # Calculate spread if both exist
                    if sell_orders and buy_orders:
                        best_ask = sell_orders[0].get('min_price', 0)
                        best_bid = buy_orders[0].get('max_price', 0)
                        spread = best_ask - best_bid
                        if best_bid > 0:
                            spread_pct = (spread / best_bid) * 100
                            info(f"Spread: {spread:.8f} ({spread_pct:.4f}%)")
                            info(f"Best Bid: {best_bid:.8f} {pair.split('/')[1]}/AIT")
                            info(f"Best Ask: {best_ask:.8f} {pair.split('/')[1]}/AIT")
                        
                else:
                    error(f"Failed to query blockchain: {response.status_code}")
                    raise click.Abort()
        except Exception as e:
            error(f"Network error querying blockchain: {e}")
            raise click.Abort()

    except Exception as e:
        error(f"Error viewing order book: {str(e)}")
        raise click.Abort()


@exchange_island.command()
@click.pass_context
def rates(ctx):
    """View current exchange rates for AIT/BTC and AIT/ETH"""
    try:
        # Load island credentials
        credentials = load_island_credentials()
        rpc_endpoint = get_rpc_endpoint()
        island_id = get_island_id()

        # Query blockchain for exchange orders to calculate rates
        try:
            import httpx
            rates_data = []
            
            for pair in SUPPORTED_PAIRS:
                params = {
                    'transaction_type': 'exchange',
                    'island_id': island_id,
                    'pair': pair,
                    'status': 'open',
                    'limit': 100
                }

                with httpx.Client() as client:
                    response = client.get(
                        f"{rpc_endpoint}/transactions",
                        params=params,
                        timeout=10
                    )
                    
                    if response.status_code == 200:
                        orders = response.json()
                        
                        # Calculate rates from order book
                        buy_orders = [o for o in orders if o.get('side') == 'buy']
                        sell_orders = [o for o in orders if o.get('side') == 'sell']
                        
                        # Get best bid and ask
                        best_bid = max([o.get('max_price', 0) for o in buy_orders]) if buy_orders else 0
                        best_ask = min([o.get('min_price', float('inf')) for o in sell_orders]) if sell_orders else 0
                        
                        # Calculate mid price
                        mid_price = (best_bid + best_ask) / 2 if best_bid > 0 and best_ask < float('inf') else 0
                        
                        rates_data.append({
                            "Pair": pair,
                            "Best Bid": f"{best_bid:.8f}" if best_bid > 0 else "N/A",
                            "Best Ask": f"{best_ask:.8f}" if best_ask < float('inf') else "N/A",
                            "Mid Price": f"{mid_price:.8f}" if mid_price > 0 else "N/A",
                            "Buy Orders": len(buy_orders),
                            "Sell Orders": len(sell_orders)
                        })
                    else:
                        rates_data.append({
                            "Pair": pair,
                            "Best Bid": "Error",
                            "Best Ask": "Error",
                            "Mid Price": "Error",
                            "Buy Orders": 0,
                            "Sell Orders": 0
                        })
            
            output(rates_data, ctx.obj.get('output_format', 'table'), title="Exchange Rates")

        except Exception as e:
            error(f"Network error querying blockchain: {e}")
            raise click.Abort()

    except Exception as e:
        error(f"Error viewing exchange rates: {str(e)}")
        raise click.Abort()


@exchange_island.command()
@click.option('--user', help='Filter by user ID')
@click.option('--status', help='Filter by status (open, filled, partially_filled, cancelled)')
@click.option('--pair', type=click.Choice(SUPPORTED_PAIRS), help='Filter by trading pair')
@click.pass_context
def orders(ctx, user: Optional[str], status: Optional[str], pair: Optional[str]):
    """List exchange orders"""
    try:
        # Load island credentials
        credentials = load_island_credentials()
        rpc_endpoint = get_rpc_endpoint()
        island_id = get_island_id()

        # Query blockchain for exchange orders
        try:
            import httpx
            params = {
                'transaction_type': 'exchange',
                'island_id': island_id
            }
            if user:
                params['user_id'] = user
            if status:
                params['status'] = status
            if pair:
                params['pair'] = pair

            with httpx.Client() as client:
                response = client.get(
                    f"{rpc_endpoint}/transactions",
                    params=params,
                    timeout=10
                )
                
                if response.status_code == 200:
                    orders = response.json()
                    
                    if not orders:
                        info("No exchange orders found")
                        return
                    
                    # Format output
                    orders_data = []
                    for order in orders:
                        orders_data.append({
                            "Order ID": order.get('order_id', '')[:20] + "...",
                            "Pair": order.get('pair'),
                            "Side": order.get('side', '').upper(),
                            "Amount": f"{order.get('amount', 0):.4f} AIT",
                            "Price": f"{order.get('max_price', order.get('min_price', 0)):.8f}" if order.get('max_price') or order.get('min_price') else "Market",
                            "Status": order.get('status'),
                            "User": order.get('user_id', '')[:16] + "...",
                            "Created": order.get('created_at', '')[:19]
                        })
                    
                    output(orders_data, ctx.obj.get('output_format', 'table'), title=f"Exchange Orders ({island_id[:16]}...)")
                else:
                    error(f"Failed to query blockchain: {response.status_code}")
                    raise click.Abort()
        except Exception as e:
            error(f"Network error querying blockchain: {e}")
            raise click.Abort()

    except Exception as e:
        error(f"Error listing orders: {str(e)}")
        raise click.Abort()


@exchange_island.command()
@click.argument('order_id')
@click.pass_context
def cancel(ctx, order_id: str):
    """Cancel an exchange order"""
    try:
        # Load island credentials
        credentials = load_island_credentials()
        rpc_endpoint = get_rpc_endpoint()
        chain_id = get_chain_id()
        island_id = get_island_id()

        # Get local node ID
        hostname = socket.gethostname()
        local_address = socket.gethostbyname(hostname)
        p2p_port = credentials.get('credentials', {}).get('p2p_port', 8001)
        
        keystore_path = '/var/lib/aitbc/keystore/validator_keys.json'
        if os.path.exists(keystore_path):
            with open(keystore_path, 'r') as f:
                keys = json.load(f)
                public_key_pem = None
                for key_id, key_data in keys.items():
                    public_key_pem = key_data.get('public_key_pem')
                    break
                if public_key_pem:
                    content = f"{hostname}:{local_address}:{p2p_port}:{public_key_pem}"
                    local_node_id = hashlib.sha256(content.encode()).hexdigest()

        # Create cancel transaction
        cancel_data = {
            'type': 'exchange',
            'action': 'cancel',
            'order_id': order_id,
            'user_id': local_node_id,
            'status': 'cancelled',
            'cancelled_at': datetime.now().isoformat(),
            'island_id': island_id,
            'chain_id': chain_id
        }

        # Submit transaction to blockchain
        try:
            import httpx
            with httpx.Client() as client:
                response = client.post(
                    f"{rpc_endpoint}/transaction",
                    json=cancel_data,
                    timeout=10
                )
                
                if response.status_code == 200:
                    success(f"Order {order_id} cancelled successfully!")
                else:
                    error(f"Failed to cancel order: {response.status_code}")
                    if response.text:
                        error(f"Error details: {response.text}")
                    raise click.Abort()
        except Exception as e:
            error(f"Network error submitting transaction: {e}")
            raise click.Abort()

    except Exception as e:
        error(f"Error cancelling order: {str(e)}")
        raise click.Abort()
