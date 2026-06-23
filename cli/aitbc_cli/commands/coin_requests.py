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
            click.echo(
                f"{req.id:<20} {req.sender:<20} {format_ait(req.amount):<15} "
                f"{req.status.value:<12} {req.created_at.strftime('%Y-%m-%d %H:%M:%S'):<20}"
            )


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
            click.echo(f"Request {request_id} is not pending (status: {req.status.value}).")
            return

        req.status = CoinRequestStatus.APPROVED
        req.approved_by = "cli"
        req.approved_at = datetime.now(UTC)
        req.rejection_reason = None
        req.audit_log += f" | CLI approved at {datetime.now(UTC).isoformat()}"
        if reason:
            req.audit_log += f" | Reason: {reason}"

        click.echo(f"Request {request_id} approved successfully.")
        click.echo(f"Amount: {format_ait(req.amount)} to {req.wallet_address}")

        # Send notification to sender
        notification_content = f"Coin request {req.id} APPROVED. Amount: {format_ait(req.amount)} to {req.wallet_address}."
        send_agent_notification(req.sender, notification_content)


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
            click.echo(f"Request {request_id} is not pending (status: {req.status.value}).")
            return

        req.status = CoinRequestStatus.REJECTED
        req.approved_by = "cli"
        req.approved_at = datetime.now(UTC)
        req.rejection_reason = reason
        req.audit_log += f" | CLI rejected at {datetime.now(UTC).isoformat()} | Reason: {reason}"

        click.echo(f"Request {request_id} rejected successfully.")

        # Send notification to sender
        notification_content = f"Coin request {req.id} REJECTED. Reason: {reason}."
        send_agent_notification(req.sender, notification_content)


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
            click.echo(f"Request {request_id} is not approved (status: {req.status.value}).")
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
            execute_url = f"{hub_url.rstrip('/')}/coin-requests/execute"
            click.echo(f"No local genesis key — forwarding execution to hub: {execute_url}")
            try:
                import httpx

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
                    req.audit_log += f" | Forwarded to hub for execution at {datetime.now(UTC).isoformat()} | Hash: {tx_hash}"
                    click.echo(f"Transaction submitted by hub: {tx_hash}")
                    click.echo(f"Amount: {format_ait(req.amount)} to {req.wallet_address}")
                    send_agent_notification(
                        req.sender, f"Coin request {req.id} EXECUTED via hub. TX: {tx_hash}. Amount: {format_ait(req.amount)}."
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
        total_required = req.amount + 36  # amount + fee
        if balance < total_required:
            click.echo(
                f"Error: Insufficient balance. Required: {format_ait(total_required)}, Available: {format_ait(balance)}"
            )
            return

        click.echo(f"Executing request {request_id}...")
        click.echo(f"Amount: {format_ait(req.amount)} to {req.wallet_address}")
        click.echo(f"Genesis wallet balance: {format_ait(balance)}")

        # Generate signed transaction
        signed_tx = tx_service.generate_signed_transaction(to_address=req.wallet_address, amount=req.amount, fee=36)

        if not signed_tx:
            click.echo("Error: Failed to generate signed transaction")
            # Revert to PENDING for retry
            req.status = CoinRequestStatus.PENDING
            req.audit_log += f" | Execution failed: could not generate signed transaction at {datetime.now(UTC).isoformat()}"
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
                req.audit_log += f" | Transaction executed at {datetime.now(UTC).isoformat()} | Hash: {tx_hash}"

                click.echo(f"Transaction submitted successfully: {tx_hash}")
                click.echo(f"Amount: {format_ait(req.amount)} to {req.wallet_address}")

                # Send notification to sender
                notification_content = (
                    f"Coin request {req.id} EXECUTED. Transaction hash: {tx_hash}. Amount: {format_ait(req.amount)}."
                )
                send_agent_notification(req.sender, notification_content)
            else:
                # Revert to PENDING on failure
                req.status = CoinRequestStatus.PENDING
                req.audit_log += f" | Execution failed: no transaction hash returned at {datetime.now(UTC).isoformat()}"
                click.echo("Error: Transaction submission failed - no hash returned")

        except Exception as e:
            # Revert to PENDING on failure
            req.status = CoinRequestStatus.PENDING
            req.audit_log += f" | Execution failed: {str(e)} at {datetime.now(UTC).isoformat()}"
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
        click.echo(f"Amount: {format_ait(req.amount)}")
        click.echo(f"Wallet Address: {req.wallet_address}")
        click.echo(f"Status: {req.status.value}")
        click.echo(f"Approval Mode: {req.approval_mode}")
        click.echo(f"Approved By: {req.approved_by}")
        click.echo(f"Approved At: {req.approved_at}")
        click.echo(f"Rejection Reason: {req.rejection_reason}")
        click.echo(f"Created At: {req.created_at}")
        click.echo(f"Expires At: {req.expires_at}")
        click.echo(f"Transaction Hash: {req.transaction_hash}")
        click.echo(f"Audit Log: {req.audit_log}")
