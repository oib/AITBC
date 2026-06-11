"""
Main node management commands for AITBC.
"""

import asyncio

import click

try:
    from ..core.config import (
        add_node_config,
        get_default_node_config,
        load_multichain_config,
        remove_node_config,
        save_multichain_config,
    )
    from ..core.node_client import NodeClient
    from ..utils.output import error, info, output, success, warning
except ImportError:
    from aitbc_cli.core.config import (
        add_node_config,
        get_default_node_config,
        load_multichain_config,
        remove_node_config,
        save_multichain_config,
    )
    from aitbc_cli.core.node_client import NodeClient
    from utils import error, output, success

    def info(message):
        click.echo(message)


@click.group()
def node():
    """Node management commands"""
    pass


@node.command()
@click.argument('node_id')
@click.pass_context
def info(ctx, node_id):
    """Get detailed node information"""
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
            "Endpoint": node_config.endpoint
        }

        output(basic_info, ctx.obj.get('output_format', 'table'), title=f"Node Information: {node_id}")

        # Performance metrics
        metrics = {
            "CPU Usage": f"{node_info['cpu_usage']}%",
            "Memory Usage": f"{node_info['memory_usage_mb']:.1f}MB",
            "Disk Usage": f"{node_info['disk_usage_mb']:.1f}MB",
            "Network In": f"{node_info['network_in_mb']:.1f}MB/s",
            "Network Out": f"{node_info['network_out_mb']:.1f}MB/s"
        }

        output(metrics, ctx.obj.get('output_format', 'table'), title="Performance Metrics")

        # Hosted chains
        if node_info.get("hosted_chains"):
            chains_data = [
                {
                    "Chain ID": chain_id,
                    "Type": chain.get("type", "unknown"),
                    "Status": chain.get("status", "unknown")
                }
                for chain_id, chain in node_info["hosted_chains"].items()
            ]

            output(chains_data, ctx.obj.get('output_format', 'table'), title="Hosted Chains")

    except Exception as e:
        error(f"Error getting node info: {str(e)}")
        raise click.Abort()


@node.command()
@click.option('--show-private', is_flag=True, help='Show private chains')
@click.option('--node-id', help='Specific node ID to query')
@click.pass_context
def chains(ctx, show_private, node_id):
    """List chains hosted on all nodes"""
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
                    except Exception as e:
                        click.echo(f"Error getting chains from node {nid}: {e}")
                        return []

                tasks.append(get_chains_for_node(node_id, node_config))

            results = await asyncio.gather(*tasks)
            for result in results:
                all_chains.extend(result)

        asyncio.run(get_all_chains())

        if not all_chains:
            output("No chains found on any node", ctx.obj.get('output_format', 'table'))
            return

        # Filter private chains if not requested
        if not show_private:
            all_chains = [(node_id, chain) for node_id, chain in all_chains
                         if chain.privacy.visibility != "private"]

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
                "Size": f"{chain.size_mb:.1f}MB"
            }
            for node_id, chain in all_chains
        ]

        output(chains_data, ctx.obj.get('output_format', 'table'), title="Chains by Node")

    except Exception as e:
        error(f"Error listing chains: {str(e)}")
        raise click.Abort()


@node.command()
@click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
@click.pass_context
def list(ctx, format):
    """List all configured nodes"""
    try:
        config = load_multichain_config()

        if not config.nodes:
            output("No nodes configured", ctx.obj.get('output_format', 'table'))
            return

        nodes_data = [
            {
                "Node ID": node_id,
                "Endpoint": node_config.endpoint,
                "Timeout": f"{node_config.timeout}s",
                "Max Connections": node_config.max_connections,
                "Retry Count": node_config.retry_count
            }
            for node_id, node_config in config.nodes.items()
        ]

        output(nodes_data, ctx.obj.get('output_format', 'table'), title="Configured Nodes")

    except Exception as e:
        error(f"Error listing nodes: {str(e)}")
        raise click.Abort()


@node.command()
@click.argument('node_id')
@click.argument('endpoint')
@click.option('--timeout', default=30, help='Request timeout in seconds')
@click.option('--max-connections', default=10, help='Maximum concurrent connections')
@click.option('--retry-count', default=3, help='Number of retry attempts')
@click.pass_context
def add(ctx, node_id, endpoint, timeout, max_connections, retry_count):
    """Add a new node to configuration"""
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
            "Retry Count": retry_count
        }

        output(result, ctx.obj.get('output_format', 'table'))

    except Exception as e:
        error(f"Error adding node: {str(e)}")
        raise click.Abort()


@node.command()
@click.argument('node_id')
@click.option('--force', is_flag=True, help='Force removal without confirmation')
@click.pass_context
def remove(ctx, node_id, force):
    """Remove a node from configuration"""
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
                "Max Connections": node_config.max_connections
            }

            output(node_info, ctx.obj.get('output_format', 'table'), title="Node to Remove")

            if not click.confirm(f"Are you sure you want to remove node {node_id}?"):
                raise click.Abort()

        config = remove_node_config(config, node_id)
        save_multichain_config(config)

        success(f"Node {node_id} removed successfully!")

    except Exception as e:
        error(f"Error removing node: {str(e)}")
        raise click.Abort()
