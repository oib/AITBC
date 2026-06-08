"""GPU resource tracking commands for AITBC CLI."""

import json
from pathlib import Path

import click

from ..utils.http_client import AITBCHTTPClient, NetworkError, get_logger

from ..config import get_config
from ..utils import error, output, success
from ..utils.crypto_utils import bech32_to_hex

logger = get_logger(__name__)


@click.group(name="gpu-onchain")
def gpu():
    """GPU resource tracking commands (on-chain)"""
    pass


@gpu.command(name="register")
@click.option('--gpu-id', required=True, help='GPU unique identifier')
@click.option('--miner-id', required=True, help='Miner/provider ID')
@click.option('--model', required=True, help='GPU model (e.g., RTX 4090)')
@click.option('--memory-gb', type=int, required=True, help='GPU memory in GB')
@click.option('--cuda-version', default='', help='CUDA version')
@click.option('--region', default='', help='Geographic region')
@click.option('--capabilities', multiple=True, help='GPU capabilities (can specify multiple)')
@click.option('--price-per-hour', type=float, required=True, help='Price per hour in AIT')
@click.option('--wallet', required=True, help='Wallet name for signing')
@click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
@click.pass_context
def register_onchain(ctx, gpu_id: str, miner_id: str, model: str, memory_gb: int, 
                     cuda_version: str, region: str, capabilities: tuple, 
                     price_per_hour: float, wallet: str, format: str):
    """Register GPU with immutable specs on blockchain"""
    config = get_config()

    try:
        # Get RPC URL from config (use hub for cross-node operations)
        rpc_url = getattr(config, 'blockchain_rpc_url', 'http://localhost:8006')
        rpc_url = rpc_url.replace('localhost', config.hub_discovery_url or 'hub.aitbc.bubuit.net')

        # Get chain_id
        try:
            from ..utils.chain_id import get_chain_id
            chain_id = get_chain_id(rpc_url, override=None, timeout=5)
        except Exception:
            import os
            chain_id = os.getenv("CHAIN_ID", "ait-hub.aitbc.bubuit.net")

        # Load wallet to get address
        wallet_dir = Path.home() / ".aitbc" / "wallets"
        wallet_path = wallet_dir / f"{wallet}.json"
        
        if not wallet_path.exists():
            error(f"Wallet '{wallet}' not found at {wallet_path}")
            return

        with open(wallet_path) as f:
            wallet_data = json.load(f)
        
        registered_by = wallet_data['address']
        hex_address = bech32_to_hex(registered_by)

        # Submit GPU registration to blockchain RPC
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
        registration_data = {
            "gpu_id": gpu_id,
            "miner_id": miner_id,
            "model": model,
            "memory_gb": memory_gb,
            "cuda_version": cuda_version,
            "region": region,
            "capabilities": list(capabilities),
            "price_per_hour": price_per_hour,
            "registered_by": hex_address
        }
        result = http_client.post(f"/rpc/gpu/register?chain_id={chain_id}", json=registration_data)

        success(f"GPU '{gpu_id}' registered on-chain")
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error registering GPU on-chain: {e}")


@gpu.command(name="query")
@click.argument('gpu_id')
@click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
@click.pass_context
def query_gpu(ctx, gpu_id: str, format: str):
    """Query GPU registration from blockchain"""
    config = get_config()

    try:
        # Get RPC URL from config (use hub for cross-node operations)
        rpc_url = getattr(config, 'blockchain_rpc_url', 'http://localhost:8006')
        rpc_url = rpc_url.replace('localhost', config.hub_discovery_url or 'hub.aitbc.bubuit.net')

        # Get chain_id
        try:
            from ..utils.chain_id import get_chain_id
            chain_id = get_chain_id(rpc_url, override=None, timeout=5)
        except Exception:
            import os
            chain_id = os.getenv("CHAIN_ID", "ait-hub.aitbc.bubuit.net")

        # Query GPU from blockchain RPC
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
        result = http_client.get(f"/rpc/gpu/info/{gpu_id}?chain_id={chain_id}")

        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error querying GPU: {e}")


@gpu.command(name="allocate")
@click.option('--gpu-id', required=True, help='GPU ID to allocate')
@click.option('--client-id', required=True, help='Client wallet address')
@click.option('--duration-hours', type=float, required=True, help='Allocation duration in hours')
@click.option('--total-cost', type=float, required=True, help='Total cost in AIT')
@click.option('--wallet', required=True, help='Wallet name for signing')
@click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
@click.pass_context
def allocate_gpu(ctx, gpu_id: str, client_id: str, duration_hours: float, 
                 total_cost: float, wallet: str, format: str):
    """Record GPU allocation on blockchain"""
    config = get_config()

    try:
        # Get RPC URL from config (use hub for cross-node operations)
        rpc_url = getattr(config, 'blockchain_rpc_url', 'http://localhost:8006')
        rpc_url = rpc_url.replace('localhost', config.hub_discovery_url or 'hub.aitbc.bubuit.net')

        # Get chain_id
        try:
            from ..utils.chain_id import get_chain_id
            chain_id = get_chain_id(rpc_url, override=None, timeout=5)
        except Exception:
            import os
            chain_id = os.getenv("CHAIN_ID", "ait-hub.aitbc.bubuit.net")

        # Load wallet to get address
        wallet_dir = Path.home() / ".aitbc" / "wallets"
        wallet_path = wallet_dir / f"{wallet}.json"
        
        if not wallet_path.exists():
            error(f"Wallet '{wallet}' not found at {wallet_path}")
            return

        with open(wallet_path) as f:
            wallet_data = json.load(f)
        
        allocated_by = wallet_data['address']
        hex_allocated_by = bech32_to_hex(allocated_by)
        hex_client_id = bech32_to_hex(client_id)

        # Submit GPU allocation to blockchain RPC
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
        allocation_data = {
            "gpu_id": gpu_id,
            "client_id": hex_client_id,
            "duration_hours": duration_hours,
            "total_cost": total_cost,
            "allocated_by": hex_allocated_by
        }
        result = http_client.post(f"/rpc/gpu/allocate?chain_id={chain_id}", json=allocation_data)

        success(f"GPU allocation recorded on-chain for '{gpu_id}'")
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error allocating GPU on-chain: {e}")


@gpu.command(name="allocations")
@click.argument('gpu_id')
@click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
@click.pass_context
def get_allocations(ctx, gpu_id: str, format: str):
    """Query GPU allocations from blockchain"""
    config = get_config()

    try:
        # Get RPC URL from config (use hub for cross-node operations)
        rpc_url = getattr(config, 'blockchain_rpc_url', 'http://localhost:8006')
        rpc_url = rpc_url.replace('localhost', config.hub_discovery_url or 'hub.aitbc.bubuit.net')

        # Get chain_id
        try:
            from ..utils.chain_id import get_chain_id
            chain_id = get_chain_id(rpc_url, override=None, timeout=5)
        except Exception:
            import os
            chain_id = os.getenv("CHAIN_ID", "ait-hub.aitbc.bubuit.net")

        # Query GPU allocations from blockchain RPC
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
        result = http_client.get(f"/rpc/gpu/allocations/{gpu_id}?chain_id={chain_id}")

        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error querying GPU allocations: {e}")


@gpu.command(name="list")
@click.option('--status', help='Filter by status (active, deactivated)')
@click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
@click.pass_context
def list_gpus(ctx, status: str | None, format: str):
    """List all GPUs registered on blockchain"""
    config = get_config()

    try:
        # Get RPC URL from config (use hub for cross-node operations)
        rpc_url = getattr(config, 'blockchain_rpc_url', 'http://localhost:8006')
        rpc_url = rpc_url.replace('localhost', config.hub_discovery_url or 'hub.aitbc.bubuit.net')

        # Get chain_id
        try:
            from ..utils.chain_id import get_chain_id
            chain_id = get_chain_id(rpc_url, override=None, timeout=5)
        except Exception:
            import os
            chain_id = os.getenv("CHAIN_ID", "ait-hub.aitbc.bubuit.net")

        # Query GPU list from blockchain RPC
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
        
        params = {"chain_id": chain_id}
        if status:
            params["status"] = status
            
        result = http_client.get("/rpc/gpus", params=params)

        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error listing GPUs: {e}")
