"""Account commands for AITBC CLI"""

import click

from aitbc import AITBCHTTPClient, NetworkError

from ..utils import error, output


@click.group()
def account():
    """Account information and management"""
    pass


@account.command()
@click.option('--address', required=True, help='Account address')
@click.option('--rpc-url', default='http://localhost:8202', help='Blockchain RPC URL')
@click.option('--chain-id', help='Chain ID for multichain operations')
@click.pass_context
def get(ctx, address, rpc_url, chain_id):
    """Get account information"""
    try:
        params = {}
        if chain_id:
            params["chain_id"] = chain_id

        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
        account_data = http_client.get(f"/rpc/account/{address}", params=params)

        output(account_data, ctx.obj.get('output_format', 'table'), title=f"Account: {address}")
    except NetworkError as e:
        error(f"Network error: {e}")
        raise click.Abort()
    except Exception as e:
        error(f"Error getting account: {e}")
        raise click.Abort()


@account.command()
@click.option('--rpc-url', default='http://localhost:8202', help='Blockchain RPC URL')
@click.option('--chain-id', help='Chain ID for multichain operations')
@click.pass_context
def list(ctx, rpc_url, chain_id):
    """List all accounts"""
    try:
        params = {}
        if chain_id:
            params["chain_id"] = chain_id

        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
        accounts = http_client.get("/rpc/accounts", params=params)

        output(accounts, ctx.obj.get('output_format', 'table'), title="Accounts")
    except NetworkError:
        # Fallback to simulated data if RPC endpoint not available
        accounts = {
            "status": "simulated",
            "accounts": [],
            "message": "RPC endpoint not available - showing simulated accounts"
        }
        output(accounts, ctx.obj.get('output_format', 'table'), title="Accounts (Simulated)")
    except Exception as e:
        error(f"Error listing accounts: {e}")
        raise click.Abort()
