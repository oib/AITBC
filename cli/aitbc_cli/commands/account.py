"""Account commands for AITBC CLI"""

import click
import httpx

from aitbc.utils import format_ait

from aitbc.exceptions import AITBCError
from ..utils import output
from ..utils.address import to_eip55
from ..utils.error_handling import CLIError, abort
from ..utils.http_client import AITBCHTTPClient, NetworkError

# Expected failure surface for the command handlers below: filesystem/JSON,
# data-shape, runtime, optional-dependency imports, HTTP-client errors and
# both error hierarchies (CLIError, aitbc_errors.AITBCError). RuntimeError
# covers generic runtime failures; abort() raises CLIError (already listed),
# preserving the previous re-abort behaviour. BaseExceptions still propagate
# (#1864).
_OPS_ERRORS = (
    OSError,
    ValueError,
    KeyError,
    TypeError,
    AttributeError,
    RuntimeError,
    ImportError,
    CLIError,
    AITBCError,
    httpx.HTTPError,
)


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

        fmt = ctx.obj.get("output_format", "table")
        if fmt not in ("json", "yaml") and "balance" in account_data:
            account_data["balance_units"] = account_data["balance"]
            account_data["balance"] = format_ait(account_data["balance"])
            account_data.pop("balance_ait", None)

        output(account_data, fmt, title=f"Account: {canonical}")
    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except _OPS_ERRORS as e:
        abort(ctx, f"Error getting account: {e}", from_exception=e)


@account.command(
    epilog="""Examples:

  aitbc account list

  aitbc account list --all

  aitbc account list --limit 500 --cursor <next_cursor>

  aitbc account list --output json"""
)
@click.option("--rpc-url", default="http://localhost:8202", help="Blockchain RPC URL")
@click.option("--chain-id", help="Chain ID for multichain operations")
@click.option("--limit", type=int, default=100, help="Accounts per page (server caps at 500)")
@click.option("--offset", type=int, default=0, help="Row offset on top of the cursor position")
@click.option("--cursor", default=None, help="Keyset cursor from a previous page's next_cursor")
@click.option(
    "--all",
    "fetch_all",
    is_flag=True,
    help="Page through every account via next_cursor instead of stopping at one page",
)
@click.pass_context
def list(ctx, rpc_url, chain_id, limit, offset, cursor, fetch_all):
    """List known accounts from the blockchain RPC, one keyset page at a time."""
    try:
        base_params: dict = {}
        if chain_id:
            base_params["chain_id"] = chain_id

        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
        accounts = http_client.get(
            "/rpc/accounts",
            params=(
                {**base_params, "limit": limit, "offset": offset, "cursor": cursor}
                if not fetch_all
                else {**base_params, "limit": min(limit, 500)}
            ),
        )
        pages = 1
        if fetch_all:
            # NB: bare ``list`` is this module's click command, not the builtin.
            merged = accounts.get("accounts", [])
            total_accounts = accounts.get("total_accounts")
            while accounts.get("next_cursor"):
                pages += 1
                accounts = http_client.get(
                    "/rpc/accounts",
                    params={**base_params, "limit": min(limit, 500), "cursor": accounts["next_cursor"]},
                )
                merged += accounts.get("accounts", [])
            accounts = {
                "chain_id": accounts.get("chain_id"),
                "accounts": merged,
                "total": len(merged),
                "total_accounts": total_accounts,
                "limit": limit,
                "pages": pages,
                "next_cursor": None,
            }

        fmt = ctx.obj.get("output_format", "table")
        shown = accounts.get("accounts", [])
        if fmt not in ("json", "yaml"):
            for account in shown:
                if "balance" in account:
                    account["balance_units"] = account["balance"]
                    account["balance"] = format_ait(account["balance"])
            total_accounts = accounts.get("total_accounts")
            if total_accounts is not None and len(shown) < total_accounts:
                click.echo(
                    f"showing {len(shown)} of {total_accounts} accounts (use --all or --cursor <next_cursor> for more)",
                    err=True,
                )

        output(accounts, fmt, title="Accounts")
    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except _OPS_ERRORS as e:
        abort(ctx, f"Error listing accounts: {e}", from_exception=e)
