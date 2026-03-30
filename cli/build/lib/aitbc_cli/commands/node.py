"""Node management commands for AITBC CLI"""

import click
from typing import Optional
from ..core.config import MultiChainConfig, load_multichain_config, get_default_node_config, add_node_config, remove_node_config
from ..core.node_client import NodeClient
from ..utils import output, error, success

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
        
        import asyncio
        
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
@click.pass_context
def chains(ctx, show_private):
    """List chains hosted on all nodes"""
    try:
        config = load_multichain_config()
        
        all_chains = []
        
        import asyncio
        
        async def get_all_chains():
            tasks = []
            for node_id, node_config in config.nodes.items():
                async def get_chains_for_node(nid, nconfig):
                    try:
                        async with NodeClient(nconfig) as client:
                            chains = await client.get_hosted_chains()
                            return [(nid, chain) for chain in chains]
                    except Exception as e:
                        print(f"Error getting chains from node {nid}: {e}")
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
        
        from ..core.config import save_multichain_config
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
        
        from ..core.config import save_multichain_config
        save_multichain_config(config)
        
        success(f"Node {node_id} removed successfully!")
        
    except Exception as e:
        error(f"Error removing node: {str(e)}")
        raise click.Abort()

@node.command()
@click.argument('node_id')
@click.option('--realtime', is_flag=True, help='Real-time monitoring')
@click.option('--interval', default=5, help='Update interval in seconds')
@click.pass_context
def monitor(ctx, node_id, realtime, interval):
    """Monitor node activity"""
    try:
        config = load_multichain_config()
        
        if node_id not in config.nodes:
            error(f"Node {node_id} not found")
            raise click.Abort()
        
        node_config = config.nodes[node_id]
        
        import asyncio
        from rich.console import Console
        from rich.layout import Layout
        from rich.live import Live
        import time
        
        console = Console()
        
        async def get_node_stats():
            async with NodeClient(node_config) as client:
                node_info = await client.get_node_info()
                return node_info
        
        if realtime:
            # Real-time monitoring
            def generate_monitor_layout():
                try:
                    node_info = asyncio.run(get_node_stats())
                    
                    layout = Layout()
                    layout.split_column(
                        Layout(name="header", size=3),
                        Layout(name="metrics"),
                        Layout(name="chains", size=10)
                    )
                    
                    # Header
                    layout["header"].update(
                        f"Node Monitor: {node_id} - {node_info['status'].upper()}"
                    )
                    
                    # Metrics table
                    metrics_data = [
                        ["CPU Usage", f"{node_info['cpu_usage']}%"],
                        ["Memory Usage", f"{node_info['memory_usage_mb']:.1f}MB"],
                        ["Disk Usage", f"{node_info['disk_usage_mb']:.1f}MB"],
                        ["Network In", f"{node_info['network_in_mb']:.1f}MB/s"],
                        ["Network Out", f"{node_info['network_out_mb']:.1f}MB/s"],
                        ["Uptime", f"{node_info['uptime_days']}d {node_info['uptime_hours']}h"]
                    ]
                    
                    layout["metrics"].update(str(metrics_data))
                    
                    # Chains info
                    if node_info.get("hosted_chains"):
                        chains_text = f"Hosted Chains: {len(node_info['hosted_chains'])}\n"
                        for chain_id, chain in list(node_info["hosted_chains"].items())[:5]:
                            chains_text += f"  • {chain_id} ({chain.get('status', 'unknown')})\n"
                        layout["chains"].update(chains_text)
                    else:
                        layout["chains"].update("No chains hosted")
                    
                    return layout
                except Exception as e:
                    return f"Error getting node stats: {e}"
            
            with Live(generate_monitor_layout(), refresh_per_second=1) as live:
                try:
                    while True:
                        live.update(generate_monitor_layout())
                        time.sleep(interval)
                except KeyboardInterrupt:
                    console.print("\n[yellow]Monitoring stopped by user[/yellow]")
        else:
            # Single snapshot
            node_info = asyncio.run(get_node_stats())
            
            stats_data = [
                {
                    "Metric": "CPU Usage",
                    "Value": f"{node_info['cpu_usage']}%"
                },
                {
                    "Metric": "Memory Usage",
                    "Value": f"{node_info['memory_usage_mb']:.1f}MB"
                },
                {
                    "Metric": "Disk Usage",
                    "Value": f"{node_info['disk_usage_mb']:.1f}MB"
                },
                {
                    "Metric": "Network In",
                    "Value": f"{node_info['network_in_mb']:.1f}MB/s"
                },
                {
                    "Metric": "Network Out",
                    "Value": f"{node_info['network_out_mb']:.1f}MB/s"
                },
                {
                    "Metric": "Uptime",
                    "Value": f"{node_info['uptime_days']}d {node_info['uptime_hours']}h"
                }
            ]
            
            output(stats_data, ctx.obj.get('output_format', 'table'), title=f"Node Statistics: {node_id}")
        
    except Exception as e:
        error(f"Error during monitoring: {str(e)}")
        raise click.Abort()

@node.command()
@click.argument('node_id')
@click.pass_context
def test(ctx, node_id):
    """Test connectivity to a node"""
    try:
        config = load_multichain_config()
        
        if node_id not in config.nodes:
            error(f"Node {node_id} not found")
            raise click.Abort()
        
        node_config = config.nodes[node_id]
        
        import asyncio
        
        async def test_node():
            try:
                async with NodeClient(node_config) as client:
                    node_info = await client.get_node_info()
                    chains = await client.get_hosted_chains()
                    
                    return {
                        "connected": True,
                        "node_id": node_info["node_id"],
                        "status": node_info["status"],
                        "version": node_info["version"],
                        "chains_count": len(chains)
                    }
            except Exception as e:
                return {
                    "connected": False,
                    "error": str(e)
                }
        
        result = asyncio.run(test_node())
        
        if result["connected"]:
            success(f"Successfully connected to node {node_id}!")
            
            test_data = [
                {
                    "Test": "Connection",
                    "Status": "✓ Pass"
                },
                {
                    "Test": "Node ID",
                    "Status": result["node_id"]
                },
                {
                    "Test": "Status",
                    "Status": result["status"]
                },
                {
                    "Test": "Version",
                    "Status": result["version"]
                },
                {
                    "Test": "Chains",
                    "Status": f"{result['chains_count']} hosted"
                }
            ]
            
            output(test_data, ctx.obj.get('output_format', 'table'), title=f"Node Test Results: {node_id}")
        else:
            error(f"Failed to connect to node {node_id}: {result['error']}")
            raise click.Abort()
        
    except Exception as e:
        error(f"Error testing node: {str(e)}")
        raise click.Abort()
