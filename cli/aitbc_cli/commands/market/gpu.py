"""CLI commands for protected fixed-duration GPU rentals (energy floor).

Commands:
  aitbc market gpu quote    - Request an operator-signed energy quote
  aitbc market gpu buy      - Fund a quoted rental (native or EVM)
  aitbc market gpu status   - Check rental/escrow status
  aitbc market gpu release  - Release escrow to provider
  aitbc market gpu refund   - Request a refund
"""

from __future__ import annotations

import json
import sys
from typing import Any

import click

from ...config import get_config
from ...utils import error, info, output, success, warning
from ...utils.address import to_canonical
from ...utils.energy_quote import (
    compute_settlement_breakdown,
    parse_quote,
    verify_quote,
)
from ...utils.escrow import create_signed_escrow_lock
from ...utils.http_client import AITBCHTTPClient, NetworkError, get_logger
from ...utils.wallet_loader import load_wallet_for_payment

logger = get_logger(__name__)


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
    info(f"TDP:          {quote.tdp_watts}W")
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


@gpu.command()
@click.option("--gpu-id", required=True, help="GPU registry ID")
@click.option("--buyer-id", required=True, help="Buyer client ID")
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
def quote(ctx, gpu_id, buyer_id, duration_hours, gpu_count, max_ait, settlement, json_output):
    """Request an operator-signed energy quote for a GPU rental."""
    client = AITBCHTTPClient(base_url=_coordinator_url(), timeout=30, headers=_auth_headers(ctx))
    payload: dict[str, Any] = {
        "buyer_id": buyer_id,
        "gpu_id": gpu_id,
        "duration_hours": duration_hours,
        "gpu_count": gpu_count,
        "settlement_route": settlement,
    }
    if max_ait is not None:
        payload["buyer_max_amount"] = str(max_ait)
    try:
        result = client.post("/v1/marketplace/gpu/quote", json=payload)
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

    # Verify the quote locally before showing it to the buyer.
    config = get_config()
    parsed = parse_quote(quote_dict)
    verification = verify_quote(
        parsed,
        expected_operator_address=config.energy_operator_address,
        expected_domain=config.energy_quote_domain,
        expected_chain_id=config.native_chain_id,
    )
    if not verification.valid:
        warning(f"Quote verification failed: {verification.refusal_reason} ({verification.refusal_code})")
    else:
        success("Quote verified locally")

    breakdown = compute_settlement_breakdown(parsed)
    _print_quote(quote_dict, breakdown)
    info(f"Buyer charge:  {result.get('buyer_charge_ait', 'N/A')} AIT")


@gpu.command()
@click.option("--gpu-id", required=True, help="GPU registry ID")
@click.option("--buyer-id", required=True, help="Buyer client ID")
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
@click.option("--password", help="Wallet password")
@click.option("--password-file", type=click.Path(exists=True), help="Wallet password file")
@click.option("--energy-quote", help="JSON file containing the energy quote")
@click.option("--max-ait", type=float, default=None, help="Maximum AIT buyer cap")
@click.option("--yes", is_flag=True, help="Skip confirmation prompt")
@click.option("--json-output", is_flag=True, help="Output raw JSON")
@click.pass_context
def buy(
    ctx,
    gpu_id,
    buyer_id,
    job_id,
    duration_hours,
    settlement,
    wallet,
    wallet_path,
    password,
    password_file,
    energy_quote,
    max_ait,
    yes,
    json_output,
):
    """Fund a quoted GPU rental (native escrow or EVM contract)."""
    # Load the energy quote from file or stdin.
    if energy_quote:
        with open(energy_quote) as f:
            quote_dict = json.load(f)
        # The quote endpoint may return a wrapper object; unwrap the energy_quote.
        quote_dict = quote_dict.get("energy_quote", quote_dict)
    else:
        error("--energy-quote is required (path to JSON file)")
        sys.exit(1)

    config = get_config()

    # Verify the quote before funding.
    parsed = parse_quote(quote_dict)
    verification = verify_quote(
        parsed,
        expected_operator_address=config.energy_operator_address,
        expected_domain=config.energy_quote_domain,
        expected_chain_id=config.native_chain_id,
    )
    if not verification.valid:
        error(f"Quote verification failed: {verification.refusal_reason} ({verification.refusal_code})")
        sys.exit(1)
    success("Quote verified")

    breakdown = compute_settlement_breakdown(parsed)

    # Load the buyer wallet for signing.
    pw = password
    if password_file:
        with open(password_file) as f:
            pw = f.read().strip()

    buyer_address, private_key, wallet_id = load_wallet_for_payment(
        ctx,
        wallet_name=wallet,
        wallet_path=wallet_path,
        password=pw,
        require_private_key=True,
    )

    if buyer_address is None:
        error("Could not resolve buyer wallet address")
        sys.exit(1)

    # Verify the buyer address matches the quote.
    if to_canonical(buyer_address) != to_canonical(parsed.buyer):
        error(f"Wallet address {buyer_address} does not match quote buyer {parsed.buyer}")
        sys.exit(1)

    if settlement == "native":
        _buy_native(
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
    """Fund a native protected rental by signing ESCROW_LOCK locally."""
    from ...utils.escrow import get_node_wallet

    config = get_config()
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
        chain_id=config.native_chain_id,
        node_wallet=node_wallet,
        energy_quote_id=parsed.quote_id,
        energy_quote_digest=parsed.digest_sha256().hex(),
        settlement_route=parsed.settlement_route.value,
        settlement_asset=parsed.settlement_asset,
        settlement_unit_scale=parsed.settlement_unit_scale,
    )

    # Submit to the coordinator's escrow create endpoint.
    client = AITBCHTTPClient(base_url=_coordinator_url(), timeout=30, headers=_auth_headers(ctx))
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

    try:
        result = client.post("/v1/marketplace/gpu/purchase", json=payload)
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

    evm = EVMContractClient(
        rpc_url=config.evm_rpc_url,
        chain_id=config.energy_pricing_chain_id,
        rental_contract_address=config.energy_rental_contract_address,
        token_contract_address=config.energy_token_contract_address,
    )

    # The buyer must have already created the rental agreement on-chain
    # via createProtectedRental. The agreement ID is passed in the quote
    # or as an additional parameter. For now, we require the buyer to
    # provide it via the energy_quote's job_id mapping or a separate flag.
    # In a full flow, the coordinator would create the agreement on-chain
    # and return the agreement ID.
    agreement_id = quote_dict.get("evm_agreement_id")
    if agreement_id is None:
        error("EVM buy requires evm_agreement_id in the quote or --agreement-id")
        sys.exit(1)
    agreement_id = int(agreement_id)

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

    # Notify the coordinator.
    client = AITBCHTTPClient(base_url=_coordinator_url(), timeout=30, headers=_auth_headers(ctx))
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
        result = client.post("/v1/marketplace/gpu/purchase", json=payload)
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
        result = client.get(f"/v1/marketplace/gpu/status/{job_id}")
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

    if json_output:
        output(json.dumps(result, indent=2, default=str))
    else:
        success(f"Release submitted for job {job_id}")
        info(f"Status: {result.get('status', 'unknown')}")


@gpu.command()
@click.option("--job-id", required=True, help="Job ID")
@click.option("--wallet", help="Wallet name for signing")
@click.option("--wallet-path", help="Direct wallet file path")
@click.option("--password", help="Wallet password")
@click.option("--password-file", type=click.Path(exists=True), help="Wallet password file")
@click.option("--reason", default="", help="Refund reason")
@click.option("--yes", is_flag=True, help="Skip confirmation prompt")
@click.option("--json-output", is_flag=True, help="Output raw JSON")
@click.pass_context
def refund(ctx, job_id, wallet, wallet_path, password, password_file, reason, yes, json_output):
    """Request a refund for a GPU rental."""
    pw = password
    if password_file:
        with open(password_file) as f:
            pw = f.read().strip()

    buyer_address, _, _ = load_wallet_for_payment(
        ctx,
        wallet_name=wallet,
        wallet_path=wallet_path,
        password=pw,
        require_private_key=False,
    )

    if not yes:
        click.confirm(f"Request refund for job {job_id}?", abort=True)

    client = AITBCHTTPClient(base_url=_coordinator_url(), timeout=30, headers=_auth_headers(ctx))
    payload: dict[str, Any] = {"job_id": job_id, "buyer_address": buyer_address, "reason": reason}
    try:
        result = client.post("/v1/marketplace/gpu/refund", json=payload)
    except NetworkError as e:
        error(f"Refund request failed: {e}")
        sys.exit(1)

    if json_output:
        output(json.dumps(result, indent=2, default=str))
    else:
        success(f"Refund requested for job {job_id}")
        info(f"Status: {result.get('status', 'unknown')}")


def _auth_headers(ctx) -> dict[str, str]:
    """Return Authorization header from --api-key or the stored client credential."""
    token = ctx.obj.get("api_key") if ctx.obj else None
    if not token:
        from ...auth import AuthManager

        token = AuthManager().get_credential("client")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}
