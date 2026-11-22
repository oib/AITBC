"""
Multi-chain management commands for parallel chains.
"""

import click

from aitbc_cli.utils import error, output


def start_chain_command(ctx, chain_id, chain_type):
    """Start a new parallel chain instance.

    #2534: there is no node-side chain lifecycle endpoint — the previous
    stub printed "started successfully" without touching any node. Fail
    clearly until a real implementation lands.
    """
    error(
        f"node chain start is not implemented: no node endpoint exists to start chain {chain_id!r} "
        "(parallel-chain lifecycle is not supported by any deployed node)"
    )
    raise click.Abort()


def stop_chain_command(ctx, chain_id):
    """Stop a parallel chain instance.

    #2534: same stub class as start — no node endpoint exists; fail clearly.
    """
    error(
        f"node chain stop is not implemented: no node endpoint exists to stop chain {chain_id!r} "
        "(parallel-chain lifecycle is not supported by any deployed node)"
    )
    raise click.Abort()


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
