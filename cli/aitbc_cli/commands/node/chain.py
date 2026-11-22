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
        from aitbc_cli.core.node_client import collect_hosted_chains

        config = load_multichain_config()

        # #2563: per-node failures are collected (not echoed to stdout);
        # unreachable nodes are reported on stderr and named in JSON output.
        all_chains, failures, answered = asyncio.run(collect_hosted_chains(config.nodes))
        unreachable = [nid for nid, _ in failures]
        for nid, err in failures:
            click.echo(f"Error getting chains from node {nid}: {err}", err=True)

        fmt = ctx.obj.get("output", "table")

        if not all_chains:
            if fmt == "json":
                output({"chains": [], "unreachable_nodes": unreachable}, fmt)
            else:
                output("No chains found on any node", fmt)
            if failures and answered == 0:
                # Every queried node failed — an outage, not an empty list.
                # SystemExit (not Abort) so the outer except doesn't re-wrap.
                raise SystemExit(1)
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

        if fmt == "json":
            output({"chains": chains_data, "unreachable_nodes": unreachable}, fmt, title="Active Chains")
        else:
            output(chains_data, fmt, title="Active Chains")

    except Exception as e:
        error(f"Error listing chains: {str(e)}")
        raise click.Abort() from e
