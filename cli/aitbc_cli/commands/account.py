"""Account commands for AITBC CLI"""

import click

from aitbc.utils import format_ait

from ..utils import output
from ..utils.address import to_eip55
from ..utils.error_handling import abort
from ..utils.http_client import AITBCHTTPClient, NetworkError


@click.group(
    epilog="""Examples:

  aitbc account get --address 0xAbc...

  aitbc account list"""
)
def account():
    """Display and manage AITBC accounts on the active blockchain."""
    pass


@account.command(
    epilog="""Examples:

  aitbc account get --address 0xC10F0E4fC10f0e4FC10f0e4fC10F0E4FC10F0e4f

  aitbc account get --address 0xAbc... --chain-id ait-mainnet"""
)
@click.option("--address", required=True, help="Account address (0x, 42 hex chars)")
@click.option("--rpc-url", default="http://localhost:8202", help="Blockchain RPC URL")
@click.option("--chain-id", help="Chain ID for multichain operations")
@click.pass_context
def get(ctx, address, rpc_url, chain_id):
    """Fetch on-chain information for a given account address, including balance and nonce."""
    try:
        params = {}
        if chain_id:
            params["chain_id"] = chain_id

        canonical = to_eip55(address)
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
        account_data = http_client.get(f"/rpc/account/{canonical}", params=params)

        # balance is in compute-units; expose the human-readable AIT string too.
        if "balance" in account_data:
            account_data["balance_ait"] = format_ait(account_data["balance"])

        # Show the canonical checksum address so callers can copy it confidently.
        account_data["canonical"] = canonical

        output(account_data, ctx.obj.get("output_format", "table"), title=f"Account: {canonical}")
    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error getting account: {e}", from_exception=e)


@account.command(
    epilog="""Examples:

  aitbc account list

  aitbc account list --output json"""
)
@click.option("--rpc-url", default="http://localhost:8202", help="Blockchain RPC URL")
@click.option("--chain-id", help="Chain ID for multichain operations")
@click.pass_context
def list(ctx, rpc_url, chain_id):
    """List all known accounts from the blockchain RPC."""
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
