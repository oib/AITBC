"""GPU resource tracking commands for AITBC CLI."""

from decimal import Decimal

import click

from aitbc.utils.validation import validate_address_strict

from ..config import get_config
from ..utils import DECIMAL, error, output, success
from ..utils.http_client import AITBCHTTPClient, NetworkError, get_logger

logger = get_logger(__name__)


@click.group(
    name="gpu-onchain",
    epilog="""Examples:

  aitbc gpu-onchain register --gpu-id gpu-1 --miner-id miner-1 --model 'RTX 4090' --memory-gb 24 --price-per-hour 10 --wallet wallet-1

  aitbc gpu-onchain list""",
)
def gpu():
    """Register, query, allocate, and list GPU resources on the blockchain."""
    pass


@gpu.command(
    name="register",
    epilog="""Examples:

  aitbc gpu-onchain register --gpu-id gpu-1 --miner-id miner-1 --model 'RTX 4090' --memory-gb 24 --price-per-hour 10 --wallet wallet-1

  aitbc gpu-onchain register --gpu-id gpu-1 --miner-id miner-1 --model 'A100' --memory-gb 80 --price-per-hour 50 --wallet wallet-1""",
)
@click.option("--gpu-id", required=True, help="GPU unique identifier")
@click.option("--miner-id", required=True, help="Miner/provider ID")
@click.option("--model", required=True, help="GPU model (e.g., RTX 4090)")
@click.option("--memory-gb", type=int, required=True, help="GPU memory in GB")
@click.option("--cuda-version", default="", help="CUDA version")
@click.option("--region", default="", help="Geographic region")
@click.option("--capabilities", multiple=True, help="GPU capabilities (can specify multiple)")
@click.option("--price-per-hour", type=DECIMAL, required=True, help="Price per hour in AIT")
@click.option("--wallet", required=True, help="Wallet name for signing")
@click.option("--password", help="Wallet password (or AITBC_WALLET_PASSWORD env var)")
@click.option("--wait", is_flag=True, help="Wait for the transaction to be mined")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def register_onchain(
    ctx,
    gpu_id: str,
    miner_id: str,
    model: str,
    memory_gb: int,
    cuda_version: str,
    region: str,
    capabilities: tuple,
    price_per_hour: Decimal,
    wallet: str,
    password: str | None,
    wait: bool,
    format: str,
):
    """Register GPU immutable specs on the blockchain with a signing wallet."""
    config = get_config()

    try:
        # Get RPC URL from config (use hub for cross-node operations)
        rpc_url = getattr(config, "blockchain_rpc_url", "http://localhost:8202")
        if config.hub_discovery_url and "localhost" in rpc_url:
            rpc_url = rpc_url.replace("localhost", config.hub_discovery_url)

        # Get chain_id
        try:
            from ..utils.chain_id import get_chain_id

            chain_id = get_chain_id(rpc_url, override=None, timeout=5)
        except Exception:
            import os

            chain_id = os.getenv("CHAIN_ID", "ait-hub.aitbc.bubuit.net")

        from ..utils.gpu_onchain import submit_gpu_register, wait_for_tx

        result = submit_gpu_register(
            ctx,
            rpc_url,
            chain_id,
            wallet,
            password,
            gpu_id,
            miner_id,
            model,
            memory_gb,
            cuda_version,
            region,
            capabilities,
            price_per_hour,
        )

        tx_hash = result.get("transaction_hash", result.get("tx_hash"))
        if wait and tx_hash:
            mined = wait_for_tx(rpc_url, tx_hash)
            if mined:
                result["mined"] = True
                result["block_height"] = mined.get("block_height")
            else:
                result["mined"] = False

        success(f"GPU '{gpu_id}' registration transaction submitted")
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error registering GPU on-chain: {e}")


@gpu.command(
    name="query",
    epilog="""Examples:

  aitbc gpu-onchain query --gpu-id gpu-1

  aitbc gpu-onchain query --gpu-id gpu-1 --output json""",
)
@click.option("--gpu-id", "gpu_id", required=True, help="The Gpu id.")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def query_gpu(ctx, gpu_id: str, format: str):
    """Query a GPU's on-chain registration details."""
    config = get_config()

    try:
        # Get RPC URL from config (use hub for cross-node operations)
        rpc_url = getattr(config, "blockchain_rpc_url", "http://localhost:8202")
        if config.hub_discovery_url and "localhost" in rpc_url:
            rpc_url = rpc_url.replace("localhost", config.hub_discovery_url)

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


@gpu.command(
    name="allocate",
    epilog="""Examples:

  aitbc gpu-onchain allocate --gpu-id gpu-1 --client-id 0x... --duration-hours 2 --total-cost 20 --wallet wallet-1""",
)
@click.option("--gpu-id", required=True, help="GPU ID to allocate")
@click.option("--client-id", required=True, help="Client wallet address")
@click.option("--duration-hours", type=float, required=True, help="Allocation duration in hours")
@click.option("--total-cost", type=DECIMAL, required=True, help="Total cost in AIT")
@click.option("--wallet", required=True, help="Wallet name for signing")
@click.option("--password", help="Wallet password (or AITBC_WALLET_PASSWORD env var)")
@click.option("--wait", is_flag=True, help="Wait for the transaction to be mined")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def allocate_gpu(
    ctx,
    gpu_id: str,
    client_id: str,
    duration_hours: float,
    total_cost: Decimal,
    wallet: str,
    password: str | None,
    wait: bool,
    format: str,
):
    """Record a GPU allocation on the blockchain for a client."""
    config = get_config()

    try:
        # Get RPC URL from config (use hub for cross-node operations)
        rpc_url = getattr(config, "blockchain_rpc_url", "http://localhost:8202")
        if config.hub_discovery_url and "localhost" in rpc_url:
            rpc_url = rpc_url.replace("localhost", config.hub_discovery_url)

        # Get chain_id
        try:
            from ..utils.chain_id import get_chain_id

            chain_id = get_chain_id(rpc_url, override=None, timeout=5)
        except Exception:
            import os

            chain_id = os.getenv("CHAIN_ID", "ait-hub.aitbc.bubuit.net")

        try:
            hex_client_id = validate_address_strict(client_id)
        except Exception as e:
            error(f"Invalid client address: {e}")
            return

        from ..utils.gpu_onchain import submit_gpu_allocate, wait_for_tx

        result = submit_gpu_allocate(
            ctx,
            rpc_url,
            chain_id,
            wallet,
            password,
            gpu_id,
            hex_client_id,
            duration_hours,
            total_cost,
        )

        tx_hash = result.get("transaction_hash", result.get("tx_hash"))
        if wait and tx_hash:
            mined = wait_for_tx(rpc_url, tx_hash)
            if mined:
                result["mined"] = True
                result["block_height"] = mined.get("block_height")
            else:
                result["mined"] = False

        success(f"GPU allocation transaction submitted for '{gpu_id}'")
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error allocating GPU on-chain: {e}")


@gpu.command(
    name="allocations",
    epilog="""Examples:

  aitbc gpu-onchain allocations --gpu-id gpu-1

  aitbc gpu-onchain allocations --gpu-id gpu-1 --output json""",
)
@click.option("--gpu-id", "gpu_id", required=True, help="The Gpu id.")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def get_allocations(ctx, gpu_id: str, format: str):
    """Query on-chain allocations for a GPU."""
    config = get_config()

    try:
        # Get RPC URL from config (use hub for cross-node operations)
        rpc_url = getattr(config, "blockchain_rpc_url", "http://localhost:8202")
        if config.hub_discovery_url and "localhost" in rpc_url:
            rpc_url = rpc_url.replace("localhost", config.hub_discovery_url)

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


@gpu.command(
    name="list",
    epilog="""Examples:

  aitbc gpu-onchain list

  aitbc gpu-onchain list --status active""",
)
@click.option("--status", help="Filter by status (active, deactivated)")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def list_gpus(ctx, status: str | None, format: str):
    """List all GPUs registered on the blockchain, optionally filtered by status."""
    config = get_config()

    try:
        # Get RPC URL from config (use hub for cross-node operations)
        rpc_url = getattr(config, "blockchain_rpc_url", "http://localhost:8202")
        if config.hub_discovery_url and "localhost" in rpc_url:
            rpc_url = rpc_url.replace("localhost", config.hub_discovery_url)

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
