"""``aitbc ai results`` / ``cancel`` — job result fetch and cancellation."""

import click

import aitbc_cli.commands.ai as _ai

from ...utils.http_client import get_logger

from ._group import ai

logger = get_logger(__name__.rpartition(".")[0])


@ai.command(
    epilog="""Examples:

  aitbc ai results --job-id job-123

  aitbc ai results --job-id job-123 --output json"""
)
@click.option("--job-id", help="Job ID")
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--format", type=click.Choice(["table", "json"]), default=None, help="Output format")
@click.pass_context
def results(ctx, job_id, coordinator_url, format):
    """Show the results of a completed AI job by job ID."""
    _ai.get_config()

    try:
        coord_url = _ai._coordinator_base_url(ctx, coordinator_url)
        if not coord_url:
            _ai.abort(ctx, "Coordinator URL not configured")

        if not job_id:
            _ai.abort(ctx, "Job ID required")

        headers = _ai._auth_headers(ctx)
        http_client = _ai.AITBCHTTPClient(base_url=coord_url, timeout=30, headers=headers)
        result = http_client.get(f"/v1/jobs/{job_id}/result")

        _ai.output(result, _ai.resolve_output_format(ctx, format), title=f"Job Results: {job_id}")

    except _ai.NetworkError as e:
        # Surface the server's detail for client-side answers (404 unknown job,
        # 409 terminal job with no result, 425 still running) instead of the
        # raw NetworkError blob; 401 keeps the login hint (#2207).
        detail = _ai.http_error_detail(e)
        status = _ai.http_response_status(e)
        if not _ai.is_unauthorized(e) and detail and status is not None and 400 <= status < 500:
            _ai.abort(ctx, f"Job {job_id}: {detail}", from_exception=e)
        _ai._abort_for_network(ctx, e)
    except _ai._OPS_ERRORS as e:
        _ai.abort(ctx, f"Error getting job results: {e}", from_exception=e)


def _refund_after_cancel(ctx, http_client: _ai.AITBCHTTPClient, result, job_id: str, reason: str):
    """Refund the escrowed payment after a cancel, falling back to the chain."""
    payment_status = result.get("payment_status", "") if isinstance(result, dict) else ""
    if payment_status not in ("escrowed", "pending", "pending_acceptance"):
        return result
    payment_id = result.get("payment_id") if isinstance(result, dict) else None
    refund_result = None
    if payment_id:
        try:
            refund_result = http_client.post(
                f"/v1/payments/{payment_id}/refund",
                json={"job_id": job_id, "payment_id": payment_id, "reason": reason},
            )
        except _ai._OPS_ERRORS as e:
            logger.warning("Coordinator refund after cancel failed: %s", e)
    if not refund_result:
        # Fallback to on-chain escrow refund.
        from ..market.escrow import refund_escrow

        refund_result = refund_escrow(ctx, job_id, reason)
    if isinstance(result, dict):
        result["refund"] = refund_result
    else:
        result = {"cancel_result": result, "refund": refund_result}
    return result


@ai.command(
    epilog="""Examples:

  aitbc ai cancel --job-id job-123

  aitbc ai cancel --job-id job-123 --refund --reason 'customer requested'"""
)
@click.option("--job-id", required=True, help="Job ID")
@click.option("--wallet", help="Wallet name (optional)")
@_ai.wallet_password_options
@click.option("--refund", is_flag=True, help="Also refund the escrowed payment after cancel")
@click.option("--reason", default="buyer_requested", help="Reason for refund")
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--format", type=click.Choice(["table", "json"]), default=None, help="Output format")
@click.pass_context
def cancel(ctx, job_id, wallet, password, password_file, password_stdin, refund, reason, coordinator_url, format):
    """Cancel an AI job and optionally refund the payment to the customer."""
    _ai.get_config()

    try:
        coord_url = _ai._coordinator_base_url(ctx, coordinator_url)
        if not coord_url:
            _ai.abort(ctx, "Coordinator URL not configured")

        if not job_id:
            _ai.abort(ctx, "Job ID required")

        headers = _ai._require_auth_headers(ctx)

        http_client = _ai.AITBCHTTPClient(base_url=coord_url, timeout=30, headers=headers)
        result = http_client.post(f"/v1/jobs/{job_id}/cancel")

        if refund:
            result = _refund_after_cancel(ctx, http_client, result, job_id, reason)

        _ai.success(f"Job {job_id} cancelled")
        _ai.output(result, _ai.resolve_output_format(ctx, format))

    except _ai.NetworkError as e:
        _ai._abort_for_network(ctx, e)
    except _ai._OPS_ERRORS as e:
        _ai.abort(ctx, f"Error cancelling job: {e}", from_exception=e)
