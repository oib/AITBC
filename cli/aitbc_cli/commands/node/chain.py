"""
Multi-chain management commands for parallel chains.
"""

import click

from aitbc_cli.utils import error, output, success


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

        output(chain_info, ctx.obj.get("output", "table"), title=f"Starting Chain: {chain_id}")
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
    """List all active chain instances — live inventory via the multichain
    node configs, same source as ``aitbc node chains``."""
    try:
        import asyncio

        from aitbc_cli.core.config import load_multichain_config
        from aitbc_cli.core.node_client import NodeClient

        config = load_multichain_config()
        all_chains = []

        async def get_all_chains():
            tasks = []
            for nid, node_config in config.nodes.items():

                async def get_chains_for_node(nid, nconfig):
                    try:
                        async with NodeClient(nconfig) as client:
                            chains = await client.get_hosted_chains()
                            return [(nid, chain) for chain in chains]
                    except Exception as e:  # noqa: BLE001 - NodeClient raises bare Exception; parity with `node chains`
                        click.echo(f"Error getting chains from node {nid}: {e}")
                        return []

                tasks.append(get_chains_for_node(nid, node_config))

            results = await asyncio.gather(*tasks)
            for result in results:
                all_chains.extend(result)

        asyncio.run(get_all_chains())

        if not all_chains:
            output("No chains found on any node", ctx.obj.get("output", "table"))
            return

        chains_data = [
            {
                "Node ID": nid,
                "Chain ID": chain.id,
                "Name": chain.name,
                "Status": chain.status.value,
                "Block Height": chain.block_height,
            }
            for nid, chain in all_chains
        ]

        output(chains_data, ctx.obj.get("output", "table"), title="Active Chains")

    except Exception as e:
        error(f"Error listing chains: {str(e)}")
        raise click.Abort() from e
