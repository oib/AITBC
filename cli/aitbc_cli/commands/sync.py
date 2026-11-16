"""Sync commands for AITBC CLI"""

import os
import subprocess
from pathlib import Path
from typing import Any

import click

from aitbc_cli.utils import output, resolve_output_format
from aitbc_cli.utils.error_handling import abort
from aitbc_cli.utils.http_client import AITBCHTTPClient, NetworkError


@click.group(
    epilog="""Examples:

  aitbc sync bulk

  aitbc sync status"""
)
def sync():
    """Bulk import blocks and check blockchain synchronization status."""
    pass


@sync.command(
    epilog="""Examples:

  aitbc sync bulk

  aitbc sync bulk --source http://leader:8202 --import-url http://localhost:8202"""
)
@click.option("--source", default="http://127.0.0.1:8202", help="Source RPC URL (leader node)")
@click.option("--import-url", default="http://127.0.0.1:8202", help="Local RPC URL for import")
@click.option("--batch-size", type=int, default=100, help="Blocks per batch (default: 100)")
@click.option("--poll-interval", type=float, default=0.2, help="Seconds between batches (default: 0.2)")
@click.pass_context
def bulk(ctx, source, import_url, batch_size, poll_interval):
    """Bulk import blocks from a leader node to catch up quickly."""
    # Resolve paths to the sync_cli.py script
    # Get the AITBC root directory (parent of cli directory)
    cli_dir = Path(__file__).resolve().parent.parent.parent
    aitbc_root = cli_dir.parent
    blockchain_dir = aitbc_root / "apps" / "blockchain-node"
    src_dir = blockchain_dir / "src"

    # Use the main AITBC venv at /opt/aitbc/venv
    venv_python = aitbc_root / "venv" / "bin" / "python3"

    # Fallback to blockchain-node .venv if main venv doesn't exist
    if not venv_python.exists():
        venv_python = blockchain_dir / ".venv" / "bin" / "python3"

    sync_cli = src_dir / "aitbc_chain" / "sync_cli.py"

    if not sync_cli.exists():
        abort(ctx, f"sync_cli.py not found at {sync_cli}. Ensure bulk sync feature is deployed.")

    cmd = [
        str(venv_python),
        str(sync_cli),
        "--source",
        source,
        "--import-url",
        import_url,
        "--batch-size",
        str(batch_size),
        "--poll-interval",
        str(poll_interval),
    ]

    # Prepare environment: keep the caller's env (PATH/HOME/etc.) and put both
    # the blockchain src dir and the repo root on PYTHONPATH — sync_cli.py
    # imports the shared `aitbc` package, which lives at the repo root and is
    # only importable from a source checkout when the repo root is on the path.
    env = dict(os.environ)
    pythonpath = [str(src_dir), str(aitbc_root)]
    if env.get("PYTHONPATH"):
        pythonpath.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(pythonpath)

    click.echo(f"Running bulk sync from {source} to {import_url} (batch size: {batch_size})")

    try:
        result = subprocess.run(cmd, env=env, capture_output=False)
        if result.returncode != 0:
            abort(ctx, "Bulk sync failed. Check logs for details.")
        click.echo("Bulk sync completed.")
    except Exception as e:
        abort(ctx, f"Error during bulk sync: {e}", from_exception=e)


def _format_status_table(
    chain_id,
    height,
    block_hash,
    timestamp,
    total_transactions,
    total_accounts,
    p2p_endpoint,
    supported_chains,
    hub_status=None,
):
    """Format sync status into an aligned text table via click.echo."""
    truncated_hash = f"{block_hash[:16]}..." if block_hash else "N/A"
    chains_str = ", ".join(supported_chains) if supported_chains else "N/A"

    rows = [
        ("Chain ID", str(chain_id) if chain_id is not None else "N/A"),
        ("Local height", str(height) if height is not None else "N/A"),
        ("Last block hash", truncated_hash),
        ("Last block timestamp", str(timestamp) if timestamp is not None else "N/A"),
        ("Total transactions", str(total_transactions) if total_transactions is not None else "N/A"),
        ("Total accounts", str(total_accounts) if total_accounts is not None else "N/A"),
        ("P2P endpoint", str(p2p_endpoint) if p2p_endpoint else "N/A"),
        ("Supported chains", chains_str),
    ]

    if hub_status:
        rows.append(("Hub height", str(hub_status.get("height", "N/A"))))
        rows.append(("Hub hash", f"{str(hub_status.get('hash', ''))[:16]}..." if hub_status.get("hash") else "N/A"))
        rows.append(("Height gap", str(hub_status.get("gap", "N/A"))))
        rows.append(("Divergence", hub_status.get("divergence", "unknown")))

    label_width = max(len(label) for label, _ in rows)
    click.echo("Sync Status")
    click.echo("-" * 40)
    for label, value in rows:
        click.echo(f"{label.ljust(label_width)} : {value}")


@sync.command(
    epilog="""Examples:

  aitbc sync status

  aitbc sync status --node-url http://localhost:8202 --alert"""
)
@click.option("--node-url", default="http://127.0.0.1:8202", help="Local node RPC URL")
@click.option("--chain-id", default=None, help="Chain ID to check (defaults to node's configured chain)")
@click.option("--hub-url", default=None, help="Hub RPC URL to compare against (defaults to HUB_RPC_URL or node-url)")
@click.option("--gap-threshold", type=int, default=5, help="Height gap considered a divergence (default: 5)")
@click.option("--alert", is_flag=True, help="Exit non-zero on divergence or unreachable hub")
@click.pass_context
def status(ctx, node_url, chain_id, hub_url, gap_threshold, alert):
    """Show synchronization status, block height, peer count, and hub divergence."""
    from aitbc_cli.config import get_config as _sync_cfg

    client = AITBCHTTPClient(
        base_url=node_url,
        api_key=(ctx.obj or {}).get("api_key") or getattr(_sync_cfg(), "blockchain_rpc_api_key", None),
    )
    head, network_info, sync_config = _query_sync_endpoints(ctx, client, chain_id, node_url)
    sync_config = _validate_sync_responses(ctx, head, network_info, sync_config)

    # Extract head fields (fall back to network-info chain_id if not provided)
    resolved_chain_id, height, block_hash, timestamp, total_transactions, total_accounts, p2p_endpoint, supported_chains = (
        _extract_head_fields(chain_id, head, network_info)
    )

    # Compare with hub if a hub URL is available
    hub_url = hub_url or os.environ.get("HUB_RPC_URL")
    hub_status = _hub_divergence_status(hub_url, chain_id, height, block_hash, gap_threshold)

    sync_optimization = _sync_optimization_block(sync_config)

    fmt = resolve_output_format(ctx)
    if fmt == "json":
        output(
            {
                "chain_id": resolved_chain_id,
                "height": height,
                "block_hash": block_hash,
                "timestamp": timestamp,
                "total_transactions": total_transactions,
                "total_accounts": total_accounts,
                "p2p_endpoint": p2p_endpoint,
                "supported_chains": supported_chains,
                "hub": hub_status or None,
                "sync_optimization": sync_optimization,
            },
            "json",
        )
    else:
        _format_status_table(
            resolved_chain_id,
            height,
            block_hash,
            timestamp,
            total_transactions,
            total_accounts,
            p2p_endpoint,
            supported_chains,
            hub_status,
        )

    divergence = hub_status.get("divergence", "none")
    if alert and divergence not in ("none", "N/A", "HUB_UNREACHABLE"):
        ctx.exit(1)

    _print_sync_optimization(sync_optimization, fmt)


def _query_sync_endpoints(ctx, client: AITBCHTTPClient, chain_id, node_url):
    """Query head, network-info, and sync config; aborts when the node is down."""
    head_params = {"chain_id": chain_id} if chain_id else None
    try:
        head = client.get("/rpc/head", params=head_params)
        network_info = client.get("/rpc/network-info")
        # Query sync configuration (v0.6.2)
        sync_config: dict[str, Any] | None = client.get("/rpc/sync/config")
    except NetworkError as e:
        abort(ctx, f"Cannot connect to node at {node_url}", from_exception=e)
    finally:
        client.close()
    return head, network_info, sync_config


def _validate_sync_responses(ctx, head, network_info, sync_config):
    """Abort on endpoint error payloads; sync config errors mean 'unsupported'."""
    # Handle error responses from endpoints
    if isinstance(head, dict) and head.get("error"):
        abort(ctx, f"Error from /rpc/head: {head['error']}")
    if isinstance(network_info, dict) and network_info.get("error"):
        abort(ctx, f"Error from /rpc/network-info: {network_info['error']}")
    # Sync config endpoint might not exist in older versions
    if isinstance(sync_config, dict) and sync_config.get("error"):
        sync_config = None
    return sync_config


def _extract_head_fields(chain_id, head, network_info):
    resolved_chain_id = chain_id or network_info.get("chain_id") or head.get("chain_id")
    height = head.get("height")
    block_hash = head.get("hash") or head.get("last_block_hash")
    timestamp = head.get("timestamp")
    total_transactions = head.get("total_transactions")
    total_accounts = head.get("total_accounts")
    p2p_endpoint = network_info.get("p2p_endpoint")
    supported_chains = network_info.get("supported_chains") or []
    return (
        resolved_chain_id,
        height,
        block_hash,
        timestamp,
        total_transactions,
        total_accounts,
        p2p_endpoint,
        supported_chains,
    )


def _hub_divergence(hub_height, hub_hash, height, block_hash, gap_threshold: int) -> str:
    gap = (hub_height - height) if (hub_height is not None and height is not None) else None
    if gap is not None and gap > gap_threshold:
        return f"BEHIND_BY_{gap}"
    if gap is not None and gap < 0:
        return f"AHEAD_BY_{-gap}"
    if hub_height is not None and height == hub_height and hub_hash and block_hash and hub_hash != block_hash:
        return "HASH_MISMATCH"
    return "none"


def _hub_status_from_head(hub_head, height, block_hash, gap_threshold: int) -> dict[str, Any]:
    hub_height = hub_head.get("height") if isinstance(hub_head, dict) else None
    hub_hash = (hub_head.get("hash") or hub_head.get("last_block_hash")) if isinstance(hub_head, dict) else None
    gap = (hub_height - height) if (hub_height is not None and height is not None) else None
    return {
        "height": hub_height if hub_height is not None else "N/A",
        "hash": hub_hash or "",
        "gap": gap if gap is not None else "N/A",
        "divergence": _hub_divergence(hub_height, hub_hash, height, block_hash, gap_threshold),
    }


def _hub_divergence_status(hub_url, chain_id, height, block_hash, gap_threshold: int) -> dict[str, Any]:
    """Compare local head against the hub; {} when no hub URL is configured."""
    if not hub_url:
        return {}
    head_params = {"chain_id": chain_id} if chain_id else None
    hub_client = AITBCHTTPClient(base_url=hub_url, timeout=10)
    try:
        hub_head = hub_client.get("/rpc/head", params=head_params)
        hub_client.get("/rpc/network-info")
    except NetworkError:
        return {
            "height": "N/A",
            "hash": "",
            "gap": "N/A",
            "divergence": "HUB_UNREACHABLE",
        }
    else:
        hub_client.close()
        return _hub_status_from_head(hub_head, height, block_hash, gap_threshold)


def _sync_optimization_block(sync_config) -> dict[str, Any] | None:
    if not sync_config:
        return None
    return {
        "parallel_enabled": sync_config.get("sync_parallel_enabled", False),
        "delta_enabled": sync_config.get("sync_delta_enabled", False),
        "priority_enabled": sync_config.get("gossip_priority_enabled", False),
    }


def _print_sync_optimization(sync_optimization, fmt: str) -> None:
    # Show v0.6.2 sync optimization status if available
    if not (sync_optimization and fmt != "json"):
        return
    click.echo("\nSync Optimization (v0.6.2)")
    click.echo("-" * 40)
    click.echo(f"Parallel sync      : {'enabled' if sync_optimization['parallel_enabled'] else 'disabled'}")
    click.echo(f"Delta sync        : {'enabled' if sync_optimization['delta_enabled'] else 'disabled'}")
    click.echo(f"Gossip priority   : {'enabled' if sync_optimization['priority_enabled'] else 'disabled'}")
