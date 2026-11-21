"""``aitbc ai pay`` — escrow payment for an existing AI job."""

import os
from decimal import Decimal
from typing import Any, cast

import click

import aitbc_cli.commands.ai as _ai

from ._group import ai


def _resolve_pay_params(
    ctx,
    rpc_url: str,
    job: dict[str, Any],
    wallet_address: str,
    buyer_address,
    provider_address,
    offer_id,
    offer_quantity,
):
    """Resolve payment fields for an existing job from flags and the job record."""
    payment_amount = job.get("payment_amount")
    if payment_amount is None:
        _ai.abort(ctx, "Job has no payment_amount; it may not be a paid job")

    node_wallet_addr = job.get("node_wallet_address") or _ai.get_node_wallet(ctx, rpc_url)
    if not node_wallet_addr:
        _ai.abort(ctx, "Cannot determine node wallet address for ESCROW_LOCK")

    buyer_address = buyer_address or job.get("buyer_address") or wallet_address
    if not buyer_address:
        _ai.abort(ctx, "buyer_address is required: set --buyer-address, --wallet, or ensure the job has one")

    provider_address = provider_address or job.get("provider_address") or os.environ.get("SHOP_WALLET_ADDRESS")
    if not provider_address:
        _ai.abort(ctx, "provider_address is required: set --provider-address or ensure the job has one")

    offer_id = offer_id or job.get("offer_id")
    if offer_quantity is None:
        offer_quantity = job.get("offer_quantity")

    return payment_amount, node_wallet_addr, buyer_address, provider_address, offer_id, offer_quantity


@ai.command(
    name="pay",
    epilog="""Examples:

  aitbc ai pay --job-id job-123 --wallet genesis

  aitbc ai pay --job-id job-123 --wallet genesis --password-file ~/secrets/wallet.pass""",
)
@click.option("--job-id", required=True, help="Job ID to pay for")
@click.option("--wallet", required=True, help="Wallet name to sign the escrow lock")
@click.option("--buyer-address", help="Override buyer/customer address")
@click.option("--provider-address", help="Override provider address")
@click.option("--buyer-agent-id", help="Buyer agent id; payment address resolved via coordinator")
@click.option("--provider-agent-id", help="Provider agent id; payment address resolved via coordinator")
@click.option("--offer-id", help="Market offer this job is bought against")
@click.option("--offer-quantity", type=Decimal, default=None, help="How many of the offer's price units to buy")
@click.option("--currency", default=None, help="Payment currency (default: AITBC)")
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--rpc-url", help="Blockchain RPC URL")
@click.option("--chain-id", help="Chain ID")
@_ai.wallet_password_options
@click.option("--format", type=click.Choice(["table", "json"]), default=None, help="Output format")
@click.pass_context
def pay(
    ctx,
    job_id,
    wallet,
    buyer_address,
    provider_address,
    buyer_agent_id,
    provider_agent_id,
    offer_id,
    offer_quantity,
    currency,
    coordinator_url,
    rpc_url,
    chain_id,
    password,
    password_file,
    password_stdin,
    format,
):
    """Create an escrow payment for an existing AI job."""
    config = _ai.get_config()

    try:
        coord_url = _ai._coordinator_base_url(ctx, coordinator_url)
        if not coord_url:
            _ai.abort(ctx, "Coordinator URL not configured")

        rpc_url = rpc_url or config.blockchain_rpc_url or "http://localhost:8202"
        if not rpc_url:
            _ai.abort(ctx, "RPC URL not configured")

        wallet_address, private_key, _ = _ai.load_wallet_for_payment(
            ctx, wallet_name=wallet, password=password, password_file=password_file, password_stdin=password_stdin
        )
        if not private_key:
            _ai.abort(ctx, f"Wallet {wallet} has no usable private key")
        private_key = cast(str, private_key)

        headers = _ai._require_auth_headers(ctx)
        http_client = _ai.AITBCHTTPClient(base_url=coord_url, timeout=30, headers=headers)

        job = http_client.get(f"/v1/jobs/{job_id}")
        if not isinstance(job, dict) or not job.get("job_id"):
            _ai.abort(ctx, f"Job {job_id} not found")

        if job.get("payment_id") and job.get("payment_status") not in ("pending", "skipped", "failed", None):
            _ai.abort(
                ctx, f"Job {job_id} already has payment_status={job.get('payment_status')}; not creating a second payment"
            )

        payment_amount, node_wallet_addr, buyer_address, provider_address, offer_id, offer_quantity = _resolve_pay_params(
            ctx, rpc_url, job, wallet_address, buyer_address, provider_address, offer_id, offer_quantity
        )

        if buyer_agent_id or provider_agent_id:
            pay_chain = int(chain_id) if chain_id else _ai.resolve_chain_id(ctx, rpc_url)
            buyer_address, provider_address, buyer_agent_id, provider_agent_id = _ai.resolve_escrow_parties(
                ctx,
                buyer=buyer_address,
                provider=provider_address,
                buyer_agent_id=buyer_agent_id,
                provider_agent_id=provider_agent_id,
                chain_id=int(pay_chain),
            )

        payment_result = _ai._create_escrow_payment(
            ctx,
            http_client,
            rpc_url,
            job_id,
            str(payment_amount),
            currency or job.get("payment_token") or "AITBC",
            buyer_address,
            provider_address,
            private_key,
            str(node_wallet_addr),
            chain_id,
            offer_id,
            Decimal(str(offer_quantity)) if offer_quantity is not None else None,
            idempotency_key=_ai._new_idempotency_key(f"ai-pay-{job_id}"),
            buyer_agent_id=buyer_agent_id,
            provider_agent_id=provider_agent_id,
        )

        _ai._report_escrow_outcome(ctx, job_id, payment_result)
        _ai.output(payment_result, _ai.resolve_output_format(ctx, format))

    except _ai.NetworkError as e:
        _ai._abort_for_network(ctx, e)
    except _ai._OPS_ERRORS as e:
        _ai.abort(ctx, f"Error paying for job: {e}", from_exception=e)
