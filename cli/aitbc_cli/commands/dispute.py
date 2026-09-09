"""Dispute and arbitration commands.

Two surfaces sit behind this group:

* the chain RPC (``/rpc/disputes/*`` on the blockchain node) carries the
  on-chain arbitration system — filing, evidence, arbitrator votes;
* the coordinator admin API (``/v1/admin/disputes/*``) rules on disputed *job
  payments*, which is a different object with its own authorisation. Only an
  operator or arbiter may call it — neither the customer who rejected the work
  nor the provider who did it can rule on their own dispute.

``resolve`` and ``auto-adjudicate`` are the coordinator commands; everything
else talks to the chain.
"""

from __future__ import annotations

import os
from typing import Any

import click

from ..auth import AuthManager, ExpiredAdminToken
from ..config import get_config
from ..utils import output
from ..utils.error_handling import abort
from ..utils.http_client import AITBCHTTPClient, NetworkError


def _looks_like_jwt(token: str) -> bool:
    """A JWT is three base64url segments separated by dots."""
    return token.startswith("ey") and token.count(".") == 2


def _coordinator_base_url(ctx, coordinator_url: str | None = None) -> str:
    """Return the coordinator base URL without a trailing /v1 path."""
    config = get_config()
    url = coordinator_url or ctx.obj.get("url") or config.coordinator_api_url or os.getenv("COORDINATOR_API_URL", "")
    if not url:
        return ""
    url = url.rstrip("/")
    if url.endswith("/v1"):
        url = url[:-3]
    return url


def _coordinator_client(ctx, coordinator_url: str | None = None, timeout: int | None = None) -> AITBCHTTPClient:
    """Return an HTTP client for the coordinator API."""
    config = get_config()
    url = _coordinator_base_url(ctx, coordinator_url)
    if not url:
        abort(ctx, "Coordinator URL not configured")

    token = ctx.obj.get("api_key") or config.api_key or ""
    if not token:
        token = AuthManager().get_admin_token() or ""

    client_kwargs: dict[str, Any] = {"base_url": url, "timeout": timeout or config.timeout or 30, "headers": None}
    if token and _looks_like_jwt(token):
        client_kwargs["headers"] = {"Authorization": f"Bearer {token}"}
    elif token:
        client_kwargs["api_key"] = token

    return AITBCHTTPClient(**client_kwargs)


def _chain_client(ctx, node_url: str | None = None, timeout: int | None = None) -> AITBCHTTPClient:
    """Return an HTTP client for the blockchain node RPC.

    The read routes are open; filing, evidence and votes are authenticated, so
    the RPC API key is attached whenever one is configured.
    """
    config = get_config()
    url = (node_url or config.blockchain_rpc_url or "http://127.0.0.1:8202").rstrip("/")
    client_kwargs: dict[str, Any] = {"base_url": url, "timeout": timeout or config.timeout or 30}
    key = config.blockchain_rpc_api_key or ""
    if key:
        client_kwargs["api_key"] = key
    return AITBCHTTPClient(**client_kwargs)


NODE_URL_OPTION = click.option("--node-url", "node_url", default=None, help="Blockchain node RPC URL")
COORDINATOR_URL_OPTION = click.option("--coordinator-url", "coordinator_url", default=None, help="Coordinator URL")
FORMAT_OPTION = click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")


@click.group(
    epilog="""Examples:

  aitbc dispute active

  aitbc dispute get 42

  aitbc dispute resolve job-7f31 --outcome refund --reason "spot-check mismatch\""""
)
def dispute():
    """File, inspect and rule on disputes: evidence, arbitrator votes, and payment rulings."""
    pass


# --------------------------------------------------------------------------
# chain RPC — filing and inspection
# --------------------------------------------------------------------------


@dispute.command(
    "file",
    epilog="""Examples:

  aitbc dispute file --agreement-id 12 --respondent 0xab07... --dispute-type non_delivery \\
      --reason "job never returned a result" --evidence-hash 0x9f2c...""",
)
@click.option("--agreement-id", "agreement_id", type=int, required=True, help="Agreement the dispute is raised against.")
@click.option("--respondent", required=True, help="Address of the party the dispute is filed against.")
@click.option("--dispute-type", "dispute_type", required=True, help="Dispute category, e.g. non_delivery or quality.")
@click.option("--reason", required=True, help="Why the dispute is being filed.")
@click.option("--evidence-hash", "evidence_hash", required=True, help="Hash of the supporting evidence.")
@NODE_URL_OPTION
@FORMAT_OPTION
@click.pass_context
def file_dispute(ctx, agreement_id, respondent, dispute_type, reason, evidence_hash, node_url, format):
    """File a new dispute against an agreement."""
    payload = {
        "agreement_id": agreement_id,
        "respondent": respondent,
        "dispute_type": dispute_type,
        "reason": reason,
        "evidence_hash": evidence_hash,
    }
    try:
        client = _chain_client(ctx, node_url)
        result = client.post("/rpc/disputes/file", json=payload)
        output(result, ctx.obj.get("output_format", format), title="Dispute Filed")
    except NetworkError as e:
        abort(ctx, f"Blockchain RPC error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error filing dispute against agreement {agreement_id}: {e}", from_exception=e)


@dispute.command(
    "active",
    epilog="""Examples:

  aitbc dispute active

  aitbc dispute active --format json""",
)
@NODE_URL_OPTION
@FORMAT_OPTION
@click.pass_context
def active(ctx, node_url, format):
    """List every dispute still open for arbitration."""
    try:
        client = _chain_client(ctx, node_url)
        result = client.get("/rpc/disputes/active")
        output(result, ctx.obj.get("output_format", format), title="Active Disputes")
    except NetworkError as e:
        abort(ctx, f"Blockchain RPC error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error listing active disputes: {e}", from_exception=e)


@dispute.command(
    "get",
    epilog="""Examples:

  aitbc dispute get 42""",
)
@click.argument("dispute_id", type=int)
@NODE_URL_OPTION
@FORMAT_OPTION
@click.pass_context
def get(ctx, dispute_id, node_url, format):
    """Show one dispute with its evidence and votes."""
    try:
        client = _chain_client(ctx, node_url)
        result = client.get(f"/rpc/disputes/{dispute_id}")
        output(result, ctx.obj.get("output_format", format), title=f"Dispute {dispute_id}")
    except NetworkError as e:
        abort(ctx, f"Blockchain RPC error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error fetching dispute {dispute_id}: {e}", from_exception=e)


@dispute.command(
    "user",
    epilog="""Examples:

  aitbc dispute user 0xab07d2f4c1e8b95a3d60f7128e4b0c99a51f1d76""",
)
@click.argument("user_address")
@NODE_URL_OPTION
@FORMAT_OPTION
@click.pass_context
def user(ctx, user_address, node_url, format):
    """List the disputes an address is party to."""
    try:
        client = _chain_client(ctx, node_url)
        result = client.get(f"/rpc/disputes/user/{user_address}")
        output(result, ctx.obj.get("output_format", format), title=f"Disputes for {user_address}")
    except NetworkError as e:
        abort(ctx, f"Blockchain RPC error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error fetching disputes for {user_address}: {e}", from_exception=e)


@dispute.command(
    "votes",
    epilog="""Examples:

  aitbc dispute votes 42""",
)
@click.argument("dispute_id", type=int)
@NODE_URL_OPTION
@FORMAT_OPTION
@click.pass_context
def votes(ctx, dispute_id, node_url, format):
    """Show the arbitration votes cast on a dispute."""
    try:
        client = _chain_client(ctx, node_url)
        result = client.get(f"/rpc/disputes/{dispute_id}/votes")
        output(result, ctx.obj.get("output_format", format), title=f"Votes on Dispute {dispute_id}")
    except NetworkError as e:
        abort(ctx, f"Blockchain RPC error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error fetching votes for dispute {dispute_id}: {e}", from_exception=e)


@dispute.command(
    "vote",
    epilog="""Examples:

  aitbc dispute vote --dispute-id 42 --vote plaintiff --reasoning "evidence is conclusive\"""",
)
@click.option("--dispute-id", "dispute_id", type=int, required=True, help="Dispute being voted on.")
@click.option("--vote", type=click.Choice(["plaintiff", "defendant"]), required=True, help="Which side the vote favours.")
@click.option("--reasoning", required=True, help="Why the arbitrator ruled this way; recorded with the vote.")
@NODE_URL_OPTION
@FORMAT_OPTION
@click.pass_context
def vote(ctx, dispute_id, vote, reasoning, node_url, format):
    """Cast an arbitration vote on a dispute (arbitrators only)."""
    payload = {"dispute_id": dispute_id, "vote": vote, "reasoning": reasoning}
    try:
        client = _chain_client(ctx, node_url)
        result = client.post("/rpc/disputes/vote", json=payload)
        output(result, ctx.obj.get("output_format", format), title="Vote Submitted")
    except NetworkError as e:
        abort(ctx, f"Blockchain RPC error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error voting on dispute {dispute_id}: {e}", from_exception=e)


# --------------------------------------------------------------------------
# chain RPC — evidence
# --------------------------------------------------------------------------


@dispute.group(
    "evidence",
    epilog="""Examples:

  aitbc dispute evidence list 42

  aitbc dispute evidence add --dispute-id 42 --evidence-hash 0x9f2c... \\
      --evidence-type transcript --description "coordinator job log\"""",
)
def evidence():
    """Submit, list and verify the evidence attached to a dispute."""
    pass


@evidence.command(
    "add",
    epilog="""Examples:

  aitbc dispute evidence add --dispute-id 42 --evidence-hash 0x9f2c... \\
      --evidence-type transcript --description "coordinator job log\"""",
)
@click.option("--dispute-id", "dispute_id", type=int, required=True, help="Dispute the evidence belongs to.")
@click.option("--evidence-hash", "evidence_hash", required=True, help="Content hash of the evidence.")
@click.option("--evidence-type", "evidence_type", required=True, help="Evidence category, e.g. transcript or receipt.")
@click.option("--description", required=True, help="What the evidence shows.")
@NODE_URL_OPTION
@FORMAT_OPTION
@click.pass_context
def evidence_add(ctx, dispute_id, evidence_hash, evidence_type, description, node_url, format):
    """Submit evidence for a dispute."""
    payload = {
        "dispute_id": dispute_id,
        "evidence_hash": evidence_hash,
        "evidence_type": evidence_type,
        "description": description,
    }
    try:
        client = _chain_client(ctx, node_url)
        result = client.post("/rpc/disputes/evidence", json=payload)
        output(result, ctx.obj.get("output_format", format), title="Evidence Submitted")
    except NetworkError as e:
        abort(ctx, f"Blockchain RPC error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error submitting evidence for dispute {dispute_id}: {e}", from_exception=e)


@evidence.command(
    "list",
    epilog="""Examples:

  aitbc dispute evidence list 42""",
)
@click.argument("dispute_id", type=int)
@NODE_URL_OPTION
@FORMAT_OPTION
@click.pass_context
def evidence_list(ctx, dispute_id, node_url, format):
    """List the evidence submitted for a dispute."""
    try:
        client = _chain_client(ctx, node_url)
        result = client.get(f"/rpc/disputes/{dispute_id}/evidence")
        output(result, ctx.obj.get("output_format", format), title=f"Evidence for Dispute {dispute_id}")
    except NetworkError as e:
        abort(ctx, f"Blockchain RPC error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error fetching evidence for dispute {dispute_id}: {e}", from_exception=e)


@evidence.command(
    "verify",
    epilog="""Examples:

  aitbc dispute evidence verify --dispute-id 42 --evidence-id 3

  aitbc dispute evidence verify --dispute-id 42 --evidence-id 3 --reject""",
)
@click.option("--dispute-id", "dispute_id", type=int, required=True, help="Dispute the evidence belongs to.")
@click.option("--evidence-id", "evidence_id", type=int, required=True, help="Evidence entry to rule on.")
@click.option("--reject", "reject", is_flag=True, default=False, help="Mark the evidence as not verified instead of verified.")
@NODE_URL_OPTION
@FORMAT_OPTION
@click.pass_context
def evidence_verify(ctx, dispute_id, evidence_id, reject, node_url, format):
    """Verify or reject a piece of evidence (arbitrators only)."""
    payload = {"dispute_id": dispute_id, "evidence_id": evidence_id, "verified": not reject}
    try:
        client = _chain_client(ctx, node_url)
        result = client.post("/rpc/disputes/verify-evidence", json=payload)
        output(result, ctx.obj.get("output_format", format), title="Evidence Verification")
    except NetworkError as e:
        abort(ctx, f"Blockchain RPC error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error verifying evidence {evidence_id}: {e}", from_exception=e)


# --------------------------------------------------------------------------
# chain RPC — arbitrators
# --------------------------------------------------------------------------


@dispute.group(
    "arbitrator",
    epilog="""Examples:

  aitbc dispute arbitrator list

  aitbc dispute arbitrator queue 0xab07...""",
)
def arbitrator():
    """Inspect the arbitrator registry and the caseload assigned to each one."""
    pass


@arbitrator.command(
    "list",
    epilog="""Examples:

  aitbc dispute arbitrator list""",
)
@NODE_URL_OPTION
@FORMAT_OPTION
@click.pass_context
def arbitrator_list(ctx, node_url, format):
    """List every authorized arbitrator."""
    try:
        client = _chain_client(ctx, node_url)
        result = client.get("/rpc/disputes/arbitrators")
        output(result, ctx.obj.get("output_format", format), title="Authorized Arbitrators")
    except NetworkError as e:
        abort(ctx, f"Blockchain RPC error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error listing arbitrators: {e}", from_exception=e)


@arbitrator.command(
    "queue",
    epilog="""Examples:

  aitbc dispute arbitrator queue 0xab07d2f4c1e8b95a3d60f7128e4b0c99a51f1d76""",
)
@click.argument("arbitrator_address")
@NODE_URL_OPTION
@FORMAT_OPTION
@click.pass_context
def arbitrator_queue(ctx, arbitrator_address, node_url, format):
    """List the disputes assigned to an arbitrator."""
    try:
        client = _chain_client(ctx, node_url)
        result = client.get(f"/rpc/disputes/arbitrators/{arbitrator_address}")
        output(result, ctx.obj.get("output_format", format), title=f"Caseload for {arbitrator_address}")
    except NetworkError as e:
        abort(ctx, f"Blockchain RPC error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error fetching caseload for {arbitrator_address}: {e}", from_exception=e)


@arbitrator.command(
    "authorize",
    epilog="""Examples:

  aitbc dispute arbitrator authorize 0xab07... --signature 0x4d1e...

  aitbc dispute arbitrator authorize 0xab07... --revoke --signature 0x4d1e...""",
)
@click.argument("arbitrator_address")
@click.option("--revoke", is_flag=True, default=False, help="Revoke authorization instead of granting it.")
@click.option(
    "--signature",
    "owner_signature",
    default=None,
    help="Owner signature authorising the change; required by nodes that enforce it.",
)
@NODE_URL_OPTION
@FORMAT_OPTION
@click.pass_context
def arbitrator_authorize(ctx, arbitrator_address, revoke, owner_signature, node_url, format):
    """Grant or revoke arbitrator rights for an address (admin only)."""
    payload: dict[str, Any] = {"arbitrator_address": arbitrator_address, "authorized": not revoke}
    if owner_signature:
        payload["owner_signature"] = owner_signature
    action = "Revoked" if revoke else "Authorized"
    try:
        client = _chain_client(ctx, node_url)
        result = client.post("/rpc/disputes/arbitrators/authorize", json=payload)
        output(result, ctx.obj.get("output_format", format), title=f"Arbitrator {action}")
    except NetworkError as e:
        abort(ctx, f"Blockchain RPC error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error updating arbitrator {arbitrator_address}: {e}", from_exception=e)


# --------------------------------------------------------------------------
# coordinator admin — payment rulings
# --------------------------------------------------------------------------


@dispute.command(
    "resolve",
    epilog="""Examples:

  aitbc dispute resolve job-7f31 --outcome refund --reason "spot-check mismatch"

  aitbc dispute resolve job-7f31 --outcome release --reason "output matches the spec\"""",
)
@click.argument("job_id")
@click.option(
    "--outcome",
    type=click.Choice(["refund", "release"]),
    required=True,
    help="Whether the escrow returns to the buyer (refund) or pays the provider (release).",
)
@click.option("--reason", required=True, help="The ruling, recorded on the settlement (1-500 characters).")
@click.option("--yes", "assume_yes", is_flag=True, default=False, help="Skip the confirmation prompt.")
@COORDINATOR_URL_OPTION
@FORMAT_OPTION
@click.pass_context
def resolve(ctx, job_id, outcome, reason, assume_yes, coordinator_url, format):
    """Rule on a disputed job payment (operator or arbiter only).

    A refund that settles also slashes the provider bond, so this moves money in
    both directions and cannot be undone from the CLI.
    """
    if not assume_yes:
        click.confirm(f"{outcome.capitalize()} the disputed payment for job {job_id}?", abort=True)
    payload = {"outcome": outcome, "reason": reason}
    try:
        client = _coordinator_client(ctx, coordinator_url)
        result = client.post(f"/v1/admin/disputes/{job_id}/resolve", json=payload)
        output(result, ctx.obj.get("output_format", format), title="Dispute Resolved")
    except ExpiredAdminToken as e:
        abort(ctx, str(e))
    except NetworkError as e:
        abort(ctx, f"Coordinator API error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error resolving dispute for job {job_id}: {e}", from_exception=e)


@dispute.command(
    "auto-adjudicate",
    epilog="""Examples:

  aitbc dispute auto-adjudicate

  aitbc dispute auto-adjudicate --yes --format json""",
)
@click.option("--yes", "assume_yes", is_flag=True, default=False, help="Skip the confirmation prompt.")
@COORDINATOR_URL_OPTION
@FORMAT_OPTION
@click.pass_context
def auto_adjudicate(ctx, assume_yes, coordinator_url, format):
    """Auto-resolve every dispute whose spot-check evidence proves a mismatch (S-3).

    Disputes without spot-check evidence are left for `aitbc dispute resolve`.
    Each auto-refund also slashes the provider bond, so one call can settle
    several payments.
    """
    if not assume_yes:
        click.confirm("Auto-adjudicate all disputes with conclusive spot-check evidence?", abort=True)
    try:
        client = _coordinator_client(ctx, coordinator_url)
        result = client.post("/v1/admin/disputes/auto-adjudicate", json={})
        output(result, ctx.obj.get("output_format", format), title="Auto-Adjudication")
    except ExpiredAdminToken as e:
        abort(ctx, str(e))
    except NetworkError as e:
        abort(ctx, f"Coordinator API error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error auto-adjudicating disputes: {e}", from_exception=e)
