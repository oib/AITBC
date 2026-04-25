"""Global chain marketplace commands for AITBC CLI"""

import click
import asyncio
import json
from decimal import Decimal
from datetime import datetime
from typing import Optional
from ..core.config import load_multichain_config
from ..core.marketplace import (
    GlobalChainMarketplace, ChainType, MarketplaceStatus, 
    TransactionStatus
)
from ..utils import output, error, success

@click.group()
@click.option("--chain-id", help="Chain ID for multichain operations (e.g., ait-mainnet, ait-devnet)")
@click.pass_context
def marketplace(ctx, chain_id: Optional[str]):
    """Global chain marketplace commands"""
    ctx.ensure_object(dict)
    
    # Handle chain_id with auto-detection
    from ..utils.chain_id import get_chain_id
    config = load_multichain_config()
    default_rpc_url = config.blockchain_rpc_url if hasattr(config, 'blockchain_rpc_url') else 'http://localhost:8006'
    ctx.obj['chain_id'] = get_chain_id(default_rpc_url, override=chain_id)

@marketplace.command()
@click.argument('chain_id')
@click.argument('chain_name')
@click.argument('chain_type')
@click.argument('description')
@click.argument('seller_id')
@click.argument('price')
@click.option('--currency', default='ETH', help='Currency for pricing')
@click.option('--specs', help='Chain specifications (JSON string)')
@click.option('--metadata', help='Additional metadata (JSON string)')
@click.pass_context
def list(ctx, chain_id, chain_name, chain_type, description, seller_id, price, currency, specs, metadata):
    """List a chain for sale in the marketplace"""
    try:
        config = load_multichain_config()
        marketplace = GlobalChainMarketplace(config)
        
        # Parse chain type
        try:
            chain_type_enum = ChainType(chain_type)
        except ValueError:
            error(f"Invalid chain type: {chain_type}")
            error(f"Valid types: {[t.value for t in ChainType]}")
            raise click.Abort()
        
        # Parse price
        try:
            price_decimal = Decimal(price)
        except:
            error("Invalid price format")
            raise click.Abort()
        
        # Parse specifications
        chain_specs = {}
        if specs:
            try:
                chain_specs = json.loads(specs)
            except json.JSONDecodeError:
                error("Invalid JSON specifications")
                raise click.Abort()
        
        # Parse metadata
        metadata_dict = {}
        if metadata:
            try:
                metadata_dict = json.loads(metadata)
            except json.JSONDecodeError:
                error("Invalid JSON metadata")
                raise click.Abort()
        
        # Create listing
        listing_id = asyncio.run(marketplace.create_listing(
            chain_id, chain_name, chain_type_enum, description, 
            seller_id, price_decimal, currency, chain_specs, metadata_dict
        ))
        
        if listing_id:
            success(f"Chain listed successfully! Listing ID: {listing_id}")
            
            listing_data = {
                "Listing ID": listing_id,
                "Chain ID": chain_id,
                "Chain Name": chain_name,
                "Type": chain_type,
                "Price": f"{price} {currency}",
                "Seller": seller_id,
                "Status": "active",
                "Created": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            output(listing_data, ctx.obj.get('output_format', 'table'))
        else:
            error("Failed to create listing")
            raise click.Abort()
        
    except Exception as e:
        error(f"Error creating listing: {str(e)}")
        raise click.Abort()

@marketplace.command()
@click.argument('listing_id')
@click.argument('buyer_id')
@click.option('--payment', default='crypto', help='Payment method')
@click.pass_context
def buy(ctx, listing_id, buyer_id, payment):
    """Purchase a chain from the marketplace"""
    try:
        config = load_multichain_config()
        marketplace = GlobalChainMarketplace(config)
        
        # Purchase chain
        transaction_id = asyncio.run(marketplace.purchase_chain(listing_id, buyer_id, payment))
        
        if transaction_id:
            success(f"Purchase initiated! Transaction ID: {transaction_id}")
            
            transaction_data = {
                "Transaction ID": transaction_id,
                "Listing ID": listing_id,
                "Buyer": buyer_id,
                "Payment Method": payment,
                "Status": "pending",
                "Created": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            output(transaction_data, ctx.obj.get('output_format', 'table'))
        else:
            error("Failed to purchase chain")
            raise click.Abort()
        
    except Exception as e:
        error(f"Error purchasing chain: {str(e)}")
        raise click.Abort()

@marketplace.command()
@click.argument('transaction_id')
@click.argument('transaction_hash')
@click.pass_context
def complete(ctx, transaction_id, transaction_hash):
    """Complete a marketplace transaction"""
    try:
        config = load_multichain_config()
        marketplace = GlobalChainMarketplace(config)
        
        # Complete transaction
        success = asyncio.run(marketplace.complete_transaction(transaction_id, transaction_hash))
        
        if success:
            success(f"Transaction {transaction_id} completed successfully!")
            
            transaction_data = {
                "Transaction ID": transaction_id,
                "Transaction Hash": transaction_hash,
                "Status": "completed",
                "Completed": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            output(transaction_data, ctx.obj.get('output_format', 'table'))
        else:
            error(f"Failed to complete transaction {transaction_id}")
            raise click.Abort()
        
    except Exception as e:
        error(f"Error completing transaction: {str(e)}")
        raise click.Abort()

@marketplace.command()
@click.option('--type', help='Filter by chain type')
@click.option('--min-price', help='Minimum price')
@click.option('--max-price', help='Maximum price')
@click.option('--seller', help='Filter by seller ID')
@click.option('--status', help='Filter by listing status')
@click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
@click.pass_context
def search(ctx, type, min_price, max_price, seller, status, format):
    """Search chain listings in the marketplace"""
    try:
        config = load_multichain_config()
        marketplace = GlobalChainMarketplace(config)
        
        # Parse filters
        chain_type = None
        if type:
            try:
                chain_type = ChainType(type)
            except ValueError:
                error(f"Invalid chain type: {type}")
                raise click.Abort()
        
        min_price_dec = None
        if min_price:
            try:
                min_price_dec = Decimal(min_price)
            except:
                error("Invalid minimum price format")
                raise click.Abort()
        
        max_price_dec = None
        if max_price:
            try:
                max_price_dec = Decimal(max_price)
            except:
                error("Invalid maximum price format")
                raise click.Abort()
        
        listing_status = None
        if status:
            try:
                listing_status = MarketplaceStatus(status)
            except ValueError:
                error(f"Invalid status: {status}")
                raise click.Abort()
        
        # Search listings
        listings = asyncio.run(marketplace.search_listings(
            chain_type, min_price_dec, max_price_dec, seller, listing_status
        ))
        
        if not listings:
            output("No listings found matching your criteria", ctx.obj.get('output_format', 'table'))
            return
        
        # Format output
        listing_data = [
            {
                "Listing ID": listing.listing_id,
                "Chain ID": listing.chain_id,
                "Chain Name": listing.chain_name,
                "Type": listing.chain_type.value,
                "Price": f"{listing.price} {listing.currency}",
                "Seller": listing.seller_id,
                "Status": listing.status.value,
                "Created": listing.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "Expires": listing.expires_at.strftime("%Y-%m-%d %H:%M:%S")
            }
            for listing in listings
        ]
        
        output(listing_data, ctx.obj.get('output_format', format), title="Marketplace Listings")
        
    except Exception as e:
        error(f"Error searching listings: {str(e)}")
        raise click.Abort()

@marketplace.command()
@click.argument('chain_id')
@click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
@click.pass_context
def economy(ctx, chain_id, format):
    """Get economic metrics for a specific chain"""
    try:
        config = load_multichain_config()
        marketplace = GlobalChainMarketplace(config)
        
        # Get chain economy
        economy = asyncio.run(marketplace.get_chain_economy(chain_id))
        
        if not economy:
            error(f"No economic data available for chain {chain_id}")
            raise click.Abort()
        
        # Format output
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
            {"Metric": "Last Updated", "Value": economy.last_updated.strftime("%Y-%m-%d %H:%M:%S")}
        ]
        
        output(economy_data, ctx.obj.get('output_format', format), title=f"Chain Economy: {chain_id}")
        
    except Exception as e:
        error(f"Error getting chain economy: {str(e)}")
        raise click.Abort()

@marketplace.command()
@click.argument('user_id')
@click.option('--role', type=click.Choice(['buyer', 'seller', 'both']), default='both', help='User role')
@click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
@click.pass_context
def transactions(ctx, user_id, role, format):
    """Get transactions for a specific user"""
    try:
        config = load_multichain_config()
        marketplace = GlobalChainMarketplace(config)
        
        # Get user transactions
        transactions = asyncio.run(marketplace.get_user_transactions(user_id, role))
        
        if not transactions:
            output(f"No transactions found for user {user_id}", ctx.obj.get('output_format', 'table'))
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
                "Completed": transaction.completed_at.strftime("%Y-%m-%d %H:%M:%S") if transaction.completed_at else "N/A"
            }
            for transaction in transactions
        ]
        
        output(transaction_data, ctx.obj.get('output_format', format), title=f"Transactions for {user_id}")
        
    except Exception as e:
        error(f"Error getting user transactions: {str(e)}")
        raise click.Abort()

@marketplace.command()
@click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
@click.pass_context
def overview(ctx, format):
    """Get comprehensive marketplace overview"""
    try:
        config = load_multichain_config()
        marketplace = GlobalChainMarketplace(config)
        
        # Get marketplace overview
        overview = asyncio.run(marketplace.get_marketplace_overview())
        
        if not overview:
            error("No marketplace data available")
            raise click.Abort()
        
        # Marketplace metrics
        if "marketplace_metrics" in overview:
            metrics = overview["marketplace_metrics"]
            metrics_data = [
                {"Metric": "Total Listings", "Value": metrics["total_listings"]},
                {"Metric": "Active Listings", "Value": metrics["active_listings"]},
                {"Metric": "Total Transactions", "Value": metrics["total_transactions"]},
                {"Metric": "Total Volume", "Value": f"{metrics['total_volume']} ETH"},
                {"Metric": "Average Price", "Value": f"{metrics['average_price']} ETH"},
                {"Metric": "Market Sentiment", "Value": f"{metrics['market_sentiment']:.2f}"}
            ]
            
            output(metrics_data, ctx.obj.get('output_format', format), title="Marketplace Metrics")
        
        # Volume 24h
        if "volume_24h" in overview:
            volume_data = [
                {"Metric": "24h Volume", "Value": f"{overview['volume_24h']} ETH"}
            ]
            
            output(volume_data, ctx.obj.get('output_format', format), title="24-Hour Volume")
        
        # Top performing chains
        if "top_performing_chains" in overview:
            chains = overview["top_performing_chains"]
            if chains:
                chain_data = [
                    {
                        "Chain ID": chain["chain_id"],
                        "Volume": f"{chain['volume']} ETH",
                        "Transactions": chain["transactions"]
                    }
                    for chain in chains[:5]  # Top 5
                ]
                
                output(chain_data, ctx.obj.get('output_format', format), title="Top Performing Chains")
        
        # Chain types distribution
        if "chain_types_distribution" in overview:
            distribution = overview["chain_types_distribution"]
            if distribution:
                dist_data = [
                    {"Chain Type": chain_type, "Count": count}
                    for chain_type, count in distribution.items()
                ]
                
                output(dist_data, ctx.obj.get('output_format', format), title="Chain Types Distribution")
        
        # User activity
        if "user_activity" in overview:
            activity = overview["user_activity"]
            activity_data = [
                {"Metric": "Active Buyers (7d)", "Value": activity["active_buyers_7d"]},
                {"Metric": "Active Sellers (7d)", "Value": activity["active_sellers_7d"]},
                {"Metric": "Total Unique Users", "Value": activity["total_unique_users"]},
                {"Metric": "Average Reputation", "Value": f"{activity['average_reputation']:.3f}"}
            ]
            
            output(activity_data, ctx.obj.get('output_format', format), title="User Activity")
        
        # Escrow summary
        if "escrow_summary" in overview:
            escrow = overview["escrow_summary"]
            escrow_data = [
                {"Metric": "Active Escrows", "Value": escrow["active_escrows"]},
                {"Metric": "Released Escrows", "Value": escrow["released_escrows"]},
                {"Metric": "Total Escrow Value", "Value": f"{escrow['total_escrow_value']} ETH"},
                {"Metric": "Escrow Fees Collected", "Value": f"{escrow['escrow_fee_collected']} ETH"}
            ]
            
            output(escrow_data, ctx.obj.get('output_format', format), title="Escrow Summary")
        
    except Exception as e:
        error(f"Error getting marketplace overview: {str(e)}")
        raise click.Abort()

@marketplace.command()
@click.option('--realtime', is_flag=True, help='Real-time monitoring')
@click.option('--interval', default=30, help='Update interval in seconds')
@click.pass_context
def monitor(ctx, realtime, interval):
    """Monitor marketplace activity"""
    try:
        config = load_multichain_config()
        marketplace = GlobalChainMarketplace(config)
        
        if realtime:
            # Real-time monitoring
            from rich.console import Console
            from rich.live import Live
            from rich.table import Table
            import time
            
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
                monitor_data.extend([
                    {"Metric": "Total Listings", "Value": metrics["total_listings"]},
                    {"Metric": "Active Listings", "Value": metrics["active_listings"]},
                    {"Metric": "Total Transactions", "Value": metrics["total_transactions"]},
                    {"Metric": "Total Volume", "Value": f"{metrics['total_volume']} ETH"},
                    {"Metric": "Market Sentiment", "Value": f"{metrics['market_sentiment']:.2f}"}
                ])
            
            if "volume_24h" in overview:
                monitor_data.append({"Metric": "24h Volume", "Value": f"{overview['volume_24h']} ETH"})
            
            if "user_activity" in overview:
                activity = overview["user_activity"]
                monitor_data.append({"Metric": "Active Users (7d)", "Value": activity["active_buyers_7d"] + activity["active_sellers_7d"]})
            
            output(monitor_data, ctx.obj.get('output_format', 'table'), title="Marketplace Monitor")
        
    except Exception as e:
        error(f"Error during monitoring: {str(e)}")
        raise click.Abort()
