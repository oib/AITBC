"""
Mining commands for AITBC CLI
"""

import json

import click

from ..utils.http_client import KEYSTORE_DIR, AITBCHTTPClient, NetworkError

from ..utils import error, success

DEFAULT_RPC_URL = "http://localhost:8202"
DEFAULT_KEYSTORE_DIR = KEYSTORE_DIR


@click.group()
def mining():
    """Mining operations commands"""
    pass


@mining.command()
@click.argument('wallet_name')
@click.option('--threads', type=int, default=1, help='Number of mining threads')
@click.option('--rpc-url', help='Blockchain RPC URL')
def start(wallet_name: str, threads: int, rpc_url: str | None):
    """Start mining with specified wallet"""
    if not rpc_url:
        rpc_url = DEFAULT_RPC_URL

    try:
        # Get wallet address
        keystore_path = DEFAULT_KEYSTORE_DIR / f"{wallet_name}.json"
        if not keystore_path.exists():
            error(f"Wallet '{wallet_name}' not found")
            return False

        with open(keystore_path) as f:
            wallet_data = json.load(f)
        address = wallet_data['address']

        # Start mining via RPC
        mining_config = {
            "miner_address": address,
            "threads": threads,
            "enabled": True
        }

        try:
            http_client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
            result = http_client.post("/rpc/mining/start", json=mining_config)
            success(f"Mining started with wallet '{wallet_name}'")
            click.echo(f"Miner address: {address}")
            click.echo(f"Threads: {threads}")
            click.echo(f"Status: {result.get('status', 'started')}")
            return result
        except NetworkError as e:
            error(f"Error starting mining: {e}")
            return None
        except Exception as e:
            error(f"Error: {e}")
            return False
    except Exception as e:
        error(f"Error: {e}")
        return False


@mining.command()
@click.option('--rpc-url', help='Blockchain RPC URL')
def stop(rpc_url: str | None):
    """Stop mining"""
    if not rpc_url:
        rpc_url = DEFAULT_RPC_URL

    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
        result = http_client.post("/rpc/mining/stop")
        success("Mining stopped")
        click.echo(f"Status: {result.get('status', 'stopped')}")
        return True
    except NetworkError as e:
        error(f"Error stopping mining: {e}")
        return False
    except Exception as e:
        error(f"Error: {e}")
        return False


@mining.command()
@click.option('--rpc-url', help='Blockchain RPC URL')
def status(rpc_url: str | None):
    """Get mining status"""
    if not rpc_url:
        rpc_url = DEFAULT_RPC_URL

    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
        result = http_client.get("/rpc/mining/status")
        success("Mining status:")
        click.echo(json.dumps(result, indent=2))
    except NetworkError as e:
        error(f"Error getting mining status: {e}")
    except Exception as e:
        error(f"Error: {e}")


@mining.command(name='list')
@click.option('--rpc-url', help='Blockchain RPC URL')
def list_miners(rpc_url: str | None):
    """List active miners"""
    if not rpc_url:
        rpc_url = DEFAULT_RPC_URL

    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
        result = http_client.get("/rpc/mining/miners")
        success("Active miners:")
        click.echo(json.dumps(result, indent=2))
    except NetworkError as e:
        error(f"Error listing miners: {e}")
    except Exception as e:
        error(f"Error: {e}")
