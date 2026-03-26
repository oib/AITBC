"""Explorer commands for AITBC CLI"""

import click
import subprocess
import json
from typing import Optional, List
from utils import output, error


def _get_explorer_endpoint(ctx):
    """Get explorer endpoint from config or default"""
    try:
        config = ctx.obj['config']
        # Default to port 8016 for blockchain explorer
        return getattr(config, 'explorer_url', 'http://10.1.223.1:8016')
    except:
        return "http://10.1.223.1:8016"


def _curl_request(url: str, params: dict = None):
    """Make curl request instead of httpx to avoid connection issues"""
    cmd = ['curl', '-s', url]
    
    if params:
        param_str = '&'.join([f"{k}={v}" for k, v in params.items()])
        cmd.append(f"{url}?{param_str}")
    else:
        cmd.append(url)
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            return result.stdout
        else:
            return None
    except Exception:
        return None


@click.group()
@click.pass_context
def explorer(ctx):
    """Blockchain explorer operations and queries"""
    ctx.ensure_object(dict)
    ctx.parent.detected_role = 'explorer'


@explorer.command()
@click.option('--chain-id', default='ait-devnet', help='Chain ID to query (default: ait-devnet)')
@click.pass_context
def status(ctx, chain_id: str):
    """Get explorer and chain status"""
    try:
        explorer_url = _get_explorer_endpoint(ctx)
        
        # Get explorer health
        response_text = _curl_request(f"{explorer_url}/health")
        if response_text:
            try:
                health = json.loads(response_text)
                output({
                    "explorer_status": health.get("status", "unknown"),
                    "node_status": health.get("node_status", "unknown"),
                    "version": health.get("version", "unknown"),
                    "features": health.get("features", [])
                }, ctx.obj['output_format'])
            except json.JSONDecodeError:
                error("Invalid response from explorer")
        else:
            error("Failed to connect to explorer")
    
    except Exception as e:
        error(f"Failed to get explorer status: {str(e)}")


@explorer.command()
@click.option('--chain-id', default='ait-devnet', help='Chain ID to query (default: ait-devnet)')
@click.pass_context
def chains(ctx, chain_id: str):
    """List all supported chains"""
    try:
        explorer_url = _get_explorer_endpoint(ctx)
        
        response_text = _curl_request(f"{explorer_url}/api/chains")
        if response_text:
            try:
                chains_data = json.loads(response_text)
                output(chains_data, ctx.obj['output_format'])
            except json.JSONDecodeError:
                error("Invalid response from explorer")
        else:
            error("Failed to connect to explorer")
    
    except Exception as e:
        error(f"Failed to list chains: {str(e)}")


@explorer.command()
@click.option('--chain-id', default='ait-devnet', help='Chain ID to query (default: ait-devnet)')
@click.pass_context
def head(ctx, chain_id: str):
    """Get current chain head information"""
    try:
        explorer_url = _get_explorer_endpoint(ctx)
        
        params = {"chain_id": chain_id}
        response_text = _curl_request(f"{explorer_url}/api/chain/head", params)
        if response_text:
            try:
                head_data = json.loads(response_text)
                output(head_data, ctx.obj['output_format'])
            except json.JSONDecodeError:
                error("Invalid response from explorer")
        else:
            error("Failed to connect to explorer")
    
    except Exception as e:
        error(f"Failed to get chain head: {str(e)}")


@explorer.command()
@click.argument('height', type=int)
@click.option('--chain-id', default='ait-devnet', help='Chain ID to query (default: ait-devnet)')
@click.pass_context
def block(ctx, height: int, chain_id: str):
    """Get block information by height"""
    try:
        explorer_url = _get_explorer_endpoint(ctx)
        
        params = {"chain_id": chain_id}
        response_text = _curl_request(f"{explorer_url}/api/blocks/{height}", params)
        if response_text:
            try:
                block_data = json.loads(response_text)
                output(block_data, ctx.obj['output_format'])
            except json.JSONDecodeError:
                error("Invalid response from explorer")
        else:
            error("Failed to connect to explorer")
    
    except Exception as e:
        error(f"Failed to get block {height}: {str(e)}")


@explorer.command()
@click.argument('tx_hash')
@click.option('--chain-id', default='ait-devnet', help='Chain ID to query (default: ait-devnet)')
@click.pass_context
def transaction(ctx, tx_hash: str, chain_id: str):
    """Get transaction information by hash"""
    try:
        explorer_url = _get_explorer_endpoint(ctx)
        
        params = {"chain_id": chain_id}
        response_text = _curl_request(f"{explorer_url}/api/transactions/{tx_hash}", params)
        if response_text:
            try:
                tx_data = json.loads(response_text)
                output(tx_data, ctx.obj['output_format'])
            except json.JSONDecodeError:
                error("Invalid response from explorer")
        else:
            error("Failed to connect to explorer")
    
    except Exception as e:
        error(f"Failed to get transaction {tx_hash}: {str(e)}")


@explorer.command()
@click.option('--address', help='Filter by address')
@click.option('--amount-min', type=float, help='Minimum amount')
@click.option('--amount-max', type=float, help='Maximum amount')
@click.option('--type', 'tx_type', help='Transaction type')
@click.option('--since', help='Start date (ISO format)')
@click.option('--until', help='End date (ISO format)')
@click.option('--limit', type=int, default=50, help='Number of results (default: 50)')
@click.option('--offset', type=int, default=0, help='Offset for pagination (default: 0)')
@click.option('--chain-id', default='ait-devnet', help='Chain ID to query (default: ait-devnet)')
@click.pass_context
def search_transactions(ctx, address: Optional[str], amount_min: Optional[float], 
                       amount_max: Optional[float], tx_type: Optional[str], 
                       since: Optional[str], until: Optional[str], 
                       limit: int, offset: int, chain_id: str):
    """Search transactions with filters"""
    try:
        explorer_url = _get_explorer_endpoint(ctx)
        
        params = {
            "limit": limit,
            "offset": offset,
            "chain_id": chain_id
        }
        
        if address:
            params["address"] = address
        if amount_min:
            params["amount_min"] = amount_min
        if amount_max:
            params["amount_max"] = amount_max
        if tx_type:
            params["tx_type"] = tx_type
        if since:
            params["since"] = since
        if until:
            params["until"] = until
        
        response_text = _curl_request(f"{explorer_url}/api/search/transactions", params)
        if response_text:
            try:
                results = json.loads(response_text)
                output(results, ctx.obj['output_format'])
            except json.JSONDecodeError:
                error("Invalid response from explorer")
        else:
            error("Failed to connect to explorer")
    
    except Exception as e:
        error(f"Failed to search transactions: {str(e)}")


@explorer.command()
@click.option('--validator', help='Filter by validator address')
@click.option('--since', help='Start date (ISO format)')
@click.option('--until', help='End date (ISO format)')
@click.option('--min-tx', type=int, help='Minimum transaction count')
@click.option('--limit', type=int, default=50, help='Number of results (default: 50)')
@click.option('--offset', type=int, default=0, help='Offset for pagination (default: 0)')
@click.option('--chain-id', default='ait-devnet', help='Chain ID to query (default: ait-devnet)')
@click.pass_context
def search_blocks(ctx, validator: Optional[str], since: Optional[str], 
                  until: Optional[str], min_tx: Optional[int], 
                  limit: int, offset: int, chain_id: str):
    """Search blocks with filters"""
    try:
        explorer_url = _get_explorer_endpoint(ctx)
        
        params = {
            "limit": limit,
            "offset": offset,
            "chain_id": chain_id
        }
        
        if validator:
            params["validator"] = validator
        if since:
            params["since"] = since
        if until:
            params["until"] = until
        if min_tx:
            params["min_tx"] = min_tx
        
        response_text = _curl_request(f"{explorer_url}/api/search/blocks", params)
        if response_text:
            try:
                results = json.loads(response_text)
                output(results, ctx.obj['output_format'])
            except json.JSONDecodeError:
                error("Invalid response from explorer")
        else:
            error("Failed to connect to explorer")
    
    except Exception as e:
        error(f"Failed to search blocks: {str(e)}")


@explorer.command()
@click.option('--period', default='24h', help='Analytics period (1h, 24h, 7d, 30d)')
@click.option('--chain-id', default='ait-devnet', help='Chain ID to query (default: ait-devnet)')
@click.pass_context
def analytics(ctx, period: str, chain_id: str):
    """Get blockchain analytics overview"""
    try:
        explorer_url = _get_explorer_endpoint(ctx)
        
        params = {
            "period": period,
            "chain_id": chain_id
        }
        
        response_text = _curl_request(f"{explorer_url}/api/analytics/overview", params)
        if response_text:
            try:
                analytics_data = json.loads(response_text)
                output(analytics_data, ctx.obj['output_format'])
            except json.JSONDecodeError:
                error("Invalid response from explorer")
        else:
            error("Failed to connect to explorer")
    
    except Exception as e:
        error(f"Failed to get analytics: {str(e)}")


@explorer.command()
@click.option('--format', 'export_format', type=click.Choice(['csv', 'json']), default='csv', help='Export format')
@click.option('--type', 'export_type', type=click.Choice(['transactions', 'blocks']), default='transactions', help='Data type to export')
@click.option('--chain-id', default='ait-devnet', help='Chain ID to query (default: ait-devnet)')
@click.pass_context
def export(ctx, export_format: str, export_type: str, chain_id: str):
    """Export blockchain data"""
    try:
        explorer_url = _get_explorer_endpoint(ctx)
        
        params = {
            "format": export_format,
            "type": export_type,
            "chain_id": chain_id
        }
        
        if export_type == 'transactions':
            response_text = _curl_request(f"{explorer_url}/api/export/search", params)
        else:
            response_text = _curl_request(f"{explorer_url}/api/export/blocks", params)
        
        if response_text:
            # Save to file
            filename = f"explorer_export_{export_type}_{chain_id}.{export_format}"
            with open(filename, 'w') as f:
                f.write(response_text)
            output(f"Data exported to {filename}", ctx.obj['output_format'])
        else:
            error("Failed to export data")
    
    except Exception as e:
        error(f"Failed to export data: {str(e)}")


@explorer.command()
@click.option('--chain-id', default='main', help='Chain ID to explore')
@click.pass_context
def web(ctx, chain_id: str):
    """Get blockchain explorer web URL"""
    try:
        explorer_url = _get_explorer_endpoint(ctx)
        web_url = explorer_url.replace('http://', 'http://')  # Ensure proper format
        
        output(f"Explorer web interface: {web_url}", ctx.obj['output_format'])
        output("Use the URL above to access the explorer in your browser", ctx.obj['output_format'])
    
    except Exception as e:
        error(f"Failed to get explorer URL: {e}", ctx.obj['output_format'])
