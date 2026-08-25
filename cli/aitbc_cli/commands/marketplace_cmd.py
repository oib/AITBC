"""Legacy global on-chain marketplace commands for AITBC CLI.

Prefer `aitbc market` for GPU/software offers (miner-published, coordinator-backed).
"""

import asyncio
import builtins

import json
from datetime import datetime
from decimal import Decimal
from typing import Any

import click

from ..config import get_config
from ..core.config import load_multichain_config
from ..core.marketplace import ChainType, GlobalChainMarketplace
from ..utils import DECIMAL, error, output, success
from ..utils.error_handling import abort
from ..utils.http_client import AITBCHTTPClient, NetworkError, get_logger

logger = get_logger(__name__)


def _marketplace_client() -> AITBCHTTPClient:
    """Return a HTTP client configured for the marketplace service."""
    config = get_config()
    return AITBCHTTPClient(base_url=config.marketplace_service_url, timeout=10)


@click.group()
@click.option("--chain-id", help="Chain ID for multichain operations (e.g., ait-mainnet, ait-devnet)")
@click.pass_context
def marketplace(ctx, chain_id: str | None):
    """Global chain marketplace commands (cross-chain offers, bridge, on-chain listings).

    For GPU/software offers published by shop miners, use `aitbc market` instead.
    """
    ctx.ensure_object(dict)

    # Handle chain_id with auto-detection
    from ..utils.chain_id import get_chain_id

    config = load_multichain_config()
    default_rpc_url = config.blockchain_rpc_url if hasattr(config, "blockchain_rpc_url") else "http://localhost:8202"
    ctx.obj["chain_id"] = get_chain_id(default_rpc_url, override=chain_id)


@marketplace.command()
@click.argument("chain_id")
@click.argument("chain_name")
@click.argument("chain_type")
@click.argument("description")
@click.argument("seller_id")
@click.argument("price")
@click.option("--currency", default="ETH", help="Currency for pricing")
@click.option("--specs", help="Chain specifications (JSON string)")
@click.option("--metadata", help="Additional metadata (JSON string)")
@click.pass_context
def list(ctx, chain_id, chain_name, chain_type, description, seller_id, price, currency, specs, metadata):
    """List a chain for sale in the marketplace"""
    try:
        # Parse chain type
        try:
            _ = ChainType(chain_type)
        except ValueError:
            error(f"Invalid chain type: {chain_type}")
            abort(ctx, f"Valid types: {[t.value for t in ChainType]}")
        # Parse price
        try:
            price_dec = Decimal(price)
        except (ValueError, TypeError):
            abort(ctx, "Invalid price format")
        # Parse specifications
        chain_specs = {}
        if specs:
            try:
                chain_specs = json.loads(specs)
            except json.JSONDecodeError:
                abort(ctx, "Invalid JSON specifications")
        # Parse metadata
        metadata_dict = {}
        if metadata:
            try:
                metadata_dict = json.loads(metadata)
            except json.JSONDecodeError:
                abort(ctx, "Invalid JSON metadata")

        listing_id = f"chain_listing_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        attributes = {
            "listing_id": listing_id,
            "chain_name": chain_name,
            "chain_type": chain_type,
            "description": description,
            "seller_id": seller_id,
            "currency": currency,
            "specs": chain_specs,
            "metadata": metadata_dict,
        }

        offer_data = {
            "provider": seller_id,
            "capacity": 1,
            "price": str(price_dec),
            "price_per_hour": str(price_dec),
            "sla": description,
            "status": "available",
            "attributes": attributes,
            "chain_id": chain_id,
            "region": metadata_dict.get("region") or "unknown",
            "gpu_model": chain_specs.get("gpu_model"),
            "gpu_count": chain_specs.get("gpu_count") or 1,
            "gpu_memory_gb": chain_specs.get("vram_gb") or chain_specs.get("gpu_memory_gb"),
        }

        http_client = _marketplace_client()
        resp = http_client.post("/v1/marketplace/offers", json=offer_data)
        result = resp.json() if hasattr(resp, "json") else resp
        offer_id = result.get("id", listing_id)
        success(f"Chain listed successfully! Listing ID: {offer_id}")

        listing_info = {
            "Listing ID": offer_id,
            "Chain ID": chain_id,
            "Chain Name": chain_name,
            "Type": chain_type,
            "Price": f"{price} {currency}",
            "Seller": seller_id,
            "Status": "available",
            "Created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        output(listing_info, ctx.obj.get("output_format", "table"))
    except NetworkError as e:
        abort(ctx, f"Network error: {e}")
    except Exception as e:
        abort(ctx, f"Error creating listing: {e}", from_exception=e)


@marketplace.command()
@click.argument("listing_id")
@click.argument("buyer_id")
@click.option("--payment", default="crypto", help="Payment method")
@click.pass_context
def buy(ctx, listing_id, buyer_id, payment):
    """Purchase a chain from the marketplace"""
    try:
        http_client = _marketplace_client()
        booking_data = {
            "wallet": buyer_id,
            "buyer": buyer_id,
            "duration_hours": 1.0,
        }
        resp = http_client.post(f"/v1/marketplace/offers/{listing_id}/book", json=booking_data)
        result = resp.json() if hasattr(resp, "json") else resp
        bid_id = result.get("bid_id")
        if not bid_id:
            abort(ctx, f"Failed to purchase listing: {result.get('error', 'unknown error')}")

        success(f"Purchase initiated! Transaction ID: {bid_id}")

        transaction_data = {
            "Transaction ID": bid_id,
            "Listing ID": listing_id,
            "Buyer": buyer_id,
            "Payment Method": payment,
            "Status": "pending",
            "Created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        output(transaction_data, ctx.obj.get("output_format", "table"))
    except NetworkError as e:
        abort(ctx, f"Network error: {e}")
    except Exception as e:
        abort(ctx, f"Error purchasing chain: {e}", from_exception=e)


@marketplace.command()
@click.argument("transaction_id")
@click.argument("transaction_hash")
@click.pass_context
def complete(ctx, transaction_id, transaction_hash):
    """Complete a marketplace transaction"""
    try:
        http_client = _marketplace_client()
        resp = http_client.post(
            f"/v1/marketplace/bids/{transaction_id}/complete",
            json={"tx_hash": transaction_hash},
        )
        result = resp.json() if hasattr(resp, "json") else resp
        if result.get("status") == "completed":
            success(f"Transaction {transaction_id} completed successfully!")

            transaction_data = {
                "Transaction ID": transaction_id,
                "Transaction Hash": transaction_hash,
                "Status": "completed",
                "Completed": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

            output(transaction_data, ctx.obj.get("output_format", "table"))
        else:
            abort(ctx, f"Failed to complete transaction {transaction_id}: {result.get('error', 'unknown')}")
    except NetworkError as e:
        abort(ctx, f"Network error: {e}")
    except Exception as e:
        abort(ctx, f"Error completing transaction: {e}", from_exception=e)


@marketplace.command()
@click.option("--type", help="Filter by chain type")
@click.option("--min-price", help="Minimum price")
@click.option("--max-price", help="Maximum price")
@click.option("--seller", help="Filter by seller ID")
@click.option("--status", help="Filter by listing status")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def search(ctx, type, min_price, max_price, seller, status, format):
    """Search chain listings in the marketplace"""
    try:
        if type:
            try:
                _ = ChainType(type)
            except ValueError:
                abort(ctx, f"Invalid chain type: {type}")
        min_price_dec = None
        if min_price:
            try:
                min_price_dec = Decimal(min_price)
            except (ValueError, TypeError):
                abort(ctx, "Invalid minimum price format")
        max_price_dec = None
        if max_price:
            try:
                max_price_dec = Decimal(max_price)
            except (ValueError, TypeError):
                abort(ctx, "Invalid maximum price format")

        http_client = _marketplace_client()
        params: dict[str, Any] = {}
        if status:
            # Scenario uses "active"; the marketplace service uses "available"
            params["status"] = "available" if status.lower() == "active" else status
        if seller:
            params["provider"] = seller
        resp = http_client.get("/v1/marketplace/offers", params=params)
        offers = resp.json() if hasattr(resp, "json") else resp
        if not isinstance(offers, builtins.list):
            offers = []

        # Client-side filters for scenario fields stored in attributes
        filtered = []
        for offer in offers:
            attrs = offer.get("attributes") or {}
            price = Decimal(str(offer.get("price") or 0))
            if min_price_dec and price < min_price_dec:
                continue
            if max_price_dec and price > max_price_dec:
                continue
            if type and attrs.get("chain_type") != type:
                continue
            if seller and offer.get("provider") != seller:
                continue
            filtered.append(offer)

        if not filtered:
            output("No listings found matching your criteria", ctx.obj.get("output_format", "table"))
            return

        listing_data = [
            {
                "Listing ID": offer.get("id"),
                "Chain ID": offer.get("chain_id"),
                "Chain Name": (offer.get("attributes") or {}).get("chain_name", ""),
                "Type": (offer.get("attributes") or {}).get("chain_type", ""),
                "Price": f"{offer.get('price')} {(offer.get('attributes') or {}).get('currency', 'ETH')}",
                "Seller": offer.get("provider"),
                "Status": offer.get("status"),
                "Created": offer.get("created_at"),
            }
            for offer in filtered
        ]

        output(listing_data, ctx.obj.get("output_format", format), title="Marketplace Listings")
    except NetworkError as e:
        abort(ctx, f"Network error: {e}")
    except Exception as e:
        abort(ctx, f"Error searching listings: {e}", from_exception=e)


@marketplace.command()
@click.argument("chain_id")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def economy(ctx, chain_id, format):
    """Get economic metrics for a specific chain"""
    try:
        config = load_multichain_config()
        marketplace = GlobalChainMarketplace(config)

        # Get chain economy
        economy = asyncio.run(marketplace.get_chain_economy(chain_id))

        if not economy:
            abort(ctx, f"No economic data available for chain {chain_id}")

        # Format output
        if economy is None:
            raise ValueError("No economic data available")
        economy_data = [
            {"Metric": "Chain ID", "Value": economy.chain_id},
            {"Metric": "Total Value Locked", "Value": f"{economy.total_value_locked} ETH"},
            {"Metric": "Daily Volume", "Value": f"{economy.daily_volume} ETH"},
            {"Metric": "Market Cap", "Value": f"{economy.market_cap} ETH"},
            {"Metric": "Transaction Count", "Value": economy.transaction_count},
            {"Metric": "Active Users", "Value": economy.active_users},
            {"Metric": "Agent Count", "Value": economy.agent_count},
            {"Metric": "Governance Tokens", "Value": f"{economy.governance_tokens}"},
            {"Metric": "Staking Rewards", "Value": f"{economy.staking_rewards}"},
            {"Metric": "Last Updated", "Value": economy.last_updated.strftime("%Y-%m-%d %H:%M:%S")},
        ]

        output(economy_data, ctx.obj.get("output_format", format), title=f"Chain Economy: {chain_id}")

    except Exception as e:
        abort(ctx, f"Error getting chain economy: {str(e)}", from_exception=e)


@marketplace.command()
@click.argument("user_id")
@click.option("--role", type=click.Choice(["buyer", "seller", "both"]), default="both", help="User role")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def transactions(ctx, user_id, role, format):
    """Get transactions for a specific user"""
    try:
        config = load_multichain_config()
        marketplace = GlobalChainMarketplace(config)

        # Get user transactions
        transactions = asyncio.run(marketplace.get_user_transactions(user_id, role))

        if not transactions:
            output(f"No transactions found for user {user_id}", ctx.obj.get("output_format", "table"))
            return

        # Format output
        transaction_data = [
            {
                "Transaction ID": transaction.transaction_id,
                "Listing ID": transaction.listing_id,
                "Chain ID": transaction.chain_id,
                "Price": f"{transaction.price} {transaction.currency}",
                "Role": "buyer" if transaction.buyer_id == user_id else "seller",
                "Counterparty": transaction.seller_id if transaction.buyer_id == user_id else transaction.buyer_id,
                "Status": transaction.status.value,
                "Created": transaction.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "Completed": transaction.completed_at.strftime("%Y-%m-%d %H:%M:%S") if transaction.completed_at else "N/A",
            }
            for transaction in transactions
        ]

        output(transaction_data, ctx.obj.get("output_format", format), title=f"Transactions for {user_id}")

    except Exception as e:
        abort(ctx, f"Error getting user transactions: {str(e)}", from_exception=e)


@marketplace.command()
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def overview(ctx, format):
    """Get comprehensive marketplace overview"""
    try:
        config = load_multichain_config()
        marketplace = GlobalChainMarketplace(config)

        # Get marketplace overview
        overview = asyncio.run(marketplace.get_marketplace_overview())

        if not overview:
            abort(ctx, "No marketplace data available")

        # Marketplace metrics
        if "marketplace_metrics" in overview:
            metrics = overview["marketplace_metrics"]
            metrics_data = [
                {"Metric": "Total Listings", "Value": metrics["total_listings"]},
                {"Metric": "Active Listings", "Value": metrics["active_listings"]},
                {"Metric": "Total Transactions", "Value": metrics["total_transactions"]},
                {"Metric": "Total Volume", "Value": f"{metrics['total_volume']} ETH"},
                {"Metric": "Average Price", "Value": f"{metrics['average_price']} ETH"},
                {"Metric": "Market Sentiment", "Value": f"{metrics['market_sentiment']:.2f}"},
            ]

            output(metrics_data, ctx.obj.get("output_format", format), title="Marketplace Metrics")

        # Volume 24h
        if "volume_24h" in overview:
            volume_data = [{"Metric": "24h Volume", "Value": f"{overview['volume_24h']} ETH"}]

            output(volume_data, ctx.obj.get("output_format", format), title="24-Hour Volume")

        # Top performing chains
        if "top_performing_chains" in overview:
            chains = overview["top_performing_chains"]
            if chains:
                chain_data = [
                    {"Chain ID": chain["chain_id"], "Volume": f"{chain['volume']} ETH", "Transactions": chain["transactions"]}
                    for chain in chains[:5]  # Top 5
                ]

                output(chain_data, ctx.obj.get("output_format", format), title="Top Performing Chains")

        # Chain types distribution
        if "chain_types_distribution" in overview:
            distribution = overview["chain_types_distribution"]
            if distribution:
                dist_data = [{"Chain Type": chain_type, "Count": count} for chain_type, count in distribution.items()]

                output(dist_data, ctx.obj.get("output_format", format), title="Chain Types Distribution")

        # User activity
        if "user_activity" in overview:
            activity = overview["user_activity"]
            activity_data = [
                {"Metric": "Active Buyers (7d)", "Value": activity["active_buyers_7d"]},
                {"Metric": "Active Sellers (7d)", "Value": activity["active_sellers_7d"]},
                {"Metric": "Total Unique Users", "Value": activity["total_unique_users"]},
                {"Metric": "Average Reputation", "Value": f"{activity['average_reputation']:.3f}"},
            ]

            output(activity_data, ctx.obj.get("output_format", format), title="User Activity")

        # Escrow summary
        if "escrow_summary" in overview:
            escrow = overview["escrow_summary"]
            escrow_data = [
                {"Metric": "Active Escrows", "Value": escrow["active_escrows"]},
                {"Metric": "Released Escrows", "Value": escrow["released_escrows"]},
                {"Metric": "Total Escrow Value", "Value": f"{escrow['total_escrow_value']} ETH"},
                {"Metric": "Escrow Fees Collected", "Value": f"{escrow['escrow_fee_collected']} ETH"},
            ]

            output(escrow_data, ctx.obj.get("output_format", format), title="Escrow Summary")

    except Exception as e:
        abort(ctx, f"Error getting marketplace overview: {str(e)}", from_exception=e)


@marketplace.command()
@click.option("--realtime", is_flag=True, help="Real-time monitoring")
@click.option("--interval", default=30, help="Update interval in seconds")
@click.pass_context
def monitor(ctx, realtime, interval):
    """Monitor marketplace activity"""
    try:
        config = load_multichain_config()
        marketplace = GlobalChainMarketplace(config)

        if realtime:
            # Real-time monitoring
            import time

            from rich.console import Console
            from rich.live import Live
            from rich.table import Table

            console = Console()

            def generate_monitor_table():
                try:
                    overview = asyncio.run(marketplace.get_marketplace_overview())

                    table = Table(title=f"Marketplace Monitor - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                    table.add_column("Metric", style="cyan")
                    table.add_column("Value", style="green")

                    if "marketplace_metrics" in overview:
                        metrics = overview["marketplace_metrics"]
                        table.add_row("Total Listings", str(metrics["total_listings"]))
                        table.add_row("Active Listings", str(metrics["active_listings"]))
                        table.add_row("Total Transactions", str(metrics["total_transactions"]))
                        table.add_row("Total Volume", f"{metrics['total_volume']} ETH")
                        table.add_row("Market Sentiment", f"{metrics['market_sentiment']:.2f}")

                    if "volume_24h" in overview:
                        table.add_row("24h Volume", f"{overview['volume_24h']} ETH")

                    if "user_activity" in overview:
                        activity = overview["user_activity"]
                        table.add_row("Active Users (7d)", str(activity["active_buyers_7d"] + activity["active_sellers_7d"]))

                    return table
                except Exception as e:
                    logger.warning("Error getting marketplace data: %s", e, exc_info=True)
                    return f"Error getting marketplace data: {e}"

            with Live(generate_monitor_table(), refresh_per_second=1) as live:
                try:
                    while True:
                        live.update(generate_monitor_table())
                        time.sleep(interval)
                except KeyboardInterrupt:
                    console.print("\n[yellow]Monitoring stopped by user[/yellow]")
        else:
            # Single snapshot
            overview = asyncio.run(marketplace.get_marketplace_overview())

            monitor_data = []

            if "marketplace_metrics" in overview:
                metrics = overview["marketplace_metrics"]
                monitor_data.extend(
                    [
                        {"Metric": "Total Listings", "Value": metrics["total_listings"]},
                        {"Metric": "Active Listings", "Value": metrics["active_listings"]},
                        {"Metric": "Total Transactions", "Value": metrics["total_transactions"]},
                        {"Metric": "Total Volume", "Value": f"{metrics['total_volume']} ETH"},
                        {"Metric": "Market Sentiment", "Value": f"{metrics['market_sentiment']:.2f}"},
                    ]
                )

            if "volume_24h" in overview:
                monitor_data.append({"Metric": "24h Volume", "Value": f"{overview['volume_24h']} ETH"})

            if "user_activity" in overview:
                activity = overview["user_activity"]
                monitor_data.append(
                    {"Metric": "Active Users (7d)", "Value": activity["active_buyers_7d"] + activity["active_sellers_7d"]}
                )

            output(monitor_data, ctx.obj.get("output_format", "table"), title="Marketplace Monitor")

    except Exception as e:
        abort(ctx, f"Error during monitoring: {str(e)}", from_exception=e)


@marketplace.command()
@click.argument("price", type=DECIMAL)
@click.argument("quantity", type=float)
@click.option("--market", help="Market identifier")
@click.pass_context
def bid(ctx, price: Decimal, quantity: float, market: str | None):
    """Place a bid in the marketplace"""
    config = get_config()

    try:
        http_client = AITBCHTTPClient(base_url=config.marketplace_service_url, timeout=10)
        bid_data = {"price": str(price), "quantity": quantity, "market": market or "default"}
        result = http_client.post("/marketplace/bid", json=bid_data)
        success(f"Bid placed: {quantity} @ {price}")
        output(result, ctx.obj.get("output_format", "table"))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error placing bid: {e}")


@marketplace.command()
@click.option("--market", help="Filter by market")
@click.option("--limit", type=int, default=20, help="Number of bids to return")
@click.pass_context
def bids(ctx, market: str | None, limit: int):
    """List bids from the marketplace"""
    config = get_config()

    try:
        http_client = AITBCHTTPClient(base_url=config.marketplace_service_url, timeout=10)
        params: dict[str, str | int] = {"limit": limit}
        if market:
            params["market"] = market

        bids_data = http_client.get("/marketplace/bids", params=params)
        success("Bids:")
        output(bids_data, ctx.obj.get("output_format", "table"))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error fetching bids: {e}")


@marketplace.command()
@click.argument("price", type=float)
@click.argument("quantity", type=float)
@click.option("--market", help="Market identifier")
@click.pass_context
def ask(ctx, price: Decimal, quantity: float, market: str | None):
    """Place an ask in the marketplace"""
    config = get_config()

    try:
        http_client = AITBCHTTPClient(base_url=config.marketplace_service_url, timeout=10)
        ask_data = {"price": str(price), "quantity": quantity, "market": market or "default"}
        result = http_client.post("/marketplace/ask", json=ask_data)
        success(f"Ask placed: {quantity} @ {price}")
        output(result, ctx.obj.get("output_format", "table"))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error placing ask: {e}")


@marketplace.command()
@click.option("--market", help="Filter by market")
@click.option("--limit", type=int, default=20, help="Number of asks to return")
@click.pass_context
def asks(ctx, market: str | None, limit: int):
    """List asks from the marketplace"""
    config = get_config()

    try:
        http_client = AITBCHTTPClient(base_url=config.marketplace_service_url, timeout=10)
        params: dict[str, str | int] = {"limit": limit}
        if market:
            params["market"] = market

        asks_data = http_client.get("/marketplace/asks", params=params)
        success("Asks:")
        output(asks_data, ctx.obj.get("output_format", "table"))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error fetching asks: {e}")


marketplace.add_command(list, name="create")
