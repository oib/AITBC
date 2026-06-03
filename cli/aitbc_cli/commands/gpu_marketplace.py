"""
Local GPU service commands for hardware management
"""

import json

import click

from aitbc import AITBCHTTPClient, NetworkError

from ..config import get_config
from ..utils import error, info, output, success


@click.group()
def gpu():
    """Local GPU service commands for hardware management"""
    pass


@gpu.command()
@click.pass_context
def discover(ctx):
    """Auto-discover GPU specifications using nvidia-smi"""
    try:
        config = get_config()
        http_client = AITBCHTTPClient(base_url=config.gpu_service_url, timeout=10)
        result = http_client.get("/v1/gpu/discover")
        success("GPU discovery completed")
        output(result, ctx.obj.get("output_format", "table"))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error discovering GPUs: {e}")


@gpu.command()
@click.argument('gpu_id')
@click.option('--specs', help='GPU specifications (JSON string) - auto-discovered if not provided')
@click.pass_context
def register(ctx, gpu_id: str, specs: str | None):
    """Register a GPU with the gpu-service (no island credentials required)"""
    config = get_config()

    try:
        http_client = AITBCHTTPClient(base_url=config.gpu_service_url, timeout=10)

        gpu_data = {"gpu_id": gpu_id}

        if specs:
            try:
                gpu_data["specs"] = json.loads(specs)
            except json.JSONDecodeError:
                error("Invalid JSON specifications")
                raise click.Abort()

        result = http_client.post("/v1/gpu/register", json=gpu_data)
        success(f"GPU {gpu_id} registered successfully")
        output(result, ctx.obj.get("output_format", "table"))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error registering GPU: {e}")


@gpu.command()
@click.argument('gpu_id')
@click.pass_context
def unregister(ctx, gpu_id: str):
    """Unregister/delete a GPU from the gpu-service"""
    config = get_config()

    try:
        http_client = AITBCHTTPClient(base_url=config.gpu_service_url, timeout=10)
        result = http_client.delete(f"/v1/gpu/{gpu_id}")
        success(f"GPU {gpu_id} unregistered successfully")
        output(result, ctx.obj.get("output_format", "table"))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error unregistering GPU: {e}")


@gpu.command()
@click.argument('gpu_id')
@click.option('--pricing', help='Updated pricing model (JSON string)')
@click.option('--status', help='Update GPU status')
@click.pass_context
def update(ctx, gpu_id: str, pricing: str | None, status: str | None):
    """Update GPU registration with the gpu-service (no island credentials required)"""
    config = get_config()

    try:
        http_client = AITBCHTTPClient(base_url=config.gpu_service_url, timeout=10)

        update_data = {}

        if pricing:
            try:
                pricing_data = json.loads(pricing)
                update_data["price_per_hour"] = pricing_data.get("price_per_hour", pricing_data)
            except json.JSONDecodeError:
                # Try as direct number
                try:
                    update_data["price_per_hour"] = float(pricing)
                except ValueError:
                    error("Invalid pricing value")
                    raise click.Abort()

        if status:
            update_data["status"] = status

        if not update_data:
            error("No updates provided. Specify --pricing or --status")
            raise click.Abort()

        result = http_client.put(f"/v1/gpu/{gpu_id}", json=update_data)
        success(f"GPU {gpu_id} updated successfully")
        output(result, ctx.obj.get("output_format", "table"))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error updating GPU: {e}")


@gpu.command()
@click.pass_context
def list(ctx):
    """List local registered GPUs (no island credentials required)"""
    try:
        # Load CLI config
        config = get_config()

        # Query GPU service for registered GPUs
        try:
            http_client = AITBCHTTPClient(base_url=config.gpu_service_url, timeout=10)
            transactions = http_client.get("/v1/transactions")

            if not transactions:
                info("No registered GPUs found")
                return

            # Format output for GPU registry data
            gpu_data = []
            for gpu in transactions:
                gpu_data.append({
                    "GPU ID": gpu.get('id'),
                    "Model": gpu.get('model'),
                    "Memory (GB)": gpu.get('memory_gb'),
                    "Price/Hour": f"{gpu.get('price_per_hour', 0):.4f} AIT",
                    "Status": gpu.get('status'),
                    "Region": gpu.get('region') or 'N/A',
                    "Miner ID": gpu.get('miner_id', '')[:16] + "...",
                    "Created": gpu.get('created_at', '')[:19] if gpu.get('created_at') else 'N/A'
                })

            output(gpu_data, ctx.obj.get('output_format', 'table'), title="Local Registered GPUs")
        except NetworkError as e:
            error(f"Network error querying GPU service: {e}")
            raise click.Abort()

    except Exception as e:
        error(f"Error listing GPUs: {str(e)}")
        raise click.Abort()
