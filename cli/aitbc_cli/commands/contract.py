"""Contract commands for AITBC CLI"""

import click

from ..utils import error, output
from ..utils.http_client import AITBCHTTPClient, NetworkError


@click.group()
def contract():
    """Smart contract operations"""
    pass


@contract.command()
@click.option('--contract-name', required=True, help='Contract name')
@click.option('--rpc-url', default='http://localhost:8202', help='Blockchain RPC URL')
@click.pass_context
def deploy(ctx, contract_name, rpc_url):
    """Deploy smart contract"""
    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
        result = http_client.post("/rpc/contracts/deploy", json={
            "contract_name": contract_name
        })
        output(result, ctx.obj.get('output_format', 'table'), title="Contract Deployed")
    except NetworkError as e:
        error(f"Network error: {e}")
        raise click.Abort()
    except Exception as e:
        error(f"Error deploying contract: {e}")
        raise click.Abort()


@contract.command()
@click.option('--contract-address', required=True, help='Contract address')
@click.option('--method', required=True, help='Method to call')
@click.option('--args', help='Method arguments (JSON array)')
@click.option('--rpc-url', default='http://localhost:8202', help='Blockchain RPC URL')
@click.pass_context
def call(ctx, contract_address, method, args, rpc_url):
    """Call smart contract method"""
    try:
        import json
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
        payload = {
            "contract_address": contract_address,
            "method": method
        }
        if args:
            payload["args"] = json.loads(args)
        result = http_client.post("/rpc/contracts/call", json=payload)
        output(result, ctx.obj.get('output_format', 'table'), title="Contract Call")
    except NetworkError as e:
        error(f"Network error: {e}")
        raise click.Abort()
    except Exception as e:
        error(f"Error calling contract: {e}")
        raise click.Abort()
