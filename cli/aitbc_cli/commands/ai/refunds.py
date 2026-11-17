"""``aitbc ai refund`` / ``refund-sweep`` — escrow refund commands."""

import builtins
from typing import Any

import click

import aitbc_cli.commands.ai as _ai

from ._group import ai


def _sweep_job(http_client: _ai.AITBCHTTPClient, job: dict[str, Any], reason: str, dry_run: bool, counts) -> None:
    """Refund one completed job's still-escrowed payment unless it is skipped."""
    if job.get("payment_status") not in ("escrowed", "pending_acceptance"):
        return
    if job.get("zk_status") == "verified":
        return
    payment_id = job.get("payment_id")
    job_id = job.get("job_id")
    if not payment_id or not job_id:
        return
    counts["candidates"] += 1
    if dry_run:
        return
    try:
        http_client.post(
            f"/v1/payments/{payment_id}/refund",
            json={"job_id": job_id, "payment_id": payment_id, "reason": reason},
            idempotency_key=_ai._new_idempotency_key(f"ai-refund-{payment_id}"),
        )
        counts["refunded"] += 1
        _ai.success(f"Refunded payment {payment_id} for job {job_id}")
    except _ai.NetworkError as e:
        counts["failed"] += 1
        _ai.warning(f"Failed to refund payment {payment_id} for job {job_id}: {e}")
    except _ai._OPS_ERRORS as e:
        counts["failed"] += 1
        _ai.warning(f"Failed to refund payment {payment_id} for job {job_id}: {e}")


@ai.command(
    epilog="""Examples:

  aitbc ai refund --job-id job-123 --reason 'job failed'

  aitbc ai refund --job-id job-123 --reason timeout"""
)
@click.option("--job-id", required=True, help="Job ID to refund")
@click.option("--reason", default="buyer_requested", help="Reason for refund")
@click.option("--coordinator-url", help="Coordinator URL")
@click.pass_context
def refund(ctx, job_id, reason, coordinator_url):
    """Refund an escrowed payment for a failed or cancelled AI job."""
    _ai.get_config()

    try:
        headers = _ai._require_auth_headers(ctx)

        coord_url = _ai._coordinator_base_url(ctx, coordinator_url)
        if not coord_url:
            _ai.abort(ctx, "Coordinator URL not configured")

        http_client = _ai.AITBCHTTPClient(base_url=coord_url, timeout=30, headers=headers)

        # Lookup payment_id for this job.
        job = http_client.get(f"/v1/jobs/{job_id}")
        payment_id = job.get("payment_id")
        if not payment_id:
            _ai.abort(ctx, f"Job {job_id} has no payment to refund")

        result = _ai._post_idempotent(
            http_client,
            f"/v1/payments/{payment_id}/refund",
            json={"job_id": job_id, "payment_id": payment_id, "reason": reason},
            idempotency_key=_ai._new_idempotency_key(f"ai-refund-{payment_id}"),
        )
        _ai.success(f"Payment {payment_id} for job {job_id} refunded")
        _ai.output(result, _ai.resolve_output_format(ctx, "table"))

    except _ai.NetworkError as e:
        _ai._abort_for_network(ctx, e)
    except _ai._OPS_ERRORS as e:
        _ai.abort(ctx, f"Error refunding job: {e}", from_exception=e)


@ai.command(
    name="refund-sweep",
    epilog="""Examples:

  aitbc ai refund-sweep

  aitbc ai refund-sweep --limit 50 --reason 'stuck jobs'""",
)
@click.option("--limit", type=int, default=100, help="Maximum completed jobs to inspect")
@click.option("--reason", default="buyer_requested", help="Reason for refund")
@click.option("--dry-run", is_flag=True, help="Count candidates without refunding")
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--format", type=click.Choice(["table", "json"]), default=None, help="Output format")
@click.pass_context
def refund_sweep(ctx, limit, reason, dry_run, coordinator_url, format):
    """Refund all client-owned AI jobs stuck in an incomplete state."""
    _ai.get_config()

    try:
        coord_url = _ai._coordinator_base_url(ctx, coordinator_url)
        if not coord_url:
            _ai.abort(ctx, "Coordinator URL not configured")

        headers = _ai._require_auth_headers(ctx)
        http_client = _ai.AITBCHTTPClient(base_url=coord_url, timeout=30, headers=headers)

        result = http_client.get("/v1/jobs", params={"status": "COMPLETED", "limit": limit})
        jobs = result.get("items") if isinstance(result, dict) else result
        if not isinstance(jobs, builtins.list):
            _ai.abort(ctx, "Unexpected response listing jobs")
        assert jobs is not None

        counts = {"candidates": 0, "refunded": 0, "failed": 0}
        for job in jobs:
            _sweep_job(http_client, job, reason, dry_run, counts)

        _ai.output(counts, _ai.resolve_output_format(ctx, format), title="ZK refund sweep")

    except _ai.NetworkError as e:
        _ai._abort_for_network(ctx, e)
    except _ai._OPS_ERRORS as e:
        _ai.abort(ctx, f"Error running refund sweep: {e}", from_exception=e)
