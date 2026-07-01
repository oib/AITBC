"""
Node monitoring commands for AITBC.
"""

import asyncio
import time

import click

try:
    from ..core.config import load_multichain_config
    from ..core.node_client import NodeClient
    from ...utils.output import error, output
except ImportError:
    from aitbc_cli.core.config import load_multichain_config
    from aitbc_cli.core.node_client import NodeClient
    from utils import error, output


def monitor_command(ctx, node_id, realtime, interval):
    """Monitor node activity"""
    try:
        config = load_multichain_config()

        if node_id not in config.nodes:
            error(f"Node {node_id} not found")
            raise click.Abort()

        node_config = config.nodes[node_id]

        from rich.console import Console
        from rich.layout import Layout
        from rich.live import Live

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
                    layout.split_column(Layout(name="header", size=3), Layout(name="metrics"), Layout(name="chains", size=10))

                    # Header
                    layout["header"].update(f"Node Monitor: {node_id} - {node_info['status'].upper()}")

                    # Metrics table
                    metrics_data = [
                        ["CPU Usage", f"{node_info['cpu_usage']}%"],
                        ["Memory Usage", f"{node_info['memory_usage_mb']:.1f}MB"],
                        ["Disk Usage", f"{node_info['disk_usage_mb']:.1f}MB"],
                        ["Network In", f"{node_info['network_in_mb']:.1f}MB/s"],
                        ["Network Out", f"{node_info['network_out_mb']:.1f}MB/s"],
                        ["Uptime", f"{node_info['uptime_days']}d {node_info['uptime_hours']}h"],
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
                    console.click.echo("\n[yellow]Monitoring stopped by user[/yellow]")
        else:
            # Single snapshot
            node_info = asyncio.run(get_node_stats())

            stats_data = [
                {"Metric": "CPU Usage", "Value": f"{node_info['cpu_usage']}%"},
                {"Metric": "Memory Usage", "Value": f"{node_info['memory_usage_mb']:.1f}MB"},
                {"Metric": "Disk Usage", "Value": f"{node_info['disk_usage_mb']:.1f}MB"},
                {"Metric": "Network In", "Value": f"{node_info['network_in_mb']:.1f}MB/s"},
                {"Metric": "Network Out", "Value": f"{node_info['network_out_mb']:.1f}MB/s"},
                {"Metric": "Uptime", "Value": f"{node_info['uptime_days']}d {node_info['uptime_hours']}h"},
            ]

            output(stats_data, ctx.obj.get("output", "table"), title=f"Node Statistics: {node_id}")

    except Exception as e:
        error(f"Error during monitoring: {str(e)}")
        raise click.Abort() from e


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
            {
                "Test": "Version",
                "Status": "PASS" if node_info.get("version") else "FAIL",
                "Details": node_info.get("version", "N/A"),
            },
        ]

        output(test_results, ctx.obj.get("output", "table"), title=f"Node Test Results: {node_id}")

        # Overall result
        all_passed = all(result["Status"] == "PASS" for result in test_results)
        if all_passed:
            from ...utils.output import success

            success("All tests passed!")
        else:
            from ...utils.output import warning

            warning("Some tests failed")

    except Exception as e:
        error(f"Error testing node: {str(e)}")
        raise click.Abort() from e
