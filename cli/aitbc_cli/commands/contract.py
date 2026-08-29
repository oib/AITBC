"""Contract commands for AITBC CLI"""

import click

from ..utils import output
from ..utils.error_handling import abort
from ..utils.http_client import AITBCHTTPClient, NetworkError


@click.group(
    epilog="""Examples:

  aitbc contract deploy --contract-name MyContract

  aitbc contract call --contract-address 0x... --method getBalance"""
)
def contract():
    """Deploy smart contracts and call methods on deployed contract addresses."""
    pass


@contract.command(
    epilog="""Examples:

  aitbc contract deploy --contract-name MyContract

  aitbc contract deploy --contract-name MyContract --rpc-url http://aitbc3:8202"""
)
@click.option("--contract-name", required=True, help="Contract name")
@click.option("--rpc-url", default="http://localhost:8202", help="Blockchain RPC URL")
@click.pass_context
def deploy(ctx, contract_name, rpc_url):
    """Deploy a named smart contract to the blockchain."""
    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
        result = http_client.post("/rpc/contracts/deploy", json={"contract_name": contract_name})
        output(result, ctx.obj.get("output_format", "table"), title="Contract Deployed")
    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error deploying contract: {e}", from_exception=e)


@contract.command(
    epilog="""Examples:

  aitbc contract call --contract-address 0x... --method getBalance

  aitbc contract call --contract-address 0x... --method setValue --args '["hello"]'"""
)
@click.option("--contract-address", required=True, help="Contract address")
@click.option("--method", required=True, help="Method to call")
@click.option("--args", help="Method arguments (JSON array)")
@click.option("--rpc-url", default="http://localhost:8202", help="Blockchain RPC URL")
@click.pass_context
def call(ctx, contract_address, method, args, rpc_url):
    """Call a method on a deployed smart contract with optional arguments."""
    try:
        import json

        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
        payload = {"contract_address": contract_address, "method": method}
        if args:
            payload["args"] = json.loads(args)
        result = http_client.post("/rpc/contracts/call", json=payload)
        output(result, ctx.obj.get("output_format", "table"), title="Contract Call")
    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error calling contract: {e}", from_exception=e)
