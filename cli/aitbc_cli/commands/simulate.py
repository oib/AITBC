"""Simulation commands for AITBC CLI"""

import click
import json
import time
import random
from pathlib import Path
from typing import Optional, List, Dict, Any
from ..utils import output, error, success


@click.group()
def simulate():
    """Run simulations and manage test users"""
    pass


@simulate.command()
@click.option(
    "--distribute",
    default="10000,1000",
    help="Initial distribution: client_amount,miner_amount",
)
@click.option("--reset", is_flag=True, help="Reset existing simulation")
@click.pass_context
def init(ctx, distribute: str, reset: bool):
    """Initialize test economy"""
    home_dir = Path("/home/oib/windsurf/aitbc/home")

    if reset:
        success("Resetting simulation...")
        # Reset wallet files
        for wallet_file in ["client_wallet.json", "miner_wallet.json"]:
            wallet_path = home_dir / wallet_file
            if wallet_path.exists():
                wallet_path.unlink()

    # Parse distribution
    try:
        client_amount, miner_amount = map(float, distribute.split(","))
    except (ValueError, TypeError):
        error("Invalid distribution format. Use: client_amount,miner_amount")
        return

    # Initialize genesis wallet
    genesis_path = home_dir / "genesis_wallet.json"
    if not genesis_path.exists():
        genesis_wallet = {
            "address": "aitbc1genesis",
            "balance": 1000000,
            "transactions": [],
        }
        with open(genesis_path, "w") as f:
            json.dump(genesis_wallet, f, indent=2)
        success("Genesis wallet created")

    # Initialize client wallet
    client_path = home_dir / "client_wallet.json"
    if not client_path.exists():
        client_wallet = {
            "address": "aitbc1client",
            "balance": client_amount,
            "transactions": [
                {
                    "type": "receive",
                    "amount": client_amount,
                    "from": "aitbc1genesis",
                    "timestamp": time.time(),
                }
            ],
        }
        with open(client_path, "w") as f:
            json.dump(client_wallet, f, indent=2)
        success(f"Client wallet initialized with {client_amount} AITBC")

    # Initialize miner wallet
    miner_path = home_dir / "miner_wallet.json"
    if not miner_path.exists():
        miner_wallet = {
            "address": "aitbc1miner",
            "balance": miner_amount,
            "transactions": [
                {
                    "type": "receive",
                    "amount": miner_amount,
                    "from": "aitbc1genesis",
                    "timestamp": time.time(),
                }
            ],
        }
        with open(miner_path, "w") as f:
            json.dump(miner_wallet, f, indent=2)
        success(f"Miner wallet initialized with {miner_amount} AITBC")

    output(
        {
            "status": "initialized",
            "distribution": {"client": client_amount, "miner": miner_amount},
            "total_supply": client_amount + miner_amount,
        },
        ctx.obj["output_format"],
    )


@simulate.group()
def user():
    """Manage test users"""
    pass


@user.command()
@click.option("--type", type=click.Choice(["client", "miner"]), required=True)
@click.option("--name", required=True, help="User name")
@click.option("--balance", type=float, default=100, help="Initial balance")
@click.pass_context
def create(ctx, type: str, name: str, balance: float):
    """Create a test user"""
    home_dir = Path("/home/oib/windsurf/aitbc/home")

    user_id = f"{type}_{name}"
    wallet_path = home_dir / f"{user_id}_wallet.json"

    if wallet_path.exists():
        error(f"User {name} already exists")
        return

    wallet = {
        "address": f"aitbc1{user_id}",
        "balance": balance,
        "transactions": [
            {
                "type": "receive",
                "amount": balance,
                "from": "aitbc1genesis",
                "timestamp": time.time(),
            }
        ],
    }

    with open(wallet_path, "w") as f:
        json.dump(wallet, f, indent=2)

    success(f"Created {type} user: {name}")
    output(
        {"user_id": user_id, "address": wallet["address"], "balance": balance},
        ctx.obj["output_format"],
    )


@user.command()
@click.pass_context
def list(ctx):
    """List all test users"""
    home_dir = Path("/home/oib/windsurf/aitbc/home")

    users = []
    for wallet_file in home_dir.glob("*_wallet.json"):
        if wallet_file.name in ["genesis_wallet.json"]:
            continue

        with open(wallet_file) as f:
            wallet = json.load(f)

        user_type = "client" if "client" in wallet_file.name else "miner"
        user_name = wallet_file.stem.replace("_wallet", "").replace(f"{user_type}_", "")

        users.append(
            {
                "name": user_name,
                "type": user_type,
                "address": wallet["address"],
                "balance": wallet["balance"],
            }
        )

    output({"users": users}, ctx.obj["output_format"])


@user.command()
@click.argument("user")
@click.pass_context
def balance(ctx, user: str):
    """Check user balance"""
    home_dir = Path("/home/oib/windsurf/aitbc/home")
    wallet_path = home_dir / f"{user}_wallet.json"

    if not wallet_path.exists():
        error(f"User {user} not found")
        return

    with open(wallet_path) as f:
        wallet = json.load(f)

    output(
        {"user": user, "address": wallet["address"], "balance": wallet["balance"]},
        ctx.obj["output_format"],
    )


@user.command()
@click.argument("user")
@click.argument("amount", type=float)
@click.pass_context
def fund(ctx, user: str, amount: float):
    """Fund a test user"""
    home_dir = Path("/home/oib/windsurf/aitbc/home")

    # Load genesis wallet
    genesis_path = home_dir / "genesis_wallet.json"
    with open(genesis_path) as f:
        genesis = json.load(f)

    if genesis["balance"] < amount:
        error(f"Insufficient genesis balance: {genesis['balance']}")
        return

    # Load user wallet
    wallet_path = home_dir / f"{user}_wallet.json"
    if not wallet_path.exists():
        error(f"User {user} not found")
        return

    with open(wallet_path) as f:
        wallet = json.load(f)

    # Transfer funds
    genesis["balance"] -= amount
    genesis["transactions"].append(
        {
            "type": "send",
            "amount": -amount,
            "to": wallet["address"],
            "timestamp": time.time(),
        }
    )

    wallet["balance"] += amount
    wallet["transactions"].append(
        {
            "type": "receive",
            "amount": amount,
            "from": genesis["address"],
            "timestamp": time.time(),
        }
    )

    # Save wallets
    with open(genesis_path, "w") as f:
        json.dump(genesis, f, indent=2)

    with open(wallet_path, "w") as f:
        json.dump(wallet, f, indent=2)

    success(f"Funded {user} with {amount} AITBC")
    output(
        {"user": user, "amount": amount, "new_balance": wallet["balance"]},
        ctx.obj["output_format"],
    )


@simulate.command()
@click.option("--jobs", type=int, default=5, help="Number of jobs to simulate")
@click.option("--rounds", type=int, default=3, help="Number of rounds")
@click.option(
    "--delay", type=float, default=1.0, help="Delay between operations (seconds)"
)
@click.pass_context
def workflow(ctx, jobs: int, rounds: int, delay: float):
    """Simulate complete workflow"""
    config = ctx.obj["config"]

    success(f"Starting workflow simulation: {jobs} jobs x {rounds} rounds")

    for round_num in range(1, rounds + 1):
        click.echo(f"\n--- Round {round_num} ---")

        # Submit jobs
        submitted_jobs = []
        for i in range(jobs):
            prompt = f"Test job {i + 1} (round {round_num})"

            # Simulate job submission
            job_id = f"job_{round_num}_{i + 1}_{int(time.time())}"
            submitted_jobs.append(job_id)

            output(
                {
                    "action": "submit_job",
                    "job_id": job_id,
                    "prompt": prompt,
                    "round": round_num,
                },
                ctx.obj["output_format"],
            )

            time.sleep(delay)

        # Simulate job processing
        for job_id in submitted_jobs:
            # Simulate miner picking up job
            output(
                {
                    "action": "job_assigned",
                    "job_id": job_id,
                    "miner": f"miner_{random.randint(1, 3)}",
                    "status": "processing",
                },
                ctx.obj["output_format"],
            )

            time.sleep(delay * 0.5)

            # Simulate job completion
            earnings = random.uniform(1, 10)
            output(
                {
                    "action": "job_completed",
                    "job_id": job_id,
                    "earnings": earnings,
                    "status": "completed",
                },
                ctx.obj["output_format"],
            )

            time.sleep(delay * 0.5)

    output(
        {"status": "completed", "total_jobs": jobs * rounds, "rounds": rounds},
        ctx.obj["output_format"],
    )


@simulate.command()
@click.option("--clients", type=int, default=10, help="Number of clients")
@click.option("--miners", type=int, default=3, help="Number of miners")
@click.option("--duration", type=int, default=300, help="Test duration in seconds")
@click.option("--job-rate", type=float, default=1.0, help="Jobs per second")
@click.pass_context
def load_test(ctx, clients: int, miners: int, duration: int, job_rate: float):
    """Run load test"""
    start_time = time.time()
    end_time = start_time + duration
    job_interval = 1.0 / job_rate

    success(f"Starting load test: {clients} clients, {miners} miners, {duration}s")

    stats = {
        "jobs_submitted": 0,
        "jobs_completed": 0,
        "errors": 0,
        "start_time": start_time,
    }

    while time.time() < end_time:
        # Submit jobs
        for client_id in range(clients):
            if time.time() >= end_time:
                break

            job_id = f"load_test_{stats['jobs_submitted']}_{int(time.time())}"
            stats["jobs_submitted"] += 1

            # Simulate random job completion
            if random.random() > 0.1:  # 90% success rate
                stats["jobs_completed"] += 1
            else:
                stats["errors"] += 1

            time.sleep(job_interval)

        # Show progress
        elapsed = time.time() - start_time
        if elapsed % 30 < 1:  # Every 30 seconds
            output(
                {
                    "elapsed": elapsed,
                    "jobs_submitted": stats["jobs_submitted"],
                    "jobs_completed": stats["jobs_completed"],
                    "errors": stats["errors"],
                    "success_rate": stats["jobs_completed"]
                    / max(1, stats["jobs_submitted"])
                    * 100,
                },
                ctx.obj["output_format"],
            )

    # Final stats
    total_time = time.time() - start_time
    output(
        {
            "status": "completed",
            "duration": total_time,
            "jobs_submitted": stats["jobs_submitted"],
            "jobs_completed": stats["jobs_completed"],
            "errors": stats["errors"],
            "avg_jobs_per_second": stats["jobs_submitted"] / total_time,
            "success_rate": stats["jobs_completed"]
            / max(1, stats["jobs_submitted"])
            * 100,
        },
        ctx.obj["output_format"],
    )


@simulate.command()
@click.option("--file", required=True, help="Scenario file path")
@click.pass_context
def scenario(ctx, file: str):
    """Run predefined scenario"""
    scenario_path = Path(file)

    if not scenario_path.exists():
        error(f"Scenario file not found: {file}")
        return

    with open(scenario_path) as f:
        scenario = json.load(f)

    success(f"Running scenario: {scenario.get('name', 'Unknown')}")

    # Execute scenario steps
    for step in scenario.get("steps", []):
        step_type = step.get("type")
        step_name = step.get("name", "Unnamed step")

        click.echo(f"\nExecuting: {step_name}")

        if step_type == "submit_jobs":
            count = step.get("count", 1)
            for i in range(count):
                output(
                    {
                        "action": "submit_job",
                        "step": step_name,
                        "job_num": i + 1,
                        "prompt": step.get("prompt", f"Scenario job {i + 1}"),
                    },
                    ctx.obj["output_format"],
                )

        elif step_type == "wait":
            duration = step.get("duration", 1)
            time.sleep(duration)

        elif step_type == "check_balance":
            user = step.get("user", "client")
            # Would check actual balance
            output({"action": "check_balance", "user": user}, ctx.obj["output_format"])

    output(
        {"status": "completed", "scenario": scenario.get("name", "Unknown")},
        ctx.obj["output_format"],
    )


@simulate.command()
@click.argument("simulation_id")
@click.pass_context
def results(ctx, simulation_id: str):
    """Show simulation results"""
    # In a real implementation, this would query stored results
    # For now, return mock data
    output(
        {
            "simulation_id": simulation_id,
            "status": "completed",
            "start_time": time.time() - 3600,
            "end_time": time.time(),
            "duration": 3600,
            "total_jobs": 50,
            "successful_jobs": 48,
            "failed_jobs": 2,
            "success_rate": 96.0,
        },
        ctx.obj["output_format"],
    )
