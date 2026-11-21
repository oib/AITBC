"""GPU resource tracking commands for AITBC CLI."""

from decimal import Decimal

import click

from aitbc.config.hub import normalize_hub_base
from aitbc.utils.validation import validate_address_strict

from ..config import get_config
from ..utils import DECIMAL, error, output, resolve_output_format, success
from ..utils.wallet_secret import wallet_password_options
from ..utils.chain_id import resolve_chain_id
from ..utils.error_handling import CLIError
from ..utils.http_client import AITBCHTTPClient, NetworkError, get_logger

logger = get_logger(__name__)

# Expected failure surface for the deregister preflight lookup (#2403): HTTP
# transport errors plus the data-shape errors an unexpected response can raise.
_PREFLIGHT_ERRORS = (
    NetworkError,
    OSError,
    ValueError,
    KeyError,
    TypeError,
    RuntimeError,
)


def _hub_rpc_url(config, rpc_url: str) -> str:
    """Swap a localhost RPC base for the hub's public one when a hub is known.

    The old ``rpc_url.replace("localhost", host)`` kept the ``http://`` scheme
    and the ``:8202`` port — both dead at the edge, which only forwards the
    nginx mounts. ``normalize_hub_base`` yields ``https://<hub>`` on followers
    and the local nginx on the hub itself; callers append ``/rpc/...`` paths.
    """
    if config.hub_discovery_url and "localhost" in rpc_url:
        return normalize_hub_base(config.hub_discovery_url) or rpc_url
    return rpc_url


@click.group(
    name="gpu-onchain",
    epilog="""Examples:

  aitbc gpu-onchain register --gpu-id gpu-1 --miner-id miner-1 --model 'RTX 4090' --memory-gb 24 --price-per-hour 10 --wallet wallet-1

  aitbc gpu-onchain list""",
)
def gpu():
    """Register, query, allocate, deregister, and list GPU resources on the blockchain."""
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
@wallet_password_options
@click.option("--wait", is_flag=True, help="Wait for the transaction to be mined")
@click.option("--format", type=click.Choice(["table", "json"]), default=None, help="Output format")
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
    password_file: str | None,
    password_stdin: bool,
    wait: bool,
    format: str,
):
    """Register GPU immutable specs on the blockchain with a signing wallet."""
    config = get_config()

    try:
        # Get RPC URL from config (use hub for cross-node operations)
        rpc_url = _hub_rpc_url(config, getattr(config, "blockchain_rpc_url", "http://localhost:8202"))

        chain_id = resolve_chain_id(ctx, rpc_url)

        from ..utils.gpu_onchain import submit_gpu_register, apply_wait_result

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
            password_file=password_file,
            password_stdin=password_stdin,
        )

        tx_hash = result.get("transaction_hash", result.get("tx_hash"))
        if wait and tx_hash:
            apply_wait_result(result, rpc_url, tx_hash)

        success(f"GPU '{gpu_id}' registration transaction submitted")
        output(result, resolve_output_format(ctx, format))
    except CLIError:
        # abort() failures already printed their message — keep the exit code.
        raise
    except click.Abort:
        raise
    except NetworkError as e:
        error(f"Network error: {e}")
        raise click.Abort() from e
    except Exception as e:
        error(f"Error registering GPU on-chain: {e}")
        raise click.Abort() from e


@gpu.command(
    name="query",
    epilog="""Examples:

  aitbc gpu-onchain query --gpu-id gpu-1

  aitbc gpu-onchain query --gpu-id gpu-1 --output json""",
)
@click.option("--gpu-id", "gpu_id", required=True, help="The Gpu id.")
@click.option("--format", type=click.Choice(["table", "json"]), default=None, help="Output format")
@click.pass_context
def query_gpu(ctx, gpu_id: str, format: str):
    """Query a GPU's on-chain registration details."""
    config = get_config()

    try:
        # Get RPC URL from config (use hub for cross-node operations)
        rpc_url = _hub_rpc_url(config, getattr(config, "blockchain_rpc_url", "http://localhost:8202"))

        chain_id = resolve_chain_id(ctx, rpc_url, required=False)

        # Query GPU from blockchain RPC; omit chain_id when unresolved so
        # the node applies its own chain default.
        http_client = AITBCHTTPClient(
            base_url=rpc_url,
            timeout=30,
            api_key=(ctx.obj or {}).get("api_key") or getattr(config, "blockchain_rpc_api_key", None),
        )
        params = {"chain_id": chain_id} if chain_id else {}
        result = http_client.get(f"/rpc/gpu/info/{gpu_id}", params=params)

        output(result, resolve_output_format(ctx, format))
    except CLIError:
        # abort() failures already printed their message — keep the exit code.
        raise
    except click.Abort:
        raise
    except NetworkError as e:
        error(f"Network error: {e}")
        raise click.Abort() from e
    except Exception as e:
        error(f"Error querying GPU: {e}")
        raise click.Abort() from e


def _refuse_deregister_with_active_allocations(ctx, config, rpc_url: str, chain_id: str, gpu_id: str) -> None:
    """Refuse ``gpu-onchain deregister`` while the GPU has active allocations (#2403).

    Before state-transition v28 there is no on-chain release/completion
    transaction, so a deregistered GPU keeps its ``active_allocations`` count
    forever — the row goes ``deactivated`` with allocations still open and
    nothing can close them (v28's ``gpu-onchain release`` is the exit, once
    armed). Query the registration first and make the operator choose
    ``--force`` deliberately. A failed lookup does not block: the chain-side
    deregister rule is unchanged.
    """
    try:
        http_client = AITBCHTTPClient(
            base_url=rpc_url,
            timeout=15,
            api_key=(ctx.obj or {}).get("api_key") or getattr(config, "blockchain_rpc_api_key", None),
        )
        params = {"chain_id": chain_id} if chain_id else {}
        info = http_client.get(f"/rpc/gpu/info/{gpu_id}", params=params)
    except _PREFLIGHT_ERRORS as e:
        # Preflight is advisory; the chain enforces the real deregister rule.
        logger.warning("Could not check active allocations for %s before deregister: %s", gpu_id, e)
        return
    active = info.get("active_allocations") if isinstance(info, dict) else None
    if isinstance(active, int) and active > 0:
        error(
            f"GPU '{gpu_id}' has {active} active on-chain allocation(s); deregistering now leaves them "
            "open (GPU_DEALLOCATE exists only once chain v28 is armed, #2403). "
            "Release them first with 'aitbc gpu-onchain release --allocation-id <id>' "
            "(chain v28+), complete them, or re-run with --force to deactivate anyway."
        )
        raise click.Abort()


@gpu.command(
    name="deregister",
    epilog="""Examples:

  aitbc gpu-onchain deregister --gpu-id gpu-1 --wallet wallet-1

  aitbc gpu-onchain deregister --gpu-id gpu-1 --wallet wallet-1 --wait""",
)
@click.option("--gpu-id", required=True, help="GPU ID to take out of service")
@click.option("--wallet", required=True, help="Wallet name for signing (must be the GPU's registrant)")
@wallet_password_options
@click.option("--wait", is_flag=True, help="Wait for the transaction to be mined")
@click.option(
    "--force",
    is_flag=True,
    help="Deregister even while on-chain allocations are still active (they stay active forever — no release tx exists yet, #2403)",
)
@click.option("--format", type=click.Choice(["table", "json"]), default=None, help="Output format")
@click.pass_context
def deregister_gpu(
    ctx,
    gpu_id: str,
    wallet: str,
    password: str | None,
    password_file: str | None,
    password_stdin: bool,
    wait: bool,
    force: bool,
    format: str,
):
    """Deactivate an on-chain GPU registration (signed by its registrant).

    The registration stays on the chain with status 'deactivated' and takes no
    new allocations; registering the same gpu-id again reactivates it. Takes
    effect only once the chain has activated state-transition v10; before that
    the node refuses the transaction. Open on-chain allocations are NOT
    released by deregistration — the command refuses while
    ``active_allocations`` is non-zero unless ``--force``; close them first
    with ``gpu-onchain release`` (chain v28+).
    This is not `aitbc gpu unregister`, which only edits the local GPU service.
    """
    config = get_config()

    try:
        # Get RPC URL from config (use hub for cross-node operations)
        rpc_url = _hub_rpc_url(config, getattr(config, "blockchain_rpc_url", "http://localhost:8202"))

        chain_id = resolve_chain_id(ctx, rpc_url)

        if not force:
            _refuse_deregister_with_active_allocations(ctx, config, rpc_url, chain_id, gpu_id)

        from ..utils.gpu_onchain import submit_gpu_deregister, apply_wait_result

        result = submit_gpu_deregister(
            ctx, rpc_url, chain_id, wallet, password, gpu_id, password_file=password_file, password_stdin=password_stdin
        )

        tx_hash = result.get("transaction_hash", result.get("tx_hash"))
        if wait and tx_hash:
            apply_wait_result(result, rpc_url, tx_hash)

        success(f"GPU '{gpu_id}' deregistration transaction submitted")
        output(result, resolve_output_format(ctx, format))
    except CLIError:
        # abort() failures already printed their message — keep the exit code.
        raise
    except click.Abort:
        raise
    except NetworkError as e:
        error(f"Network error: {e}")
        raise click.Abort() from e
    except Exception as e:
        error(f"Error deregistering GPU on-chain: {e}")
        raise click.Abort() from e


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
@wallet_password_options
@click.option("--wait", is_flag=True, help="Wait for the transaction to be mined")
@click.option("--format", type=click.Choice(["table", "json"]), default=None, help="Output format")
@click.pass_context
def allocate_gpu(
    ctx,
    gpu_id: str,
    client_id: str,
    duration_hours: float,
    total_cost: Decimal,
    wallet: str,
    password: str | None,
    password_file: str | None,
    password_stdin: bool,
    wait: bool,
    format: str,
):
    """Record a GPU allocation on the blockchain for a client."""
    config = get_config()

    try:
        # Get RPC URL from config (use hub for cross-node operations)
        rpc_url = _hub_rpc_url(config, getattr(config, "blockchain_rpc_url", "http://localhost:8202"))

        chain_id = resolve_chain_id(ctx, rpc_url)

        try:
            hex_client_id = validate_address_strict(client_id)
        except Exception as e:
            error(f"Invalid client address: {e}")
            raise click.Abort() from e

        from ..utils.gpu_onchain import submit_gpu_allocate, apply_wait_result

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
            password_file=password_file,
            password_stdin=password_stdin,
        )

        tx_hash = result.get("transaction_hash", result.get("tx_hash"))
        if wait and tx_hash:
            apply_wait_result(result, rpc_url, tx_hash)

        success(f"GPU allocation transaction submitted for '{gpu_id}'")
        output(result, resolve_output_format(ctx, format))
    except CLIError:
        # abort() failures already printed their message — keep the exit code.
        raise
    except click.Abort:
        raise
    except NetworkError as e:
        error(f"Network error: {e}")
        raise click.Abort() from e
    except Exception as e:
        error(f"Error allocating GPU on-chain: {e}")
        raise click.Abort() from e


@gpu.command(
    name="release",
    epilog="""Examples:

  aitbc gpu-onchain release --allocation-id alloc_abc123 --wallet wallet-1

  aitbc gpu-onchain release --allocation-id alloc_abc123 --wallet wallet-1 --wait""",
)
@click.option(
    "--allocation-id",
    "allocation_id",
    required=True,
    help="On-chain allocation id to complete (from 'gpu-onchain allocations')",
)
@click.option("--gpu-id", "gpu_id", default=None, help="GPU id (optional; recorded in the tx payload)")
@click.option("--wallet", required=True, help="Wallet name for signing (allocator or recorded client)")
@wallet_password_options
@click.option("--wait", is_flag=True, help="Wait for the transaction to be mined")
@click.option("--format", type=click.Choice(["table", "json"]), default=None, help="Output format")
@click.pass_context
def release_allocation(
    ctx,
    allocation_id: str,
    gpu_id: str | None,
    wallet: str,
    password: str | None,
    password_file: str | None,
    password_stdin: bool,
    wait: bool,
    format: str,
):
    """Complete an on-chain GPU allocation (signed GPU_DEALLOCATE, chain v28+).

    Marks the ``gpu_allocation`` row ``completed`` so the GPU's
    ``active_allocations`` count drops and the registration can be
    deregistered cleanly. The signing wallet must be the allocation's
    allocator or its recorded client; the node refuses anyone else. Before
    the chain activates state-transition v28 the node refuses the type at
    admission — there is no off-chain release.
    """
    config = get_config()

    try:
        rpc_url = _hub_rpc_url(config, getattr(config, "blockchain_rpc_url", "http://localhost:8202"))

        chain_id = resolve_chain_id(ctx, rpc_url)

        from ..utils.gpu_onchain import submit_gpu_deallocate, wait_for_tx

        result = submit_gpu_deallocate(
            ctx,
            rpc_url,
            chain_id,
            wallet,
            password,
            allocation_id,
            gpu_id=gpu_id,
            password_file=password_file,
            password_stdin=password_stdin,
        )

        tx_hash = result.get("transaction_hash", result.get("tx_hash"))
        if wait and tx_hash:
            mined = wait_for_tx(rpc_url, tx_hash)
            if mined:
                result["mined"] = True
                result["block_height"] = mined.get("block_height")
            else:
                result["mined"] = False

        success(f"GPU allocation '{allocation_id}' release transaction submitted")
        output(result, resolve_output_format(ctx, format))
    except CLIError:
        # abort() failures already printed their message — keep the exit code.
        raise
    except click.Abort:
        raise
    except NetworkError as e:
        error(f"Network error: {e}")
        raise click.Abort() from e
    except Exception as e:
        error(f"Error releasing GPU allocation on-chain: {e}")
        raise click.Abort() from e


@gpu.command(
    name="allocations",
    epilog="""Examples:

  aitbc gpu-onchain allocations --gpu-id gpu-1

  aitbc gpu-onchain allocations --gpu-id gpu-1 --output json""",
)
@click.option("--gpu-id", "gpu_id", required=True, help="The Gpu id.")
@click.option("--format", type=click.Choice(["table", "json"]), default=None, help="Output format")
@click.pass_context
def get_allocations(ctx, gpu_id: str, format: str):
    """Query on-chain allocations for a GPU."""
    config = get_config()

    try:
        # Get RPC URL from config (use hub for cross-node operations)
        rpc_url = _hub_rpc_url(config, getattr(config, "blockchain_rpc_url", "http://localhost:8202"))

        chain_id = resolve_chain_id(ctx, rpc_url, required=False)

        # Query GPU allocations; omit chain_id when unresolved so the node
        # applies its own chain default.
        http_client = AITBCHTTPClient(
            base_url=rpc_url,
            timeout=30,
            api_key=(ctx.obj or {}).get("api_key") or getattr(config, "blockchain_rpc_api_key", None),
        )
        params = {"chain_id": chain_id} if chain_id else {}
        result = http_client.get(f"/rpc/gpu/allocations/{gpu_id}", params=params)

        output(result, resolve_output_format(ctx, format))
    except CLIError:
        # abort() failures already printed their message — keep the exit code.
        raise
    except click.Abort:
        raise
    except NetworkError as e:
        error(f"Network error: {e}")
        raise click.Abort() from e
    except Exception as e:
        error(f"Error querying GPU allocations: {e}")
        raise click.Abort() from e


@gpu.command(
    name="list",
    epilog="""Examples:

  aitbc gpu-onchain list

  aitbc gpu-onchain list --status active""",
)
@click.option("--status", help="Filter by status (active, deactivated)")
@click.option("--format", type=click.Choice(["table", "json"]), default=None, help="Output format")
@click.pass_context
def list_gpus(ctx, status: str | None, format: str):
    """List all GPUs registered on the blockchain, optionally filtered by status."""
    config = get_config()

    try:
        # Get RPC URL from config (use hub for cross-node operations)
        rpc_url = _hub_rpc_url(config, getattr(config, "blockchain_rpc_url", "http://localhost:8202"))

        chain_id = resolve_chain_id(ctx, rpc_url, required=False)

        # Query GPU list from blockchain RPC
        http_client = AITBCHTTPClient(
            base_url=rpc_url,
            timeout=30,
            api_key=(ctx.obj or {}).get("api_key") or getattr(config, "blockchain_rpc_api_key", None),
        )

        params = {"chain_id": chain_id} if chain_id else {}
        if status:
            params["status"] = status

        result = http_client.get("/rpc/gpus", params=params)

        output(result, resolve_output_format(ctx, format))
    except CLIError:
        # abort() failures already printed their message — keep the exit code.
        raise
    except click.Abort:
        raise
    except NetworkError as e:
        error(f"Network error: {e}")
        raise click.Abort() from e
    except Exception as e:
        error(f"Error listing GPUs: {e}")
        raise click.Abort() from e
