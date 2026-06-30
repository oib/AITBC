"""Chain management commands for AITBC CLI"""

import click
from click import echo

from ..core.chain_manager import ChainManager, ChainNotFoundError
from ..core.config import load_multichain_config
from ..models.chain import ChainType
from ..utils import error, output, success
from ..utils.http_client import AITBCHTTPClient, NetworkError


@click.group()
def chain():
    """Multi-chain management commands"""
    pass


@chain.command()
@click.option(
    "--type", "chain_type", type=click.Choice(["main", "topic", "private", "all"]), default="all", help="Filter by chain type"
)
@click.option("--show-private", is_flag=True, help="Show private chains")
@click.option("--sort", type=click.Choice(["id", "size", "nodes", "created"]), default="id", help="Sort by field")
@click.pass_context
def list(ctx, chain_type, show_private, sort):
    """List all available chains"""
    try:
        config = load_multichain_config()
        chain_manager = ChainManager(config)

        # Get chains
        import asyncio

        chains = asyncio.run(
            chain_manager.list_chains(
                chain_type=ChainType(chain_type) if chain_type != "all" else None, include_private=show_private, sort_by=sort
            )
        )

        if not chains:
            output("No chains found", ctx.obj.get("output_format", "table"))
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
                "Status": chain.status.value,
            }
            for chain in chains
        ]

        output(chains_data, ctx.obj.get("output_format", "table"), title="Available Chains")

    except Exception as e:
        error(f"Error listing chains: {str(e)}")
        raise click.Abort() from e


@chain.command()
@click.option("--chain-id", help="Specific chain ID to check status (shows all if not specified)")
@click.option("--detailed", is_flag=True, help="Show detailed status information")
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
                "Total Nodes": chain_info.node_count,
            }

            if detailed:
                status_data.update(
                    {
                        "Consensus": chain_info.consensus_algorithm.value,
                        "TPS": f"{chain_info.tps:.1f}",
                        "Gas Price": f"{chain_info.gas_price / 1e9:.1f} gwei",
                        "Memory Usage": f"{chain_info.memory_usage_mb:.1f}MB",
                    }
                )

            output(status_data, ctx.obj.get("output_format", "table"), title=f"Chain Status: {chain_id}")
        else:
            # Get all chains status
            chains = asyncio.run(chain_manager.list_chains())

            if not chains:
                output({"message": "No chains found"}, ctx.obj.get("output_format", "table"))
                return

            status_list = []
            for chain in chains:
                status_info = {
                    "Chain ID": chain.id,
                    "Name": chain.name,
                    "Type": chain.type.value,
                    "Status": chain.status.value,
                    "Block Height": chain.block_height,
                    "Active Nodes": chain.active_nodes,
                }
                status_list.append(status_info)

            # Simple output without formatting
            echo(status_list)

    except ChainNotFoundError:
        error(f"Chain {chain_id} not found")
        raise click.Abort() from None
    except Exception as e:
        error(f"Error getting chain status: {str(e)}")
        raise click.Abort() from e


@chain.command()
@click.argument("chain_id")
@click.option("--detailed", is_flag=True, help="Show detailed information")
@click.option("--metrics", is_flag=True, help="Show performance metrics")
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
            "Size": f"{chain_info.size_mb:.1f}MB",
        }

        output(basic_info, ctx.obj.get("output_format", "table"), title=f"Chain Information: {chain_id}")

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
                "Access Control": chain_info.privacy.access_control,
            }

            output(network_info, ctx.obj.get("output_format", "table"), title="Network Details")

        if metrics:
            # Performance metrics
            performance_info = {
                "TPS": f"{chain_info.tps:.1f}",
                "Avg Block Time": f"{chain_info.avg_block_time:.1f}s",
                "Avg Gas Used": f"{chain_info.avg_gas_used:,}",
                "Gas Price": f"{chain_info.gas_price / 1e9:.1f} gwei",
                "Growth Rate": f"{chain_info.growth_rate_mb_per_day:.1f}MB/day",
                "Memory Usage": f"{chain_info.memory_usage_mb:.1f}MB",
                "Disk Usage": f"{chain_info.disk_usage_mb:.1f}MB",
            }

            output(performance_info, ctx.obj.get("output_format", "table"), title="Performance Metrics")

    except ChainNotFoundError:
        error(f"Chain {chain_id} not found")
        raise click.Abort() from None
    except Exception as e:
        error(f"Error getting chain info: {str(e)}")
        raise click.Abort() from e


@chain.command()
@click.argument("config_file", type=click.Path(exists=True))
@click.option("--node", help="Target node for chain creation")
@click.option("--dry-run", is_flag=True, help="Show what would be created without actually creating")
@click.pass_context
def create(ctx, config_file, node, dry_run):
    """Create a new chain from configuration file"""
    try:
        import yaml

        from ..models.chain import ChainConfig

        config = load_multichain_config()
        chain_manager = ChainManager(config)

        # Load and validate configuration
        with open(config_file) as f:
            config_data = yaml.safe_load(f)

        chain_config = ChainConfig(**config_data["chain"])

        if dry_run:
            dry_run_info = {
                "Chain Type": chain_config.type.value,
                "Purpose": chain_config.purpose,
                "Name": chain_config.name,
                "Description": chain_config.description or "No description",
                "Consensus": chain_config.consensus.algorithm.value,
                "Privacy": chain_config.privacy.visibility,
                "Target Node": node or "Auto-selected",
            }

            output(dry_run_info, ctx.obj.get("output_format", "table"), title="Dry Run - Chain Creation")
            return

        # Create chain
        chain_id = chain_manager.create_chain(chain_config, node)

        success("Chain created successfully!")
        result = {
            "Chain ID": chain_id,
            "Type": chain_config.type.value,
            "Purpose": chain_config.purpose,
            "Name": chain_config.name,
            "Node": node or "Auto-selected",
        }

        output(result, ctx.obj.get("output_format", "table"))

        if chain_config.privacy.visibility == "private":
            success("Private chain created! Use access codes to invite participants.")

    except Exception as e:
        error(f"Error creating chain: {str(e)}")
        raise click.Abort() from e


@chain.command()
@click.argument("chain_id")
@click.option("--force", is_flag=True, help="Force deletion without confirmation")
@click.option("--confirm", is_flag=True, help="Confirm deletion")
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
                "Transactions": "Multiple",  # Would get actual count
            }

            output(warning_info, ctx.obj.get("output_format", "table"), title="Chain Deletion Warning")

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
        raise click.Abort() from None
    except Exception as e:
        error(f"Error deleting chain: {str(e)}")
        raise click.Abort() from e


@chain.command()
@click.argument("chain_id")
@click.argument("node_id")
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
        raise click.Abort() from e


@chain.command()
@click.argument("chain_id")
@click.argument("node_id")
@click.option("--migrate", is_flag=True, help="Migrate to another node before removal")
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
        raise click.Abort() from e


@chain.command()
@click.argument("chain_id")
@click.argument("from_node")
@click.argument("to_node")
@click.option("--dry-run", is_flag=True, help="Show migration plan without executing")
@click.option("--verify", is_flag=True, help="Verify migration after completion")
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
                "Error": migration_result.error or "None",
            }

            output(plan_info, ctx.obj.get("output_format", "table"), title="Migration Plan")
            return

        if migration_result.success:
            success("Chain migration completed successfully!")
            result = {
                "Chain ID": chain_id,
                "Source Node": from_node,
                "Target Node": to_node,
                "Blocks Transferred": migration_result.blocks_transferred,
                "Transfer Time": f"{migration_result.transfer_time_seconds}s",
                "Verification": "Passed" if migration_result.verification_passed else "Failed",
            }

            output(result, ctx.obj.get("output_format", "table"))
        else:
            error(f"Migration failed: {migration_result.error}")
            raise click.Abort()

    except Exception as e:
        error(f"Error during migration: {str(e)}")
        raise click.Abort() from e


@chain.command()
@click.argument("chain_id")
@click.option("--path", help="Backup directory path")
@click.option("--compress", is_flag=True, help="Compress backup")
@click.option("--verify", is_flag=True, help="Verify backup integrity")
@click.pass_context
def backup(ctx, chain_id, path, compress, verify):
    """Backup chain data"""
    try:
        config = load_multichain_config()
        chain_manager = ChainManager(config)

        import asyncio

        backup_result = asyncio.run(chain_manager.backup_chain(chain_id, path, compress, verify))

        success("Chain backup completed successfully!")
        result = {
            "Chain ID": chain_id,
            "Backup File": backup_result.backup_file,
            "Original Size": f"{backup_result.original_size_mb:.1f}MB",
            "Backup Size": f"{backup_result.backup_size_mb:.1f}MB",
            "Compression": f"{backup_result.compression_ratio:.1f}x" if compress else "None",
            "Checksum": backup_result.checksum,
            "Verification": "Passed" if backup_result.verification_passed else "Failed",
        }

        output(result, ctx.obj.get("output_format", "table"))

    except Exception as e:
        error(f"Error during backup: {str(e)}")
        raise click.Abort() from e


@chain.command()
@click.argument("backup_file", type=click.Path(exists=True))
@click.option("--node", help="Target node for restoration")
@click.option("--verify", is_flag=True, help="Verify restoration")
@click.pass_context
def restore(ctx, backup_file, node, verify):
    """Restore chain from backup"""
    try:
        config = load_multichain_config()
        chain_manager = ChainManager(config)

        import asyncio

        restore_result = asyncio.run(chain_manager.restore_chain(backup_file, node, verify))

        success("Chain restoration completed successfully!")
        result = {
            "Chain ID": restore_result.chain_id,
            "Node": restore_result.node_id,
            "Blocks Restored": restore_result.blocks_restored,
            "Verification": "Passed" if restore_result.verification_passed else "Failed",
        }

        output(result, ctx.obj.get("output_format", "table"))

    except Exception as e:
        error(f"Error during restoration: {str(e)}")
        raise click.Abort() from e


@chain.command()
@click.argument("chain_id")
@click.option("--realtime", is_flag=True, help="Real-time monitoring")
@click.option("--export", help="Export monitoring data to file")
@click.option("--interval", default=5, help="Update interval in seconds")
@click.pass_context
def monitor(ctx, chain_id, realtime, export, interval):
    """Monitor chain activity"""
    try:
        config = load_multichain_config()
        chain_manager = ChainManager(config)

        if realtime:
            # Real-time monitoring (placeholder implementation)
            import time

            from rich.console import Console
            from rich.layout import Layout
            from rich.live import Live

            console = Console()

            def generate_monitor_layout():
                try:
                    import asyncio

                    chain_info = asyncio.run(chain_manager.get_chain_info(chain_id, detailed=True, metrics=True))

                    layout = Layout()
                    layout.split_column(Layout(name="header", size=3), Layout(name="stats"), Layout(name="activity", size=10))

                    # Header
                    layout["header"].update(f"Chain Monitor: {chain_id} - {chain_info.status.value.upper()}")

                    # Stats table
                    stats_data = [
                        ["Block Height", str(chain_info.block_height)],
                        ["TPS", f"{chain_info.tps:.1f}"],
                        ["Active Nodes", str(chain_info.active_nodes)],
                        ["Gas Price", f"{chain_info.gas_price / 1e9:.1f} gwei"],
                        ["Memory Usage", f"{chain_info.memory_usage_mb:.1f}MB"],
                        ["Disk Usage", f"{chain_info.disk_usage_mb:.1f}MB"],
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
                    console.click.echo("\n[yellow]Monitoring stopped by user[/yellow]")
        else:
            # Single snapshot
            import asyncio

            chain_info = asyncio.run(chain_manager.get_chain_info(chain_id, detailed=True, metrics=True))

            stats_data = [
                {"Metric": "Block Height", "Value": str(chain_info.block_height)},
                {"Metric": "TPS", "Value": f"{chain_info.tps:.1f}"},
                {"Metric": "Active Nodes", "Value": str(chain_info.active_nodes)},
                {"Metric": "Gas Price", "Value": f"{chain_info.gas_price / 1e9:.1f} gwei"},
                {"Metric": "Memory Usage", "Value": f"{chain_info.memory_usage_mb:.1f}MB"},
                {"Metric": "Disk Usage", "Value": f"{chain_info.disk_usage_mb:.1f}MB"},
            ]

            output(stats_data, ctx.obj.get("output_format", "table"), title=f"Chain Statistics: {chain_id}")

            if export:
                import json

                with open(export, "w") as f:
                    json.dump(chain_info.dict(), f, indent=2, default=str)
                success(f"Statistics exported to {export}")

    except ChainNotFoundError:
        error(f"Chain {chain_id} not found")
        raise click.Abort() from None
    except Exception as e:
        error(f"Error during monitoring: {str(e)}")
        raise click.Abort() from e


@chain.command(name="sync-status")
@click.option("--node-url", default="http://127.0.0.1:8202", help="Local node RPC URL")
@click.option("--all-chains", is_flag=True, help="Show status for all supported chains (default: node's configured chains)")
@click.option("--chain-id", default=None, help="Show status for a specific chain only")
@click.pass_context
def sync_status(ctx, node_url, all_chains, chain_id):
    """Show synchronization status per chain (block height, last hash, sync source).

    Queries the local node's /head and /network-info endpoints. When --all-chains
    is set, iterates over every chain in the node's supported_chains list and
    reports per-chain sync status. Use --chain-id to check a single chain.
    """
    client = AITBCHTTPClient(base_url=node_url)
    try:
        network_info = client.get("/network-info")
    except NetworkError as e:
        error(f"Cannot connect to node at {node_url}: {e}")
        raise click.Abort() from e
    finally:
        client.close()

    if isinstance(network_info, dict) and network_info.get("error"):
        error(f"Error from /network-info: {network_info['error']}")
        raise click.Abort()

    # Determine which chains to query
    if chain_id:
        chains_to_check = [chain_id]
    elif all_chains or not network_info.get("supported_chains"):
        # Use supported_chains from network-info, fall back to node's chain_id
        chains_to_check = network_info.get("supported_chains") or [network_info.get("chain_id", "unknown")]
    else:
        chains_to_check = network_info.get("supported_chains") or [network_info.get("chain_id", "unknown")]

    p2p_endpoint = network_info.get("p2p_endpoint", "N/A")

    # Query /head for each chain
    rows = []
    client = AITBCHTTPClient(base_url=node_url)
    try:
        for cid in chains_to_check:
            try:
                head = client.get("/head", params={"chain_id": cid})
            except NetworkError:
                rows.append(
                    {
                        "Chain ID": cid,
                        "Height": "N/A",
                        "Last Block Hash": "N/A",
                        "Timestamp": "N/A",
                        "Sync Source": p2p_endpoint,
                    }
                )
                continue

            if isinstance(head, dict) and head.get("error"):
                rows.append(
                    {
                        "Chain ID": cid,
                        "Height": "N/A",
                        "Last Block Hash": "N/A",
                        "Timestamp": "N/A",
                        "Sync Source": p2p_endpoint,
                    }
                )
                continue

            block_hash = head.get("hash") or head.get("last_block_hash") or "N/A"
            truncated_hash = f"{block_hash[:16]}..." if block_hash and block_hash != "N/A" else "N/A"
            rows.append(
                {
                    "Chain ID": cid,
                    "Height": str(head.get("height", "N/A")),
                    "Last Block Hash": truncated_hash,
                    "Timestamp": str(head.get("timestamp", "N/A")),
                    "Sync Source": p2p_endpoint,
                }
            )
    finally:
        client.close()

    output(rows, ctx.obj.get("output_format", "table"), title="Chain Sync Status")


@chain.command(name="start")
@click.argument("chain_id")
@click.option("--node-url", default="http://127.0.0.1:8202", help="Local node RPC URL")
@click.option("--type", "chain_type", type=click.Choice(["bilateral", "micro"]), default="micro", help="Chain type")
@click.pass_context
def start_cmd(ctx, chain_id, node_url, chain_type):
    """Start a secondary chain on the local node (v0.6.4).

    Sends a POST /chains/start request to the node's MultiChainManager.
    The chain must not already be running and must not be the default chain.
    """
    client = AITBCHTTPClient(base_url=node_url)
    try:
        result = client.post("/chains/start", json={"chain_id": chain_id, "chain_type": chain_type})
    except NetworkError as e:
        error(f"Cannot connect to node at {node_url}: {e}")
        raise click.Abort() from e
    finally:
        client.close()

    if result.get("success"):
        success(f"Chain {chain_id} started successfully")
    else:
        error(f"Failed to start chain {chain_id}: {result.get('message', 'unknown error')}")
        raise click.Abort()


@chain.command(name="stop")
@click.argument("chain_id")
@click.option("--node-url", default="http://127.0.0.1:8202", help="Local node RPC URL")
@click.pass_context
def stop_cmd(ctx, chain_id, node_url):
    """Stop a secondary chain on the local node (v0.6.4).

    Sends a POST /chains/stop request to the node's MultiChainManager.
    The default chain cannot be stopped.
    """
    client = AITBCHTTPClient(base_url=node_url)
    try:
        result = client.post("/chains/stop", json={"chain_id": chain_id, "chain_type": "micro"})
    except NetworkError as e:
        error(f"Cannot connect to node at {node_url}: {e}")
        raise click.Abort() from e
    finally:
        client.close()

    if result.get("success"):
        success(f"Chain {chain_id} stopped successfully")
    else:
        error(f"Failed to stop chain {chain_id}: {result.get('message', 'unknown error')}")
        raise click.Abort()


@chain.command(name="instances")
@click.option("--node-url", default="http://127.0.0.1:8202", help="Local node RPC URL")
@click.option("--island", default=None, help="Filter chains by island ID")
@click.pass_context
def instances_cmd(ctx, node_url, island):
    """List all chain instances on the local node (v0.6.4).

    Queries the node's /chains endpoint (MultiChainManager) for all chain
    instances and their status. Use --island to filter by island ID.
    """
    client = AITBCHTTPClient(base_url=node_url)
    try:
        result = client.get("/chains")
    except NetworkError as e:
        error(f"Cannot connect to node at {node_url}: {e}")
        raise click.Abort() from e
    finally:
        client.close()

    chains = result.get("chains", [])
    if island:
        # Filter by island — chain_id typically contains island prefix
        chains = [c for c in chains if island in c.get("chain_id", "")]

    if not chains:
        output("No chains found", ctx.obj.get("output_format", "table"))
        return

    rows = [
        {
            "Chain ID": c.get("chain_id", "N/A"),
            "Type": c.get("chain_type", "N/A"),
            "Status": c.get("status", "N/A"),
            "RPC Port": c.get("rpc_port", "N/A"),
            "P2P Port": c.get("p2p_port", "N/A"),
            "Error": c.get("error_message") or "",
        }
        for c in chains
    ]
    output(rows, ctx.obj.get("output_format", "table"), title="Chain Instances")


# ============================================================================
# v0.7.4 §B8: Consensus CLI commands
# ============================================================================


@chain.group(name="consensus")
def consensus_group():
    """Consensus-related commands (v0.7.4)"""
    pass


@consensus_group.command(name="status")
@click.option("--node-url", default="http://localhost:8202", help="Blockchain node RPC URL")
@click.option("--chain-id", default="ait-hub", help="Chain ID to query consensus status for")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def consensus_status(ctx, node_url: str, chain_id: str, format: str):
    """Show consensus mode, view, sequence, epoch, and fault tolerance (v0.7.5)"""
    try:
        client = AITBCHTTPClient(base_url=node_url, timeout=10)
        try:
            result = client.get(f"/rpc/consensus/status?chain_id={chain_id}")
        except NetworkError:
            result = {}
        finally:
            client.close()

        consensus_info = {
            "mode": result.get("mode", "PoA (single proposer)"),
            "multi_validator_enabled": result.get("multi_validator_enabled", False),
            "chain_id": chain_id,
            "current_view": result.get("current_view", 0),
            "current_sequence": result.get("current_sequence", 0),
            "current_epoch": result.get("current_epoch", 0),
            "fault_tolerance": result.get("fault_tolerance", 0),
            "required_messages": result.get("required_messages", 0),
            "active_validators": result.get("active_validators", 0),
            "total_validators": result.get("total_validators", 0),
            "node_url": node_url,
        }
        output(consensus_info, ctx.obj.get("output_format", format), title="Consensus Status")
    except Exception as e:
        error(f"Error getting consensus status: {e}")


@consensus_group.command(name="validators")
@click.option("--node-url", default="http://localhost:8202", help="Blockchain node RPC URL")
@click.option("--chain-id", default="ait-hub", help="Chain ID to query validators for")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def consensus_validators(ctx, node_url: str, chain_id: str, format: str):
    """List active validators (address, stake, reputation, role, last_proposed) (v0.7.5)"""
    try:
        client = AITBCHTTPClient(base_url=node_url, timeout=10)
        try:
            result = client.get(f"/rpc/consensus/validators?chain_id={chain_id}")
        except NetworkError as e:
            error(f"Cannot connect to node at {node_url}: {e}")
            return
        finally:
            client.close()

        validators = result.get("validators", [])
        if not validators:
            output(f"No validators registered for chain {chain_id}", ctx.obj.get("output_format", format))
            return

        rows = [
            {
                "Address": v.get("address", "N/A"),
                "Stake": v.get("stake", "N/A"),
                "Reputation": v.get("reputation", "N/A"),
                "Role": v.get("role", "N/A"),
                "Active": v.get("is_active", "N/A"),
                "Last Proposed": v.get("last_proposed", "N/A"),
            }
            for v in validators
        ]
        output(rows, ctx.obj.get("output_format", format), title=f"Validators for {chain_id}")
    except Exception as e:
        error(f"Error listing validators: {e}")


@consensus_group.command(name="slashing-history")
@click.option("--node-url", default="http://localhost:8202", help="Blockchain node RPC URL")
@click.option("--chain-id", default="ait-hub", help="Chain ID to query slashing history for")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def consensus_slashing_history(ctx, node_url: str, chain_id: str, format: str):
    """Show slashing events (validator, condition, amount, block height) (v0.7.5)"""
    try:
        client = AITBCHTTPClient(base_url=node_url, timeout=10)
        try:
            result = client.get(f"/rpc/consensus/slashing-history?chain_id={chain_id}")
        except NetworkError as e:
            error(f"Cannot connect to node at {node_url}: {e}")
            return
        finally:
            client.close()

        events = result.get("slashing_events", [])
        if not events:
            output(f"No slashing events for chain {chain_id}", ctx.obj.get("output_format", format))
            return

        rows = [
            {
                "Validator": e.get("validator_address", "N/A"),
                "Condition": e.get("condition", "N/A"),
                "Amount": e.get("slash_amount", "N/A"),
                "Block Height": e.get("block_height", "N/A"),
                "Timestamp": e.get("timestamp", "N/A"),
            }
            for e in events
        ]
        output(rows, ctx.obj.get("output_format", format), title=f"Slashing History for {chain_id}")
    except Exception as e:
        error(f"Error getting slashing history: {e}")
