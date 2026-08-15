"""CLI commands for coin request management."""

import json
import os
from datetime import UTC, datetime

import click
import requests


def _load_env_file(path: str, override: bool = False):
    if os.path.exists(path):
        with open(path) as f:
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


def send_agent_notification(recipient: str, content: str):
    """Send an agent message notification via Agent Coordinator."""
    coordinator_url = os.getenv("AGENT_COORDINATOR_URL", os.getenv("HERMES_COORDINATOR_URL", "http://localhost:8107"))
    agent_id = os.getenv("AGENT_ID", os.getenv("HERMES_AGENT_ID", "cli-admin"))

    try:
        response = requests.post(
            f"{coordinator_url}/api/v1/agent/messages/send",
            json={
                "sender": agent_id,
                "recipient": recipient,
                "content": {"text": content},
                "message_type": "direct",
                "encrypt": False,
            },
            timeout=10,
        )
        if response.status_code == 200:
            click.echo(f"Notification sent to {recipient}")
        else:
            click.echo(f"Failed to send notification: {response.text}")
    except Exception as e:
        click.echo(f"Error sending notification: {e}")


@click.group()
def coin_requests():
    """Manage coin transfer requests."""
    init_db()


@coin_requests.command()
@click.option("--status", help="Filter by status (pending, approved, rejected, expired)")
@click.option("--sender", help="Filter by sender")
@click.pass_context
def list(ctx, status, sender):
    """List coin requests."""
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


@coin_requests.command()
@click.argument("request_id")
@click.option("--reason", help="Reason for approval")
@click.pass_context
def approve(ctx, request_id, reason):
    """Approve a pending coin request."""
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


@coin_requests.command()
@click.argument("request_id")
@click.option("--reason", help="Reason for rejection", required=True)
@click.pass_context
def reject(ctx, request_id, reason):
    """Reject a pending coin request."""
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


@coin_requests.command()
@click.argument("request_id")
@click.pass_context
def execute(ctx, request_id):
    """Execute an approved coin request (submit signed transaction to blockchain)."""
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
            hub_url = os.getenv("HUB_AGENT_URL", os.getenv("HUB_HERMES_URL", "https://hub.aitbc.bubuit.net/api/v1/agent"))
            api_key = os.getenv("COORDINATOR_API_KEY") or os.getenv("SECRET_KEY")
            if not api_key:
                click.echo("Error: No GENESIS_PRIVATE_KEY locally and COORDINATOR_API_KEY not set.")
                click.echo("Ensure /etc/aitbc/blockchain-secrets.env contains COORDINATOR_API_KEY.")
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
        total_required = (req.amount or 0) + 36  # amount + fee
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
        signed_tx = tx_service.generate_signed_transaction(to_address=req.wallet_address, amount=req.amount, fee=36)

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


@coin_requests.command()
@click.argument("request_id")
@click.pass_context
def show(ctx, request_id):
    """Show details of a specific coin request."""
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


def _chain_has_transaction(rpc_url: str, tx_hash: str) -> bool | None:
    """Does the chain hold this transaction? None when the chain could not be reached.

    The distinction matters: a missing transaction is a discrepancy to act on, an
    unreachable node is not, and treating the second as the first would invite someone
    to reopen a request that was paid perfectly well.
    """
    chain_id = TransactionService().chain_id
    try:
        response = requests.get(
            f"{rpc_url.rstrip('/')}/rpc/transaction/{tx_hash}?chain_id={chain_id}",
            timeout=10,
        )
    except Exception as e:
        click.echo(f"  Could not reach {rpc_url}: {e}")
        return None
    if response.status_code == 200:
        return True
    if response.status_code == 404:
        return False
    click.echo(f"  Unexpected {response.status_code} from {rpc_url}: {response.text[:200]}")
    return None


@coin_requests.command()
@click.option("--rpc-url", default=None, help="Blockchain RPC to check against (defaults to BLOCKCHAIN_RPC_URL)")
@click.option("--annotate", is_flag=True, help="Record the discrepancy in each affected request's audit log")
@click.pass_context
def reconcile(ctx, rpc_url, annotate):
    """Check executed requests against the chain and report any the chain has never heard of.

    A coin request records its `transaction_hash` here, in a database the chain knows nothing
    about. The two can disagree — a chain reset is the obvious way, and it happened on
    2026-08-15 — and when they do this database keeps claiming a payout that no longer exists
    anywhere. Nothing detects that on its own.

    Reporting is all this does by default. It deliberately will not clear a hash, because
    clearing one makes the request payable again and the operator has usually already reissued
    it; use `reopen` for that, one request at a time, once you know what happened.
    """
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
            present = _chain_has_transaction(rpc_url, tx_hash)
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


@coin_requests.command()
@click.argument("request_id")
@click.option("--rpc-url", default=None, help="Blockchain RPC to check against (defaults to BLOCKCHAIN_RPC_URL)")
@click.option("--force", is_flag=True, help="Reopen even though the chain still has the transaction")
@click.pass_context
def reopen(ctx, request_id, rpc_url, force):
    """Clear one request's transaction hash so it can be executed again.

    Named explicitly and one at a time, because this is the operation that can pay twice: the
    hash is the only thing stopping a second payout, here and at the hub. It refuses when the
    chain still has the transaction, and when the chain cannot be reached to say either way.
    """
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
            present = _chain_has_transaction(rpc_url, tx_hash)
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
