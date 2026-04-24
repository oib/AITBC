"""Cross-chain trading commands for AITBC CLI"""

import click
import json
from typing import Optional
from tabulate import tabulate
from ..config import get_config
from ..utils import success, error, output

# Import shared modules
from aitbc.aitbc_logging import get_logger
from aitbc.http_client import AITBCHTTPClient
from aitbc.exceptions import NetworkError

# Initialize logger
logger = get_logger(__name__)


@click.group()
def cross_chain():
    """Cross-chain trading operations"""
    pass


@cross_chain.command()
@click.option("--from-chain", help="Source chain ID")
@click.option("--to-chain", help="Target chain ID")
@click.option("--from-token", help="Source token symbol")
@click.option("--to-token", help="Target token symbol")
@click.pass_context
def rates(ctx, from_chain: Optional[str], to_chain: Optional[str], 
          from_token: Optional[str], to_token: Optional[str]):
    """Get cross-chain exchange rates"""
    config = ctx.obj['config']
    
    try:
        with AITBCHTTPClient() as client:
            # Get rates from cross-chain exchange
            response = client.get(
                f"http://localhost:8001/api/v1/cross-chain/rates",
                timeout=10
            )
            
            if response.status_code == 200:
                rates_data = response.json()
                rates = rates_data.get('rates', {})
                
                if from_chain and to_chain:
                    # Get specific rate
                    pair_key = f"{from_chain}-{to_chain}"
                    if pair_key in rates:
                        success(f"Exchange rate {from_chain} → {to_chain}: {rates[pair_key]}")
                    else:
                        error(f"No rate available for {from_chain} → {to_chain}")
                else:
                    # Show all rates
                    success("Cross-chain exchange rates:")
                    rate_table = []
                    for pair, rate in rates.items():
                        chains = pair.split('-')
                        rate_table.append([chains[0], chains[1], f"{rate:.6f}"])
                    
                    if rate_table:
                        headers = ["From Chain", "To Chain", "Rate"]
                        print(tabulate(rate_table, headers=headers, tablefmt="grid"))
                    else:
                        output("No cross-chain rates available")
            else:
                error(f"Failed to get cross-chain rates: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")


@cross_chain.command()
@click.option("--from-chain", required=True, help="Source chain ID")
@click.option("--to-chain", required=True, help="Target chain ID")
@click.option("--from-token", required=True, help="Source token symbol")
@click.option("--to-token", required=True, help="Target token symbol")
@click.option("--amount", type=float, required=True, help="Amount to swap")
@click.option("--min-amount", type=float, help="Minimum amount to receive")
@click.option("--slippage", type=float, default=0.01, help="Slippage tolerance (0-0.1)")
@click.option("--address", help="User wallet address")
@click.pass_context
def swap(ctx, from_chain: str, to_chain: str, from_token: str, to_token: str,
         amount: float, min_amount: Optional[float], slippage: float, address: Optional[str]):
    """Create cross-chain swap"""
    config = ctx.obj['config']
    
    # Validate inputs
    if from_chain == to_chain:
        error("Source and target chains must be different")
        return
    
    if amount <= 0:
        error("Amount must be greater than 0")
        return
    
    # Use default address if not provided
    if not address:
        address = config.get('default_address', '0x1234567890123456789012345678901234567890')
    
    # Calculate minimum amount if not provided
    if not min_amount:
        # Get rate first
        try:
            with AITBCHTTPClient() as client:
                response = client.get(
                    f"http://localhost:8001/api/v1/cross-chain/rates",
                    timeout=10
                )
                if response.status_code == 200:
                    rates_data = response.json()
                    pair_key = f"{from_chain}-{to_chain}"
                    rate = rates_data.get('rates', {}).get(pair_key, 1.0)
                    min_amount = amount * rate * (1 - slippage) * 0.97  # Account for fees
                else:
                    min_amount = amount * 0.95  # Conservative fallback
        except:
            min_amount = amount * 0.95
    
    swap_data = {
        "from_chain": from_chain,
        "to_chain": to_chain,
        "from_token": from_token,
        "to_token": to_token,
        "amount": amount,
        "min_amount": min_amount,
        "user_address": address,
        "slippage_tolerance": slippage
    }
    
    try:
        http_client = AITBCHTTPClient(base_url="http://localhost:8001/api/v1/cross-chain", timeout=30)
        swap_result = http_client.post("/swap", json=swap_data)
        success("Cross-chain swap created successfully!")
        output({
            "Swap ID": swap_result.get('swap_id'),
            "From Chain": swap_result.get('from_chain'),
            "To Chain": swap_result.get('to_chain'),
            "Amount": swap_result.get('amount'),
            "Expected Amount": swap_result.get('expected_amount'),
            "Rate": swap_result.get('rate'),
            "Total Fees": swap_result.get('total_fees'),
            "Status": swap_result.get('status')
        }, ctx.obj['output_format'])
                
                # Show swap ID for tracking
                success(f"Track swap with: aitbc cross-chain status {swap_result.get('swap_id')}")
            else:
                error(f"Failed to create swap: {response.status_code}")
                if response.text:
                    error(f"Details: {response.text}")
    except Exception as e:
        error(f"Network error: {e}")


@cross_chain.command()
@click.argument("swap_id")
@click.pass_context
def status(ctx, swap_id: str):
    """Check cross-chain swap status"""
    try:
        http_client = AITBCHTTPClient(base_url="http://localhost:8001/api/v1", timeout=10)
        swap_data = http_client.get(f"/cross-chain/swap/{swap_id}")
        success(f"Swap Status: {swap_data.get('status', 'unknown')}")
        
        # Display swap details
        details = {
            "Swap ID": swap_data.get('swap_id'),
            "From Chain": swap_data.get('from_chain'),
            "To Chain": swap_data.get('to_chain'),
            "From Token": swap_data.get('from_token'),
            "To Token": swap_data.get('to_token'),
            "Amount": swap_data.get('amount'),
            "Expected Amount": swap_data.get('expected_amount'),
            "Actual Amount": swap_data.get('actual_amount'),
            "Status": swap_data.get('status'),
            "Created At": swap_data.get('created_at'),
            "Completed At": swap_data.get('completed_at'),
            "Bridge Fee": swap_data.get('bridge_fee'),
            "From Tx Hash": swap_data.get('from_tx_hash'),
            "To Tx Hash": swap_data.get('to_tx_hash')
        }
        
        output(details, ctx.obj['output_format'])
        
        # Show additional status info
        if swap_data.get('status') == 'completed':
            success("✅ Swap completed successfully!")
        elif swap_data.get('status') == 'failed':
            error("❌ Swap failed")
            if swap_data.get('error_message'):
                error(f"Error: {swap_data['error_message']}")
        elif swap_data.get('status') == 'pending':
            success("⏳ Swap is pending...")
        elif swap_data.get('status') == 'executing':
            success("🔄 Swap is executing...")
        elif swap_data.get('status') == 'refunded':
            success("💰 Swap was refunded")
    except NetworkError as e:
                output(details, ctx.obj['output_format'])
                
                # Show additional status info
                if swap_data.get('status') == 'completed':
                    success("✅ Swap completed successfully!")
                elif swap_data.get('status') == 'failed':
                    error("❌ Swap failed")
                    if swap_data.get('error_message'):
                        error(f"Error: {swap_data['error_message']}")
                elif swap_data.get('status') == 'pending':
                    success("⏳ Swap is pending...")
                elif swap_data.get('status') == 'executing':
                    success("🔄 Swap is executing...")
                elif swap_data.get('status') == 'refunded':
                    success("💰 Swap was refunded")
            else:
                error(f"Failed to get swap status: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")


@cross_chain.command()
@click.option("--user-address", help="Filter by user address")
@click.option("--status", help="Filter by status")
@click.option("--limit", type=int, default=10, help="Number of swaps to show")
@click.pass_context
def swaps(ctx, user_address: Optional[str], status: Optional[str], limit: int):
    """List cross-chain swaps"""
    params = {}
    if user_address:
        params['user_address'] = user_address
    if status:
        params['status'] = status
    
    try:
        http_client = AITBCHTTPClient(base_url="http://localhost:8001/api/v1", timeout=10)
        swaps_data = http_client.get("/cross-chain/swaps", params=params)
        swaps = swaps_data.get('swaps', [])
        
        if swaps:
            success(f"Found {len(swaps)} cross-chain swaps:")
                    
                    # Create table
                    swap_table = []
                    for swap in swaps[:limit]:
                        swap_table.append([
                            swap.get('swap_id', '')[:8] + '...',
                            swap.get('from_chain', ''),
                            swap.get('to_chain', ''),
                            swap.get('amount', 0),
                            swap.get('status', ''),
                            swap.get('created_at', '')[:19]
                        ])
                    
                    table(["ID", "From", "To", "Amount", "Status", "Created"], swap_table)
                    
                    if len(swaps) > limit:
                        success(f"Showing {limit} of {len(swaps)} total swaps")
                else:
                    success("No cross-chain swaps found")
            else:
                error(f"Failed to get swaps: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")


@cross_chain.command()
@click.option("--source-chain", required=True, help="Source chain ID")
@click.option("--target-chain", required=True, help="Target chain ID")
@click.option("--token", required=True, help="Token to bridge")
@click.option("--amount", type=float, required=True, help="Amount to bridge")
@click.option("--recipient", help="Recipient address")
@click.pass_context
def bridge(ctx, source_chain: str, target_chain: str, token: str, 
           amount: float, recipient: Optional[str]):
    """Create cross-chain bridge transaction"""
    config = ctx.obj['config']
    
    # Validate inputs
    if source_chain == target_chain:
        error("Source and target chains must be different")
        return
    
    if amount <= 0:
        error("Amount must be greater than 0")
        return
    
    # Use default recipient if not provided
    if not recipient:
        recipient = config.get('default_address', '0x1234567890123456789012345678901234567890')
    
    bridge_data = {
        "source_chain": source_chain,
        "target_chain": target_chain,
        "token": token,
        "amount": amount,
        "recipient_address": recipient
    }
    
    try:
        http_client = AITBCHTTPClient(base_url="http://localhost:8001/api/v1", timeout=30)
        bridge_result = http_client.post("/cross-chain/bridge", json=bridge_data)
        success("Cross-chain bridge created successfully!")
        output({
            "Bridge ID": bridge_result.get('bridge_id'),
            "Source Chain": bridge_result.get('source_chain'),
            "Target Chain": bridge_result.get('target_chain'),
            "Token": bridge_result.get('token'),
            "Amount": bridge_result.get('amount'),
            "Bridge Fee": bridge_result.get('bridge_fee'),
                    "Status": bridge_result.get('status')
                }, ctx.obj['output_format'])
                
                # Show bridge ID for tracking
                success(f"Track bridge with: aitbc cross-chain bridge-status {bridge_result.get('bridge_id')}")
            else:
                error(f"Failed to create bridge: {response.status_code}")
                if response.text:
                    error(f"Details: {response.text}")
    except Exception as e:
        error(f"Network error: {e}")


@cross_chain.command()
@click.argument("bridge_id")
@click.pass_context
def bridge_status(ctx, bridge_id: str):
    """Check cross-chain bridge status"""
    try:
        http_client = AITBCHTTPClient(base_url="http://localhost:8001/api/v1", timeout=10)
        bridge_data = http_client.get(f"/cross-chain/bridge/{bridge_id}")
        success(f"Bridge Status: {bridge_data.get('status', 'unknown')}")
                
                # Display bridge details
                details = {
                    "Bridge ID": bridge_data.get('bridge_id'),
                    "Source Chain": bridge_data.get('source_chain'),
                    "Target Chain": bridge_data.get('target_chain'),
                    "Token": bridge_data.get('token'),
                    "Amount": bridge_data.get('amount'),
                    "Recipient Address": bridge_data.get('recipient_address'),
                    "Status": bridge_data.get('status'),
                    "Created At": bridge_data.get('created_at'),
                    "Completed At": bridge_data.get('completed_at'),
                    "Bridge Fee": bridge_data.get('bridge_fee'),
                    "Source Tx Hash": bridge_data.get('source_tx_hash'),
                    "Target Tx Hash": bridge_data.get('target_tx_hash')
                }
                
                output(details, ctx.obj['output_format'])
                
                # Show additional status info
                if bridge_data.get('status') == 'completed':
                    success("✅ Bridge completed successfully!")
                elif bridge_data.get('status') == 'failed':
                    error("❌ Bridge failed")
                    if bridge_data.get('error_message'):
                        error(f"Error: {bridge_data['error_message']}")
                elif bridge_data.get('status') == 'pending':
                    success("⏳ Bridge is pending...")
                elif bridge_data.get('status') == 'locked':
                    success("🔒 Bridge is locked...")
                elif bridge_data.get('status') == 'transferred':
                    success("🔄 Bridge is transferring...")
            else:
                error(f"Failed to get bridge status: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")


@cross_chain.command()
@click.pass_context
def pools(ctx):
    """Show cross-chain liquidity pools"""
    try:
        http_client = AITBCHTTPClient(base_url="http://localhost:8001/api/v1", timeout=10)
            response = client.get(
                f"http://localhost:8001/api/v1/cross-chain/pools",
                timeout=10
            )
            
            if response.status_code == 200:
                pools_data = response.json()
                pools = pools_data.get('pools', [])
                
                if pools:
                    success(f"Found {len(pools)} cross-chain liquidity pools:")
                    
                    # Create table
                    pool_table = []
                    for pool in pools:
                        pool_table.append([
                            pool.get('pool_id', ''),
                            pool.get('token_a', ''),
                            pool.get('token_b', ''),
                            pool.get('chain_a', ''),
                            pool.get('chain_b', ''),
                            f"{pool.get('reserve_a', 0):.2f}",
                            f"{pool.get('reserve_b', 0):.2f}",
                            f"{pool.get('total_liquidity', 0):.2f}",
                            f"{pool.get('apr', 0):.2%}"
                        ])
                    
                    table(["Pool ID", "Token A", "Token B", "Chain A", "Chain B", 
                          "Reserve A", "Reserve B", "Liquidity", "APR"], pool_table)
                else:
                    success("No cross-chain liquidity pools found")
            else:
                error(f"Failed to get pools: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")


@cross_chain.command()
@click.pass_context
def stats(ctx):
    """Show cross-chain trading statistics"""
    try:
        http_client = AITBCHTTPClient(base_url="http://localhost:8001/api/v1", timeout=10)
            response = client.get(
                f"http://localhost:8001/api/v1/cross-chain/stats",
                timeout=10
            )
            
            if response.status_code == 200:
                stats_data = response.json()
                
                success("Cross-Chain Trading Statistics:")
                
                # Show swap stats
                swap_stats = stats_data.get('swap_stats', [])
                if swap_stats:
                    success("Swap Statistics:")
                    swap_table = []
                    for stat in swap_stats:
                        swap_table.append([
                            stat.get('status', ''),
                            stat.get('count', 0),
                            f"{stat.get('volume', 0):.2f}"
                        ])
                    table(["Status", "Count", "Volume"], swap_table)
                
                # Show bridge stats
                bridge_stats = stats_data.get('bridge_stats', [])
                if bridge_stats:
                    success("Bridge Statistics:")
                    bridge_table = []
                    for stat in bridge_stats:
                        bridge_table.append([
                            stat.get('status', ''),
                            stat.get('count', 0),
                            f"{stat.get('volume', 0):.2f}"
                        ])
                    table(["Status", "Count", "Volume"], bridge_table)
                
                # Show overall stats
                success("Overall Statistics:")
                output({
                    "Total Volume": f"{stats_data.get('total_volume', 0):.2f}",
                    "Supported Chains": ", ".join(stats_data.get('supported_chains', [])),
                    "Last Updated": stats_data.get('timestamp', '')
                }, ctx.obj['output_format'])
            else:
                error(f"Failed to get stats: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")
