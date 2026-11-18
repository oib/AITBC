"""
Main node management commands for AITBC.
"""

import asyncio
from typing import Any

import click
import httpx

try:
    from aitbc_cli.core.config import (
        add_node_config,
        get_default_node_config,
        load_multichain_config,
        remove_node_config,
        save_multichain_config,
    )
    from aitbc_cli.core.node_client import NodeClient, probe_nodes
    from aitbc_cli.utils import error, info, output, resolve_output_format, success, warning
except ImportError:
    from aitbc_cli.core.config import (
        add_node_config,
        get_default_node_config,
        load_multichain_config,
        remove_node_config,
        save_multichain_config,
    )
    from aitbc_cli.core.node_client import NodeClient, probe_nodes
    from aitbc_cli.utils import error, output, resolve_output_format, success, warning

    def info(message: str, **kwargs: Any):
        click.echo(message)


@click.group(
    epilog="""Examples:

  aitbc node list

  aitbc node add --node-id node-1 --endpoint http://localhost:8202"""
)
def node():
    """Manage nodes, islands, hubs, bridges, and chains in the federated mesh."""
    pass


def _live_local_node() -> dict[str, Any] | None:
    """Live identity of this host's own blockchain RPC, if it answers.

    ``~/.aitbc/multichain_config.yaml`` is a static registry that goes stale
    (ANALYTICS-NODECFG-STALE-1, #2219); ``/rpc/network-info`` on the
    configured ``blockchain_rpc_url`` is the live source of truth for the
    local node. Returns None when the RPC does not answer.
    """
    try:
        from aitbc_cli.config import get_config

        rpc = (getattr(get_config(), "blockchain_rpc_url", "") or "").rstrip("/")
        if not rpc:
            return None
        base = rpc[:-4] if rpc.endswith("/rpc") else rpc
        resp = httpx.get(f"{base}/rpc/network-info", timeout=3.0)
        if resp.status_code != 200:
            return None
        info = resp.json()
        return {
            "node_id": info.get("node_id"),
            "role": info.get("role"),
            "chain_id": info.get("chain_id"),
            "island_id": info.get("island_id"),
            "endpoint": f"{base}/rpc",
        }
    except Exception:  # noqa: BLE001 - live probe is best-effort; registry view still prints
        return None


@node.command(
    epilog="""Examples:

  aitbc node info --node-id node-1

  aitbc node info --node-id node-1 --output json"""
)
@click.option("--node-id", "node_id", required=True, help="The Node id.")
@click.pass_context
def node_info(ctx, node_id):
    """Get detailed information about a configured node."""
    try:
        config = load_multichain_config()

        if node_id not in config.nodes:
            error(f"Node {node_id} not found in configuration")
            raise click.Abort()

        node_config = config.nodes[node_id]

        async def get_node_info():
            async with NodeClient(node_config) as client:
                return await client.get_node_info()

        node_info = asyncio.run(get_node_info())

        # Basic node information
        basic_info = {
            "Node ID": node_info["node_id"],
            "Node Type": node_info["type"],
            "Status": node_info["status"],
            "Version": node_info["version"],
            "Uptime": f"{node_info['uptime_days']} days, {node_info['uptime_hours']} hours",
            "Endpoint": node_config.endpoint,
        }

        output(basic_info, ctx.obj.get("output", "table"), title=f"Node Information: {node_id}")

        # Performance metrics
        metrics = {
            "CPU Usage": f"{node_info['cpu_usage']}%",
            "Memory Usage": f"{node_info['memory_usage_mb']:.1f}MB",
            "Disk Usage": f"{node_info['disk_usage_mb']:.1f}MB",
            "Network In": f"{node_info['network_in_mb']:.1f}MB/s",
            "Network Out": f"{node_info['network_out_mb']:.1f}MB/s",
        }

        output(metrics, ctx.obj.get("output", "table"), title="Performance Metrics")

        # Hosted chains
        if node_info.get("hosted_chains"):
            chains_data = [
                {"Chain ID": chain_id, "Type": chain.get("type", "unknown"), "Status": chain.get("status", "unknown")}
                for chain_id, chain in node_info["hosted_chains"].items()
            ]

            output(chains_data, ctx.obj.get("output", "table"), title="Hosted Chains")

    except Exception as e:
        error(f"Error getting node info: {str(e)}")
        raise click.Abort() from e


@node.command(
    epilog="""Examples:

  aitbc node chains

  aitbc node chains --show-private --node-id node-1"""
)
@click.option("--show-private", is_flag=True, help="Show private chains")
@click.option("--node-id", help="Specific node ID to query")
@click.pass_context
def chains(ctx, show_private, node_id):
    """List chains hosted on all nodes or a specific node."""
    try:
        config = load_multichain_config()

        all_chains = []

        async def get_all_chains():
            tasks = []
            for nid, node_config in config.nodes.items():
                if node_id and nid != node_id:
                    continue

                async def get_chains_for_node(nid, nconfig):
                    try:
                        async with NodeClient(nconfig) as client:
                            chains = await client.get_hosted_chains()
                            return [(nid, chain) for chain in chains]
                    except Exception as e:  # noqa: BLE001 - NodeClient raises plain Exception for HTTP failures; per-node probe degrades to []
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

        # Filter private chains if not requested
        if not show_private:
            all_chains = [(node_id, chain) for node_id, chain in all_chains if chain.privacy.visibility != "private"]

        # Format output
        chains_data = [
            {
                "Node ID": node_id,
                "Chain ID": chain.id,
                "Type": chain.type.value,
                "Purpose": chain.purpose,
                "Name": chain.name,
                "Status": chain.status.value,
                "Block Height": chain.block_height,
                "Size": f"{chain.size_mb:.1f}MB",
            }
            for node_id, chain in all_chains
        ]

        output(chains_data, ctx.obj.get("output", "table"), title="Chains by Node")

    except Exception as e:
        error(f"Error listing chains: {str(e)}")
        raise click.Abort() from e


@node.command(
    epilog="""Examples:

  aitbc node list

  aitbc node list --output json"""
)
@click.option("--format", type=click.Choice(["table", "json"]), default=None, help="Output format")
@click.option("--no-probe", is_flag=True, help="Skip endpoint reachability checks")
@click.pass_context
def list(ctx, format, no_probe):
    """List all configured nodes and their connection settings.

    The multichain registry is static config, not live mesh state: each
    endpoint is probed and unreachable entries are flagged, and a warning is
    printed when nothing answers (#2219).
    """
    try:
        config = load_multichain_config()
        live = _live_local_node()

        if not config.nodes:
            fmt = resolve_output_format(ctx, format)
            if fmt == "json":
                output([], fmt)
            else:
                info("No nodes configured")
            _print_live_local_node(live)
            return

        statuses = {} if no_probe else asyncio.run(probe_nodes(config.nodes))

        nodes_data = []
        for node_id, node_config in config.nodes.items():
            row = {
                "Node ID": node_id,
                "Endpoint": node_config.endpoint,
                "Timeout": f"{node_config.timeout}s",
                "Max Connections": node_config.max_connections,
                "Retry Count": node_config.retry_count,
            }
            if statuses:
                row["Status"] = "reachable" if statuses.get(node_id) else "unreachable"
            nodes_data.append(row)

        output(nodes_data, resolve_output_format(ctx, format), title="Configured Nodes")

        if statuses and not any(statuses.values()):
            warning(
                "No configured node answered — the registry may be stale. "
                "Live mesh state: `aitbc network status` / `aitbc network peers`."
            )
        elif statuses and not all(statuses.values()):
            warning("Some configured nodes are unreachable — the registry may be stale.")
        _print_live_local_node(live)

    except Exception as e:
        error(f"Error listing nodes: {str(e)}")
        raise click.Abort() from e


def _print_live_local_node(live: dict[str, Any] | None) -> None:
    """Show the live local-node identity alongside the static registry."""
    if not live:
        return
    parts = [live["node_id"] or "unknown"]
    if live.get("role"):
        parts.append(f"role={live['role']}")
    if live.get("chain_id"):
        parts.append(f"chain={live['chain_id']}")
    if live.get("island_id"):
        parts.append(f"island={live['island_id']}")
    parts.append(live["endpoint"])
    info(f"Live local node: {' '.join(parts)}")


@node.command(
    epilog="""Examples:

  aitbc node add --node-id node-1 --endpoint http://localhost:8202

  aitbc node add --node-id node-1 --endpoint http://localhost:8202 --timeout 30"""
)
@click.option("--node-id", "node_id", required=True, help="The Node id.")
@click.option("--endpoint", "endpoint", required=True, help="The Endpoint.")
@click.option("--timeout", default=30, help="Request timeout in seconds")
@click.option("--max-connections", default=10, help="Maximum concurrent connections")
@click.option("--retry-count", default=3, help="Number of retry attempts")
@click.pass_context
def add(ctx, node_id, endpoint, timeout, max_connections, retry_count):
    """Add a new node to the local configuration."""
    try:
        config = load_multichain_config()

        if node_id in config.nodes:
            error(f"Node {node_id} already exists")
            raise click.Abort()

        node_config = get_default_node_config()
        node_config.id = node_id
        node_config.endpoint = endpoint
        node_config.timeout = timeout
        node_config.max_connections = max_connections
        node_config.retry_count = retry_count

        config = add_node_config(config, node_config)
        save_multichain_config(config)

        success(f"Node {node_id} added successfully!")

        result = {
            "Node ID": node_id,
            "Endpoint": endpoint,
            "Timeout": f"{timeout}s",
            "Max Connections": max_connections,
            "Retry Count": retry_count,
        }

        output(result, ctx.obj.get("output", "table"))

    except Exception as e:
        error(f"Error adding node: {str(e)}")
        raise click.Abort() from e


@node.command(
    epilog="""Examples:

  aitbc node remove --node-id node-1

  aitbc node remove --node-id node-1 --force"""
)
@click.option("--node-id", "node_id", required=True, help="The Node id.")
@click.option("--force", is_flag=True, help="Force removal without confirmation")
@click.pass_context
def remove(ctx, node_id, force):
    """Remove a node from the local configuration."""
    try:
        config = load_multichain_config()

        if node_id not in config.nodes:
            error(f"Node {node_id} not found")
            raise click.Abort()

        if not force:
            # Show node information before removal
            node_config = config.nodes[node_id]
            node_info = {
                "Node ID": node_id,
                "Endpoint": node_config.endpoint,
                "Timeout": f"{node_config.timeout}s",
                "Max Connections": node_config.max_connections,
            }

            output(node_info, ctx.obj.get("output", "table"), title="Node to Remove")

            if not click.confirm(f"Are you sure you want to remove node {node_id}?"):
                raise click.Abort()

        config = remove_node_config(config, node_id)
        save_multichain_config(config)

        success(f"Node {node_id} removed successfully!")

    except Exception as e:
        error(f"Error removing node: {str(e)}")
        raise click.Abort() from e


node.add_command(node_info, name="info")
