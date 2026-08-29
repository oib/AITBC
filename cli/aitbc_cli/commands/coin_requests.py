"""CLI commands for coin request management."""

import json
import os
from datetime import UTC, datetime

import click
import requests


def _load_env_file(path: str, override: bool = False):
    # AITBC_SKIP_ENV_FILES lets a process opt out of inheriting the machine's deployed
    # configuration. The test suite sets it in the root conftest, because importing this
    # module puts the hub's real BLOCKCHAIN_RPC_URL, GENESIS_* and AGENT_DB_PATH in front of
    # every test that runs afterwards, and a suite whose results depend on what is deployed
    # on the box is not measuring the code (V23-69).
    if os.getenv("AITBC_SKIP_ENV_FILES"):
        return
    if os.path.exists(path):
        try:
            fh = open(path)
        except OSError:
            return
        with fh as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    if override:
                        os.environ[key.strip()] = value.strip()
                    else:
                        os.environ.setdefault(key.strip(), value.strip())


# Load environment variables BEFORE importing storage
# blockchain.env has public URLs (for followers); node.env has localhost (for hub CLI)
# node.env must override blockchain.env
_load_env_file("/etc/aitbc/blockchain.env")
_load_env_file("/etc/aitbc/blockchain-secrets.env")
_load_env_file("/etc/aitbc/node.env", override=True)

from aitbc.crypto import TransactionService  # noqa: E402
from aitbc.db import get_db_session, init_db  # noqa: E402
from aitbc.models import CoinRequest, CoinRequestStatus  # noqa: E402
from aitbc.utils import format_ait  # noqa: E402
from aitbc.utils.units import DEFAULT_TX_FEE_UNITS  # noqa: E402


def _agent_api_base() -> str:
    """Where the agent API lives, seen from this node (V23-92).

    `aitbc-agent-coordinator` is a hub-only service — it is not installed on a follower or
    shop node, which reaches the hub's instance instead. So `http://localhost:8107` is the
    wrong default off the hub: nothing listens there, and every notification failed with a
    connection error naming a port the node is correct not to be running.

    The two variable families mean different things, and both are already in use:

    - `AGENT_COORDINATOR_URL` / `HERMES_COORDINATOR_URL` are an *origin*, so the router
      prefix is appended. A hub sets these to its own localhost.
    - `HUB_AGENT_URL` / `HUB_HERMES_URL` are the hub's *mounted base*, prefix included —
      the same precedence and default `execute` uses when it forwards to the hub.
    """
    local = os.getenv("AGENT_COORDINATOR_URL") or os.getenv("HERMES_COORDINATOR_URL")
    if local:
        return f"{local.rstrip('/')}/api/v1/agent"

    from aitbc.config.hub import hub_agent_url

    hub = hub_agent_url()
    if not hub:
        raise RuntimeError(
            "No hub agent URL configured. Set HUB_AGENT_URL, HUB_HERMES_URL, or HUB_DISCOVERY_URL "
            "in /etc/aitbc/blockchain.env or /etc/aitbc/node.env."
        )
    return hub


def send_agent_notification(recipient: str, content: str):
    """Send an agent message notification via Agent Coordinator."""
    try:
        url = f"{_agent_api_base()}/messages/send"
    except RuntimeError as e:
        # Approve/reject already committed; naming the missing config is enough.
        click.echo(f"Error sending notification: {e}")
        return
    agent_id = os.getenv("AGENT_ID", os.getenv("HERMES_AGENT_ID", "cli-admin"))

    # This call sent no credential at all, so it answered 401 anywhere the coordinator was
    # not an unauthenticated localhost (V23-92). FOLLOWER_API_KEY is deliberately not offered
    # here: it is published, and it reaches /register and /execute only (V23-68). Agent
    # messaging is a hub-operator action, so it takes a hub credential or none.
    api_key = os.getenv("COORDINATOR_API_KEY") or os.getenv("SECRET_KEY")

    try:
        response = requests.post(
            url,
            json={
                "sender": agent_id,
                "recipient": recipient,
                "content": {"text": content},
                "message_type": "direct",
                "encrypt": False,
            },
            headers={"x-api-key": api_key} if api_key else {},
            timeout=10,
        )
        if response.status_code == 200:
            click.echo(f"Notification sent to {recipient}")
        elif response.status_code in (401, 403):
            click.echo(f"Notification refused ({response.status_code}) by {url}")
            click.echo("  Agent messaging needs a hub credential; FOLLOWER_API_KEY does not open this route.")
        else:
            click.echo(f"Failed to send notification: {response.status_code} {response.text}")
    except Exception as e:
        # Naming the URL is the point: the failure used to blame a local port on nodes that
        # have no local agent-coordinator, which read as a broken service rather than config.
        click.echo(f"Error sending notification to {url}: {e}")


@click.group(
    epilog="""Examples:

  aitbc coin-requests list

  aitbc coin-requests show --request-id req-123"""
)
def coin_requests():
    """List, approve, reject, execute, and inspect coin transfer requests."""
    init_db()


@coin_requests.command(
    epilog="""Examples:

  aitbc coin-requests list

  aitbc coin-requests list --status pending --sender user-1"""
)
@click.option("--status", help="Filter by status (pending, approved, rejected, expired)")
@click.option("--sender", help="Filter by sender")
@click.pass_context
def list(ctx, status, sender):
    """List coin transfer requests with optional status and sender filters."""
    with get_db_session() as session:
        query = session.query(CoinRequest)

        if status:
            try:
                status_enum = CoinRequestStatus(status.lower())
                query = query.filter(CoinRequest.status == status_enum)
            except ValueError:
                click.echo(f"Invalid status: {status}")
                return

        if sender:
            query = query.filter(CoinRequest.sender == sender)

        requests = query.order_by(CoinRequest.created_at.desc()).all()

        if not requests:
            click.echo("No coin requests found.")
            return

        click.echo(f"{'ID':<20} {'Sender':<20} {'Amount':<15} {'Status':<12} {'Created':<20}")
        click.echo("-" * 87)

        for req in requests:
            amount_str = format_ait(req.amount) if req.amount is not None else "N/A"
            status_str = req.status.value if req.status is not None else "N/A"
            created_str = req.created_at.strftime("%Y-%m-%d %H:%M:%S") if req.created_at is not None else "N/A"
            click.echo(f"{req.id:<20} {req.sender:<20} {amount_str:<15} {status_str:<12} {created_str:<20}")


@coin_requests.command(
    epilog="""Examples:

  aitbc coin-requests approve --request-id req-123

  aitbc coin-requests approve --request-id req-123 --reason 'funded'"""
)
@click.option("--request-id", "request_id", required=True, help="The Request id.")
@click.option("--reason", help="Reason for approval")
@click.pass_context
def approve(ctx, request_id, reason):
    """Approve a pending coin transfer request by request ID."""
    with get_db_session() as session:
        req = session.query(CoinRequest).filter(CoinRequest.id == request_id).first()

        if not req:
            click.echo(f"Request {request_id} not found.")
            return

        if req.status != CoinRequestStatus.PENDING:
            click.echo(f"Request {request_id} is not pending (status: {req.status.value if req.status else 'N/A'}).")
            return

        req.status = CoinRequestStatus.APPROVED
        req.approved_by = "cli"
        req.approved_at = datetime.now(UTC)
        req.rejection_reason = None
        audit_entry = f" | CLI approved at {datetime.now(UTC).isoformat()}"
        if reason:
            audit_entry += f" | Reason: {reason}"
        req.audit_log = (req.audit_log or "") + audit_entry

        click.echo(f"Request {request_id} approved successfully.")
        click.echo(f"Amount: {format_ait(req.amount) if req.amount is not None else 'N/A'} to {req.wallet_address}")

        # Send notification to sender
        notification_content = f"Coin request {req.id} APPROVED. Amount: {format_ait(req.amount) if req.amount is not None else 'N/A'} to {req.wallet_address}."
        send_agent_notification(req.sender if req.sender else "unknown", notification_content)


@coin_requests.command(
    epilog="""Examples:

  aitbc coin-requests reject --request-id req-123 --reason 'insufficient funds'

  aitbc coin-requests reject --request-id req-123 --reason 'invalid request'"""
)
@click.option("--request-id", "request_id", required=True, help="The Request id.")
@click.option("--reason", help="Reason for rejection", required=True)
@click.pass_context
def reject(ctx, request_id, reason):
    """Reject a pending coin transfer request with a required reason."""
    with get_db_session() as session:
        req = session.query(CoinRequest).filter(CoinRequest.id == request_id).first()

        if not req:
            click.echo(f"Request {request_id} not found.")
            return

        if req.status != CoinRequestStatus.PENDING:
            click.echo(f"Request {request_id} is not pending (status: {req.status.value if req.status else 'N/A'}).")
            return

        req.status = CoinRequestStatus.REJECTED
        req.approved_by = "cli"
        req.approved_at = datetime.now(UTC)
        req.rejection_reason = reason
        audit_entry = f" | CLI rejected at {datetime.now(UTC).isoformat()} | Reason: {reason}"
        req.audit_log = (req.audit_log or "") + audit_entry

        click.echo(f"Request {request_id} rejected successfully.")

        # Send notification to sender
        notification_content = f"Coin request {req.id} REJECTED. Reason: {reason}."
        send_agent_notification(req.sender if req.sender else "unknown", notification_content)


@coin_requests.command(
    epilog="""Examples:

  aitbc coin-requests execute --request-id req-123

  aitbc coin-requests execute --request-id req-123 --output json"""
)
@click.option("--request-id", "request_id", required=True, help="The Request id.")
@click.pass_context
def execute(ctx, request_id):
    """Execute an approved coin transfer request by submitting a signed transaction."""
    with get_db_session() as session:
        req = session.query(CoinRequest).filter(CoinRequest.id == request_id).first()

        if not req:
            click.echo(f"Request {request_id} not found.")
            return

        if req.status != CoinRequestStatus.APPROVED:
            click.echo(f"Request {request_id} is not approved (status: {req.status.value if req.status else 'N/A'}).")
            return

        if req.transaction_hash:
            click.echo(f"Request {request_id} already executed (tx hash: {req.transaction_hash}).")
            return

        # Initialize transaction service
        tx_service = TransactionService()

        # If no local genesis key, forward to hub for execution
        if not tx_service.genesis_private_key:
            from aitbc.config.hub import hub_agent_url

            hub_url = hub_agent_url()
            if not hub_url:
                click.echo(
                    "Error: No hub agent URL configured. Set HUB_AGENT_URL or HUB_DISCOVERY_URL in /etc/aitbc/blockchain.env."
                )
                return
            # FOLLOWER_API_KEY first: it is the one an island is meant to hold, published in
            # the public bootstrap file and scoped to /register and /execute. The other two
            # also open the agent WebSocket and coordinator-api's miner endpoints, so they
            # belong to hub operators only and are accepted here as a fallback (V23-68).
            api_key = os.getenv("FOLLOWER_API_KEY") or os.getenv("COORDINATOR_API_KEY") or os.getenv("SECRET_KEY")
            if not api_key:
                click.echo("Error: No GENESIS_PRIVATE_KEY locally and no API key set.")
                click.echo("Followers: FOLLOWER_API_KEY comes from the hub's public bootstrap file,")
                click.echo("  /etc/aitbc/blockchain.env. Do not use COORDINATOR_API_KEY on a follower.")
                return
            base_url = f"{hub_url.rstrip('/')}/coin-requests"
            execute_url = f"{base_url}/execute"
            click.echo(f"No local genesis key — forwarding execution to hub: {execute_url}")
            try:
                import httpx

                # The hub pays from its own record of the request, not from what we send it,
                # so a request raised on this island has to exist there before it can execute.
                # Registering is idempotent, so re-running after a failure is safe.
                reg = httpx.post(
                    f"{base_url}/register",
                    json={
                        "request_id": req.id,
                        "sender": req.sender,
                        "amount": req.amount,
                        "wallet_address": req.wallet_address,
                        "recipient": req.recipient,
                    },
                    headers={"x-api-key": api_key},
                    timeout=30,
                )
                if reg.status_code != 200:
                    click.echo(f"Hub registration failed: {reg.status_code} {reg.text}")
                    return
                registered = reg.json()
                if registered.get("status") != "approved":
                    click.echo(f"Hub has not approved {req.id}: {registered.get('reason', 'no reason given')}")
                    click.echo(f"Status at hub: {registered.get('status')}. A hub operator must approve it.")
                    return

                resp = httpx.post(
                    execute_url,
                    json={
                        "request_id": req.id,
                        "sender": req.sender,
                        "amount": req.amount,
                        "wallet_address": req.wallet_address,
                        "approved_by": req.approved_by or "cli",
                    },
                    headers={"x-api-key": api_key},
                    timeout=30,
                )
                if resp.status_code == 200:
                    result = resp.json()
                    tx_hash = result.get("tx_hash")
                    req.transaction_hash = tx_hash
                    audit_entry = f" | Forwarded to hub for execution at {datetime.now(UTC).isoformat()} | Hash: {tx_hash}"
                    req.audit_log = (req.audit_log or "") + audit_entry
                    click.echo(f"Transaction submitted by hub: {tx_hash}")
                    click.echo(
                        f"Amount: {format_ait(req.amount) if req.amount is not None else 'N/A'} to {req.wallet_address}"
                    )
                    send_agent_notification(
                        req.sender if req.sender else "unknown",
                        f"Coin request {req.id} EXECUTED via hub. TX: {tx_hash}. Amount: {format_ait(req.amount) if req.amount is not None else 'N/A'}.",
                    )
                else:
                    click.echo(f"Hub execution failed: {resp.status_code} {resp.text}")
            except Exception as e:
                click.echo(f"Error forwarding to hub: {e}")
            return

        # Check genesis wallet configuration
        if not tx_service.genesis_address:
            click.echo("Error: GENESIS_ADDRESS not configured")
            return

        # Check balance before submission
        balance = tx_service.get_balance(tx_service.genesis_address)
        total_required = (req.amount or 0) + DEFAULT_TX_FEE_UNITS  # amount + fee
        if balance < total_required:
            click.echo(
                f"Error: Insufficient balance. Required: {format_ait(total_required)}, Available: {format_ait(balance)}"
            )
            return

        click.echo(f"Executing request {request_id}...")
        click.echo(f"Amount: {format_ait(req.amount) if req.amount is not None else 'N/A'} to {req.wallet_address}")
        click.echo(f"Genesis wallet balance: {format_ait(balance)}")

        # Generate signed transaction
        if req.wallet_address is None or req.amount is None:
            click.echo("Error: Missing wallet_address or amount in request")
            return
        signed_tx = tx_service.generate_signed_transaction(
            to_address=req.wallet_address, amount=req.amount, fee=DEFAULT_TX_FEE_UNITS
        )

        if not signed_tx:
            click.echo("Error: Failed to generate signed transaction")
            # Revert to PENDING for retry
            req.status = CoinRequestStatus.PENDING
            audit_entry = f" | Execution failed: could not generate signed transaction at {datetime.now(UTC).isoformat()}"
            req.audit_log = (req.audit_log or "") + audit_entry
            return

        # Submit transaction to blockchain
        try:
            from ..utils.http_client import AITBCHTTPClient

            http_client = AITBCHTTPClient(base_url=tx_service.rpc_url, timeout=30)
            result = http_client.post("/rpc/transaction", json=signed_tx)
            tx_hash = result.get("transaction_hash")

            if tx_hash:
                # Update database with transaction hash
                req.transaction_hash = tx_hash
                req.signed_transaction = json.dumps(signed_tx)
                audit_entry = f" | Transaction executed at {datetime.now(UTC).isoformat()} | Hash: {tx_hash}"
                req.audit_log = (req.audit_log or "") + audit_entry

                click.echo(f"Transaction submitted successfully: {tx_hash}")
                click.echo(f"Amount: {format_ait(req.amount) if req.amount is not None else 'N/A'} to {req.wallet_address}")

                # Send notification to sender
                notification_content = f"Coin request {req.id} EXECUTED. Transaction hash: {tx_hash}. Amount: {format_ait(req.amount) if req.amount is not None else 'N/A'}."
                send_agent_notification(req.sender if req.sender else "unknown", notification_content)
            else:
                # Revert to PENDING on failure
                req.status = CoinRequestStatus.PENDING
                audit_entry = f" | Execution failed: no transaction hash returned at {datetime.now(UTC).isoformat()}"
                req.audit_log = (req.audit_log or "") + audit_entry
                click.echo("Error: Transaction submission failed - no hash returned")

        except Exception as e:
            # Revert to PENDING on failure
            req.status = CoinRequestStatus.PENDING
            audit_entry = f" | Execution failed: {str(e)} at {datetime.now(UTC).isoformat()}"
            req.audit_log = (req.audit_log or "") + audit_entry
            click.echo(f"Error submitting transaction: {e}")


@coin_requests.command(
    epilog="""Examples:

  aitbc coin-requests show --request-id req-123

  aitbc coin-requests show --request-id req-123 --output json"""
)
@click.option("--request-id", "request_id", required=True, help="The Request id.")
@click.pass_context
def show(ctx, request_id):
    """Show details of a specific coin transfer request."""
    with get_db_session() as session:
        req = session.query(CoinRequest).filter(CoinRequest.id == request_id).first()

        if not req:
            click.echo(f"Request {request_id} not found.")
            return

        click.echo(f"Request ID: {req.id}")
        click.echo(f"Sender: {req.sender}")
        click.echo(f"Recipient: {req.recipient}")
        click.echo(f"Amount: {format_ait(req.amount) if req.amount is not None else 'N/A'}")
        click.echo(f"Wallet Address: {req.wallet_address}")
        click.echo(f"Status: {req.status.value}")  # type: ignore[union-attr]
        click.echo(f"Approval Mode: {req.approval_mode}")
        click.echo(f"Approved By: {req.approved_by}")
        click.echo(f"Approved At: {req.approved_at}")
        click.echo(f"Rejection Reason: {req.rejection_reason}")
        click.echo(f"Created At: {req.created_at}")
        click.echo(f"Expires At: {req.expires_at}")
        click.echo(f"Transaction Hash: {req.transaction_hash}")
        click.echo(f"Audit Log: {req.audit_log}")


def _chain_has_transaction(rpc_url: str, tx_hash: str, chain_id: str | None = None) -> bool | None:
    """Does the chain hold this transaction? None when the chain could not be reached.

    The distinction matters: a missing transaction is a discrepancy to act on, an
    unreachable node is not, and treating the second as the first would invite someone
    to reopen a request that was paid perfectly well.

    `chain_id` is left off unless asked for. The node knows which chain it is serving and
    the caller does not: guessing here — from `CHAIN_ID`, which defaults to `ait-hub` while
    the hub actually serves `ait-hub.aitbc.bubuit.net` — sends a chain nobody has, and every
    hash comes back 404. That failure reads as "no payout was ever made", which is exactly
    the state that invites reopening requests that were paid. Pass `--chain-id` to query a
    node serving several islands.
    """
    url = f"{rpc_url.rstrip('/')}/rpc/transaction/{tx_hash}"
    try:
        response = requests.get(url, params={"chain_id": chain_id} if chain_id else None, timeout=10)
    except Exception as e:
        click.echo(f"  Could not reach {rpc_url}: {e}")
        return None
    if response.status_code == 200:
        return True
    if response.status_code == 404:
        return False
    click.echo(f"  Unexpected {response.status_code} from {rpc_url}: {response.text[:200]}")
    return None


@coin_requests.command(
    epilog="""Examples:

  aitbc coin-requests reconcile

  aitbc coin-requests reconcile --annotate --chain-id ait-mainnet"""
)
@click.option("--rpc-url", default=None, help="Blockchain RPC to check against (defaults to BLOCKCHAIN_RPC_URL)")
@click.option("--annotate", is_flag=True, help="Record the discrepancy in each affected request's audit log")
@click.option("--chain-id", default=None, help="Island to query; omit to let the node answer for its own chain")
@click.pass_context
def reconcile(ctx, rpc_url, annotate, chain_id):
    """Check executed coin requests against the chain and report or annotate discrepancies."""
    rpc_url = rpc_url or os.getenv("BLOCKCHAIN_RPC_URL", "http://localhost:8202")
    click.echo(f"Checking executed coin requests against {rpc_url}\n")

    checked = missing = unreachable = 0
    with get_db_session() as session:
        executed = session.query(CoinRequest).filter(CoinRequest.transaction_hash.isnot(None)).all()
        for req in executed:
            tx_hash = str(req.transaction_hash)
            if tx_hash.startswith("claiming:"):
                click.echo(f"{req.id}: stranded mid-execution ({tx_hash}) — reconcile against the chain by hand")
                continue
            checked += 1
            present = _chain_has_transaction(rpc_url, tx_hash, chain_id)
            if present is None:
                unreachable += 1
                continue
            if present:
                continue
            missing += 1
            amount = format_ait(req.amount) if req.amount is not None else "N/A"
            click.echo(f"{req.id}: chain has no {tx_hash}")
            click.echo(f"  claims {amount} paid to {req.wallet_address}")
            if annotate:
                entry = f" | Reconciled {datetime.now(UTC).isoformat()}: {tx_hash} absent from chain at {rpc_url}"
                req.audit_log = (req.audit_log or "") + entry
                click.echo("  recorded in audit log")

    click.echo(f"\n{checked} checked, {missing} not on chain, {unreachable} unverifiable")
    if missing and not annotate:
        click.echo("Re-run with --annotate to record these, or `reopen <id>` to make one executable again.")


@coin_requests.command(
    epilog="""Examples:

  aitbc coin-requests reopen --request-id req-123

  aitbc coin-requests reopen --request-id req-123 --force"""
)
@click.option("--request-id", "request_id", required=True, help="The Request id.")
@click.option("--rpc-url", default=None, help="Blockchain RPC to check against (defaults to BLOCKCHAIN_RPC_URL)")
@click.option("--force", is_flag=True, help="Reopen even though the chain still has the transaction")
@click.option("--chain-id", default=None, help="Island to query; omit to let the node answer for its own chain")
@click.pass_context
def reopen(ctx, request_id, rpc_url, force, chain_id):
    """Clear a request's transaction hash so it can be executed again."""
    rpc_url = rpc_url or os.getenv("BLOCKCHAIN_RPC_URL", "http://localhost:8202")
    with get_db_session() as session:
        req = session.query(CoinRequest).filter(CoinRequest.id == request_id).first()
        if not req:
            click.echo(f"Request {request_id} not found.")
            return
        if not req.transaction_hash:
            click.echo(f"Request {request_id} has no transaction hash — it is already executable.")
            return

        tx_hash = str(req.transaction_hash)
        if not tx_hash.startswith("claiming:"):
            present = _chain_has_transaction(rpc_url, tx_hash, chain_id)
            if present is None and not force:
                click.echo("Refusing to reopen: could not confirm with the chain whether this was paid.")
                return
            if present:
                click.echo(f"Refusing to reopen: the chain has {tx_hash}. This request was paid.")
                if not force:
                    return
                click.echo("--force given; reopening a request the chain says was paid.")

        entry = f" | Reopened {datetime.now(UTC).isoformat()}: cleared {tx_hash} (absent from chain at {rpc_url})"
        req.audit_log = (req.audit_log or "") + entry
        req.transaction_hash = None
        click.echo(f"Reopened {request_id}. It is executable again — the hub will pay it if you execute it.")
