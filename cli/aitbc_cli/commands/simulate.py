#!/usr/bin/env python3
"""
AITBC CLI - Simulate Command
Simulate blockchain scenarios and test environments deterministically.
"""

import json
from typing import Any

import click

from ..config import get_config
from ..utils.error_handling import abort
from ..utils.http_client import AITBCHTTPClient, NetworkError, get_logger
from ..utils.output import error, output, success
from ..utils.simulation import make_rng

logger = get_logger(__name__)


@click.group()
def simulate():
    """Simulate blockchain scenarios and test environments"""
    pass


@simulate.command()
@click.option("--blocks", default=10, help="Number of blocks to simulate")
@click.option("--transactions", default=50, help="Number of transactions per block")
@click.option("--delay", default=1.0, help="Delay between blocks (seconds)")
@click.option("--output", default="table", type=click.Choice(["table", "json", "yaml"]))
@click.option("--seed", type=int, default=None, help="Seed for deterministic simulation (default: live)")
def blockchain(blocks, transactions, delay, output, seed):
    """Simulate blockchain block production and transactions"""
    click.echo(f"Simulating blockchain with {blocks} blocks, {transactions} transactions per block")

    rng, use_real_sleeps = make_rng(seed)
    results: list[dict[str, Any]] = []
    for block_num in range(blocks):
        block_timestamp = rng.advance(delay)
        # Simulate block production
        block_data: dict[str, Any] = {
            "block_number": block_num + 1,
            "timestamp": block_timestamp,
            "transactions": [],
        }

        # Generate transactions
        for _tx_num in range(transactions):
            tx = {
                "tx_id": f"0x{rng.getrandbits(256):064x}",
                "from_address": f"ait{rng.getrandbits(160):040x}",
                "to_address": f"ait{rng.getrandbits(160):040x}",
                "amount": round(rng.uniform(0.1, 1000.0), 8),
                "fee": round(rng.uniform(0.01, 1.0), 8),
            }
            block_data["transactions"].append(tx)

        block_data["tx_count"] = len(block_data["transactions"])
        block_data["total_amount"] = sum(tx["amount"] for tx in block_data["transactions"])
        block_data["total_fees"] = sum(tx["fee"] for tx in block_data["transactions"])

        results.append(block_data)

        # Output block info
        if output == "table":
            click.echo(
                f"Block {block_data['block_number']}: {block_data['tx_count']} txs, "
                f"{block_data['total_amount']:.2f} AIT, {block_data['total_fees']:.2f} fees"
            )
        else:
            click.echo(json.dumps(block_data, indent=2))

        if delay > 0 and block_num < blocks - 1 and use_real_sleeps:
            rng.sleep(delay)

    # Summary
    total_txs = sum(block["tx_count"] for block in results)
    total_amount = sum(block["total_amount"] for block in results)
    total_fees = sum(block["total_fees"] for block in results)

    click.echo("\nSimulation Summary:")
    click.echo(f"  Total Blocks: {blocks}")
    click.echo(f"  Total Transactions: {total_txs}")
    click.echo(f"  Total Amount: {total_amount:.2f} AIT")
    click.echo(f"  Total Fees: {total_fees:.2f} AIT")
    click.echo(f"  Average TPS: {total_txs / (blocks * max(delay, 0.1)):.2f}")


@simulate.command()
@click.option("--wallets", default=5, help="Number of wallets to simulate")
@click.option("--balance", default=1000.0, help="Initial balance for each wallet")
@click.option("--transactions", default=20, help="Number of transactions to simulate")
@click.option("--amount-range", default="1.0-100.0", help="Transaction amount range (min-max)")
@click.option("--seed", type=int, default=None, help="Seed for deterministic simulation (default: live)")
def wallets(wallets, balance, transactions, amount_range, seed):
    """Simulate wallet creation and transactions"""
    click.echo(f"Simulating {wallets} wallets with {balance:.2f} AIT initial balance")

    rng, _ = make_rng(seed)

    # Parse amount range
    try:
        min_amount, max_amount = map(float, amount_range.split("-"))
    except ValueError:
        min_amount, max_amount = 1.0, 100.0

    # Create wallets
    created_wallets = []
    for i in range(wallets):
        wallet = {
            "name": f"sim_wallet_{i + 1}",
            "address": f"ait{rng.getrandbits(160):040x}",
            "balance": balance,
        }
        created_wallets.append(wallet)
        click.echo(f"Created wallet {wallet['name']}: {wallet['address']} with {balance:.2f} AIT")

    # Simulate transactions
    click.echo(f"\nSimulating {transactions} transactions...")
    for i in range(transactions):
        # Random sender and receiver
        sender = rng.choice(created_wallets)
        receiver = rng.choice([w for w in created_wallets if w != sender])

        # Random amount
        amount = round(rng.uniform(min_amount, max_amount), 8)

        # Check if sender has enough balance
        if sender["balance"] >= amount:
            sender["balance"] -= amount
            receiver["balance"] += amount

            click.echo(f"Tx {i + 1}: {sender['name']} -> {receiver['name']}: {amount:.2f} AIT")
        else:
            click.echo(f"Tx {i + 1}: {sender['name']} -> {receiver['name']}: FAILED (insufficient balance)")

    # Final balances
    click.echo("\nFinal Wallet Balances:")
    for wallet in created_wallets:
        click.echo(f"  {wallet['name']}: {wallet['balance']:.2f} AIT")


@simulate.command()
@click.option("--price", default=100.0, help="Starting AIT price")
@click.option("--volatility", default=0.05, help="Price volatility (0.0-1.0)")
@click.option("--timesteps", default=100, help="Number of timesteps to simulate")
@click.option("--delay", default=0.1, help="Delay between timesteps (seconds)")
@click.option("--seed", type=int, default=None, help="Seed for deterministic simulation (default: live)")
def price(price, volatility, timesteps, delay, seed):
    """Simulate AIT price movements"""
    click.echo(f"Simulating AIT price from {price:.2f} with {volatility:.2f} volatility")

    rng, use_real_sleeps = make_rng(seed)

    current_price = price
    prices = [current_price]

    for step in range(timesteps):
        # Random price change
        change_percent = rng.uniform(-volatility, volatility)
        current_price = current_price * (1 + change_percent)

        # Ensure price doesn't go negative
        current_price = max(current_price, 0.01)

        prices.append(current_price)

        click.echo(f"Step {step + 1}: {current_price:.4f} AIT ({change_percent:+.2f}%)")

        if delay > 0 and step < timesteps - 1 and use_real_sleeps:
            rng.sleep(delay)

    # Statistics
    min_price = min(prices)
    max_price = max(prices)
    avg_price = sum(prices) / len(prices)

    click.echo("\nPrice Statistics:")
    click.echo(f"  Starting Price: {price:.4f} AIT")
    click.echo(f"  Ending Price: {current_price:.4f} AIT")
    click.echo(f"  Minimum Price: {min_price:.4f} AIT")
    click.echo(f"  Maximum Price: {max_price:.4f} AIT")
    click.echo(f"  Average Price: {avg_price:.4f} AIT")
    click.echo(f"  Total Change: {((current_price - price) / price * 100):+.2f}%")


@simulate.command()
@click.option("--nodes", default=3, help="Number of nodes to simulate")
@click.option("--network-delay", default=0.1, help="Network delay in seconds")
@click.option("--failure-rate", default=0.05, help="Node failure rate (0.0-1.0)")
@click.option("--seed", type=int, default=None, help="Seed for deterministic simulation (default: live)")
def network(nodes, network_delay, failure_rate, seed):
    """Simulate network topology and node failures"""
    click.echo(f"Simulating network with {nodes} nodes, {network_delay}s delay, {failure_rate:.2f} failure rate")

    rng, use_real_sleeps = make_rng(seed)

    # Create nodes
    network_nodes: list[dict[str, Any]] = []
    for i in range(nodes):
        node: dict[str, Any] = {
            "id": f"node_{i + 1}",
            "address": f"10.1.223.{90 + i}",
            "status": "active",
            "height": 0,
            "connected_to": [],
        }
        network_nodes.append(node)

    # Create network topology (ring + mesh)
    for i, node in enumerate(network_nodes):
        # Connect to next node (ring)
        next_node = network_nodes[(i + 1) % len(network_nodes)]
        node_connected_to: list[str] = node["connected_to"]
        node_connected_to.append(next_node["id"])

        # Connect to random nodes (mesh)
        if len(network_nodes) > 2:
            mesh_connections = rng.sample(
                [n["id"] for n in network_nodes if n["id"] != node["id"]],
                min(2, len(network_nodes) - 1),
            )
            for conn in mesh_connections:
                if conn not in node_connected_to:
                    node_connected_to.append(conn)

    # Display network topology
    click.echo("\nNetwork Topology:")
    for node in network_nodes:
        node_connections = node["connected_to"]
        click.echo(f"  {node['id']} ({node['address']}): connected to {', '.join(node_connections)}")

    # Simulate network operations
    click.echo("\nSimulating network operations...")
    active_nodes: list[dict[str, Any]] = network_nodes.copy()

    for step in range(10):
        # Simulate failures
        for node in active_nodes:
            if rng.random() < failure_rate:
                node["status"] = "failed"
                click.echo(f"Step {step + 1}: {node['id']} failed")

        # Remove failed nodes
        active_nodes = [n for n in active_nodes if n["status"] == "active"]

        # Simulate block propagation
        if active_nodes:
            # Random node produces block
            producer = rng.choice(active_nodes)
            producer_height: int = producer["height"]
            producer["height"] = producer_height + 1

            # Propagate to connected nodes
            for node in active_nodes:
                node_height: int = node["height"]
                if node["id"] != producer["id"] and node["id"] in producer["connected_to"]:
                    node["height"] = max(node_height, producer["height"] - 1)

            click.echo(
                f"Step {step + 1}: {producer['id']} produced block {producer['height']}, {len(active_nodes)} nodes active"
            )

        if network_delay > 0 and use_real_sleeps:
            rng.sleep(network_delay)

    # Final network status
    click.echo("\nFinal Network Status:")
    for node in network_nodes:
        status_icon = "✅" if node["status"] == "active" else "❌"
        connected_to: list[str] = node["connected_to"]
        click.echo(f"  {status_icon} {node['id']}: height {node['height']}, connections: {len(connected_to)}")


@simulate.command()
@click.option("--jobs", default=10, help="Number of AI jobs to simulate")
@click.option("--models", default="text-generation,image-generation", help="Available models (comma-separated)")
@click.option("--duration-range", default="30-300", help="Job duration range in seconds (min-max)")
@click.option("--delay", default=1.0, help="Delay between job status checks (seconds)")
@click.option("--seed", type=int, default=None, help="Seed for deterministic simulation (default: live)")
def ai_jobs(jobs, models, duration_range, delay, seed):
    """Simulate AI job submission and processing"""
    click.echo(f"Simulating {jobs} AI jobs with models: {models}")

    rng, use_real_sleeps = make_rng(seed)
    base_time = rng.now()

    # Parse models
    model_list = [m.strip() for m in models.split(",")]

    # Parse duration range
    try:
        min_duration, max_duration = map(int, duration_range.split("-"))
    except ValueError:
        min_duration, max_duration = 30, 300

    # Simulate job submission
    submitted_jobs = []
    for i in range(jobs):
        job = {
            "job_id": f"job_{i + 1:03d}",
            "model": rng.choice(model_list),
            "status": "queued",
            "submit_time": base_time,
            "duration": rng.randint(min_duration, max_duration),
            "wallet": f"wallet_{rng.randint(1, 5):03d}",
        }
        submitted_jobs.append(job)

        click.echo(f"Submitted job {job['job_id']}: {job['model']} (est. {job['duration']}s)")

    # Simulate job processing
    click.echo("\nSimulating job processing...")
    processing_jobs = submitted_jobs.copy()
    completed_jobs = []

    current_time = base_time
    max_iterations = max(jobs * max(max_duration, 1) // max(delay, 1) + 10, 1000)
    iteration = 0
    while processing_jobs and iteration < max_iterations:
        iteration += 1
        current_time += delay

        for job in processing_jobs[:]:
            if job["status"] == "queued" and current_time - job["submit_time"] > 5:
                job["status"] = "running"
                job["start_time"] = current_time
                click.echo(f"Started {job['job_id']}")

            elif job["status"] == "running":
                if current_time - job["start_time"] >= job["duration"]:
                    job["status"] = "completed"
                    job["end_time"] = current_time
                    job["actual_duration"] = job["end_time"] - job["start_time"]
                    processing_jobs.remove(job)
                    completed_jobs.append(job)
                    click.echo(f"Completed {job['job_id']} in {job['actual_duration']:.1f}s")

        if delay > 0 and use_real_sleeps:
            rng.sleep(delay)

    # Job statistics
    click.echo("\nJob Statistics:")
    click.echo(f"  Total Jobs: {jobs}")
    click.echo(f"  Completed Jobs: {len(completed_jobs)}")
    click.echo(f"  Failed Jobs: {len(processing_jobs)}")

    if completed_jobs:
        avg_duration = sum(job["actual_duration"] for job in completed_jobs) / len(completed_jobs)
        click.echo(f"  Average Duration: {avg_duration:.1f}s")

        # Model statistics
        model_stats: dict[str, int] = {}
        for job in completed_jobs:
            model_stats[job["model"]] = model_stats.get(job["model"], 0) + 1

        click.echo("  Model Usage:")
        for model, count in model_stats.items():
            click.echo(f"    {model}: {count} jobs")


@simulate.command()
@click.argument("scenario")
@click.option("--params", help="Simulation parameters (JSON string)")
@click.option("--async-run", is_flag=True, help="Run simulation asynchronously")
@click.pass_context
def run(ctx, scenario: str, params: str | None, async_run: bool):
    """Run a simulation scenario via coordinator-api"""
    config = get_config()

    try:
        http_client = AITBCHTTPClient(base_url=config.agent_coordinator_url, timeout=10)
        sim_data = {"scenario": scenario, "async": async_run}

        if params:
            try:
                sim_data["params"] = json.loads(params)
            except json.JSONDecodeError:
                abort(ctx, "Invalid JSON parameters")
        result = http_client.post("/simulate/run", json=sim_data)
        success(f"Simulation '{scenario}' started")
        output(result, ctx.obj.get("output_format", "table"))
    except NetworkError as e:
        error(f"Network error: {e}")
        ctx.exit(1)
    except Exception as e:
        error(f"Error running simulation: {e}")
        ctx.exit(1)


@simulate.command()
@click.argument("simulation_id")
@click.pass_context
def status(ctx, simulation_id: str):
    """Get simulation status from coordinator-api"""
    config = get_config()

    try:
        http_client = AITBCHTTPClient(base_url=config.agent_coordinator_url, timeout=10)
        status_data = http_client.get(f"/simulate/{simulation_id}/status")
        success(f"Simulation {simulation_id} Status:")
        output(status_data, ctx.obj.get("output_format", "table"))
    except NetworkError as e:
        error(f"Network error: {e}")
        ctx.exit(1)
    except Exception as e:
        error(f"Error fetching simulation status: {e}")
        ctx.exit(1)


@simulate.command()
@click.argument("simulation_id")
@click.pass_context
def result(ctx, simulation_id: str):
    """Get simulation results from coordinator-api"""
    config = get_config()

    try:
        http_client = AITBCHTTPClient(base_url=config.agent_coordinator_url, timeout=10)
        result_data = http_client.get(f"/simulate/{simulation_id}/result")
        success(f"Simulation {simulation_id} Results:")
        output(result_data, ctx.obj.get("output_format", "table"))
    except NetworkError as e:
        error(f"Network error: {e}")
        ctx.exit(1)
    except Exception as e:
        error(f"Error fetching simulation results: {e}")


if __name__ == "__main__":
    simulate()
