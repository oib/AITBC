"""Chain management commands for AITBC CLI"""

import click
from click import echo

from ..core.chain_manager import ChainManager, ChainNotFoundError
from ..core.config import load_multichain_config
from ..models.chain import ChainType
from ..utils import OUTPUT_FORMAT_OPTION, error, output, resolve_output_format, success
from ..utils.error_handling import abort
from ..utils.http_client import AITBCHTTPClient, NetworkError, get_logger

logger = get_logger(__name__)


@click.group(
    epilog="""Examples:

  aitbc blockchain list

  aitbc blockchain status --chain-id ait-mainnet"""
)
def chain():
    """Manage AITBC blockchains: list, create, migrate, backup, monitor, and control nodes."""
    pass


@chain.command(
    epilog="""Examples:

  aitbc blockchain list

  aitbc blockchain list --type main --sort nodes"""
)
@click.option(
    "--type", "chain_type", type=click.Choice(["main", "topic", "private", "all"]), default="all", help="Filter by chain type"
)
@click.option("--show-private", is_flag=True, help="Show private chains")
@click.option("--sort", type=click.Choice(["id", "size", "nodes", "created"]), default="id", help="Sort by field")
@click.option(
    "--island",
    is_flag=False,
    flag_value="__LIST__",
    default=None,
    help="List attached islands when used without a value; with a value, filter chains by island ID (substring match on chain ID).",
)
@click.option("--node-url", default="http://127.0.0.1:8202", help="Local node RPC URL (used with --island)")
@click.pass_context
def list(ctx, chain_type, show_private, sort, island, node_url):
    """List all available chains with optional type, island, and sorting filters."""
    import asyncio

    # Bare --island: list attached islands from the node
    if island == "__LIST__":
        client = AITBCHTTPClient(base_url=node_url)
        try:
            result = client.get("/rpc/islands")
        except NetworkError as e:
            abort(ctx, f"Cannot connect to node at {node_url}: {e}", from_exception=e)
        finally:
            client.close()

        islands = result.get("islands", [])
        if not islands:
            output("No islands found", ctx.obj.get("output_format", "table"))
            return

        islands_data = [
            {
                "Island ID": isl.get("island_id", "N/A"),
                "Island Name": isl.get("island_name", "N/A"),
                "Chain ID": isl.get("chain_id", "N/A"),
                "Chain IDs": ", ".join(isl.get("chain_ids", [])) if isl.get("chain_ids") else isl.get("chain_id", "N/A"),
                "Status": isl.get("status", "N/A"),
                "Role": isl.get("role", "N/A"),
                "Peer Count": isl.get("peer_count", 0),
                "Is Hub": isl.get("is_hub", False),
            }
            for isl in islands
        ]
        output(islands_data, ctx.obj.get("output_format", "table"), title="Attached Islands")
        return

    try:
        config = load_multichain_config()
        chain_manager = ChainManager(config)

        # Get chains
        chains = asyncio.run(
            chain_manager.list_chains(
                chain_type=ChainType(chain_type) if chain_type != "all" else None,
                include_private=show_private,
                sort_by=sort,
            )
        )

        # Filter by island — chain_id typically contains island prefix
        if island:
            chains = [c for c in chains if island in c.id]

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
        abort(ctx, f"Error listing chains: {str(e)}", from_exception=e)


@chain.command(
    epilog="""Examples:

  aitbc blockchain status --chain-id ait-mainnet

  aitbc blockchain status --chain-id ait-mainnet --detailed --metrics"""
)
@click.option("--chain-id", help="Specific chain ID to check status (shows all if not specified)")
@click.option("--detailed", is_flag=True, help="Show detailed status information")
@click.pass_context
def status(ctx, chain_id, detailed):
    """Check the status and optional details or metrics of a chain."""
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
        abort(ctx, f"Chain {chain_id} not found")
    except Exception as e:
        abort(ctx, f"Error getting chain status: {str(e)}", from_exception=e)


@chain.command(
    epilog="""Examples:

  aitbc blockchain info --chain-id ait-mainnet

  aitbc blockchain info --chain-id ait-mainnet --detailed --metrics"""
)
@click.option("--chain-id", "chain_id", required=True, help="The Chain id.")
@click.option("--detailed", is_flag=True, help="Show detailed information")
@click.option("--metrics", is_flag=True, help="Show performance metrics")
@click.pass_context
def info(ctx, chain_id, detailed, metrics):
    """Get detailed information and optional metrics about a chain."""
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
        abort(ctx, f"Chain {chain_id} not found")
    except Exception as e:
        abort(ctx, f"Error getting chain info: {str(e)}", from_exception=e)


@chain.command(
    epilog="""Examples:

  aitbc blockchain create --config-file /tmp/chain.json

  aitbc blockchain create --config-file /tmp/chain.json --dry-run"""
)
@click.option("--config-file", "config_file", required=True, type=click.Path(exists=True), help="The Config file.")
@click.option("--node", help="Target node for chain creation")
@click.option("--dry-run", is_flag=True, help="Show what would be created without actually creating")
@click.pass_context
def create(ctx, config_file, node, dry_run):
    """Create a new chain from a JSON configuration file."""
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
        abort(ctx, f"Error creating chain: {str(e)}", from_exception=e)


@chain.command(
    epilog="""Examples:

  aitbc blockchain delete --chain-id ait-mainnet --confirm

  aitbc blockchain delete --chain-id ait-mainnet --force"""
)
@click.option("--chain-id", "chain_id", required=True, help="The Chain id.")
@click.option("--force", is_flag=True, help="Force deletion without confirmation")
@click.option("--confirm", is_flag=True, help="Confirm deletion")
@click.pass_context
def delete(ctx, chain_id, force, confirm):
    """Delete a chain permanently after confirmation."""
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
                abort(ctx, "To confirm deletion, use --confirm flag")

        # Delete chain
        import asyncio

        is_success = asyncio.run(chain_manager.delete_chain(chain_id, force))

        if is_success:
            success(f"Chain {chain_id} deleted successfully!")
        else:
            abort(ctx, f"Failed to delete chain {chain_id}")

    except ChainNotFoundError:
        abort(ctx, f"Chain {chain_id} not found")
    except Exception as e:
        abort(ctx, f"Error deleting chain: {str(e)}", from_exception=e)


@chain.command(
    epilog="""Examples:

  aitbc blockchain add --chain-id ait-mainnet --node-id node-1"""
)
@click.option("--chain-id", "chain_id", required=True, help="The Chain id.")
@click.option("--node-id", "node_id", required=True, help="The Node id.")
@click.pass_context
def add(ctx, chain_id, node_id):
    """Add a chain to a specific node."""
    try:
        config = load_multichain_config()
        chain_manager = ChainManager(config)

        import asyncio

        is_success = asyncio.run(chain_manager.add_chain_to_node(chain_id, node_id))

        if is_success:
            success(f"Chain {chain_id} added to node {node_id} successfully!")
        else:
            abort(ctx, f"Failed to add chain {chain_id} to node {node_id}")

    except Exception as e:
        abort(ctx, f"Error adding chain to node: {str(e)}", from_exception=e)


@chain.command(
    epilog="""Examples:

  aitbc blockchain remove --chain-id ait-mainnet --node-id node-1

  aitbc blockchain remove --chain-id ait-mainnet --node-id node-1 --migrate"""
)
@click.option("--chain-id", "chain_id", required=True, help="The Chain id.")
@click.option("--node-id", "node_id", required=True, help="The Node id.")
@click.option("--migrate", is_flag=True, help="Migrate to another node before removal")
@click.pass_context
def remove(ctx, chain_id, node_id, migrate):
    """Remove a chain from a specific node, optionally migrating first."""
    try:
        config = load_multichain_config()
        chain_manager = ChainManager(config)

        is_success = chain_manager.remove_chain_from_node(chain_id, node_id, migrate)

        if is_success:
            success(f"Chain {chain_id} removed from node {node_id} successfully!")
        else:
            abort(ctx, f"Failed to remove chain {chain_id} from node {node_id}")

    except Exception as e:
        abort(ctx, f"Error removing chain from node: {str(e)}", from_exception=e)


@chain.command(
    epilog="""Examples:

  aitbc blockchain migrate --chain-id ait-mainnet --from-node node-1 --to-node node-2

  aitbc blockchain migrate --chain-id ait-mainnet --from-node node-1 --to-node node-2 --dry-run"""
)
@click.option("--chain-id", "chain_id", required=True, help="The Chain id.")
@click.option("--from-node", "from_node", required=True, help="The From node.")
@click.option("--to-node", "to_node", required=True, help="The To node.")
@click.option("--dry-run", is_flag=True, help="Show migration plan without executing")
@click.option("--verify", is_flag=True, help="Verify migration after completion")
@click.pass_context
def migrate(ctx, chain_id, from_node, to_node, dry_run, verify):
    """Migrate a chain between two nodes with optional dry-run and verify."""
    try:
        config = load_multichain_config()
        chain_manager = ChainManager(config)

        import asyncio

        migration_result = asyncio.run(chain_manager.migrate_chain(chain_id, from_node, to_node, dry_run))

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
            abort(ctx, f"Migration failed: {migration_result.error}")

    except Exception as e:
        abort(ctx, f"Error during migration: {str(e)}", from_exception=e)


@chain.command(
    epilog="""Examples:

  aitbc blockchain backup --chain-id ait-mainnet

  aitbc blockchain backup --chain-id ait-mainnet --path /var/backups --compress --verify"""
)
@click.option("--chain-id", "chain_id", required=True, help="The Chain id.")
@click.option("--path", help="Backup directory path")
@click.option("--compress", is_flag=True, help="Compress backup")
@click.option("--verify", is_flag=True, help="Verify backup integrity")
@click.pass_context
def backup(ctx, chain_id, path, compress, verify):
    """Back up chain data to a directory with optional compression and verify."""
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
        abort(ctx, f"Error during backup: {str(e)}", from_exception=e)


@chain.command(
    epilog="""Examples:

  aitbc blockchain restore --backup-file /tmp/backup.tar

  aitbc blockchain restore --backup-file /tmp/backup.tar --node aitbc3"""
)
@click.option("--backup-file", "backup_file", required=True, type=click.Path(exists=True), help="The Backup file.")
@click.option("--node", help="Target node for restoration")
@click.option("--verify", is_flag=True, help="Verify restoration")
@click.pass_context
def restore(ctx, backup_file, node, verify):
    """Restore a chain from a backup file on a target node."""
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
        abort(ctx, f"Error during restoration: {str(e)}", from_exception=e)


@chain.command(
    epilog="""Examples:

  aitbc blockchain monitor --chain-id ait-mainnet

  aitbc blockchain monitor --chain-id ait-mainnet --realtime --interval 10"""
)
@click.option("--chain-id", "chain_id", required=True, help="The Chain id.")
@click.option("--realtime", is_flag=True, help="Real-time monitoring")
@click.option("--export", help="Export monitoring data to file")
@click.option("--interval", default=5, help="Update interval in seconds")
@click.pass_context
def monitor(ctx, chain_id, realtime, export, interval):
    """Monitor chain activity in real time or export snapshots."""
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
                    logger.warning("Error getting chain info: %s", e, exc_info=True)
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
        abort(ctx, f"Chain {chain_id} not found")
    except Exception as e:
        abort(ctx, f"Error during monitoring: {str(e)}", from_exception=e)


@chain.command(
    name="sync-status",
    epilog="""Examples:

  aitbc blockchain sync-status

  aitbc blockchain sync-status --chain-id ait-mainnet --node-url http://aitbc3:8202""",
)
@click.option("--node-url", default="http://127.0.0.1:8202", help="Local node RPC URL")
@click.option("--all-chains", is_flag=True, help="Show status for all supported chains (default: node's configured chains)")
@click.option("--chain-id", default=None, help="Show status for a specific chain only")
@click.pass_context
def sync_status(ctx, node_url, all_chains, chain_id):
    """Show synchronization status per chain and connected node."""
    client = AITBCHTTPClient(base_url=node_url)
    try:
        network_info = client.get("/rpc/network-info")
    except NetworkError as e:
        abort(ctx, f"Cannot connect to node at {node_url}: {e}", from_exception=e)
    finally:
        client.close()

    if isinstance(network_info, dict) and network_info.get("error"):
        abort(ctx, f"Error from /rpc/network-info: {network_info['error']}")

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
                head = client.get("/rpc/head", params={"chain_id": cid})
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


@chain.command(
    name="start",
    epilog="""Examples:

  aitbc blockchain start --chain-id ait-mainnet

  aitbc blockchain start --chain-id ait-mainnet --type micro""",
)
@click.option("--chain-id", "chain_id", required=True, help="The Chain id.")
@click.option("--node-url", default="http://127.0.0.1:8202", help="Local node RPC URL")
@click.option("--type", "chain_type", type=click.Choice(["bilateral", "micro"]), default="micro", help="Chain type")
@click.pass_context
def start_cmd(ctx, chain_id, node_url, chain_type):
    """Start a secondary chain on the local node."""
    client = AITBCHTTPClient(base_url=node_url)
    try:
        result = client.post("/rpc/chains/start", json={"chain_id": chain_id, "chain_type": chain_type})
    except NetworkError as e:
        abort(ctx, f"Cannot connect to node at {node_url}: {e}", from_exception=e)
    finally:
        client.close()

    if result.get("success"):
        success(f"Chain {chain_id} started successfully")
    else:
        abort(ctx, f"Failed to start chain {chain_id}: {result.get('message', 'unknown error')}")


@chain.command(
    name="stop",
    epilog="""Examples:

  aitbc blockchain stop --chain-id ait-mainnet

  aitbc blockchain stop --chain-id ait-mainnet --node-url http://aitbc3:8202""",
)
@click.option("--chain-id", "chain_id", required=True, help="The Chain id.")
@click.option("--node-url", default="http://127.0.0.1:8202", help="Local node RPC URL")
@click.pass_context
def stop_cmd(ctx, chain_id, node_url):
    """Stop a secondary chain on the local node."""
    client = AITBCHTTPClient(base_url=node_url)
    try:
        result = client.post("/rpc/chains/stop", json={"chain_id": chain_id, "chain_type": "micro"})
    except NetworkError as e:
        abort(ctx, f"Cannot connect to node at {node_url}: {e}", from_exception=e)
    finally:
        client.close()

    if result.get("success"):
        success(f"Chain {chain_id} stopped successfully")
    else:
        abort(ctx, f"Failed to stop chain {chain_id}: {result.get('message', 'unknown error')}")


@chain.command(
    name="instances",
    epilog="""Examples:

  aitbc blockchain instances

  aitbc blockchain instances --island island-1""",
)
@click.option("--node-url", default="http://127.0.0.1:8202", help="Local node RPC URL")
@click.option("--island", default=None, help="Filter chains by island ID")
@click.pass_context
def instances_cmd(ctx, node_url, island):
    """List all chain instances on the local node."""
    client = AITBCHTTPClient(base_url=node_url)
    try:
        result = client.get("/rpc/chains")
    except NetworkError as e:
        abort(ctx, f"Cannot connect to node at {node_url}: {e}", from_exception=e)
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


@chain.group(
    name="consensus",
    epilog="""Examples:

  aitbc blockchain consensus status --chain-id ait-mainnet

  aitbc blockchain consensus validators --chain-id ait-mainnet""",
)
def consensus_group():
    """Inspect consensus status, validators, and slashing history for a chain."""
    pass


@consensus_group.command(
    name="status",
    epilog="""Examples:

  aitbc blockchain consensus status

  aitbc blockchain consensus status --chain-id ait-mainnet --node-url http://aitbc3:8202""",
)
@click.option("--node-url", default="http://localhost:8202", help="Blockchain node RPC URL")
@click.option("--chain-id", default="ait-hub", help="Chain ID to query consensus status for")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def consensus_status(ctx, node_url: str, chain_id: str, format: str):
    """Show consensus mode, view, sequence, epoch, and fault tolerance for a chain."""
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


@consensus_group.command(
    name="validators",
    epilog="""Examples:

  aitbc blockchain consensus validators

  aitbc blockchain consensus validators --chain-id ait-mainnet --output json""",
)
@click.option("--node-url", default="http://localhost:8202", help="Blockchain node RPC URL")
@click.option("--chain-id", default="ait-hub", help="Chain ID to query validators for")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def consensus_validators(ctx, node_url: str, chain_id: str, format: str):
    """List active validators with address, stake, reputation, role, and last proposed."""
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


def _slash_rate(event: dict) -> str:
    """The penalty rate, as a percentage.

    Older nodes send it under `slash_amount`; that key never held an amount, so reading it
    here is correct rather than a fallback to something else.

    Module-level rather than nested in the command so it can be tested without standing up
    a node and driving the whole click invocation.
    """
    rate = event.get("slash_rate", event.get("slash_amount"))
    if rate is None:
        return "N/A"
    try:
        return f"{float(rate) * 100:g}%"
    except (TypeError, ValueError):
        return "N/A"


@consensus_group.command(
    name="slashing-history",
    epilog="""Examples:

  aitbc blockchain consensus slashing-history

  aitbc blockchain consensus slashing-history --chain-id ait-mainnet""",
)
@click.option("--node-url", default="http://localhost:8202", help="Blockchain node RPC URL")
@click.option("--chain-id", default="ait-hub", help="Chain ID to query slashing history for")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def consensus_slashing_history(ctx, node_url: str, chain_id: str, format: str):
    """Show slashing events with validator, condition, amount, and block height."""
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
                # V23-48: this column read `slash_amount`, which held the rate -- so a 50%
                # double-sign penalty displayed as "0.5" under a heading of "Amount". The
                # rate and the amount are now separate, and an amount of None means the
                # event was detected but never levied.
                "Rate": _slash_rate(e),
                "Amount Slashed": e.get("slashed_amount") or "not levied",
                "Block Height": e.get("block_height", "N/A"),
                "Timestamp": e.get("timestamp", "N/A"),
            }
            for e in events
        ]
        output(rows, ctx.obj.get("output_format", format), title=f"Slashing History for {chain_id}")
    except Exception as e:
        error(f"Error getting slashing history: {e}")


@chain.command(
    epilog="""Examples:

  aitbc blockchain height

  aitbc --output=json blockchain height --node-url http://localhost:8202"""
)
@click.option("--node-url", default="http://127.0.0.1:8202", help="Blockchain RPC URL")
@OUTPUT_FORMAT_OPTION
@click.pass_context
def height(ctx, node_url: str, output_format: str):
    """Get the current blockchain height from a node."""
    output_format = resolve_output_format(ctx, output_format)
    client = AITBCHTTPClient(base_url=node_url, timeout=10)
    try:
        result = client.get("/rpc/height")
        output(result, output_format, title="Blockchain Height")
    except NetworkError as e:
        error(f"Cannot connect to node at {node_url}: {e}")
    finally:
        client.close()


@chain.command(
    epilog="""Examples:

  aitbc blockchain block --height 42

  aitbc --output=json blockchain block --height 42 --node-url http://localhost:8202"""
)
@click.option("--height", "block_height", required=True, type=int, help="Block height to fetch")
@click.option("--node-url", default="http://127.0.0.1:8202", help="Blockchain RPC URL")
@OUTPUT_FORMAT_OPTION
@click.pass_context
def block(ctx, block_height: int, node_url: str, output_format: str):
    """Get a block by height from a node."""
    output_format = resolve_output_format(ctx, output_format)
    client = AITBCHTTPClient(base_url=node_url, timeout=10)
    try:
        result = client.get(f"/rpc/blocks/{block_height}")
        output(result, output_format, title=f"Block {block_height}")
    except NetworkError as e:
        error(f"Cannot connect to node at {node_url}: {e}")
    finally:
        client.close()
