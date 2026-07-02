"""Account commands for AITBC CLI"""

import click

from ..utils import output
from ..utils.error_handling import abort
from ..utils.http_client import AITBCHTTPClient, NetworkError


@click.group()
def account():
    """Account information and management"""
    pass


@account.command()
@click.option("--address", required=True, help="Account address")
@click.option("--rpc-url", default="http://localhost:8202", help="Blockchain RPC URL")
@click.option("--chain-id", help="Chain ID for multichain operations")
@click.pass_context
def get(ctx, address, rpc_url, chain_id):
    """Get account information"""
    try:
        params = {}
        if chain_id:
            params["chain_id"] = chain_id

        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
        account_data = http_client.get(f"/rpc/account/{address}", params=params)

        output(account_data, ctx.obj.get("output_format", "table"), title=f"Account: {address}")
    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error getting account: {e}", from_exception=e)


@account.command()
@click.option("--rpc-url", default="http://localhost:8202", help="Blockchain RPC URL")
@click.option("--chain-id", help="Chain ID for multichain operations")
@click.pass_context
def list(ctx, rpc_url, chain_id):
    """List all accounts"""
    try:
        params = {}
        if chain_id:
            params["chain_id"] = chain_id

        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
        accounts = http_client.get("/rpc/accounts", params=params)

        output(accounts, ctx.obj.get("output_format", "table"), title="Accounts")
    except NetworkError:
        # Fallback to simulated data if RPC endpoint not available
        accounts = {
            "status": "simulated",
            "accounts": [],
            "message": "RPC endpoint not available - showing simulated accounts",
        }
        output(accounts, ctx.obj.get("output_format", "table"), title="Accounts (Simulated)")
    except Exception as e:
        abort(ctx, f"Error listing accounts: {e}", from_exception=e)
