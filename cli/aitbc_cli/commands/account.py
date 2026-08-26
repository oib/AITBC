"""Account commands for AITBC CLI"""

import click

from aitbc.utils import format_ait

from ..utils import output
from ..utils.address import to_eip55
from ..utils.error_handling import abort
from ..utils.http_client import AITBCHTTPClient, NetworkError


@click.group()
def account():
    """Account information and management"""
    pass


@account.command()
@click.option("--address", required=True, help="Account address (0x, ait1 or aitbc1)")
@click.option("--rpc-url", default="http://localhost:8202", help="Blockchain RPC URL")
@click.option("--chain-id", help="Chain ID for multichain operations")
@click.pass_context
def get(ctx, address, rpc_url, chain_id):
    """Get account information."""
    try:
        params = {}
        if chain_id:
            params["chain_id"] = chain_id

        canonical = to_eip55(address)
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
        account_data = http_client.get(f"/rpc/account/{canonical}", params=params)

        # balance is in compute-seconds; expose the human-readable AIT string too.
        if "balance" in account_data:
            account_data["balance_ait"] = format_ait(account_data["balance"])

        # Show the canonical checksum address so callers can copy it confidently.
        account_data["canonical"] = canonical

        output(account_data, ctx.obj.get("output_format", "table"), title=f"Account: {canonical}")
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
    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error listing accounts: {e}", from_exception=e)
