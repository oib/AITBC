"""Marketplace commands for AITBC CLI"""

import click
import httpx
import json
import asyncio
from typing import Optional, List, Dict, Any
from utils import output, error, success
import os


@click.group()
def marketplace():
    """GPU marketplace operations"""
    pass


@marketplace.group()
def gpu():
    """GPU marketplace operations"""
    pass


@gpu.command()
@click.option("--name", help="GPU name/model (auto-detected if not provided)")
@click.option("--memory", type=int, help="GPU memory in GB (auto-detected if not provided)")
@click.option("--cuda-cores", type=int, help="Number of CUDA cores")
@click.option("--compute-capability", help="Compute capability (e.g., 8.9)")
@click.option("--price-per-hour", type=float, required=True, help="Price per hour in AITBC")
@click.option("--description", help="GPU description")
@click.option("--miner-id", help="Miner ID (uses auth key if not provided)")
@click.option("--force", is_flag=True, help="Force registration even if hardware validation fails")
@click.pass_context
def register(ctx, name: Optional[str], memory: Optional[int], cuda_cores: Optional[int],
            compute_capability: Optional[str], price_per_hour: Optional[float],
            description: Optional[str], miner_id: Optional[str], force: bool):
    """Register GPU on marketplace (auto-detects hardware)"""
    config = ctx.obj['config']
    
    # Note: GPU hardware detection should be done by separate system monitoring tools
    # CLI provides guidance for manual hardware specification
    if not name or memory is None:
        output("💡 To auto-detect GPU hardware, use system monitoring tools:", ctx.obj['output_format'])
        output("   nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits", ctx.obj['output_format'])
        output("   Or specify --name and --memory manually", ctx.obj['output_format'])
        
        if not name and not memory:
            error("GPU name and memory must be specified for registration", ctx.obj['output_format'])
            return
    
    if not force:
        output("⚠️  Hardware validation skipped. Use --force to register without hardware validation.", 
               ctx.obj['output_format'])
    
    # Build GPU specs for registration
    gpu_specs = {
        "name": name,
        "memory_gb": memory,
        "cuda_cores": cuda_cores,
        "compute_capability": compute_capability,
        "price_per_hour": price_per_hour,
        "description": description,
        "miner_id": miner_id or config.api_key[:8],  # Use auth key as miner ID if not provided
        "registered_at": datetime.now().isoformat()
    }
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/v1/marketplace/gpu/register",
                headers={
                    "Content-Type": "application/json",
                    "X-Api-Key": config.api_key or "",
                    "X-Miner-ID": miner_id or "default"
                },
                json={"gpu": gpu_specs}
            )
            
            if response.status_code in (200, 201):
                result = response.json()
                success(f"GPU registered successfully: {result.get('gpu_id')}")
                output(result, ctx.obj['output_format'])
            else:
                error(f"Failed to register GPU: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")


@gpu.command()
@click.option("--available", is_flag=True, help="Show only available GPUs")
@click.option("--model", help="Filter by GPU model (supports wildcards)")
@click.option("--memory-min", type=int, help="Minimum memory in GB")
@click.option("--price-max", type=float, help="Maximum price per hour")
@click.option("--limit", type=int, default=20, help="Maximum number of results")
@click.pass_context
def list(ctx, available: bool, model: Optional[str], memory_min: Optional[int],
         price_max: Optional[float], limit: int):
    """List available GPUs"""
    config = ctx.obj['config']
    
    # Build query params
    params = {"limit": limit}
    if available:
        params["available"] = "true"
    if model:
        params["model"] = model
    if memory_min:
        params["memory_min"] = memory_min
    if price_max:
        params["price_max"] = price_max
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/v1/marketplace/gpu/list",
                params=params,
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                gpus = response.json()
                output(gpus, ctx.obj['output_format'])
            else:
                error(f"Failed to list GPUs: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")


@gpu.command()
@click.argument("gpu_id")
@click.pass_context
def details(ctx, gpu_id: str):
    """Get GPU details"""
    config = ctx.obj['config']
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/v1/marketplace/gpu/{gpu_id}",
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                gpu_data = response.json()
                output(gpu_data, ctx.obj['output_format'])
            else:
                error(f"GPU not found: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")


@gpu.command()
@click.argument("gpu_id")
@click.option("--duration", type=float, required=True, help="Rental duration in hours")
@click.option("--total-cost", type=float, required=True, help="Total cost")
@click.option("--job-id", help="Job ID to associate with rental")
@click.pass_context
def book(ctx, gpu_id: str, duration: float, total_cost: float, job_id: Optional[str]):
    """Book a GPU"""
    config = ctx.obj['config']
    
    try:
        booking_data = {
            "gpu_id": gpu_id,
            "duration_hours": duration,
            "total_cost": total_cost
        }
        if job_id:
            booking_data["job_id"] = job_id
            
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/v1/marketplace/gpu/{gpu_id}/book",
                headers={
                    "Content-Type": "application/json",
                    "X-Api-Key": config.api_key or ""
                },
                json=booking_data
            )
            
            if response.status_code in (200, 201):
                booking = response.json()
                success(f"GPU booked successfully: {booking.get('booking_id')}")
                output(booking, ctx.obj['output_format'])
            else:
                error(f"Failed to book GPU: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")


@gpu.command()
@click.argument("gpu_id")
@click.pass_context
def confirm(ctx, gpu_id: str):
    """Confirm booking (client ACK)."""
    config = ctx.obj["config"]
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/v1/marketplace/gpu/{gpu_id}/confirm",
                headers={"Content-Type": "application/json", "X-Api-Key": config.api_key or ""},
                json={"client_id": config.api_key or "client"},
            )
        if response.status_code in (200, 201):
            result = response.json()
            success(f"Booking confirmed for GPU {gpu_id}")
            output(result, ctx.obj["output_format"])
        else:
            error(f"Failed to confirm booking: {response.status_code} {response.text}")
    except Exception as e:
        error(f"Confirmation failed: {e}")


@gpu.command(name="ollama-task")
@click.argument("gpu_id")
@click.option("--model", default="llama2", help="Model name for Ollama task")
@click.option("--prompt", required=True, help="Prompt to execute")
@click.option("--temperature", type=float, default=0.7, show_default=True)
@click.option("--max-tokens", type=int, default=128, show_default=True)
@click.pass_context
def ollama_task(ctx, gpu_id: str, model: str, prompt: str, temperature: float, max_tokens: int):
    """Submit Ollama task via coordinator API."""
    config = ctx.obj["config"]
    try:
        payload = {
            "gpu_id": gpu_id,
            "model": model,
            "prompt": prompt,
            "parameters": {"temperature": temperature, "max_tokens": max_tokens},
        }
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/v1/tasks/ollama",
                headers={"Content-Type": "application/json", "X-Api-Key": config.api_key or ""},
                json=payload,
            )
        if response.status_code in (200, 201):
            result = response.json()
            success(f"Ollama task submitted: {result.get('task_id')}")
            output(result, ctx.obj["output_format"])
        else:
            error(f"Failed to submit Ollama task: {response.status_code} {response.text}")
    except Exception as e:
        error(f"Failed to submit Ollama task: {e}")


@gpu.command(name="pay")
@click.argument("booking_id")
@click.argument("amount", type=float)
@click.option("--from-wallet", required=True, help="Sender wallet name")
@click.option("--to-wallet", required=True, help="Recipient wallet address")
@click.option("--task-id", help="Optional task id to link payment")
@click.pass_context
def pay(ctx, booking_id: str, amount: float, from_wallet: str, to_wallet: str, task_id: Optional[str]):
    """Send payment via blockchain RPC (password-free for marketplace operations)"""
    config = ctx.obj["config"]
    
    try:
        # Get sender wallet address
        wallet_path = Path(f"/var/lib/aitbc/keystore/{from_wallet}.json")
        if not wallet_path.exists():
            error(f"Wallet '{from_wallet}' not found")
            return
            
        with open(wallet_path) as f:
            wallet_data = json.load(f)
        address = wallet_data["address"]
        
        # Get wallet balance from blockchain
        from aitbc_cli.utils.chain_id import get_chain_id
        rpc_url = config.get('rpc_url', 'http://localhost:8006')
        chain_id = get_chain_id(rpc_url)
        balance_response = httpx.Client().get(f"{rpc_url}/rpc/account/{address}?chain_id={chain_id}", timeout=5)
        if balance_response.status_code != 200:
            error(f"Failed to get wallet balance")
            return
            
        balance_data = balance_response.json()
        
        if balance_data["balance"] < amount:
            error(f"Insufficient balance. Have: {balance_data['balance']}, Need: {amount}")
            return
        
        # Create payment transaction
        tx_data = {
            "from": address,
            "to": to_wallet,
            "value": amount,
            "fee": 1,
            "nonce": balance_data["nonce"],
            "chain_id": chain_id,
            "payload": {
                "type": "marketplace_payment",
                "booking_id": booking_id,
                "task_id": task_id,
                "timestamp": str(time.time())
            }
        }
        
        # Submit transaction to blockchain
        tx_response = httpx.Client().post(f"{rpc_url}/rpc/transactions/marketplace", json=tx_data, timeout=5)
        if tx_response.status_code not in (200, 201):
            error(f"Failed to submit payment transaction: {tx_response.text}")
            return
            
        tx_result = tx_response.json()
        
        success(f"Payment sent: {tx_result.get('tx_hash')}")
        output({
            "tx_hash": tx_result.get("tx_hash"),
            "booking_id": booking_id,
            "amount": amount,
            "from": address,
            "to": to_wallet,
            "remaining_balance": balance_data["balance"] - amount
        }, ctx.obj["output_format"])
        
    except Exception as e:
        error(f"Payment failed: {e}")

@gpu.command()
@click.argument("gpu_id")
@click.option("--force", is_flag=True, help="Force delete even if GPU is booked")
@click.pass_context
def unregister(ctx, gpu_id: str, force: bool):
    """Unregister (delete) a GPU from marketplace"""
    config = ctx.obj['config']
    
    try:
        with httpx.Client() as client:
            response = client.delete(
                f"{config.coordinator_url}/v1/marketplace/gpu/{gpu_id}",
                params={"force": force},
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                result = response.json()
                success(f"GPU {gpu_id} unregistered")
                output(result, ctx.obj['output_format'])
            else:
                error(f"Failed to unregister GPU: {response.status_code}")
                if response.text:
                    error(response.text)
    except Exception as e:
        error(f"Network error: {e}")


@gpu.command()
@click.argument("gpu_id")
@click.pass_context
def release(ctx, gpu_id: str):
    """Release a booked GPU"""
    config = ctx.obj['config']
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/v1/marketplace/gpu/{gpu_id}/release",
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                success(f"GPU {gpu_id} released")
                output({"status": "released", "gpu_id": gpu_id}, ctx.obj['output_format'])
            else:
                error(f"Failed to release GPU: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")


@marketplace.command()
@click.option("--status", help="Filter by status (active, completed, cancelled)")
@click.option("--limit", type=int, default=10, help="Number of orders to show")
@click.pass_context
def orders(ctx, status: Optional[str], limit: int):
    """List marketplace orders"""
    config = ctx.obj['config']
    
    params = {"limit": limit}
    if status:
        params["status"] = status
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/v1/marketplace/orders",
                params=params,
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                orders = response.json()
                output(orders, ctx.obj['output_format'])
            else:
                error(f"Failed to get orders: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")


@marketplace.command()
@click.argument("model")
@click.pass_context
def pricing(ctx, model: str):
    """Get pricing information for a GPU model"""
    config = ctx.obj['config']
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/v1/marketplace/pricing/{model}",
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                pricing_data = response.json()
                output(pricing_data, ctx.obj['output_format'])
            else:
                error(f"Pricing not found: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")


@marketplace.command()
@click.argument("gpu_id")
@click.option("--limit", type=int, default=10, help="Number of reviews to show")
@click.pass_context
def reviews(ctx, gpu_id: str, limit: int):
    """Get GPU reviews"""
    config = ctx.obj['config']
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/v1/marketplace/gpu/{gpu_id}/reviews",
                params={"limit": limit},
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                reviews = response.json()
                output(reviews, ctx.obj['output_format'])
            else:
                error(f"Failed to get reviews: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")


@marketplace.command()
@click.argument("gpu_id")
@click.option("--rating", type=int, required=True, help="Rating (1-5)")
@click.option("--comment", help="Review comment")
@click.pass_context
def review(ctx, gpu_id: str, rating: int, comment: Optional[str]):
    """Add a review for a GPU"""
    config = ctx.obj['config']
    
    if not 1 <= rating <= 5:
        error("Rating must be between 1 and 5")
        return
    
    try:
        review_data = {
            "rating": rating,
            "comment": comment
        }
        
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/v1/marketplace/gpu/{gpu_id}/reviews",
                headers={
                    "Content-Type": "application/json",
                    "X-Api-Key": config.api_key or ""
                },
                json=review_data
            )
            
            if response.status_code in (200, 201):
                success("Review added successfully")
                output({"status": "review_added", "gpu_id": gpu_id}, ctx.obj['output_format'])
            else:
                error(f"Failed to add review: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")


@marketplace.group()
def bid():
    """Marketplace bid operations"""
    pass


@bid.command()
@click.option("--provider", required=True, help="Provider ID (e.g., miner123)")
@click.option("--capacity", type=int, required=True, help="Bid capacity (number of units)")
@click.option("--price", type=float, required=True, help="Price per unit in AITBC")
@click.option("--notes", help="Additional notes for the bid")
@click.pass_context
def submit(ctx, provider: str, capacity: int, price: float, notes: Optional[str]):
    """Submit a bid to the marketplace"""
    config = ctx.obj['config']
    
    # Validate inputs
    if capacity <= 0:
        error("Capacity must be greater than 0")
        return
    if price <= 0:
        error("Price must be greater than 0")
        return
    
    # Build bid data
    bid_data = {
        "provider": provider,
        "capacity": capacity,
        "price": price
    }
    if notes:
        bid_data["notes"] = notes
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/v1/marketplace/bids",
                headers={
                    "Content-Type": "application/json",
                    "X-Api-Key": config.api_key or ""
                },
                json=bid_data
            )
            
            if response.status_code == 202:
                result = response.json()
                success(f"Bid submitted successfully: {result.get('id')}")
                output(result, ctx.obj['output_format'])
            else:
                error(f"Failed to submit bid: {response.status_code}")
                if response.text:
                    error(f"Error details: {response.text}")
    except Exception as e:
        error(f"Network error: {e}")


@bid.command()
@click.option("--status", help="Filter by bid status (pending, accepted, rejected)")
@click.option("--provider", help="Filter by provider ID")
@click.option("--limit", type=int, default=20, help="Maximum number of results")
@click.pass_context
def list(ctx, status: Optional[str], provider: Optional[str], limit: int):
    """List marketplace bids"""
    config = ctx.obj['config']
    
    # Build query params
    params = {"limit": limit}
    if status:
        params["status"] = status
    if provider:
        params["provider"] = provider
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/v1/marketplace/bids",
                params=params,
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                bids = response.json()
                output(bids, ctx.obj['output_format'])
            else:
                error(f"Failed to list bids: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")


@bid.command()
@click.argument("bid_id")
@click.pass_context
def details(ctx, bid_id: str):
    """Get bid details"""
    config = ctx.obj['config']
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/v1/marketplace/bids/{bid_id}",
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                bid_data = response.json()
                output(bid_data, ctx.obj['output_format'])
            else:
                error(f"Bid not found: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")


@marketplace.group()
def offers():
    """Marketplace offers operations"""
    pass


@offers.command()
@click.option("--gpu-id", required=True, help="GPU ID to create offer for")
@click.option("--price-per-hour", type=float, required=True, help="Price per hour in AITBC")
@click.option("--min-hours", type=float, default=1, help="Minimum rental hours")
@click.option("--max-hours", type=float, default=24, help="Maximum rental hours")
@click.option("--models", help="Supported models (comma-separated, e.g. gemma3:1b,qwen2.5)")
@click.pass_context
def create(ctx, gpu_id: str, price_per_hour: float, min_hours: float, 
           max_hours: float, models: Optional[str]):
    """Create a marketplace offer for a registered GPU"""
    config = ctx.obj['config']
    
    offer_data = {
        "gpu_id": gpu_id,
        "price_per_hour": price_per_hour,
        "min_hours": min_hours,
        "max_hours": max_hours,
        "supported_models": models.split(",") if models else [],
        "status": "open"
    }
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/v1/marketplace/offers",
                headers={
                    "Content-Type": "application/json",
                    "X-Api-Key": config.api_key or ""
                },
                json=offer_data
            )
            
            if response.status_code in (200, 201, 202):
                result = response.json()
                success(f"Offer created: {result.get('id', 'ok')}")
                output(result, ctx.obj['output_format'])
            else:
                error(f"Failed to create offer: {response.status_code}")
                if response.text:
                    error(response.text)
    except Exception as e:
        error(f"Network error: {e}")


@offers.command()
@click.option("--status", help="Filter by offer status (open, reserved, closed)")
@click.option("--gpu-model", help="Filter by GPU model")
@click.option("--price-max", type=float, help="Maximum price per hour")
@click.option("--memory-min", type=int, help="Minimum memory in GB")
@click.option("--region", help="Filter by region")
@click.option("--limit", type=int, default=20, help="Maximum number of results")
@click.pass_context
def list(ctx, status: Optional[str], gpu_model: Optional[str], price_max: Optional[float],
         memory_min: Optional[int], region: Optional[str], limit: int):
    """List marketplace offers"""
    config = ctx.obj['config']
    
    # Build query params
    params = {"limit": limit}
    if status:
        params["status"] = status
    if gpu_model:
        params["gpu_model"] = gpu_model
    if price_max:
        params["price_max"] = price_max
    if memory_min:
        params["memory_min"] = memory_min
    if region:
        params["region"] = region
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/v1/marketplace/offers",
                params=params,
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                offers = response.json()
                output(offers, ctx.obj['output_format'])
            else:
                error(f"Failed to list offers: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")


# OpenClaw Agent Marketplace Commands
@marketplace.group()
def agents():
    """OpenClaw agent marketplace operations"""
    pass


@agents.command()
@click.option("--agent-id", required=True, help="Agent ID")
@click.option("--agent-type", required=True, help="Agent type (compute_provider, compute_consumer, power_trader)")
@click.option("--capabilities", help="Agent capabilities (comma-separated)")
@click.option("--region", help="Agent region")
@click.option("--reputation", type=float, default=0.8, help="Initial reputation score")
@click.pass_context
def register(ctx, agent_id: str, agent_type: str, capabilities: Optional[str], 
            region: Optional[str], reputation: float):
    """Register agent on OpenClaw marketplace"""
    config = ctx.obj['config']
    
    agent_data = {
        "agent_id": agent_id,
        "agent_type": agent_type,
        "capabilities": capabilities.split(",") if capabilities else [],
        "region": region,
        "initial_reputation": reputation
    }
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/agents/register",
                json=agent_data,
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code in (200, 201):
                success(f"Agent {agent_id} registered successfully")
                output(response.json(), ctx.obj['output_format'])
            else:
                error(f"Failed to register agent: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")


@agents.command()
@click.option("--agent-id", help="Filter by agent ID")
@click.option("--agent-type", help="Filter by agent type")
@click.option("--region", help="Filter by region")
@click.option("--reputation-min", type=float, help="Minimum reputation score")
@click.option("--limit", type=int, default=20, help="Maximum number of results")
@click.pass_context
def list_agents(ctx, agent_id: Optional[str], agent_type: Optional[str],
                region: Optional[str], reputation_min: Optional[float], limit: int):
    """List registered agents"""
    config = ctx.obj['config']
    
    params = {"limit": limit}
    if agent_id:
        params["agent_id"] = agent_id
    if agent_type:
        params["agent_type"] = agent_type
    if region:
        params["region"] = region
    if reputation_min:
        params["reputation_min"] = reputation_min
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/agents",
                params=params,
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                agents = response.json()
                output(agents, ctx.obj['output_format'])
            else:
                error(f"Failed to list agents: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")


@agents.command()
@click.option("--resource-id", required=True, help="AI resource ID")
@click.option("--resource-type", required=True, help="Resource type (nvidia_a100, nvidia_h100, edge_gpu)")
@click.option("--compute-power", type=float, required=True, help="Compute power (TFLOPS)")
@click.option("--gpu-memory", type=int, required=True, help="GPU memory in GB")
@click.option("--price-per-hour", type=float, required=True, help="Price per hour in AITBC")
@click.option("--provider-id", required=True, help="Provider agent ID")
@click.pass_context
def list_resource(ctx, resource_id: str, resource_type: str, compute_power: float,
                 gpu_memory: int, price_per_hour: float, provider_id: str):
    """List AI resource on marketplace"""
    config = ctx.obj['config']
    
    resource_data = {
        "resource_id": resource_id,
        "resource_type": resource_type,
        "compute_power": compute_power,
        "gpu_memory": gpu_memory,
        "price_per_hour": price_per_hour,
        "provider_id": provider_id,
        "availability": True
    }
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/v1/marketplace/list",
                json=resource_data,
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code in (200, 201):
                success(f"Resource {resource_id} listed successfully")
                output(response.json(), ctx.obj['output_format'])
            else:
                error(f"Failed to list resource: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")


@agents.command()
@click.option("--resource-id", required=True, help="AI resource ID to rent")
@click.option("--consumer-id", required=True, help="Consumer agent ID")
@click.option("--duration", type=int, required=True, help="Rental duration in hours")
@click.option("--max-price", type=float, help="Maximum price per hour")
@click.pass_context
def rent(ctx, resource_id: str, consumer_id: str, duration: int, max_price: Optional[float]):
    """Rent AI resource from marketplace"""
    config = ctx.obj['config']
    
    rental_data = {
        "resource_id": resource_id,
        "consumer_id": consumer_id,
        "duration_hours": duration,
        "max_price_per_hour": max_price or 10.0,
        "requirements": {
            "min_compute_power": 50.0,
            "min_gpu_memory": 8,
            "gpu_required": True
        }
    }
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/v1/marketplace/rent",
                json=rental_data,
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code in (200, 201):
                success("AI resource rented successfully")
                output(response.json(), ctx.obj['output_format'])
            else:
                error(f"Failed to rent resource: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")


@agents.command()
@click.option("--contract-type", required=True, help="Smart contract type")
@click.option("--params", required=True, help="Contract parameters (JSON string)")
@click.option("--gas-limit", type=int, default=1000000, help="Gas limit")
@click.pass_context
def execute_contract(ctx, contract_type: str, params: str, gas_limit: int):
    """Execute blockchain smart contract"""
    config = ctx.obj['config']
    
    try:
        contract_params = json.loads(params)
    except json.JSONDecodeError:
        error("Invalid JSON parameters")
        return
    
    contract_data = {
        "contract_type": contract_type,
        "parameters": contract_params,
        "gas_limit": gas_limit,
        "value": contract_params.get("value", 0)
    }
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/blockchain/contracts/execute",
                json=contract_data,
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                success("Smart contract executed successfully")
                output(response.json(), ctx.obj['output_format'])
            else:
                error(f"Failed to execute contract: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")


@agents.command()
@click.option("--from-agent", required=True, help="From agent ID")
@click.option("--to-agent", required=True, help="To agent ID")
@click.option("--amount", type=float, required=True, help="Amount in AITBC")
@click.option("--payment-type", default="ai_power_rental", help="Payment type")
@click.pass_context
def pay(ctx, from_agent: str, to_agent: str, amount: float, payment_type: str):
    """Process AITBC payment between agents"""
    config = ctx.obj['config']
    
    payment_data = {
        "from_agent": from_agent,
        "to_agent": to_agent,
        "amount": amount,
        "currency": "AITBC",
        "payment_type": payment_type
    }
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/payments/process",
                json=payment_data,
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                success(f"Payment of {amount} AITBC processed successfully")
                output(response.json(), ctx.obj['output_format'])
            else:
                error(f"Failed to process payment: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")


@agents.command()
@click.option("--agent-id", required=True, help="Agent ID")
@click.pass_context
def reputation(ctx, agent_id: str):
    """Get agent reputation information"""
    config = ctx.obj['config']
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/agents/{agent_id}/reputation",
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                output(response.json(), ctx.obj['output_format'])
            else:
                error(f"Failed to get reputation: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")


@agents.command()
@click.option("--agent-id", required=True, help="Agent ID")
@click.pass_context
def balance(ctx, agent_id: str):
    """Get agent AITBC balance"""
    config = ctx.obj['config']
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/agents/{agent_id}/balance",
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                output(response.json(), ctx.obj['output_format'])
            else:
                error(f"Failed to get balance: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")


@agents.command()
@click.option("--time-range", default="daily", help="Time range (daily, weekly, monthly)")
@click.pass_context
def analytics(ctx, time_range: str):
    """Get marketplace analytics"""
    config = ctx.obj['config']
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/analytics/marketplace",
                params={"time_range": time_range},
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                output(response.json(), ctx.obj['output_format'])
            else:
                error(f"Failed to get analytics: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")


# Governance Commands
@marketplace.group()
def governance():
    """OpenClaw agent governance operations"""
    pass


@governance.command()
@click.option("--title", required=True, help="Proposal title")
@click.option("--description", required=True, help="Proposal description")
@click.option("--proposal-type", required=True, help="Proposal type")
@click.option("--params", required=True, help="Proposal parameters (JSON string)")
@click.option("--voting-period", type=int, default=72, help="Voting period in hours")
@click.pass_context
def create_proposal(ctx, title: str, description: str, proposal_type: str, 
                   params: str, voting_period: int):
    """Create governance proposal"""
    config = ctx.obj['config']
    
    try:
        proposal_params = json.loads(params)
    except json.JSONDecodeError:
        error("Invalid JSON parameters")
        return
    
    proposal_data = {
        "title": title,
        "description": description,
        "proposal_type": proposal_type,
        "proposed_changes": proposal_params,
        "voting_period_hours": voting_period
    }
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/proposals/create",
                json=proposal_data,
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code in (200, 201):
                success("Proposal created successfully")
                output(response.json(), ctx.obj['output_format'])
            else:
                error(f"Failed to create proposal: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")


@governance.command()
@click.option("--proposal-id", required=True, help="Proposal ID")
@click.option("--vote", required=True, type=click.Choice(["for", "against", "abstain"]), help="Vote type")
@click.option("--reasoning", help="Vote reasoning")
@click.pass_context
def vote(ctx, proposal_id: str, vote: str, reasoning: Optional[str]):
    """Vote on governance proposal"""
    config = ctx.obj['config']
    
    vote_data = {
        "proposal_id": proposal_id,
        "vote": vote,
        "reasoning": reasoning or ""
    }
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/voting/cast-vote",
                json=vote_data,
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code in (200, 201):
                success(f"Vote '{vote}' cast successfully")
                output(response.json(), ctx.obj['output_format'])
            else:
                error(f"Failed to cast vote: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")


@governance.command()
@click.option("--status", help="Filter by status")
@click.option("--limit", type=int, default=20, help="Maximum number of results")
@click.pass_context
def list_proposals(ctx, status: Optional[str], limit: int):
    """List governance proposals"""
    config = ctx.obj['config']
    
    params = {"limit": limit}
    if status:
        params["status"] = status
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/proposals",
                params=params,
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                output(response.json(), ctx.obj['output_format'])
            else:
                error(f"Failed to list proposals: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")


# Performance Testing Commands
@marketplace.group()
def test():
    """OpenClaw marketplace testing operations"""
    pass


@test.command()
@click.option("--concurrent-users", type=int, default=10, help="Concurrent users")
@click.option("--rps", type=int, default=50, help="Requests per second")
@click.option("--duration", type=int, default=30, help="Test duration in seconds")
@click.pass_context
def load(ctx, concurrent_users: int, rps: int, duration: int):
    """Run marketplace load test"""
    config = ctx.obj['config']
    
    test_config = {
        "concurrent_users": concurrent_users,
        "requests_per_second": rps,
        "test_duration_seconds": duration,
        "ramp_up_period_seconds": 5
    }
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/testing/load-test",
                json=test_config,
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                success("Load test completed successfully")
                output(response.json(), ctx.obj['output_format'])
            else:
                error(f"Failed to run load test: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")


@test.command()
@click.pass_context
def health(ctx):
    """Test marketplace health endpoints"""
    config = ctx.obj['config']
    
    endpoints = [
        "/health",
        "/v1/v1/marketplace/status",
        "/v1/agents/health",
        "/v1/blockchain/health"
    ]
    
    results = {}
    
    for endpoint in endpoints:
        try:
            with httpx.Client() as client:
                response = client.get(
                    f"{config.coordinator_url}{endpoint}",
                    headers={"X-Api-Key": config.api_key or ""}
                )
                results[endpoint] = {
                    "status_code": response.status_code,
                    "healthy": response.status_code == 200
                }
        except Exception as e:
            results[endpoint] = {
                "status_code": 0,
                "healthy": False,
                "error": str(e)
            }
    
    output(results, ctx.obj['output_format'])
