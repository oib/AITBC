"""
Node monitoring commands for AITBC.
"""

import asyncio
import time

import click

try:
    from aitbc_cli.core.config import load_multichain_config
    from aitbc_cli.core.node_client import NodeClient
    from aitbc_cli.utils import error, output
    from aitbc_cli.utils.http_client import get_logger
except ImportError:
    from aitbc_cli.core.config import load_multichain_config
    from aitbc_cli.core.node_client import NodeClient
    from aitbc_cli.utils import error, output
    from aitbc_cli.utils.http_client import get_logger

from aitbc_cli.utils.error_handling import CLIError, abort

logger = get_logger(__name__)


def _fetch_node_info(node_config):
    """Fetch node info once via an async client call."""

    async def get_node_stats():
        async with NodeClient(node_config) as client:
            return await client.get_node_info()

    return asyncio.run(get_node_stats())


_METRIC_FIELDS = (
    ("CPU Usage", "cpu_usage", "{}%"),
    ("Memory Usage", "memory_usage_mb", "{:.1f}MB"),
    ("Disk Usage", "disk_usage_mb", "{:.1f}MB"),
    ("Network In", "network_in_mb", "{:.1f}MB/s"),
    ("Network Out", "network_out_mb", "{:.1f}MB/s"),
)


def _monitor_metric_rows(node_info):
    """Rows for whichever telemetry fields the node actually publishes (#2230)."""
    rows = []
    for label, key, fmt in _METRIC_FIELDS:
        value = node_info.get(key)
        if value is not None:
            rows.append([label, fmt.format(value)])
    uptime_days = node_info.get("uptime_days")
    if uptime_days is not None:
        rows.append(["Uptime", f"{uptime_days}d {node_info.get('uptime_hours', 0)}h"])
    if not rows:
        rows.append(["Status", str(node_info.get("status", "unknown"))])
        rows.append(["Hosted Chains", str(len(node_info.get("hosted_chains") or {}))])
    return rows


def _monitor_metrics_table(node_info):
    return _monitor_metric_rows(node_info)


def _monitor_chains_text(node_info):
    hosted_chains = node_info.get("hosted_chains")
    if not hosted_chains:
        return "No chains hosted"
    text = f"Hosted Chains: {len(hosted_chains)}\n"
    for chain_id, chain in list(hosted_chains.items())[:5]:
        text += f"  • {chain_id} ({chain.get('status', 'unknown')})\n"
    return text


def _build_monitor_layout(node_id, node_info):
    from rich.layout import Layout

    layout = Layout()
    layout.split_column(Layout(name="header", size=3), Layout(name="metrics"), Layout(name="chains", size=10))

    layout["header"].update(f"Node Monitor: {node_id} - {str(node_info.get('status', 'unknown')).upper()}")
    layout["metrics"].update(str(_monitor_metrics_table(node_info)))
    layout["chains"].update(_monitor_chains_text(node_info))

    return layout


def _monitor_layout_or_error(node_id, node_config):
    """Render the monitor layout for one snapshot; error text on failure."""
    try:
        node_info = _fetch_node_info(node_config)
        return _build_monitor_layout(node_id, node_info)
    except Exception as e:  # noqa: BLE001 - NodeClient raises plain Exception for HTTP failures; layout degrades to an error string
        logger.warning("Error getting node stats: %s", e, exc_info=True)
        return f"Error getting node stats: {e}"


def _snapshot_stats_rows(node_info):
    return [{"Metric": label, "Value": value} for label, value in _monitor_metric_rows(node_info)]


def monitor_command(ctx, node_id, realtime, interval):
    """Monitor node activity"""
    try:
        config = load_multichain_config()

        if node_id not in config.nodes:
            error(f"Node {node_id} not found")
            raise click.Abort()

        node_config = config.nodes[node_id]

        if realtime:
            _monitor_realtime(ctx, node_id, node_config, interval)
        else:
            node_info = _fetch_node_info(node_config)
            output(
                _snapshot_stats_rows(node_info),
                ctx.obj.get("output", "table"),
                title=f"Node Statistics: {node_id}",
            )

    except Exception as e:
        error(f"Error during monitoring: {str(e)}")
        raise click.Abort() from e


def _monitor_realtime(ctx, node_id, node_config, interval):
    from rich.console import Console
    from rich.live import Live

    console = Console()

    with Live(_monitor_layout_or_error(node_id, node_config), refresh_per_second=1) as live:
        try:
            while True:
                live.update(_monitor_layout_or_error(node_id, node_config))
                time.sleep(interval)
        except KeyboardInterrupt:
            console.print("\n[yellow]Monitoring stopped by user[/yellow]")


def test_command(ctx, node_id):
    """Test node connectivity"""
    try:
        config = load_multichain_config()

        if node_id not in config.nodes:
            error(f"Node {node_id} not found")
            raise click.Abort()

        node_config = config.nodes[node_id]

        async def test_connection():
            async with NodeClient(node_config) as client:
                start_time = time.time()
                node_info = await client.get_node_info()
                latency = (time.time() - start_time) * 1000
                return node_info, latency

        node_info, latency = asyncio.run(test_connection())

        test_results = [
            {"Test": "Connection", "Status": "PASS" if node_info else "FAIL", "Latency": f"{latency:.2f}ms"},
            {
                "Test": "Node ID",
                "Status": "PASS" if node_info.get("node_id") == node_id else "FAIL",
                "Details": node_info.get("node_id", "N/A"),
            },
            {
                "Test": "Node Status",
                "Status": "PASS" if node_info.get("status") else "FAIL",
                "Details": node_info.get("status", "N/A"),
            },
        ]
        # Version/telemetry only exist on nodes exposing the admin API.
        if node_info.get("version"):
            test_results.append(
                {
                    "Test": "Version",
                    "Status": "PASS",
                    "Details": node_info["version"],
                }
            )
        else:
            test_results.append(
                {
                    "Test": "Chain RPC",
                    "Status": "PASS" if node_info.get("supported_chains") is not None else "FAIL",
                    "Details": f"{len(node_info.get('supported_chains') or [])} supported chain(s)",
                }
            )

        output(test_results, ctx.obj.get("output", "table"), title=f"Node Test Results: {node_id}")

        # Overall result
        all_passed = all(result["Status"] == "PASS" for result in test_results)
        if all_passed:
            from aitbc_cli.utils import success

            success("All tests passed!")
        else:
            abort(ctx, "Some tests failed")

    except (CLIError, click.Abort):
        raise
    except Exception as e:
        error(f"Error testing node: {str(e)}")
        raise click.Abort() from e
