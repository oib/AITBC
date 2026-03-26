"""Chain management commands for AITBC CLI"""

import click
from typing import Optional
from core.chain_manager import ChainManager, ChainNotFoundError, NodeNotAvailableError
from core.config import MultiChainConfig, load_multichain_config
from models.chain import ChainType
from utils import output, error, success

@click.group()
def chain():
    """Multi-chain management commands"""
    pass

@chain.command()
@click.option('--type', 'chain_type', type=click.Choice(['main', 'topic', 'private', 'all']), 
              default='all', help='Filter by chain type')
@click.option('--show-private', is_flag=True, help='Show private chains')
@click.option('--sort', type=click.Choice(['id', 'size', 'nodes', 'created']), 
              default='id', help='Sort by field')
@click.pass_context
def list(ctx, chain_type, show_private, sort):
    """List all available chains"""
    try:
        config = load_multichain_config()
        chain_manager = ChainManager(config)
        
        # Get chains
        import asyncio
        chains = asyncio.run(chain_manager.list_chains(
            chain_type=ChainType(chain_type) if chain_type != 'all' else None,
            include_private=show_private,
            sort_by=sort
        ))
        
        if not chains:
            output("No chains found", ctx.obj.get('output_format', 'table'))
            return
        
        # Format output
        chains_data = [
            {
                "Chain ID": chain.id,
                "Type": chain.type.value,
                "Purpose": chain.purpose,
                "Name": chain.name,
                "Size": f"{chain.size_mb:.1f}MB",
                "Nodes": chain.node_count,
                "Contracts": chain.contract_count,
                "Clients": chain.client_count,
                "Miners": chain.miner_count,
                "Status": chain.status.value
            }
            for chain in chains
        ]
        
        output(chains_data, ctx.obj.get('output_format', 'table'), title="Available Chains")
        
    except Exception as e:
        error(f"Error listing chains: {str(e)}")
        raise click.Abort()

@chain.command()
@click.option('--chain-id', help='Specific chain ID to check status (shows all if not specified)')
@click.option('--detailed', is_flag=True, help='Show detailed status information')
@click.pass_context
def status(ctx, chain_id, detailed):
    """Check status of chains"""
    try:
        config = load_multichain_config()
        chain_manager = ChainManager(config)
        
        import asyncio
        
        if chain_id:
            # Get specific chain status
            chain_info = asyncio.run(chain_manager.get_chain_info(chain_id, detailed=detailed))
            
            status_data = {
                "Chain ID": chain_info.id,
                "Name": chain_info.name,
                "Type": chain_info.type.value,
                "Status": chain_info.status.value,
                "Block Height": chain_info.block_height,
                "Active Nodes": chain_info.active_nodes,
                "Total Nodes": chain_info.node_count
            }
            
            if detailed:
                status_data.update({
                    "Consensus": chain_info.consensus_algorithm.value,
                    "TPS": f"{chain_info.tps:.1f}",
                    "Gas Price": f"{chain_info.gas_price / 1e9:.1f} gwei",
                    "Memory Usage": f"{chain_info.memory_usage_mb:.1f}MB"
                })
            
            output(status_data, ctx.obj.get('output_format', 'table'), title=f"Chain Status: {chain_id}")
        else:
            # Get all chains status
            chains = asyncio.run(chain_manager.list_chains())
            
            if not chains:
                output({"message": "No chains found"}, ctx.obj.get('output_format', 'table'))
                return
            
            status_list = []
            for chain in chains:
                status_info = {
                    "Chain ID": chain.id,
                    "Name": chain.name,
                    "Type": chain.type.value,
                    "Status": chain.status.value,
                    "Block Height": chain.block_height,
                    "Active Nodes": chain.active_nodes
                }
                status_list.append(status_info)
            
            output(status_list, ctx.obj.get('output_format', 'table'), title="Chain Status Overview")
        
    except ChainNotFoundError:
        error(f"Chain {chain_id} not found")
        raise click.Abort()
    except Exception as e:
        error(f"Error getting chain status: {str(e)}")
        raise click.Abort()

@chain.command()
@click.argument('chain_id')
@click.option('--detailed', is_flag=True, help='Show detailed information')
@click.option('--metrics', is_flag=True, help='Show performance metrics')
@click.pass_context
def info(ctx, chain_id, detailed, metrics):
    """Get detailed information about a chain"""
    try:
        config = load_multichain_config()
        chain_manager = ChainManager(config)
        
        import asyncio
        chain_info = asyncio.run(chain_manager.get_chain_info(chain_id, detailed, metrics))
        
        # Basic information
        basic_info = {
            "Chain ID": chain_info.id,
            "Type": chain_info.type.value,
            "Purpose": chain_info.purpose,
            "Name": chain_info.name,
            "Description": chain_info.description or "No description",
            "Status": chain_info.status.value,
            "Created": chain_info.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "Block Height": chain_info.block_height,
            "Size": f"{chain_info.size_mb:.1f}MB"
        }
        
        output(basic_info, ctx.obj.get('output_format', 'table'), title=f"Chain Information: {chain_id}")
        
        if detailed:
            # Network details
            network_info = {
                "Total Nodes": chain_info.node_count,
                "Active Nodes": chain_info.active_nodes,
                "Consensus": chain_info.consensus_algorithm.value,
                "Block Time": f"{chain_info.block_time}s",
                "Clients": chain_info.client_count,
                "Miners": chain_info.miner_count,
                "Contracts": chain_info.contract_count,
                "Agents": chain_info.agent_count,
                "Privacy": chain_info.privacy.visibility,
                "Access Control": chain_info.privacy.access_control
            }
            
            output(network_info, ctx.obj.get('output_format', 'table'), title="Network Details")
        
        if metrics:
            # Performance metrics
            performance_info = {
                "TPS": f"{chain_info.tps:.1f}",
                "Avg Block Time": f"{chain_info.avg_block_time:.1f}s",
                "Avg Gas Used": f"{chain_info.avg_gas_used:,}",
                "Gas Price": f"{chain_info.gas_price / 1e9:.1f} gwei",
                "Growth Rate": f"{chain_info.growth_rate_mb_per_day:.1f}MB/day",
                "Memory Usage": f"{chain_info.memory_usage_mb:.1f}MB",
                "Disk Usage": f"{chain_info.disk_usage_mb:.1f}MB"
            }
            
            output(performance_info, ctx.obj.get('output_format', 'table'), title="Performance Metrics")
        
    except ChainNotFoundError:
        error(f"Chain {chain_id} not found")
        raise click.Abort()
    except Exception as e:
        error(f"Error getting chain info: {str(e)}")
        raise click.Abort()

@chain.command()
@click.argument('config_file', type=click.Path(exists=True))
@click.option('--node', help='Target node for chain creation')
@click.option('--dry-run', is_flag=True, help='Show what would be created without actually creating')
@click.pass_context
def create(ctx, config_file, node, dry_run):
    """Create a new chain from configuration file"""
    try:
        import yaml
        from models.chain import ChainConfig
        
        config = load_multichain_config()
        chain_manager = ChainManager(config)
        
        # Load and validate configuration
        with open(config_file, 'r') as f:
            config_data = yaml.safe_load(f)
        
        chain_config = ChainConfig(**config_data['chain'])
        
        if dry_run:
            dry_run_info = {
                "Chain Type": chain_config.type.value,
                "Purpose": chain_config.purpose,
                "Name": chain_config.name,
                "Description": chain_config.description or "No description",
                "Consensus": chain_config.consensus.algorithm.value,
                "Privacy": chain_config.privacy.visibility,
                "Target Node": node or "Auto-selected"
            }
            
            output(dry_run_info, ctx.obj.get('output_format', 'table'), title="Dry Run - Chain Creation")
            return
        
        # Create chain
        chain_id = chain_manager.create_chain(chain_config, node)
        
        success(f"Chain created successfully!")
        result = {
            "Chain ID": chain_id,
            "Type": chain_config.type.value,
            "Purpose": chain_config.purpose,
            "Name": chain_config.name,
            "Node": node or "Auto-selected"
        }
        
        output(result, ctx.obj.get('output_format', 'table'))
        
        if chain_config.privacy.visibility == "private":
            success("Private chain created! Use access codes to invite participants.")
        
    except Exception as e:
        error(f"Error creating chain: {str(e)}")
        raise click.Abort()

@chain.command()
@click.argument('chain_id')
@click.option('--force', is_flag=True, help='Force deletion without confirmation')
@click.option('--confirm', is_flag=True, help='Confirm deletion')
@click.pass_context
def delete(ctx, chain_id, force, confirm):
    """Delete a chain permanently"""
    try:
        config = load_multichain_config()
        chain_manager = ChainManager(config)
        
        # Get chain information for confirmation
        import asyncio
        chain_info = asyncio.run(chain_manager.get_chain_info(chain_id, detailed=True))
        
        if not force:
            # Show warning and confirmation
            warning_info = {
                "Chain ID": chain_id,
                "Type": chain_info.type.value,
                "Purpose": chain_info.purpose,
                "Name": chain_info.name,
                "Status": chain_info.status.value,
                "Participants": chain_info.client_count,
                "Transactions": "Multiple"  # Would get actual count
            }
            
            output(warning_info, ctx.obj.get('output_format', 'table'), title="Chain Deletion Warning")
            
            if not confirm:
                error("To confirm deletion, use --confirm flag")
                raise click.Abort()
        
        # Delete chain
        import asyncio
        is_success = asyncio.run(chain_manager.delete_chain(chain_id, force))
        
        if is_success:
            success(f"Chain {chain_id} deleted successfully!")
        else:
            error(f"Failed to delete chain {chain_id}")
            raise click.Abort()
        
    except ChainNotFoundError:
        error(f"Chain {chain_id} not found")
        raise click.Abort()
    except Exception as e:
        error(f"Error deleting chain: {str(e)}")
        raise click.Abort()

@chain.command()
@click.argument('chain_id')
@click.argument('node_id')
@click.pass_context
def add(ctx, chain_id, node_id):
    """Add a chain to a specific node"""
    try:
        config = load_multichain_config()
        chain_manager = ChainManager(config)
        
        import asyncio
        is_success = asyncio.run(chain_manager.add_chain_to_node(chain_id, node_id))
        
        if is_success:
            success(f"Chain {chain_id} added to node {node_id} successfully!")
        else:
            error(f"Failed to add chain {chain_id} to node {node_id}")
            raise click.Abort()
        
    except Exception as e:
        error(f"Error adding chain to node: {str(e)}")
        raise click.Abort()

@chain.command()
@click.argument('chain_id')
@click.argument('node_id')
@click.option('--migrate', is_flag=True, help='Migrate to another node before removal')
@click.pass_context
def remove(ctx, chain_id, node_id, migrate):
    """Remove a chain from a specific node"""
    try:
        config = load_multichain_config()
        chain_manager = ChainManager(config)
        
        is_success = chain_manager.remove_chain_from_node(chain_id, node_id, migrate)
        
        if is_success:
            success(f"Chain {chain_id} removed from node {node_id} successfully!")
        else:
            error(f"Failed to remove chain {chain_id} from node {node_id}")
            raise click.Abort()
        
    except Exception as e:
        error(f"Error removing chain from node: {str(e)}")
        raise click.Abort()

@chain.command()
@click.argument('chain_id')
@click.argument('from_node')
@click.argument('to_node')
@click.option('--dry-run', is_flag=True, help='Show migration plan without executing')
@click.option('--verify', is_flag=True, help='Verify migration after completion')
@click.pass_context
def migrate(ctx, chain_id, from_node, to_node, dry_run, verify):
    """Migrate a chain between nodes"""
    try:
        config = load_multichain_config()
        chain_manager = ChainManager(config)
        
        migration_result = chain_manager.migrate_chain(chain_id, from_node, to_node, dry_run)
        
        if dry_run:
            plan_info = {
                "Chain ID": chain_id,
                "Source Node": from_node,
                "Target Node": to_node,
                "Feasible": "Yes" if migration_result.success else "No",
                "Estimated Time": f"{migration_result.transfer_time_seconds}s",
                "Error": migration_result.error or "None"
            }
            
            output(plan_info, ctx.obj.get('output_format', 'table'), title="Migration Plan")
            return
        
        if migration_result.success:
            success(f"Chain migration completed successfully!")
            result = {
                "Chain ID": chain_id,
                "Source Node": from_node,
                "Target Node": to_node,
                "Blocks Transferred": migration_result.blocks_transferred,
                "Transfer Time": f"{migration_result.transfer_time_seconds}s",
                "Verification": "Passed" if migration_result.verification_passed else "Failed"
            }
            
            output(result, ctx.obj.get('output_format', 'table'))
        else:
            error(f"Migration failed: {migration_result.error}")
            raise click.Abort()
        
    except Exception as e:
        error(f"Error during migration: {str(e)}")
        raise click.Abort()

@chain.command()
@click.argument('chain_id')
@click.option('--path', help='Backup directory path')
@click.option('--compress', is_flag=True, help='Compress backup')
@click.option('--verify', is_flag=True, help='Verify backup integrity')
@click.pass_context
def backup(ctx, chain_id, path, compress, verify):
    """Backup chain data"""
    try:
        config = load_multichain_config()
        chain_manager = ChainManager(config)
        
        import asyncio
        backup_result = asyncio.run(chain_manager.backup_chain(chain_id, path, compress, verify))
        
        success(f"Chain backup completed successfully!")
        result = {
            "Chain ID": chain_id,
            "Backup File": backup_result.backup_file,
            "Original Size": f"{backup_result.original_size_mb:.1f}MB",
            "Backup Size": f"{backup_result.backup_size_mb:.1f}MB",
            "Compression": f"{backup_result.compression_ratio:.1f}x" if compress else "None",
            "Checksum": backup_result.checksum,
            "Verification": "Passed" if backup_result.verification_passed else "Failed"
        }
        
        output(result, ctx.obj.get('output_format', 'table'))
        
    except Exception as e:
        error(f"Error during backup: {str(e)}")
        raise click.Abort()

@chain.command()
@click.argument('backup_file', type=click.Path(exists=True))
@click.option('--node', help='Target node for restoration')
@click.option('--verify', is_flag=True, help='Verify restoration')
@click.pass_context
def restore(ctx, backup_file, node, verify):
    """Restore chain from backup"""
    try:
        config = load_multichain_config()
        chain_manager = ChainManager(config)
        
        import asyncio
        restore_result = asyncio.run(chain_manager.restore_chain(backup_file, node, verify))
        
        success(f"Chain restoration completed successfully!")
        result = {
            "Chain ID": restore_result.chain_id,
            "Node": restore_result.node_id,
            "Blocks Restored": restore_result.blocks_restored,
            "Verification": "Passed" if restore_result.verification_passed else "Failed"
        }
        
        output(result, ctx.obj.get('output_format', 'table'))
        
    except Exception as e:
        error(f"Error during restoration: {str(e)}")
        raise click.Abort()

@chain.command()
@click.argument('chain_id')
@click.option('--realtime', is_flag=True, help='Real-time monitoring')
@click.option('--export', help='Export monitoring data to file')
@click.option('--interval', default=5, help='Update interval in seconds')
@click.pass_context
def monitor(ctx, chain_id, realtime, export, interval):
    """Monitor chain activity"""
    try:
        config = load_multichain_config()
        chain_manager = ChainManager(config)
        
        if realtime:
            # Real-time monitoring (placeholder implementation)
            from rich.console import Console
            from rich.layout import Layout
            from rich.live import Live
            import time
            
            console = Console()
            
            def generate_monitor_layout():
                try:
                    import asyncio
                    chain_info = asyncio.run(chain_manager.get_chain_info(chain_id, detailed=True, metrics=True))
                    
                    layout = Layout()
                    layout.split_column(
                        Layout(name="header", size=3),
                        Layout(name="stats"),
                        Layout(name="activity", size=10)
                    )
                    
                    # Header
                    layout["header"].update(
                        f"Chain Monitor: {chain_id} - {chain_info.status.value.upper()}"
                    )
                    
                    # Stats table
                    stats_data = [
                        ["Block Height", str(chain_info.block_height)],
                        ["TPS", f"{chain_info.tps:.1f}"],
                        ["Active Nodes", str(chain_info.active_nodes)],
                        ["Gas Price", f"{chain_info.gas_price / 1e9:.1f} gwei"],
                        ["Memory Usage", f"{chain_info.memory_usage_mb:.1f}MB"],
                        ["Disk Usage", f"{chain_info.disk_usage_mb:.1f}MB"]
                    ]
                    
                    layout["stats"].update(str(stats_data))
                    
                    # Recent activity (placeholder)
                    layout["activity"].update("Recent activity would be displayed here")
                    
                    return layout
                except Exception as e:
                    return f"Error getting chain info: {e}"
            
            with Live(generate_monitor_layout(), refresh_per_second=1) as live:
                try:
                    while True:
                        live.update(generate_monitor_layout())
                        time.sleep(interval)
                except KeyboardInterrupt:
                    console.print("\n[yellow]Monitoring stopped by user[/yellow]")
        else:
            # Single snapshot
            import asyncio
            chain_info = asyncio.run(chain_manager.get_chain_info(chain_id, detailed=True, metrics=True))
            
            stats_data = [
                {
                    "Metric": "Block Height",
                    "Value": str(chain_info.block_height)
                },
                {
                    "Metric": "TPS",
                    "Value": f"{chain_info.tps:.1f}"
                },
                {
                    "Metric": "Active Nodes",
                    "Value": str(chain_info.active_nodes)
                },
                {
                    "Metric": "Gas Price",
                    "Value": f"{chain_info.gas_price / 1e9:.1f} gwei"
                },
                {
                    "Metric": "Memory Usage",
                    "Value": f"{chain_info.memory_usage_mb:.1f}MB"
                },
                {
                    "Metric": "Disk Usage",
                    "Value": f"{chain_info.disk_usage_mb:.1f}MB"
                }
            ]
            
            output(stats_data, ctx.obj.get('output_format', 'table'), title=f"Chain Statistics: {chain_id}")
            
            if export:
                import json
                with open(export, 'w') as f:
                    json.dump(chain_info.dict(), f, indent=2, default=str)
                success(f"Statistics exported to {export}")
        
    except ChainNotFoundError:
        error(f"Chain {chain_id} not found")
        raise click.Abort()
    except Exception as e:
        error(f"Error during monitoring: {str(e)}")
        raise click.Abort()
