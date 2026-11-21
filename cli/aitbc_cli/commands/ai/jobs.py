"""``aitbc ai jobs`` / ``status`` / ``accept`` — job listing and inspection commands."""

from typing import Any

import click

import aitbc_cli.commands.ai as _ai

from ._group import ai


def _job_row(job: dict[str, Any]) -> dict[str, Any]:
    """Flatten one JobView into the columns the table renderer needs (#2453)."""
    payment = job.get("payment_amount")
    if payment is not None:
        payment = f"{payment} {job.get('payment_token') or ''}".strip()
    return {
        "job_id": job.get("job_id"),
        "state": job.get("state"),
        "requested_at": job.get("requested_at"),
        "payment": payment,
        "payment_status": job.get("payment_status"),
        "miner": job.get("assigned_miner_id"),
    }


@ai.command(
    epilog="""Examples:

  aitbc ai jobs

  aitbc ai jobs --status QUEUED --limit 20

  aitbc ai jobs --inflight"""
)
@click.option("--limit", type=int, default=10, help="Limit results")
@click.option(
    "--status",
    help="Filter by status (QUEUED, RUNNING, COMPLETED, FAILED, CANCELED, EXPIRED; "
    "'pending' is accepted as an alias for QUEUED, 'all' disables the filter)",
)
@click.option(
    "--inflight",
    is_flag=True,
    help="Show only the queued+running count and the configured cap — no job rows",
)
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--format", type=click.Choice(["table", "json"]), default=None, help="Output format")
@click.pass_context
def jobs(ctx, limit, status, inflight, coordinator_url, format):
    """List AI jobs from the coordinator with optional status and limit filters."""
    _ai.get_config()

    try:
        coord_url = _ai._coordinator_base_url(ctx, coordinator_url)
        if not coord_url:
            _ai.abort(ctx, "Coordinator URL not configured")

        headers = _ai._auth_headers(ctx)
        http_client = _ai.AITBCHTTPClient(base_url=coord_url, timeout=30, headers=headers)
        fmt = _ai.resolve_output_format(ctx, format)

        if inflight:
            # Cheap headroom check: one aggregate row, no job payloads (#2453).
            result = http_client.get("/v1/jobs/inflight")
            _ai.output(result, fmt, title="AI Jobs Inflight")
            return

        params = {"limit": limit}
        if status:
            params["status"] = status

        result = http_client.get("/v1/jobs", params=params)
        if fmt == "table":
            items = result.get("items") if isinstance(result, dict) else result
            _ai.output([_job_row(j) for j in (items or [])], fmt, title="AI Jobs")
            _ai.info(
                f"total={result.get('total')} shown={len(items or [])} "
                f"has_more={result.get('has_more')} (use --inflight for the queued+running cap check)"
            )
        else:
            _ai.output(result, fmt, title="AI Jobs")

    except _ai.NetworkError as e:
        _ai._abort_for_network(ctx, e)
    except _ai._OPS_ERRORS as e:
        _ai.abort(ctx, f"Error listing jobs: {e}", from_exception=e)


@ai.command(
    epilog="""Examples:

  aitbc ai status --job-id job-123

  aitbc ai status --job-id job-123 --output json"""
)
@click.option("--job-id", help="Job ID")
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--format", type=click.Choice(["table", "json"]), default=None, help="Output format")
@click.pass_context
def status(ctx, job_id, coordinator_url, format):
    """Show the current status of an AI job by job ID."""
    _ai.get_config()

    try:
        coord_url = _ai._coordinator_base_url(ctx, coordinator_url)
        if not coord_url:
            _ai.abort(ctx, "Coordinator URL not configured")

        if not job_id:
            _ai.abort(ctx, "Job ID required")

        headers = _ai._auth_headers(ctx)
        http_client = _ai.AITBCHTTPClient(base_url=coord_url, timeout=30, headers=headers)
        result = http_client.get(f"/v1/jobs/{job_id}")

        _ai.output(result, _ai.resolve_output_format(ctx, format), title=f"Job Status: {job_id}")

    except _ai.NetworkError as e:
        _ai._abort_for_network(ctx, e)
    except _ai._OPS_ERRORS as e:
        _ai.abort(ctx, f"Error getting job status: {e}", from_exception=e)


@ai.command(
    epilog="""Examples:

  aitbc ai accept --job-id job-123

  aitbc ai accept --job-id job-123 --wallet genesis"""
)
@click.option("--job-id", required=True, help="Job ID to accept")
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--format", type=click.Choice(["table", "json"]), default=None, help="Output format")
@click.pass_context
def accept(ctx, job_id, coordinator_url, format):
    """Accept a completed AI job and release the escrowed payment."""
    _ai.get_config()

    try:
        coord_url = _ai._coordinator_base_url(ctx, coordinator_url)
        if not coord_url:
            _ai.abort(ctx, "Coordinator URL not configured")

        headers = _ai._require_auth_headers(ctx)
        http_client = _ai.AITBCHTTPClient(base_url=coord_url, timeout=30, headers=headers)
        result = _ai._post_idempotent(
            http_client,
            f"/v1/jobs/{job_id}/accept",
            idempotency_key=_ai._new_idempotency_key(f"ai-accept-{job_id}"),
        )

        _ai.success(f"Job {job_id} accepted and payment released")
        _ai.output(result, _ai.resolve_output_format(ctx, format))

    except _ai.NetworkError as e:
        _ai._abort_for_network(ctx, e)
    except _ai._OPS_ERRORS as e:
        _ai.abort(ctx, f"Error accepting job: {e}", from_exception=e)
