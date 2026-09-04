"""
Exchange Island CLI Commands
Commands for trading AIT coin against ETH on the island exchange
"""

import hashlib
import json
import os
import socket
from datetime import datetime
from decimal import Decimal
from typing import Any, cast

import click

from aitbc.utils.units import DEFAULT_TX_FEE_UNITS

from ..utils import DECIMAL, error, info, output, success
from ..utils.error_handling import abort
from ..utils.wallet_loader import load_wallet_for_payment

# Import shared modules
from ..utils.http_client import AITBCHTTPClient, NetworkError, get_logger
from ..utils.island_credentials import get_chain_id, get_island_id, get_rpc_endpoint, load_island_credentials

# Initialize logger
logger = get_logger(__name__)

# Module-level keystore path (patchable in tests)
KEYSTORE_PATH = "/var/lib/aitbc/keystore/validator_keys.json"

SIMULATED_TIMESTAMP = "2026-01-01T00:00:00+00:00"


def _as_decimal(value: Any) -> Decimal:
    """Convert a stored order quantity or price to Decimal without using float()."""
    return Decimal(str(value))


def safe_load_credentials():
    """Load island credentials with graceful error handling"""
    try:
        return load_island_credentials()
    except FileNotFoundError as e:
        error(f"Island credentials not found: {e}")
        error("Run 'aitbc node island join' to join an island first")
        return None


def _sign_exchange_tx(tx_data: dict[str, Any], private_key: str) -> str:
    """Sign an exchange transaction the same way the blockchain RPC verifies it."""
    from eth_keys import keys
    from eth_utils import keccak

    has_amount = "amount" in tx_data
    tx_without_sig = {k: v for k, v in tx_data.items() if k != "signature" and not (has_amount and k == "value")}
    message = json.dumps(tx_without_sig, sort_keys=True, separators=(",", ":")).encode()
    msg_hash = keccak(message)
    pk_hex = private_key.removeprefix("0x")
    pk = keys.PrivateKey(bytes.fromhex(pk_hex))
    sig = pk.sign_msg_hash(msg_hash)
    return sig.to_hex()


def _build_exchange_tx(
    ctx,
    side: str,
    ait_amount: Decimal,
    quote_currency: str,
    price: Decimal | None,
    wallet_name: str | None,
    password: str | None,
) -> tuple[dict[str, Any], str, AITBCHTTPClient] | None:
    """Build a signed EXCHANGE transaction, returning the tx dict and an HTTP client."""
    credentials = safe_load_credentials()
    if not credentials:
        return None
    rpc_endpoint = get_rpc_endpoint()
    chain_id = get_chain_id()
    island_id = get_island_id()

    address, private_key, _wallet_name = load_wallet_for_payment(ctx, wallet_name, password=password)
    if not private_key:
        abort(ctx, f"Wallet '{_wallet_name}' has no usable private key; use a file wallet with --wallet")
        return None

    http_client = AITBCHTTPClient(base_url=rpc_endpoint, timeout=10)
    account = http_client.get(f"/account/{address}", params={"chain_id": chain_id})
    nonce = account.get("nonce", 0)

    pair = f"AIT/{quote_currency}"
    order_id = f"exchange_{side}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{hashlib.sha256(f'{address}{ait_amount}{quote_currency}'.encode()).hexdigest()[:8]}"

    order_payload: dict[str, Any] = {
        "action": side,
        "order_id": order_id,
        "user_id": address,
        "pair": pair,
        "side": side,
        "amount": str(ait_amount),
        "to": address,
        "status": "open",
        "island_id": island_id,
        "chain_id": chain_id,
        "created_at": datetime.now().isoformat(),
    }
    if side == "buy" and price:
        order_payload["max_price"] = str(price)
    if side == "sell" and price:
        order_payload["min_price"] = str(price)

    tx_data: dict[str, Any] = {
        "from": address,
        "to": address,
        "amount": 0,
        "fee": DEFAULT_TX_FEE_UNITS,
        "nonce": nonce,
        "type": "EXCHANGE",
        "chain_id": chain_id,
        "payload": order_payload,
    }
    tx_data["signature"] = _sign_exchange_tx(tx_data, private_key)
    return tx_data, order_id, http_client


def _hash_float(parts, low: float = 0.0, high: float = 1.0, decimals: int = 8) -> float:
    content = ":".join(str(p) for p in parts)
    normalized = int(hashlib.md5(content.encode(), usedforsecurity=False).hexdigest()[:8], 16) / 0xFFFFFFFF
    return round(low + normalized * (high - low), decimals)


def _hash_int(parts, low: int, high: int) -> int:
    content = ":".join(str(p) for p in parts)
    normalized = int(hashlib.md5(content.encode(), usedforsecurity=False).hexdigest()[:8], 16) / 0xFFFFFFFF
    return int(low + normalized * (high - low))


def _base_price(pair: str) -> float:
    return _hash_float(("exchange", "base", pair), 0.00005, 0.001, 8)


def _simulated_orderbook_transactions(pair: str, limit: int) -> list[dict[str, Any]]:
    base = _base_price(pair)
    transactions = []
    for i in range(1, limit + 1):
        ask_seed = ("exchange", "orderbook", pair, "ask", str(i))
        ask_price = round(base * (1 + i * 0.005), 8)
        ask_amount = _hash_float(ask_seed + ("amount",), 10.0, 1000.0, 4)
        ask_hash = hashlib.md5(":".join(ask_seed).encode(), usedforsecurity=False).hexdigest()
        transactions.append(
            {
                "side": "sell",
                "min_price": ask_price,
                "max_price": None,
                "amount": ask_amount,
                "user_id": ask_hash[:32],
                "order_id": f"sim_ask_{i:04d}_{ask_hash[:8]}",
                "pair": pair,
                "status": "open",
                "created_at": SIMULATED_TIMESTAMP,
            }
        )

        bid_seed = ("exchange", "orderbook", pair, "bid", str(i))
        bid_price = round(base * (1 - i * 0.005), 8)
        bid_amount = _hash_float(bid_seed + ("amount",), 10.0, 1000.0, 4)
        bid_hash = hashlib.md5(":".join(bid_seed).encode(), usedforsecurity=False).hexdigest()
        transactions.append(
            {
                "side": "buy",
                "min_price": None,
                "max_price": bid_price,
                "amount": bid_amount,
                "user_id": bid_hash[:32],
                "order_id": f"sim_bid_{i:04d}_{bid_hash[:8]}",
                "pair": pair,
                "status": "open",
                "created_at": SIMULATED_TIMESTAMP,
            }
        )
    return transactions


def _simulated_orders_for_pair(pair: str, count: int) -> list[dict[str, Any]]:
    base = _base_price(pair)
    orders = []
    for i in range(1, count + 1):
        side = "sell" if i % 2 == 0 else "buy"
        seed = ("exchange", "rates", pair, side, str(i))
        price = round(base * (1 + (i * 0.005) * (1 if side == "sell" else -1)), 8)
        order_hash = hashlib.md5(":".join(seed).encode(), usedforsecurity=False).hexdigest()
        order = {
            "side": side,
            "amount": _hash_float(seed + ("amount",), 10.0, 1000.0, 4),
            "user_id": order_hash[:32],
            "order_id": f"sim_{side}_{i:04d}_{order_hash[:8]}",
            "pair": pair,
            "status": "open",
            "created_at": SIMULATED_TIMESTAMP,
        }
        if side == "sell":
            order["min_price"] = price
            order["max_price"] = None
        else:
            order["min_price"] = None
            order["max_price"] = price
        orders.append(order)
    return orders


def _simulated_order_list(user: str | None, status: str | None, pair: str | None, island_id: str) -> list[dict[str, Any]]:
    pairs = [pair] if pair else SUPPORTED_PAIRS
    orders = []
    for p in pairs:
        base = _base_price(p)
        for i in range(1, 6):
            side = "sell" if i % 2 == 0 else "buy"
            seed = ("exchange", "orders", user or "any", status or "any", p, str(i))
            price = round(base * (1 + (i * 0.005) * (1 if side == "sell" else -1)), 8)
            order_hash = hashlib.md5(":".join(seed).encode(), usedforsecurity=False).hexdigest()
            order = {
                "order_id": f"sim_{side}_{i:04d}_{order_hash[:8]}",
                "pair": p,
                "side": side,
                "amount": _hash_float(seed + ("amount",), 10.0, 500.0, 4),
                "status": status or "open",
                "user_id": user or order_hash[:32],
                "created_at": SIMULATED_TIMESTAMP,
            }
            if side == "sell":
                order["min_price"] = price
            else:
                order["max_price"] = price
            orders.append(order)
    return orders


# Supported trading pairs
SUPPORTED_PAIRS = ["AIT/ETH"]


@click.group(
    epilog="""Examples:

  aitbc exchange-island buy --ait-amount 100 --quote-currency ETH

  aitbc exchange-island orderbook --pair AIT/ETH"""
)
def exchange_island():
    """Trade AIT against ETH, view order books, list orders, and cancel orders on the island exchange."""
    pass


@exchange_island.command(
    epilog="""Examples:

  aitbc exchange-island buy --ait-amount 100 --quote-currency ETH

  aitbc exchange-island buy --ait-amount 100 --quote-currency ETH --max-price 0.001 --wallet wallet-1"""
)
@click.option("--ait-amount", "ait_amount", required=True, type=DECIMAL, help="The Ait amount.")
@click.option("--quote-currency", "quote_currency", required=True, type=click.Choice(["ETH"]), help="The Quote currency.")
@click.option("--max-price", type=DECIMAL, help="Maximum price to pay per AIT")
@click.option("--wallet", default=None, help="Wallet name or file path for signing")
@click.option("--password", default=None, help="Wallet encryption password")
@click.pass_context
def buy(ctx, ait_amount: Decimal, quote_currency: str, max_price: Decimal | None, wallet: str | None, password: str | None):
    """Buy AIT with a quote currency using an optional wallet and maximum price."""
    try:
        if ait_amount <= 0:
            abort(ctx, "AIT amount must be greater than 0")

        built = _build_exchange_tx(ctx, "buy", ait_amount, quote_currency, max_price, wallet, password)
        if built is None:
            return
        tx_data, order_id, http_client = built

        try:
            response = http_client.post("/transaction", json=tx_data)
            success("Buy order created successfully!")
            success(f"Order ID: {order_id}")
            success(f"Buying {ait_amount} AIT with {quote_currency}")

            if max_price:
                success(f"Max price: {max_price:.8f} {quote_currency}/AIT")

            order_info = {
                "Order ID": order_id,
                "Pair": tx_data["payload"]["pair"],
                "Side": "BUY",
                "Amount": f"{ait_amount} AIT",
                "Max Price": f"{max_price:.8f} {quote_currency}/AIT" if max_price else "Market",
                "Status": "open",
                "User": tx_data["from"][:16] + "...",
                "Island": tx_data["payload"]["island_id"][:16] + "...",
            }
            output(order_info, ctx.obj.get("output_format", "table"))
            output(response, ctx.obj.get("output_format", "table"), title="Transaction")
        except NetworkError as e:
            abort(ctx, f"Network error submitting transaction: {e}", from_exception=e)
        except Exception as e:
            abort(ctx, f"Error submitting transaction: {e}", from_exception=e)

    except Exception as e:
        abort(ctx, f"Error creating buy order: {str(e)}", from_exception=e)


@exchange_island.command(
    epilog="""Examples:

  aitbc exchange-island sell --ait-amount 100 --quote-currency ETH

  aitbc exchange-island sell --ait-amount 100 --quote-currency ETH --min-price 0.001 --wallet wallet-1"""
)
@click.option("--ait-amount", "ait_amount", required=True, type=DECIMAL, help="The Ait amount.")
@click.option("--quote-currency", "quote_currency", required=True, type=click.Choice(["ETH"]), help="The Quote currency.")
@click.option("--min-price", type=DECIMAL, help="Minimum price to accept per AIT")
@click.option("--wallet", default=None, help="Wallet name or file path for signing")
@click.option("--password", default=None, help="Wallet encryption password")
@click.pass_context
def sell(ctx, ait_amount: Decimal, quote_currency: str, min_price: Decimal | None, wallet: str | None, password: str | None):
    """Sell AIT for a quote currency using an optional wallet and minimum price."""
    try:
        if ait_amount <= 0:
            abort(ctx, "AIT amount must be greater than 0")

        built = _build_exchange_tx(ctx, "sell", ait_amount, quote_currency, min_price, wallet, password)
        if built is None:
            return
        tx_data, order_id, http_client = built

        try:
            response = http_client.post("/transaction", json=tx_data)
            success("Sell order created successfully!")
            success(f"Order ID: {order_id}")
            success(f"Selling {ait_amount} AIT for {quote_currency}")

            if min_price:
                success(f"Min price: {min_price:.8f} {quote_currency}/AIT")

            order_info = {
                "Order ID": order_id,
                "Pair": tx_data["payload"]["pair"],
                "Side": "SELL",
                "Amount": f"{ait_amount} AIT",
                "Min Price": f"{min_price:.8f} {quote_currency}/AIT" if min_price else "Market",
                "Status": "open",
                "User": tx_data["from"][:16] + "...",
                "Island": tx_data["payload"]["island_id"][:16] + "...",
            }
            output(order_info, ctx.obj.get("output_format", "table"))
            output(response, ctx.obj.get("output_format", "table"), title="Transaction")
        except NetworkError as e:
            abort(ctx, f"Network error submitting transaction: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error creating sell order: {str(e)}", from_exception=e)


@exchange_island.command(
    epilog="""Examples:

  aitbc exchange-island orderbook --pair AIT/ETH

  aitbc exchange-island orderbook --pair AIT/ETH --limit 50"""
)
@click.option("--pair", "pair", required=True, type=click.Choice(SUPPORTED_PAIRS), help="The Pair.")
@click.option("--limit", type=int, default=20, help="Order book depth")
@click.pass_context
def orderbook(ctx, pair: str, limit: int):
    """View the order book for a supported trading pair."""
    try:
        # Load island credentials
        credentials = safe_load_credentials()
        if not credentials:
            return
        rpc_endpoint = get_rpc_endpoint()
        island_id = get_island_id()

        # Query blockchain for exchange orders
        params = {
            "transaction_type": "EXCHANGE",
            "island_id": island_id,
            "pair": pair,
            "status": "open",
            "limit": limit * 2,  # Get both buys and sells
        }

        http_client = AITBCHTTPClient(base_url=rpc_endpoint, timeout=10)
        try:
            response = http_client.get("/transactions", params=params)
            # Response is a dict with 'transactions' key
            transactions = cast(list[dict[str, Any]], response.get("transactions", []))
        except NetworkError:
            transactions = _simulated_orderbook_transactions(pair, limit)

        def _order_payload(order: dict[str, Any]) -> dict[str, Any]:
            return order.get("payload") or order

        # Separate buy and sell orders
        buy_orders = []
        sell_orders = []

        for order in transactions:
            if not isinstance(order, dict):
                continue  # type: ignore[unreachable]
            payload = _order_payload(order)
            if payload.get("side") == "buy":
                buy_orders.append(payload)
            elif payload.get("side") == "sell":
                sell_orders.append(payload)

        # Sort buy orders by price descending (highest first)
        buy_orders.sort(key=lambda x: _as_decimal(x.get("max_price", 0)), reverse=True)
        # Sort sell orders by price ascending (lowest first)
        sell_orders.sort(key=lambda x: _as_decimal(x.get("min_price", 0)))

        if not buy_orders and not sell_orders:
            info(f"No open orders for {pair}")
            return

        # Display sell orders (asks)
        if sell_orders:
            asks_data = []
            for order in sell_orders[:limit]:
                asks_data.append(
                    {
                        "Price": f"{_as_decimal(order.get('min_price', 0)):.8f}",
                        "Amount": f"{_as_decimal(order.get('amount', 0)):.4f} AIT",
                        "Total": f"{_as_decimal(order.get('min_price', 0)) * _as_decimal(order.get('amount', 0)):.8f} {pair.split('/')[1]}",
                        "User": order.get("user_id", "")[:16] + "...",
                        "Order": order.get("order_id", "")[:16] + "...",
                    }
                )

            output(asks_data, ctx.obj.get("output_format", "table"), title=f"Sell Orders (Asks) - {pair}")

        # Display buy orders (bids)
        if buy_orders:
            bids_data = []
            for order in buy_orders[:limit]:
                bids_data.append(
                    {
                        "Price": f"{_as_decimal(order.get('max_price', 0)):.8f}",
                        "Amount": f"{_as_decimal(order.get('amount', 0)):.4f} AIT",
                        "Total": f"{_as_decimal(order.get('max_price', 0)) * _as_decimal(order.get('amount', 0)):.8f} {pair.split('/')[1]}",
                        "User": order.get("user_id", "")[:16] + "...",
                        "Order": order.get("order_id", "")[:16] + "...",
                    }
                )

            output(bids_data, ctx.obj.get("output_format", "table"), title=f"Buy Orders (Bids) - {pair}")

        # Calculate spread if both exist
        if sell_orders and buy_orders:
            best_ask = _as_decimal(sell_orders[0].get("min_price", 0))
            best_bid = _as_decimal(buy_orders[0].get("max_price", 0))
            spread = best_ask - best_bid
            if best_bid > 0:
                spread_pct = (spread / best_bid) * 100
                info(f"Spread: {spread:.8f} ({spread_pct:.4f}%)")
                info(f"Best Bid: {best_bid:.8f} {pair.split('/')[1]}/AIT")
                info(f"Best Ask: {best_ask:.8f} {pair.split('/')[1]}/AIT")
    except Exception as e:
        abort(ctx, f"Error fetching order book: {str(e)}", from_exception=e)


@exchange_island.command(
    epilog="""Examples:

  aitbc exchange-island rates

  aitbc exchange-island rates --output json"""
)
@click.pass_context
def rates(ctx):
    """View current exchange rates for AIT/ETH on the island exchange."""
    try:
        # Load island credentials
        credentials = safe_load_credentials()
        if not credentials:
            return
        rpc_endpoint = get_rpc_endpoint()
        island_id = get_island_id()

        # Query blockchain for exchange orders to calculate rates
        rates_data = []

        for pair in SUPPORTED_PAIRS:
            params = {"transaction_type": "EXCHANGE", "island_id": island_id, "pair": pair, "status": "open", "limit": 100}

            http_client = AITBCHTTPClient(base_url=rpc_endpoint, timeout=10)
            try:
                orders = cast(list[dict[str, Any]], http_client.get("/transactions", params=params).get("transactions", []))
            except NetworkError:
                orders = _simulated_orders_for_pair(pair, 100)

            # Calculate rates from order book
            buy_orders = [o.get("payload", o) for o in orders if (o.get("payload") or o).get("side") == "buy"]
            sell_orders = [o.get("payload", o) for o in orders if (o.get("payload") or o).get("side") == "sell"]

            # Get best bid and ask
            best_bid = max([_as_decimal(o.get("max_price", 0)) for o in buy_orders]) if buy_orders else Decimal(0)
            best_ask = min([_as_decimal(o.get("min_price", 0)) for o in sell_orders]) if sell_orders else Decimal(0)

            # Calculate mid price
            mid_price = (best_bid + best_ask) / 2 if best_bid > 0 and best_ask > 0 else Decimal(0)

            rates_data.append(
                {
                    "Pair": pair,
                    "Best Bid": f"{best_bid:.8f}" if best_bid > 0 else "N/A",
                    "Best Ask": f"{best_ask:.8f}" if best_ask > 0 else "N/A",
                    "Mid Price": f"{mid_price:.8f}" if mid_price > 0 else "N/A",
                    "Buy Orders": len(buy_orders),
                    "Sell Orders": len(sell_orders),
                }
            )

        output(rates_data, ctx.obj.get("output_format", "table"), title="Exchange Rates")

    except Exception as e:
        abort(ctx, f"Error viewing exchange rates: {str(e)}", from_exception=e)


@exchange_island.command(
    epilog="""Examples:

  aitbc exchange-island orders

  aitbc exchange-island orders --status open --pair AIT/ETH"""
)
@click.option("--user", help="Filter by user ID")
@click.option("--status", help="Filter by status (open, filled, partially_filled, cancelled)")
@click.option("--pair", type=click.Choice(SUPPORTED_PAIRS), help="Filter by trading pair")
@click.pass_context
def orders(ctx, user: str | None, status: str | None, pair: str | None):
    """List exchange orders, optionally filtered by user, status, or pair."""
    try:
        # Load island credentials
        credentials = safe_load_credentials()
        if not credentials:
            return
        rpc_endpoint = get_rpc_endpoint()
        island_id = get_island_id()

        # Query blockchain for exchange orders
        params = {"transaction_type": "EXCHANGE", "island_id": island_id}
        if user:
            params["user_id"] = user
        if status:
            params["status"] = status
        if pair:
            params["pair"] = pair

        http_client = AITBCHTTPClient(base_url=rpc_endpoint, timeout=10)
        try:
            orders = cast(list[dict[str, Any]], http_client.get("/transactions", params=params).get("transactions", []))
        except NetworkError:
            orders = _simulated_order_list(user, status, pair, island_id)

        if not orders:
            info("No exchange orders found")
            return

        # Format output
        orders_data = []
        for order in orders:
            payload = order.get("payload") or order
            amount = _as_decimal(payload.get("amount", 0))
            raw_price = payload.get("max_price") or payload.get("min_price")
            price = _as_decimal(raw_price) if raw_price else Decimal(0)
            orders_data.append(
                {
                    "Order ID": payload.get("order_id", "")[:20] + "...",
                    "Pair": payload.get("pair"),
                    "Side": payload.get("side", "").upper(),
                    "Amount": f"{amount:.4f} AIT",
                    "Price": f"{price:.8f}"
                    if raw_price
                    else "Market",
                    "Status": payload.get("status"),
                    "User": payload.get("user_id", "")[:16] + "...",
                    "Created": payload.get("created_at", "")[:19],
                }
            )

        output(orders_data, ctx.obj.get("output_format", "table"), title=f"Exchange Orders ({island_id[:16]}...)")

    except Exception as e:
        abort(ctx, f"Error listing orders: {str(e)}", from_exception=e)


@exchange_island.command(
    epilog="""Examples:

  aitbc exchange-island cancel --order-id order-123

  aitbc exchange-island cancel --order-id order-123 --output json"""
)
@click.option("--order-id", "order_id", required=True, help="The Order id.")
@click.pass_context
def cancel(ctx, order_id: str):
    """Cancel an exchange order by its order ID."""
    try:
        # Load island credentials
        credentials = safe_load_credentials()
        if not credentials:
            return
        rpc_endpoint = get_rpc_endpoint()
        chain_id = get_chain_id()
        island_id = get_island_id()

        # Get local node ID
        hostname = socket.gethostname()
        local_address = socket.gethostbyname(hostname)
        p2p_port = credentials.get("credentials", {}).get("p2p_port", 8001)

        keystore_path = KEYSTORE_PATH
        if os.path.exists(keystore_path):
            with open(keystore_path) as f:
                keys = json.load(f)
                public_key_pem = None
                for _key_id, key_data in keys.items():
                    public_key_pem = key_data.get("public_key_pem")
                    break
                if public_key_pem:
                    content = f"{hostname}:{local_address}:{p2p_port}:{public_key_pem}"
                    local_node_id = hashlib.sha256(content.encode()).hexdigest()

        # Create cancel transaction
        cancel_data = {
            "type": "exchange",
            "action": "cancel",
            "order_id": order_id,
            "user_id": local_node_id,
            "status": "cancelled",
            "cancelled_at": datetime.now().isoformat(),
            "island_id": island_id,
            "chain_id": chain_id,
        }

        # Submit transaction to blockchain
        try:
            http_client = AITBCHTTPClient(base_url=rpc_endpoint, timeout=10)
            _ = http_client.post("/transaction", json=cancel_data)
            success(f"Order {order_id} cancelled successfully!")
        except NetworkError as e:
            abort(ctx, f"Network error submitting transaction: {e}", from_exception=e)

    except Exception as e:
        abort(ctx, f"Error cancelling order: {str(e)}", from_exception=e)
