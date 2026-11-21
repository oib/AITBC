"""CLI commands for protected fixed-duration GPU rentals (energy floor).

Commands:
  aitbc market gpu list     - List GPUs in the coordinator registry
  aitbc market gpu register - Register a GPU in the coordinator registry (miner credential)
  aitbc market gpu quote    - Request an operator-signed energy quote
  aitbc market gpu buy      - Fund a quoted rental (native or EVM)
  aitbc market gpu agreement-create - Mint an AIPowerRental agreement id (EVM)
  aitbc market gpu status   - Check rental/escrow status
  aitbc market gpu release  - Release escrow to provider
  aitbc market gpu refund   - Request a refund
"""

from __future__ import annotations

import json
import os
import sys
from decimal import Decimal, InvalidOperation
from typing import Any

import click
from eth_utils import is_address

from ...config import _resolve_market_api_key, get_config
from ...utils.wallet_secret import wallet_password_options
from ...utils import error, info, output, success, warning
from ...utils.address import to_canonical
from ...utils.agent_identity_resolve import resolve_escrow_parties
from ...utils.chain_id import agent_registry_chain_id, resolve_chain_id
from ...utils.energy_quote import (
    assert_configured_native_chain,
    expected_quote_chain_id,
    compute_settlement_breakdown,
    parse_quote,
    verify_quote,
)
from ...utils.escrow import create_signed_escrow_lock
from ...utils.http_client import (
    AITBCHTTPClient,
    NetworkError,
    auth_headers,
    get_logger,
    http_error_detail,
    http_response_status,
)
from ...utils.wallet_loader import load_wallet_for_payment
from ._signing import signed_job_request_fields

logger = get_logger(__name__)


# The coordinator holds POST /v1/market/gpu/purchase open while it waits for the
# escrow lock to seal (ESCROW_LOCK_SEAL_WAIT_SECONDS, 180 s on hub; bc-2 blocks
# land every ~79 s). A 30 s client timeout made every real purchase report
# "outcome unknown" on a purchase that had succeeded (#2302).
_PURCHASE_TIMEOUT_DEFAULT_SECONDS = 240.0


def _purchase_timeout() -> float:
    """Read timeout for the purchase POST; ``AITBC_GPU_BUY_TIMEOUT_SECONDS`` overrides."""
    raw = os.environ.get("AITBC_GPU_BUY_TIMEOUT_SECONDS", "").strip()
    if raw:
        try:
            value = float(raw)
        except ValueError:
            return _PURCHASE_TIMEOUT_DEFAULT_SECONDS
        if value > 0:
            return value
    return _PURCHASE_TIMEOUT_DEFAULT_SECONDS


def _coordinator_url() -> str:
    """Return the coordinator API base URL, stripping a trailing /v1 path
    so endpoints that already begin with /v1/ do not double-prefix it.
    """
    config = get_config()
    url = (config.coordinator_url or config.coordinator_api_url or "http://localhost:8203").rstrip("/")
    if url.endswith("/v1"):
        url = url[:-3]
    return url.rstrip("/")


def _blockchain_rpc_url() -> str:
    """Return the blockchain RPC base URL."""
    config = get_config()
    return config.blockchain_rpc_url or "http://localhost:8202"


def _print_quote(quote_dict: dict[str, Any], breakdown: dict[str, Any] | None = None) -> None:
    """Print a human-readable summary of an energy quote."""
    quote = parse_quote(quote_dict)
    info(f"Quote ID:     {quote.quote_id}")
    info(f"Job ID:       {quote.job_id}")
    info(f"Domain:       {quote.domain}")
    info(f"Chain:        {quote.chain_id}")
    info(f"Route:        {quote.settlement_route.value}")
    info(f"Resource:     {quote.resource_id}")
    info(f"Model:        {quote.model_id}")
    info(f"GPUs:         {quote.gpu_count}")
    info(f"Duration:     {quote.duration_seconds}s ({quote.duration_seconds / 3600:.2f}h)")
    info(f"TBP:          {quote.tbp_watts}W")
    info(f"EUR/kWh:      {quote.eur_per_kwh_scaled / 1e18:.6f}")
    info(f"AIT/EUR:      {quote.ait_per_eur_scaled / 1e18:.6f}")
    info(f"Net floor:    {quote.net_energy_floor_units} units")
    info(f"Principal:    {quote.principal_units} units")
    info(f"Fee (bps):    {quote.fee_basis_points}")
    info(f"Operator:     {quote.operator_address or '(unsigned)'}")
    info(f"Expires at:   {quote.expires_at}")
    if breakdown:
        info(f"Buyer charge: {breakdown['buyer_charge_units']} units")
        info(f"Provider:     {breakdown['provider_credit_units']} units")
        info(f"Platform fee: {breakdown['platform_fee_units']} units")
    if quote.operator_signature:
        success("Operator signature present")
    else:
        warning("No operator signature -- quote cannot be funded")


@click.group()
def gpu():
    """Protected fixed-duration GPU rental commands (energy floor)."""


def _gpu_list_params(
    status_filter: str | None,
    # Opaque passthrough to the coordinator's price_max query param — a filter
    # bound, not a settled amount, so it is forwarded verbatim (no float money).
    price_max: Any,
    region: str | None,
    model: str | None,
    limit: int,
) -> dict[str, Any]:
    """Build the query params for GET /v1/market/gpu/list."""
    params: dict[str, Any] = {"limit": min(limit, 500)}
    if status_filter == "available":
        params["available"] = "true"
    elif status_filter == "booked":
        params["available"] = "false"
    if price_max is not None:
        params["price_max"] = price_max
    if region:
        params["region"] = region
    if model:
        params["model"] = model
    return params


@gpu.command("register")
@click.option("--name", required=True, help="GPU model name, e.g. 'RTX 4060 Ti'")
@click.option("--memory-gb", type=int, required=True, help="GPU memory in GB")
@click.option("--price-per-hour", required=True, help="Listing price per hour, in AIT (decimal string)")
@click.option("--compute-capability", default="", help="CUDA compute capability, e.g. 8.9")
@click.option("--region", default="localhost", help="Region label")
@click.option("--resource-id", default=None, help="Energy-floor resource id (enables protected rentals)")
@click.option("--model-id", default=None, help="Model id for the quote")
@click.option("--protected", is_flag=True, help="Mark as a protected (energy-floor) resource")
@click.option("--json-output", is_flag=True, help="Output raw JSON")
@click.pass_context
def register_gpu_cmd(
    ctx, name, memory_gb, price_per_hour, compute_capability, region, resource_id, model_id, protected, json_output
):
    """Register a GPU in the coordinator registry (POST /v1/market/gpu/register).

    Needs a miner credential (``aitbc auth login`` or ``--api-key``).
    Idempotent: registering the same name/resource again returns the same id.
    """
    try:
        price = Decimal(price_per_hour)
    except InvalidOperation:
        error(f"Invalid --price-per-hour: {price_per_hour!r}")
        raise click.Abort() from None
    if not price.is_finite() or price < 0:
        error("--price-per-hour must be a finite non-negative AIT amount")
        raise click.Abort()
    specs: dict[str, Any] = {
        "name": name,
        "memory_gb": memory_gb,
        "price_per_hour": str(price),
        "compute_capability": compute_capability,
        "region": region,
        "protected": protected,
    }
    if resource_id:
        specs["resource_id"] = resource_id
    if model_id:
        specs["model_id"] = model_id
    client = AITBCHTTPClient(base_url=_coordinator_url(), timeout=30, headers=_auth_headers(ctx))
    try:
        result = client.post("/v1/market/gpu/register", json={"gpu": specs})
    except NetworkError as e:
        error(f"Failed to register GPU: {e}")
        raise click.Abort() from e
    if json_output:
        output(result, "json")
        return
    gpu_id = result.get("gpu_id", "?") if isinstance(result, dict) else "?"
    if isinstance(result, dict) and result.get("already_registered"):
        success(f"GPU already registered: {gpu_id} (price updated)")
    else:
        success(f"GPU registered: {gpu_id}")


@gpu.command("list")
@click.option(
    "--status",
    "status_filter",
    type=click.Choice(["available", "booked", "all"]),
    default=None,
    help="Filter by GPU status (default: all)",
)
@click.option("--price-max", "price_max", type=float, default=None, help="Maximum price_per_hour")
@click.option("--region", default=None, help="Filter by region (case-insensitive)")
@click.option("--model", default=None, help="Filter by model substring")
@click.option("--limit", type=int, default=100, help="Max rows (server cap 500)")
@click.option("--json-output", is_flag=True, help="Output raw JSON")
@click.pass_context
def list_gpus(ctx, status_filter, price_max, region, model, limit, json_output):
    """List GPUs in the coordinator registry (GET /v1/market/gpu/list)."""
    client = AITBCHTTPClient(base_url=_coordinator_url(), timeout=30, headers=_auth_headers(ctx))
    params = _gpu_list_params(status_filter, price_max, region, model, limit)
    try:
        gpus = client.get_json("/v1/market/gpu/list", params=params)
    except NetworkError as e:
        error(f"Failed to list GPUs: {e}")
        raise click.Abort() from e
    if not isinstance(gpus, list):
        error(f"Unexpected response shape from /market/gpu/list: {type(gpus).__name__}")
        raise click.Abort()
    if json_output:
        output(gpus, "json")
        return
    if not gpus:
        info("No GPUs in the coordinator registry")
        return
    for g in gpus:
        if not isinstance(g, dict):
            continue
        info(
            f"{g.get('id', '?')}  {g.get('model', '?')}  "
            f"{g.get('price_per_hour', '?')}/h  status={g.get('status', '?')}  "
            f"region={g.get('region', '-')}  mem={g.get('memory_gb', '?')}GB"
        )
    success(f"{len(gpus)} GPU(s) listed")


@gpu.command()
@click.option("--gpu-id", required=True, help="GPU registry ID")
@click.option(
    "--buyer-id",
    required=True,
    help="Buyer client ID (native rail: funding wallet 0x…, or auth client id with --buyer-agent-id)",
)
@click.option("--buyer-agent-id", default=None, help="Buyer agent id; quote buyer field resolved via coordinator")
@click.option("--duration-hours", type=float, default=1.0, help="Rental duration in hours")
@click.option("--gpu-count", type=int, default=1, help="Number of GPUs")
@click.option("--max-ait", type=float, default=None, help="Maximum AIT buyer cap")
@click.option(
    "--settlement",
    type=click.Choice(["native", "evm"]),
    default="native",
    help="Settlement rail",
)
@click.option("--json-output", is_flag=True, help="Output raw JSON")
@click.pass_context
def quote(ctx, gpu_id, buyer_id, buyer_agent_id, duration_hours, gpu_count, max_ait, settlement, json_output):
    """Request an operator-signed energy quote for a GPU rental."""
    if settlement == "native" and not buyer_agent_id and not is_address(buyer_id):
        error(
            f"--buyer-id {buyer_id!r} is not a wallet address. On the native rail the quote's "
            "buyer field is set from --buyer-id and `aitbc market gpu buy` can only fund it when it "
            "equals the signing wallet — a non-address buyer id produces an unfundable quote. "
            "Pass the buyer wallet address (0x...) as --buyer-id, or pass --buyer-agent-id to resolve it"
        )
        sys.exit(1)
    client = AITBCHTTPClient(base_url=_coordinator_url(), timeout=30, headers=_auth_headers(ctx))
    payload: dict[str, Any] = {
        "buyer_id": buyer_id,
        "gpu_id": gpu_id,
        "duration_hours": duration_hours,
        "gpu_count": gpu_count,
        "settlement_route": settlement,
    }
    if buyer_agent_id:
        payload["buyer_agent_id"] = buyer_agent_id
    if max_ait is not None:
        payload["buyer_max_amount"] = str(max_ait)
    try:
        result = client.post("/v1/market/gpu/quote", json=payload)
    except NetworkError as e:
        error(f"Failed to get quote: {e}")
        sys.exit(1)

    if json_output:
        output(json.dumps(result, indent=2, default=str))
        return

    quote_dict = result.get("energy_quote") or {}
    if not quote_dict:
        error("No energy quote in response")
        sys.exit(1)

    # Verify the quote locally before showing it to the buyer. The expected
    # chain id is the operator-configured NATIVE_CHAIN_ID if set, else the
    # chain this node would sign for; if it cannot be resolved the binding
    # check is skipped with a caveat rather than claimed.
    config = get_config()
    parsed = parse_quote(quote_dict)
    expected_id, expected_src = expected_quote_chain_id(ctx, _blockchain_rpc_url(), strict=False)
    verification = verify_quote(
        parsed,
        expected_operator_address=config.energy_operator_address,
        expected_domain=config.energy_quote_domain,
        expected_chain_id=expected_id,
        max_rate_age_seconds=config.energy_max_rate_age_seconds,
    )
    if not verification.valid:
        warning(
            f"Quote verification failed: {verification.refusal_reason} ({verification.refusal_code}; expected id from {expected_src})"
        )
    elif expected_id is None:
        warning("Quote verified locally (chain binding not checked: chain id unresolved)")
    else:
        success("Quote verified locally")

    breakdown = compute_settlement_breakdown(parsed)
    _print_quote(quote_dict, breakdown)
    info(f"Buyer charge:  {result.get('buyer_charge_ait', 'N/A')} AIT")


def _load_energy_quote_file(path: str | None) -> dict[str, Any]:
    """Read and unwrap the operator energy-quote JSON; aborts on bad input."""
    if not path:
        error("--energy-quote is required (path to JSON file)")
        sys.exit(1)
    try:
        with open(path) as f:
            quote_dict: dict[str, Any] = json.load(f)
    except OSError as e:
        error(f"Cannot read --energy-quote file {path}: {e.strerror or e}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        error(f"Invalid JSON in --energy-quote file {path}: {e}")
        sys.exit(1)
    # The quote endpoint may return a wrapper object; unwrap the energy_quote.
    unwrapped = quote_dict.get("energy_quote", quote_dict)
    return unwrapped if isinstance(unwrapped, dict) else quote_dict


@gpu.command()
@click.option("--gpu-id", required=True, help="GPU registry ID")
@click.option("--buyer-id", required=True, help="Buyer client ID from the quote (must match authenticated client on purchase)")
@click.option("--buyer-agent-id", default=None, help="Buyer agent id; must match signing wallet via resolve API")
@click.option("--provider-agent-id", default=None, help="Provider agent id; must match quote provider via resolve API")
@click.option("--job-id", required=True, help="Job ID from the quote response")
@click.option("--duration-hours", type=float, required=True, help="Rental duration in hours")
@click.option(
    "--settlement",
    type=click.Choice(["native", "evm"]),
    default="native",
    help="Settlement rail",
)
@click.option("--wallet", help="Wallet name for signing")
@click.option("--wallet-path", help="Direct wallet file path")
@wallet_password_options
@click.option("--energy-quote", help="JSON file containing the energy quote")
@click.option("--max-ait", type=float, default=None, help="Maximum AIT buyer cap")
@click.option("--yes", is_flag=True, help="Skip confirmation prompt")
@click.option("--json-output", is_flag=True, help="Output raw JSON")
@click.pass_context
def buy(
    ctx,
    gpu_id,
    buyer_id,
    buyer_agent_id,
    provider_agent_id,
    job_id,
    duration_hours,
    settlement,
    wallet,
    wallet_path,
    password,
    password_file,
    password_stdin,
    energy_quote,
    max_ait,
    yes,
    json_output,
):
    """Fund a quoted GPU rental (native escrow or EVM contract)."""
    quote_dict = _load_energy_quote_file(energy_quote)

    config = get_config()

    # Verify the quote before funding. On the native rail the ESCROW_LOCK is
    # signed for exactly the resolved chain (--chain-id > CHAIN_ID > RPC
    # probe), resolved once here and reused for the lock. A configured
    # NATIVE_CHAIN_ID is only an assertion about the chain the quote was
    # minted for — it may refuse the buy, never redirect it onto another
    # chain. The read-only EVM rail keeps configured-wins semantics.
    rpc_url = _blockchain_rpc_url()
    if settlement == "native":
        signing_id = resolve_chain_id(ctx, rpc_url)
        assert_configured_native_chain(ctx, config.native_chain_id, signing_id)
        expected_id: str | None = signing_id
        expected_src = "resolved --chain-id/CHAIN_ID/RPC probe"
    else:
        expected_id, expected_src = expected_quote_chain_id(ctx, rpc_url, strict=False)
    parsed = parse_quote(quote_dict)
    verification = verify_quote(
        parsed,
        expected_operator_address=config.energy_operator_address,
        expected_domain=config.energy_quote_domain,
        expected_chain_id=expected_id,
        max_rate_age_seconds=config.energy_max_rate_age_seconds,
    )
    if not verification.valid:
        error(
            f"Quote verification failed: {verification.refusal_reason} ({verification.refusal_code}; expected id from {expected_src})"
        )
        sys.exit(1)
    if expected_id is None:
        warning("chain binding not checked: chain id unresolved")
    success("Quote verified")

    breakdown = compute_settlement_breakdown(parsed)

    # Load the buyer wallet for signing.
    buyer_address, private_key, wallet_id = load_wallet_for_payment(
        ctx,
        wallet_name=wallet,
        wallet_path=wallet_path,
        password=password,
        password_file=password_file,
        password_stdin=password_stdin,
        require_private_key=True,
    )

    # Verify the buyer address matches the quote.
    if to_canonical(buyer_address) != to_canonical(parsed.buyer):
        error(f"Wallet address {buyer_address} does not match quote buyer {parsed.buyer}")
        sys.exit(1)

    if buyer_agent_id or provider_agent_id:
        bind_chain = signing_id if settlement == "native" and signing_id else resolve_chain_id(ctx, rpc_url)
        buyer_address, provider_resolved, buyer_agent_id, provider_agent_id = resolve_escrow_parties(
            ctx,
            buyer=buyer_address,
            provider=parsed.provider,
            buyer_agent_id=buyer_agent_id,
            provider_agent_id=provider_agent_id,
            chain_id=agent_registry_chain_id(bind_chain),
        )
        if to_canonical(provider_resolved) != to_canonical(parsed.provider):
            error(f"Resolved provider {provider_resolved} does not match quote provider {parsed.provider}")
            sys.exit(1)

    if settlement == "native":
        _buy_native(
            ctx,
            buyer_id=buyer_id,
            buyer_agent_id=buyer_agent_id,
            provider_agent_id=provider_agent_id,
            gpu_id=gpu_id,
            job_id=job_id,
            duration_hours=duration_hours,
            quote_dict=quote_dict,
            buyer_address=buyer_address,
            private_key=private_key or "",
            max_ait=max_ait,
            yes=yes,
            json_output=json_output,
            breakdown=breakdown,
            chain_id=expected_id,
        )
    else:
        _buy_evm(
            ctx,
            buyer_id=buyer_id,
            gpu_id=gpu_id,
            job_id=job_id,
            duration_hours=duration_hours,
            quote_dict=quote_dict,
            buyer_address=buyer_address,
            private_key=private_key or "",
            max_ait=max_ait,
            yes=yes,
            json_output=json_output,
            breakdown=breakdown,
        )


def _buy_native(
    ctx,
    *,
    buyer_id,
    buyer_agent_id=None,
    provider_agent_id=None,
    gpu_id,
    job_id,
    duration_hours,
    quote_dict,
    buyer_address,
    private_key,
    max_ait,
    yes,
    json_output,
    breakdown,
    chain_id=None,
):
    """Fund a native protected rental by signing ESCROW_LOCK locally."""
    from ...utils.escrow import get_node_wallet

    rpc_url = _blockchain_rpc_url()
    parsed = parse_quote(quote_dict)

    # Get the node wallet to send the lock to.
    node_wallet = get_node_wallet(ctx, rpc_url)
    if not node_wallet:
        error("Could not determine node wallet address from RPC")
        sys.exit(1)

    from decimal import Decimal

    # Confirm the funding action.
    charge_ait = Decimal(str(breakdown["buyer_charge_units"])) / Decimal(str(parsed.settlement_unit_scale))
    if not yes:
        click.confirm(
            f"This will lock {charge_ait:.6f} AIT ({breakdown['buyer_charge_units']} units) "
            f"for GPU {gpu_id} rental. Continue?",
            abort=True,
        )

    # Build and sign the ESCROW_LOCK transaction locally.
    amount_ait = Decimal(str(charge_ait))
    lock_tx, signature = create_signed_escrow_lock(
        ctx,
        rpc_url=rpc_url,
        job_id=job_id,
        buyer=buyer_address,
        provider=parsed.provider,
        amount_ait=amount_ait,
        private_key=private_key,
        chain_id=chain_id or resolve_chain_id(ctx, rpc_url),
        node_wallet=node_wallet,
        energy_quote_id=parsed.quote_id,
        energy_quote_digest=parsed.digest_sha256().hex(),
        settlement_route=parsed.settlement_route.value,
        settlement_asset=parsed.settlement_asset,
        settlement_unit_scale=parsed.settlement_unit_scale,
    )

    # Submit to the coordinator's escrow create endpoint.
    client = AITBCHTTPClient(base_url=_coordinator_url(), timeout=_purchase_timeout(), headers=_auth_headers(ctx))
    payload: dict[str, Any] = {
        "buyer_id": buyer_id,
        "gpu_id": gpu_id,
        "duration_hours": duration_hours,
        "payment_method": "blockchain",
        "job_id": job_id,
        "energy_quote": quote_dict,
        "protected": True,
        "buyer_address": buyer_address,
        "provider_address": parsed.provider,
        "buyer_lock_signature": signature,
        "buyer_lock_nonce": lock_tx["nonce"],
        "buyer_lock_fee": lock_tx["fee"],
    }
    if max_ait is not None:
        payload["buyer_max_amount"] = str(max_ait)
    if buyer_agent_id:
        payload["buyer_agent_id"] = buyer_agent_id
    if provider_agent_id:
        payload["provider_agent_id"] = provider_agent_id

    try:
        result = client.post("/v1/market/gpu/purchase", json=payload)
    except NetworkError as e:
        error(f"Purchase failed: {e}")
        sys.exit(1)

    if json_output:
        output(json.dumps(result, indent=2, default=str))
    else:
        success(f"Purchase submitted for job {job_id}")
        info(f"Payment status: {result.get('payment_status', 'unknown')}")
        info(f"Booking ID: {result.get('booking_id', 'N/A')}")


def _buy_evm(
    ctx,
    *,
    buyer_id,
    gpu_id,
    job_id,
    duration_hours,
    quote_dict,
    buyer_address,
    private_key,
    max_ait,
    yes,
    json_output,
    breakdown,
):
    """Fund an EVM protected rental by calling AIPowerRental.startRental."""
    config = get_config()
    parsed = parse_quote(quote_dict)
    evm = _evm_contract_client(config)

    # The buyer must have already created the rental agreement on-chain
    # via createProtectedRental. The agreement ID is passed in the quote
    # or as an additional parameter. For now, we require the buyer to
    # provide it via the energy_quote's job_id mapping or a separate flag.
    # In a full flow, the coordinator would create the agreement on-chain
    # and return the agreement ID.
    agreement_id = _evm_agreement_id(quote_dict)

    # Check the agreement on-chain.
    agreement = evm.get_rental_agreement(agreement_id)
    if to_canonical(agreement[2]) != to_canonical(buyer_address):  # consumer field
        error(f"Agreement consumer {agreement[2]} does not match buyer {buyer_address}")
        sys.exit(1)

    charge_ait = breakdown["buyer_charge_units"] / (10 ** evm.get_token_decimals())
    if not yes:
        click.confirm(
            f"This will call startRental({agreement_id}) on-chain, transferring {charge_ait:.6f} AIT. Continue?",
            abort=True,
        )

    start_result = _run_evm_rental_txs(evm, config, agreement, agreement_id, buyer_address, private_key)
    _notify_evm_purchase(
        ctx,
        buyer_id=buyer_id,
        gpu_id=gpu_id,
        job_id=job_id,
        duration_hours=duration_hours,
        quote_dict=quote_dict,
        buyer_address=buyer_address,
        parsed=parsed,
        max_ait=max_ait,
        json_output=json_output,
        start_result=start_result,
        agreement_id=agreement_id,
    )


def _agreement_create_preflight(
    evm, config, buyer_address: str, provider_address: str, duration: int, price: Decimal
) -> tuple[int, int]:
    """Fail-closed on-chain checks for agreement-create; returns (price_units, next_id)."""
    if evm.rentals_paused():
        error("AIPowerRental is paused; agreement creation is unavailable")
        sys.exit(1)
    if evm.require_protected_rentals():
        error(
            "Contract is in protected-only mode (requireProtectedRentals=true) and no EnergyPricing "
            "contract is configured — createProtectedRental cannot run. Operator must configure "
            "energy pricing or disable protected-only mode first."
        )
        sys.exit(1)
    min_dur, max_dur = evm.rental_duration_bounds()
    if not (min_dur <= duration <= max_dur):
        error(f"--duration {duration}s outside contract bounds [{min_dur}, {max_dur}]")
        sys.exit(1)
    if not evm.is_authorized_consumer(buyer_address):
        error(
            f"Signing wallet {buyer_address} is not an authorized consumer on AIPowerRental "
            f"({config.energy_rental_contract_address}). The contract owner must call "
            f"authorizeConsumer({buyer_address}) first."
        )
        sys.exit(1)
    if not evm.is_authorized_provider(provider_address):
        error(
            f"Provider {provider_address} is not authorized on AIPowerRental "
            f"({config.energy_rental_contract_address}). The contract owner must call "
            f"authorizeProvider({provider_address}) first."
        )
        sys.exit(1)

    decimals = evm.get_token_decimals()
    price_units = int(price * (10**decimals))
    if price_units <= 0:
        error("--price must be positive")
        sys.exit(1)
    return price_units, evm.agreement_counter()


@gpu.command("agreement-create")
@click.option("--provider", "provider_address", required=True, help="Authorized provider wallet address (0x...)")
@click.option("--consumer", "consumer_address", default=None, help="Consumer wallet address (default: signing wallet)")
@click.option("--duration", type=int, default=3600, help="Rental duration in seconds (contract bounds apply)")
@click.option(
    "--price", type=float, required=True, help="Provider principal price in AIT (atomic units = price * 10^decimals)"
)
@click.option("--gpu-model", default="", help="GPU model string recorded on the agreement")
@click.option("--compute-units", type=int, default=1, help="Compute units recorded on the agreement")
@click.option("--wallet", help="Wallet name for signing (must be an authorized consumer)")
@click.option("--wallet-path", help="Direct wallet file path")
@wallet_password_options
@click.option("--yes", is_flag=True, help="Skip confirmation prompt")
@click.option("--json-output", is_flag=True, help="Output raw JSON")
@click.pass_context
def agreement_create(
    ctx,
    provider_address,
    consumer_address,
    duration,
    price,
    gpu_model,
    compute_units,
    wallet,
    wallet_path,
    password,
    password_file,
    password_stdin,
    yes,
    json_output,
):
    """Create an AIPowerRental agreement on-chain (EVM rail) — mints the agreement_id that `aitbc dispute file` references (#2052).

    The buyer wallet must be authorized on the contract (`authorizedConsumers`)
    and the provider must be authorized (`authorizedProviders`); both are
    owner (Safe) calls on AIPowerRental. Legacy `createRental` is used — the
    protected path requires an EnergyPricing contract that is not configured
    on the deployed instance.
    """
    config = get_config()
    evm = _evm_contract_client(config)

    buyer_address, private_key, _wallet_id = load_wallet_for_payment(
        ctx,
        wallet_name=wallet,
        wallet_path=wallet_path,
        password=password,
        password_file=password_file,
        password_stdin=password_stdin,
        require_private_key=True,
    )
    consumer = to_canonical(consumer_address) if consumer_address else to_canonical(buyer_address)
    provider_address = to_canonical(provider_address)
    if not is_address(provider_address) or not is_address(consumer):
        error("--provider and --consumer must be 0x addresses")
        sys.exit(1)

    try:
        price_dec = Decimal(str(price))
    except InvalidOperation:
        error(f"Invalid --price {price!r}")
        sys.exit(1)
    price_units, next_id = _agreement_create_preflight(evm, config, buyer_address, provider_address, duration, price_dec)
    if not yes:
        click.confirm(
            f"This will call createRental(provider={provider_address}, consumer={consumer}, "
            f"duration={duration}s, price={price_units} units) on {config.energy_rental_contract_address} "
            f"(chain {config.energy_pricing_chain_id}), minting agreement id {next_id}. Continue?",
            abort=True,
        )

    nonce = evm.rpc._get_web3().eth.get_transaction_count(buyer_address)
    tx = evm.build_create_rental_tx(
        provider=provider_address,
        consumer=consumer,
        duration=duration,
        price_units=price_units,
        gpu_model=gpu_model,
        compute_units=compute_units,
        from_address=buyer_address,
        nonce=nonce,
    )
    info(f"Submitting createRental tx (nonce {nonce})...")
    result = evm.submit_and_wait(tx, private_key)
    if result.status != 1:
        error(f"createRental transaction failed: {result.tx_hash}")
        sys.exit(1)

    # The minted id is agreementCounter-1 after this tx; verify by reading it back.
    minted = evm.agreement_counter() - 1
    agreement = evm.get_rental_agreement(minted)
    if to_canonical(agreement[1]) != provider_address or to_canonical(agreement[2]) != consumer:
        error(f"Post-create verification failed for agreement {minted}: provider/consumer mismatch")
        sys.exit(1)

    if json_output:
        output(
            json.dumps(
                {
                    "agreement_id": minted,
                    "tx_hash": result.tx_hash,
                    "block_number": result.block_number,
                    "provider": provider_address,
                    "consumer": consumer,
                    "duration": duration,
                    "price_units": price_units,
                },
                indent=2,
            )
        )
    else:
        success(f"Agreement {minted} created on AIPowerRental")
        info(f"TX hash: {result.tx_hash}")
        info(f"Provider: {provider_address}")
        info(f"Consumer: {consumer}")
        info(f"Use with: aitbc dispute file --agreement-id {minted} ...")


def _evm_contract_client(config):
    """Build the EVM contract client after validating the required config."""
    if not config.evm_rpc_url:
        error("EVM RPC URL not configured (set EVM_RPC_URL)")
        sys.exit(1)
    if not config.energy_rental_contract_address:
        error("AIPowerRental contract address not configured")
        sys.exit(1)
    if not config.energy_token_contract_address:
        error("ERC-20 token contract address not configured")
        sys.exit(1)

    from ...utils.evm_contract import EVMContractClient

    return EVMContractClient(
        rpc_url=config.evm_rpc_url,
        chain_id=config.energy_pricing_chain_id,
        rental_contract_address=config.energy_rental_contract_address,
        token_contract_address=config.energy_token_contract_address,
    )


def _evm_agreement_id(quote_dict) -> int:
    agreement_id = quote_dict.get("evm_agreement_id")
    if agreement_id is None:
        error("EVM buy requires evm_agreement_id in the quote or --agreement-id")
        sys.exit(1)
    return int(agreement_id)


def _run_evm_rental_txs(evm, config, agreement, agreement_id: int, buyer_address, private_key):
    """Approve token spend, then call startRental; return the start result."""
    # Approve the rental contract to spend the buyer's tokens.
    total_amount = int(agreement[4]) + int(agreement[7])  # price + platformFee
    nonce = evm.rpc._get_web3().eth.get_transaction_count(buyer_address)
    approve_tx = evm.build_approve_tx(
        spender=config.energy_rental_contract_address,
        amount=total_amount,
        from_address=buyer_address,
        nonce=nonce,
    )
    info(f"Submitting approve({total_amount}) tx (nonce {nonce})...")
    approve_result = evm.submit_and_wait(approve_tx, private_key)
    if approve_result.status != 1:
        error(f"Approve transaction failed: {approve_result.tx_hash}")
        sys.exit(1)
    success(f"Approve confirmed: {approve_result.tx_hash}")

    # Start the rental.
    start_tx = evm.build_start_rental_tx(
        agreement_id=agreement_id,
        from_address=buyer_address,
        nonce=nonce + 1,
    )
    info(f"Submitting startRental({agreement_id}) tx (nonce {nonce + 1})...")
    start_result = evm.submit_and_wait(start_tx, private_key)
    if start_result.status != 1:
        error(f"startRental transaction failed: {start_result.tx_hash}")
        sys.exit(1)
    success(f"startRental confirmed: {start_result.tx_hash}")
    return start_result


def _notify_evm_purchase(
    ctx,
    *,
    buyer_id,
    gpu_id,
    job_id,
    duration_hours,
    quote_dict,
    buyer_address,
    parsed,
    max_ait,
    json_output,
    start_result,
    agreement_id: int,
) -> None:
    """Notify the coordinator of the EVM rental and print the result."""
    client = AITBCHTTPClient(base_url=_coordinator_url(), timeout=_purchase_timeout(), headers=_auth_headers(ctx))
    payload: dict[str, Any] = {
        "buyer_id": buyer_id,
        "gpu_id": gpu_id,
        "duration_hours": duration_hours,
        "payment_method": "evm",
        "job_id": job_id,
        "energy_quote": quote_dict,
        "protected": True,
        "buyer_address": buyer_address,
        "provider_address": parsed.provider,
        "evm_tx_hash": start_result.tx_hash,
        "evm_agreement_id": agreement_id,
    }
    if max_ait is not None:
        payload["buyer_max_amount"] = str(max_ait)

    try:
        result = client.post("/v1/market/gpu/purchase", json=payload)
    except NetworkError as e:
        error(f"Coordinator notification failed: {e}")
        sys.exit(1)

    if json_output:
        output(json.dumps(result, indent=2, default=str))
    else:
        success(f"EVM rental started for job {job_id}")
        info(f"Agreement ID: {agreement_id}")
        info(f"TX hash: {start_result.tx_hash}")
        info(f"Payment status: {result.get('payment_status', 'unknown')}")


@gpu.command()
@click.option("--job-id", required=True, help="Job ID")
@click.option("--json-output", is_flag=True, help="Output raw JSON")
@click.pass_context
def status(ctx, job_id, json_output):
    """Check the status of a GPU rental and its escrow."""
    client = AITBCHTTPClient(base_url=_coordinator_url(), timeout=10)
    try:
        result = client.get(f"/v1/market/gpu/status/{job_id}")
    except NetworkError as e:
        error(f"Failed to get status: {e}")
        sys.exit(1)

    if json_output:
        output(json.dumps(result, indent=2, default=str))
    else:
        info(f"Job ID:     {job_id}")
        info(f"Status:     {result.get('status', 'unknown')}")
        info(f"Payment:    {result.get('payment_status', 'unknown')}")
        info(f"Protected:  {result.get('protected', False)}")
        if result.get("energy_quote"):
            q = result["energy_quote"]
            info(f"Quote ID:   {q.get('quote_id', 'N/A')}")
            info(f"Route:      {q.get('settlement_route', 'N/A')}")
            info(f"Principal:  {q.get('principal_units', 'N/A')} units")


@gpu.command()
@click.option("--job-id", required=True, help="Job ID")
@click.option("--yes", is_flag=True, help="Skip confirmation prompt")
@click.option("--json-output", is_flag=True, help="Output raw JSON")
@click.pass_context
def release(ctx, job_id, yes, json_output):
    """Release escrow funds to the provider after rental completion."""
    if not yes:
        click.confirm(f"Release escrow for job {job_id} to the provider?", abort=True)

    client = AITBCHTTPClient(base_url=_coordinator_url(), timeout=30, headers=_auth_headers(ctx))
    try:
        result = client.post(f"/v1/jobs/{job_id}/accept")
    except NetworkError as e:
        error(f"Release failed: {e}")
        sys.exit(1)

    success(f"Release submitted for job {job_id}")
    fmt = "json" if json_output else "table"
    output(result, format=fmt)


@gpu.command()
@click.option("--job-id", required=True, help="Job ID")
@click.option("--wallet", help="Wallet name for signing")
@click.option("--wallet-path", help="Direct wallet file path")
@wallet_password_options
@click.option("--reason", default="", help="Refund reason")
@click.option("--yes", is_flag=True, help="Skip confirmation prompt")
@click.option("--json-output", is_flag=True, help="Output raw JSON")
@click.pass_context
def refund(ctx, job_id, wallet, wallet_path, password, password_file, password_stdin, reason, yes, json_output):
    """Request a refund for a GPU rental."""
    wallet_creds = load_wallet_for_payment(
        ctx,
        wallet_name=wallet,
        wallet_path=wallet_path,
        password=password,
        password_file=password_file,
        password_stdin=password_stdin,
        require_private_key=False,
    )
    buyer_address = wallet_creds[0]

    if not yes:
        click.confirm(f"Request refund for job {job_id}?", abort=True)

    # #2303: a rental bought through the coordinator (gpu quote/buy) is a
    # coordinator job with a coordinator payment; the market service does not
    # know it ("Job not found"). Refund through the coordinator's escrow
    # refund path first, and fall back to the market service's job endpoint
    # only when the coordinator holds no payment for this job.
    coordinator_result = _refund_via_coordinator(ctx, job_id, reason)
    if coordinator_result is not None:
        if json_output:
            output(json.dumps(coordinator_result, indent=2, default=str))
        else:
            success(f"Refund requested for job {job_id}")
            info(f"Status: {coordinator_result.get('status', 'unknown')}")
        return

    client = AITBCHTTPClient(
        base_url=get_config().market_service_url,
        timeout=30,
        api_key=_resolve_market_api_key(get_config()),
    )
    payload: dict[str, Any] = {"buyer_address": buyer_address, "reason": reason}
    # #1907: the market refund route is party-gated (#1893) — sign as a job
    # party when the wallet key resolves, else the operator credential is
    # required server-side.
    payload.update(signed_job_request_fields(ctx, f"/v1/market/jobs/{job_id}/refund", wallet=wallet_creds))
    try:
        result = client.post(f"/v1/market/jobs/{job_id}/refund", json=payload)
    except NetworkError as e:
        error(f"Refund request failed: {e}")
        sys.exit(1)

    if json_output:
        output(json.dumps(result, indent=2, default=str))
    else:
        success(f"Refund requested for job {job_id}")
        info(f"Status: {result.get('status', 'unknown')}")


def _refund_via_coordinator(ctx, job_id: str, reason: str) -> dict[str, Any] | None:
    """Refund a coordinator-created rental; None when the coordinator has no payment for the job.

    Looks the payment up by job (``GET /v1/jobs/{id}/payment``) and refunds it
    through ``POST /v1/payments/{id}/refund`` (escrow refund path). Any answer
    other than "no payment for this job" is final and exits non-zero rather
    than silently retrying against the market service.
    """
    client = AITBCHTTPClient(base_url=_coordinator_url(), timeout=_purchase_timeout(), headers=_auth_headers(ctx))
    try:
        payment = client.get(f"/v1/jobs/{job_id}/payment")
    except NetworkError as e:
        if http_response_status(e) in (401, 403):
            error(f"Refund lookup refused by the coordinator: {http_error_detail(e) or e}")
            sys.exit(1)
        if http_response_status(e) == 404:
            return None
        error(f"Refund lookup failed: {e}")
        sys.exit(1)
    payment_id = payment.get("payment_id") if isinstance(payment, dict) else None
    if not payment_id:
        return None
    try:
        return client.post(
            f"/v1/payments/{payment_id}/refund",
            json={"job_id": job_id, "payment_id": payment_id, "reason": reason or "buyer refund request"},
        )
    except NetworkError as e:
        error(f"Refund request failed: {http_error_detail(e) or e}")
        sys.exit(1)


def _auth_headers(ctx) -> dict[str, str]:
    """Auth headers for coordinator calls (#2246).

    Precedence: explicit ``--api-key`` > stored ``auth login`` credential >
    ``config.api_key``; a JWT goes out as ``Authorization: Bearer``, any
    other key as ``X-API-Key``.
    """
    return auth_headers(ctx.obj.get("api_key") if ctx.obj else None, getattr(get_config(), "api_key", None))
