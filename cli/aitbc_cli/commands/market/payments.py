"""Read-only coordinator payment lookup for market jobs (job_payments ledger)."""

import click

from ...utils import error, output
from ...utils.http_client import AITBCHTTPClient, http_error_detail, http_response_status

from ._group import market
from .escrow import _client_token, _coordinator_base_url


@market.command(
    name="payment",
    epilog="""Examples:

  aitbc market payment --job-id job-123

  aitbc market payment --payment-id pay-456 --output json""",
)
@click.option("--job-id", "job_id", default=None, help="Coordinator job ID")
@click.option("--payment-id", "payment_id", default=None, help="Payment record ID")
@click.pass_context
def payment(ctx, job_id: str | None, payment_id: str | None):
    """Show the coordinator payment record for a job or payment ID.

    Read-only view of the coordinator's ``job_payments`` ledger. The API
    scopes the read to the caller's own jobs — a 403 means the stored client
    credential does not own this job, not that the payment is missing.
    """
    if bool(job_id) == bool(payment_id):
        raise click.ClickException("Pass exactly one of --job-id or --payment-id")
    token = _client_token(ctx)
    if not token:
        error("No client token — run `aitbc auth login --wallet <name>` first (admin or the job's client).")
        raise click.Abort()
    client = AITBCHTTPClient(
        base_url=_coordinator_base_url(ctx),
        timeout=15,
        headers={"Authorization": f"Bearer {token}"},
    )
    path = f"/v1/jobs/{job_id}/payment" if job_id else f"/v1/payments/{payment_id}"
    try:
        result = client.get(path)
    except Exception as exc:
        status = http_response_status(exc)
        detail = http_error_detail(exc)
        if status == 403:
            error(f"HTTP 403: the stored credential does not own this job's payment ({detail or 'not authorized'}).")
        elif status == 404:
            error("No payment found (404).")
        elif status is not None:
            error(f"HTTP {status} from coordinator: {detail or exc}")
        else:
            error(f"Payment query failed: {exc}")
        raise click.Abort() from exc
    finally:
        client.close()
    output(result, ctx.obj.get("output_format", "table"), title=f"Payment: {job_id or payment_id}")
