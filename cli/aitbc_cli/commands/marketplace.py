"""Marketplace commands for AITBC CLI"""

import click
import httpx
import json
from typing import Optional, List
from ..utils import output, error, success


@click.group()
def marketplace():
    """GPU marketplace operations"""
    pass


@marketplace.group()
def gpu():
    """GPU marketplace operations"""
    pass


@gpu.command()
@click.option("--name", required=True, help="GPU name/model")
@click.option("--memory", type=int, help="GPU memory in GB")
@click.option("--cuda-cores", type=int, help="Number of CUDA cores")
@click.option("--compute-capability", help="Compute capability (e.g., 8.9)")
@click.option("--price-per-hour", type=float, help="Price per hour in AITBC")
@click.option("--description", help="GPU description")
@click.option("--miner-id", help="Miner ID (uses auth key if not provided)")
@click.pass_context
def register(ctx, name: str, memory: Optional[int], cuda_cores: Optional[int],
            compute_capability: Optional[str], price_per_hour: Optional[float],
            description: Optional[str], miner_id: Optional[str]):
    """Register GPU on marketplace"""
    config = ctx.obj['config']
    
    # Build GPU specs
    gpu_specs = {
        "name": name,
        "memory_gb": memory,
        "cuda_cores": cuda_cores,
        "compute_capability": compute_capability,
        "price_per_hour": price_per_hour,
        "description": description
    }
    
    # Remove None values
    gpu_specs = {k: v for k, v in gpu_specs.items() if v is not None}
    
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
            
            if response.status_code == 201:
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
@click.option("--hours", type=float, required=True, help="Rental duration in hours")
@click.option("--job-id", help="Job ID to associate with rental")
@click.pass_context
def book(ctx, gpu_id: str, hours: float, job_id: Optional[str]):
    """Book a GPU"""
    config = ctx.obj['config']
    
    try:
        booking_data = {
            "gpu_id": gpu_id,
            "duration_hours": hours
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
            
            if response.status_code == 201:
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
            
            if response.status_code == 201:
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
