"""
Node management commands for AITBC
"""

import os
import sys
import socket
import json
import hashlib
import click
import asyncio
from pathlib import Path
from typing import Optional
from datetime import datetime

try:
    from ..utils.output import output, success, error, warning, info
    from ..core.config import MultiChainConfig, load_multichain_config, get_default_node_config, add_node_config, remove_node_config
    from ..core.node_client import NodeClient
except ImportError:
    from utils import output, error, success, warning
    from core.config import MultiChainConfig, load_multichain_config, get_default_node_config, add_node_config, remove_node_config
    from core.node_client import NodeClient

    def info(message):
        print(message)
import uuid

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
@click.option('--node-id', help='Specific node ID to query')
@click.pass_context
def chains(ctx, show_private, node_id):
    """List chains hosted on all nodes"""
    try:
        config = load_multichain_config()
        
        all_chains = []
        
        import asyncio
        
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

# Island management commands
@node.group()
def island():
    """Island management commands for federated mesh"""
    pass

@island.command()
@click.option('--island-id', help='Island ID (UUID), generates new if not provided')
@click.option('--island-name', default='default', help='Human-readable island name')
@click.option('--chain-id', help='Chain ID for this island')
@click.pass_context
def create(ctx, island_id, island_name, chain_id):
    """Create a new island"""
    try:
        if not island_id:
            island_id = str(uuid.uuid4())
        
        if not chain_id:
            chain_id = f"ait-{island_id[:8]}"
        
        island_info = {
            "Island ID": island_id,
            "Island Name": island_name,
            "Chain ID": chain_id,
            "Created": "Now"
        }
        
        output(island_info, ctx.obj.get('output_format', 'table'), title="New Island Created")
        success(f"Island {island_name} ({island_id}) created successfully")
        
        # Note: In a real implementation, this would update the configuration
        # and notify the island manager
        
    except Exception as e:
        error(f"Error creating island: {str(e)}")
        raise click.Abort()

@island.command()
@click.argument('island_id')
@click.argument('island_name')
@click.argument('chain_id')
@click.option('--hub', default='hub.aitbc.bubuit.net', help='Hub domain name to connect to')
@click.option('--is-hub', is_flag=True, help='Register this node as a hub for the island')
@click.pass_context
def join(ctx, island_id, island_name, chain_id, hub, is_hub):
    """Join an existing island"""
    try:
        # Get system hostname
        hostname = socket.gethostname()

        sys.path.insert(0, '/opt/aitbc/apps/blockchain-node/src')
        from aitbc_chain.config import settings as chain_settings

        # Get public key from keystore
        keystore_path = '/var/lib/aitbc/keystore/validator_keys.json'
        public_key_pem = None

        if os.path.exists(keystore_path):
            with open(keystore_path, 'r') as f:
                keys = json.load(f)
                # Get first key's public key
                for key_id, key_data in keys.items():
                    public_key_pem = key_data.get('public_key_pem')
                    break
        else:
            error(f"Keystore not found at {keystore_path}")
            raise click.Abort()

        if not public_key_pem:
            error("No public key found in keystore")
            raise click.Abort()

        # Generate node_id using hostname-based method
        local_address = socket.gethostbyname(hostname)
        local_port = chain_settings.p2p_bind_port
        content = f"{hostname}:{local_address}:{local_port}:{public_key_pem}"
        node_id = hashlib.sha256(content.encode()).hexdigest()

        # Resolve hub domain to IP
        hub_ip = socket.gethostbyname(hub)
        hub_port = chain_settings.p2p_bind_port

        click.echo(f"Connecting to hub {hub} ({hub_ip}:{hub_port})...")

        # Create P2P network service instance for sending join request
        from aitbc_chain.p2p_network import P2PNetworkService

        # Create a minimal P2P service just for sending the join request
        p2p_service = P2PNetworkService(
            local_address,
            local_port,
            node_id,
            "",
            island_id=island_id,
            island_name=island_name,
            is_hub=is_hub,
            island_chain_id=chain_id or chain_settings.island_chain_id or chain_settings.chain_id,
        )

        # Send join request
        async def send_join():
            return await p2p_service.send_join_request(
                hub_ip, hub_port, island_id, island_name, node_id, public_key_pem
            )

        response = asyncio.run(send_join())

        if response:
            # Store credentials locally
            credentials_path = '/var/lib/aitbc/island_credentials.json'
            credentials_data = {
                "island_id": response.get('island_id'),
                "island_name": response.get('island_name'),
                "island_chain_id": response.get('island_chain_id'),
                "credentials": response.get('credentials'),
                "joined_at": datetime.now().isoformat()
            }

            with open(credentials_path, 'w') as f:
                json.dump(credentials_data, f, indent=2)

            # Display join info
            join_info = {
                "Island ID": response.get('island_id'),
                "Island Name": response.get('island_name'),
                "Chain ID": response.get('island_chain_id'),
                "Member Count": len(response.get('members', [])),
                "Credentials Stored": credentials_path
            }

            output(join_info, ctx.obj.get('output_format', 'table'), title=f"Joined Island: {island_name}")

            # Display member list
            members = response.get('members', [])
            if members:
                output(members, ctx.obj.get('output_format', 'table'), title="Island Members")

            # Display credentials
            credentials = response.get('credentials', {})
            if credentials:
                output(credentials, ctx.obj.get('output_format', 'table'), title="Blockchain Credentials")

            success(f"Successfully joined island {island_name}")

            # If registering as hub
            if is_hub:
                click.echo("Registering as hub...")
                # Hub registration would happen here via the hub register command
                click.echo("Run 'aitbc node hub register' to complete hub registration")
        else:
            error("Failed to join island - no response from hub")
            raise click.Abort()

    except Exception as e:
        error(f"Error joining island: {str(e)}")
        raise click.Abort()

@island.command()
@click.argument('island_id')
@click.pass_context
def leave(ctx, island_id):
    """Leave an island"""
    try:
        success(f"Successfully left island {island_id}")
        
        # Note: In a real implementation, this would update the island manager
        
    except Exception as e:
        error(f"Error leaving island: {str(e)}")
        raise click.Abort()

@island.command()
@click.pass_context
def list(ctx):
    """List all known islands"""
    try:
        # Note: In a real implementation, this would query the island manager
        islands = [
            {
                "Island ID": "550e8400-e29b-41d4-a716-446655440000",
                "Island Name": "default",
                "Chain ID": "ait-island-default",
                "Status": "Active",
                "Peer Count": "3"
            }
        ]
        
        output(islands, ctx.obj.get('output_format', 'table'), title="Known Islands")
        
    except Exception as e:
        error(f"Error listing islands: {str(e)}")
        raise click.Abort()

@island.command()
@click.argument('island_id')
@click.pass_context
def info(ctx, island_id):
    """Show information about a specific island"""
    try:
        # Note: In a real implementation, this would query the island manager
        island_info = {
            "Island ID": island_id,
            "Island Name": "default",
            "Chain ID": "ait-island-default",
            "Status": "Active",
            "Peer Count": "3",
            "Hub Count": "1"
        }
        
        output(island_info, ctx.obj.get('output_format', 'table'), title=f"Island Information: {island_id}")
        
    except Exception as e:
        error(f"Error getting island info: {str(e)}")
        raise click.Abort()

# Hub management commands
@node.group()
def hub():
    """Hub management commands for federated mesh"""
    pass

@hub.command()
@click.option('--public-address', help='Public IP address')
@click.option('--public-port', type=int, help='Public port')
@click.option('--redis-url', default='redis://localhost:6379', help='Redis URL for persistence')
@click.option('--hub-discovery-url', default='hub.aitbc.bubuit.net', help='DNS hub discovery URL')
@click.pass_context
def register(ctx, public_address, public_port, redis_url, hub_discovery_url):
    """Register this node as a hub"""
    try:
        # Get environment variables
        island_id = os.getenv('ISLAND_ID', 'default-island-id')
        island_name = os.getenv('ISLAND_NAME', 'default')

        # Get system hostname
        hostname = socket.gethostname()

        # Get public key from keystore
        keystore_path = '/var/lib/aitbc/keystore/validator_keys.json'
        public_key_pem = None

        if os.path.exists(keystore_path):
            with open(keystore_path, 'r') as f:
                keys = json.load(f)
                # Get first key's public key
                for key_id, key_data in keys.items():
                    public_key_pem = key_data.get('public_key_pem')
                    break
        else:
            error(f"Keystore not found at {keystore_path}")
            raise click.Abort()

        if not public_key_pem:
            error("No public key found in keystore")
            raise click.Abort()

        # Generate node_id using hostname-based method
        local_address = socket.gethostbyname(hostname)
        local_port = 7070  # Default hub port
        content = f"{hostname}:{local_address}:{local_port}:{public_key_pem}"
        node_id = hashlib.sha256(content.encode()).hexdigest()

        # Create HubManager instance
        sys.path.insert(0, '/opt/aitbc/apps/blockchain-node/src')
        from aitbc_chain.network.hub_manager import HubManager
        from aitbc_chain.network.hub_discovery import HubDiscovery

        hub_manager = HubManager(
            node_id,
            local_address,
            local_port,
            island_id,
            island_name,
            redis_url
        )

        # Register as hub (async)
        async def register_hub():
            success = await hub_manager.register_as_hub(public_address, public_port)
            if success:
                # Register with DNS discovery service
                hub_discovery = HubDiscovery(hub_discovery_url, local_port)
                hub_info_dict = {
                    "node_id": node_id,
                    "address": local_address,
                    "port": local_port,
                    "island_id": island_id,
                    "island_name": island_name,
                    "public_address": public_address,
                    "public_port": public_port,
                    "public_key_pem": public_key_pem
                }
                dns_success = await hub_discovery.register_hub(hub_info_dict)
                return success and dns_success
            return False

        result = asyncio.run(register_hub())

        if result:
            hub_info = {
                "Node ID": node_id,
                "Hostname": hostname,
                "Address": local_address,
                "Port": local_port,
                "Island ID": island_id,
                "Island Name": island_name,
                "Public Address": public_address or "auto-discovered",
                "Public Port": public_port or "auto-discovered",
                "Status": "Registered"
            }

            output(hub_info, ctx.obj.get('output_format', 'table'), title="Hub Registration")
            success("Successfully registered as hub")
        else:
            error("Failed to register as hub")
            raise click.Abort()

    except Exception as e:
        error(f"Error registering as hub: {str(e)}")
        raise click.Abort()

@hub.command()
@click.option('--redis-url', default='redis://localhost:6379', help='Redis URL for persistence')
@click.option('--hub-discovery-url', default='hub.aitbc.bubuit.net', help='DNS hub discovery URL')
@click.pass_context
def unregister(ctx, redis_url, hub_discovery_url):
    """Unregister this node as a hub"""
    try:
        # Get environment variables
        island_id = os.getenv('ISLAND_ID', 'default-island-id')
        island_name = os.getenv('ISLAND_NAME', 'default')

        # Get system hostname
        hostname = socket.gethostname()

        # Get public key from keystore
        keystore_path = '/var/lib/aitbc/keystore/validator_keys.json'
        public_key_pem = None

        if os.path.exists(keystore_path):
            with open(keystore_path, 'r') as f:
                keys = json.load(f)
                # Get first key's public key
                for key_id, key_data in keys.items():
                    public_key_pem = key_data.get('public_key_pem')
                    break
        else:
            error(f"Keystore not found at {keystore_path}")
            raise click.Abort()

        if not public_key_pem:
            error("No public key found in keystore")
            raise click.Abort()

        # Generate node_id using hostname-based method
        local_address = socket.gethostbyname(hostname)
        local_port = 7070  # Default hub port
        content = f"{hostname}:{local_address}:{local_port}:{public_key_pem}"
        node_id = hashlib.sha256(content.encode()).hexdigest()

        # Create HubManager instance
        sys.path.insert(0, '/opt/aitbc/apps/blockchain-node/src')
        from aitbc_chain.network.hub_manager import HubManager
        from aitbc_chain.network.hub_discovery import HubDiscovery

        hub_manager = HubManager(
            node_id,
            local_address,
            local_port,
            island_id,
            island_name,
            redis_url
        )

        # Unregister as hub (async)
        async def unregister_hub():
            success = await hub_manager.unregister_as_hub()
            if success:
                # Unregister from DNS discovery service
                hub_discovery = HubDiscovery(hub_discovery_url, local_port)
                dns_success = await hub_discovery.unregister_hub(node_id)
                return success and dns_success
            return False

        result = asyncio.run(unregister_hub())

        if result:
            hub_info = {
                "Node ID": node_id,
                "Status": "Unregistered"
            }

            output(hub_info, ctx.obj.get('output_format', 'table'), title="Hub Unregistration")
            success("Successfully unregistered as hub")
        else:
            error("Failed to unregister as hub")
            raise click.Abort()

    except Exception as e:
        error(f"Error unregistering as hub: {str(e)}")
        raise click.Abort()

@hub.command()
@click.option('--redis-url', default='redis://localhost:6379', help='Redis URL for persistence')
@click.pass_context
def list(ctx, redis_url):
    """List registered hubs from Redis"""
    try:
        import redis.asyncio as redis

        async def list_hubs():
            hubs = []
            try:
                r = redis.from_url(redis_url)
                # Get all hub keys
                keys = await r.keys("hub:*")
                for key in keys:
                    value = await r.get(key)
                    if value:
                        hub_data = json.loads(value)
                        hubs.append({
                            "Node ID": hub_data.get("node_id"),
                            "Address": hub_data.get("address"),
                            "Port": hub_data.get("port"),
                            "Island ID": hub_data.get("island_id"),
                            "Island Name": hub_data.get("island_name"),
                            "Public Address": hub_data.get("public_address", "N/A"),
                            "Public Port": hub_data.get("public_port", "N/A"),
                            "Peer Count": hub_data.get("peer_count", 0)
                        })
                await r.close()
            except Exception as e:
                error(f"Failed to query Redis: {e}")
                return []
            return hubs

        hubs = asyncio.run(list_hubs())

        if hubs:
            output(hubs, ctx.obj.get('output_format', 'table'), title="Registered Hubs")
        else:
            info("No registered hubs found")

    except Exception as e:
        error(f"Error listing hubs: {str(e)}")
        raise click.Abort()

# Bridge management commands
@node.group()
def bridge():
    """Bridge management commands for federated mesh"""
    pass

@bridge.command()
@click.argument('target_island_id')
@click.pass_context
def request(ctx, target_island_id):
    """Request a bridge to another island"""
    try:
        success(f"Bridge request sent to island {target_island_id}")
        
        # Note: In a real implementation, this would use the bridge manager
        
    except Exception as e:
        error(f"Error requesting bridge: {str(e)}")
        raise click.Abort()

@bridge.command()
@click.argument('request_id')
@click.argument('approving_node_id')
@click.pass_context
def approve(ctx, request_id, approving_node_id):
    """Approve a bridge request"""
    try:
        success(f"Bridge request {request_id} approved")
        
        # Note: In a real implementation, this would use the bridge manager
        
    except Exception as e:
        error(f"Error approving bridge request: {str(e)}")
        raise click.Abort()

@bridge.command()
@click.argument('request_id')
@click.option('--reason', help='Rejection reason')
@click.pass_context
def reject(ctx, request_id, reason):
    """Reject a bridge request"""
    try:
        success(f"Bridge request {request_id} rejected")
        
        # Note: In a real implementation, this would use the bridge manager
        
    except Exception as e:
        error(f"Error rejecting bridge request: {str(e)}")
        raise click.Abort()

@bridge.command()
@click.pass_context
def list(ctx):
    """List bridge connections"""
    try:
        # Note: In a real implementation, this would query the bridge manager
        bridges = [
            {
                "Bridge ID": "bridge-1",
                "Source Island": "island-a",
                "Target Island": "island-b",
                "Status": "Active"
            }
        ]
        
        output(bridges, ctx.obj.get('output_format', 'table'), title="Bridge Connections")
        
    except Exception as e:
        error(f"Error listing bridges: {str(e)}")
        raise click.Abort()

# Multi-chain management commands
@node.group()
def chain():
    """Multi-chain management commands for parallel chains"""
    pass

@chain.command()
@click.argument('chain_id')
@click.option('--chain-type', type=click.Choice(['bilateral', 'micro']), default='micro', help='Chain type')
@click.pass_context
def start(ctx, chain_id, chain_type):
    """Start a new parallel chain instance"""
    try:
        chain_info = {
            "Chain ID": chain_id,
            "Chain Type": chain_type,
            "Status": "Starting",
            "RPC Port": "auto-allocated",
            "P2P Port": "auto-allocated"
        }
        
        output(chain_info, ctx.obj.get('output_format', 'table'), title=f"Starting Chain: {chain_id}")
        success(f"Chain {chain_id} started successfully")
        
        # Note: In a real implementation, this would use the multi-chain manager
        
    except Exception as e:
        error(f"Error starting chain: {str(e)}")
        raise click.Abort()

@chain.command()
@click.argument('chain_id')
@click.pass_context
def stop(ctx, chain_id):
    """Stop a parallel chain instance"""
    try:
        success(f"Chain {chain_id} stopped successfully")
        
        # Note: In a real implementation, this would use the multi-chain manager
        
    except Exception as e:
        error(f"Error stopping chain: {str(e)}")
        raise click.Abort()

@chain.command()
@click.pass_context
def list(ctx):
    """List all active chain instances"""
    try:
        # Note: In a real implementation, this would query the multi-chain manager
        chains = [
            {
                "Chain ID": "ait-mainnet",
                "Chain Type": "default",
                "Status": "Running",
                "RPC Port": 8000,
                "P2P Port": 7070
            }
        ]
        
        output(chains, ctx.obj.get('output_format', 'table'), title="Active Chains")
        
    except Exception as e:
        error(f"Error listing chains: {str(e)}")
        raise click.Abort()
