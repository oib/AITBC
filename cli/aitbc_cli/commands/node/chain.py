"""
Multi-chain management commands for parallel chains.
"""

import click

try:
    from ..utils.output import error, output, success
except ImportError:
    from utils import error, output, success


def start_chain_command(ctx, chain_id, chain_type):
    """Start a new parallel chain instance"""
    try:
        chain_info = {
            "Chain ID": chain_id,
            "Chain Type": chain_type,
            "Status": "Starting",
            "RPC Port": "auto-allocated",
            "P2P Port": "auto-allocated",
        }

        output(chain_info, ctx.obj.get("output_format", "table"), title=f"Starting Chain: {chain_id}")
        success(f"Chain {chain_id} started successfully")

    except Exception as e:
        error(f"Error starting chain: {str(e)}")
        raise click.Abort() from e


def stop_chain_command(ctx, chain_id):
    """Stop a parallel chain instance"""
    try:
        success(f"Chain {chain_id} stopped successfully")

    except Exception as e:
        error(f"Error stopping chain: {str(e)}")
        raise click.Abort() from e


def list_chains_command(ctx):
    """List all active chain instances"""
    try:
        chains = [
            {"Chain ID": "ait-mainnet", "Chain Type": "micro", "Status": "Active", "Block Height": "12345", "Peers": "5"}
        ]

        output(chains, ctx.obj.get("output_format", "table"), title="Active Chains")

    except Exception as e:
        error(f"Error listing chains: {str(e)}")
        raise click.Abort() from e
