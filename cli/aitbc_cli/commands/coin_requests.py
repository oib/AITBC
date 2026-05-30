"""CLI commands for coin request management."""

import click
from datetime import datetime
import sys
import os

# Add path to import Hermes storage
sys.path.insert(0, "/opt/aitbc/apps/agent-services/examples/hermes-service/src")

from hermes_service.storage import get_db_session, CoinRequest, CoinRequestStatus, init_db


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
        
        click.echo(f"{'ID':<20} {'Sender':<20} {'Amount':<10} {'Status':<12} {'Created':<20}")
        click.echo("-" * 82)
        
        for req in requests:
            click.echo(
                f"{req.id:<20} {req.sender:<20} {req.amount:<10} "
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
        req.approved_at = datetime.utcnow()
        req.rejection_reason = None
        req.audit_log += f" | CLI approved at {datetime.utcnow().isoformat()}"
        if reason:
            req.audit_log += f" | Reason: {reason}"
        
        click.echo(f"Request {request_id} approved successfully.")
        click.echo(f"Amount: {req.amount} AIT to {req.wallet_address}")


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
        req.approved_at = datetime.utcnow()
        req.rejection_reason = reason
        req.audit_log += f" | CLI rejected at {datetime.utcnow().isoformat()} | Reason: {reason}"
        
        click.echo(f"Request {request_id} rejected successfully.")


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
        
        # Check if signed transaction exists
        if not req.signed_transaction:
            click.echo(f"No signed transaction found for request {request_id}.")
            click.echo("Please generate signed transaction first.")
            return
        
        # Submit transaction to blockchain
        # This would integrate with the existing wallet transfer logic
        click.echo(f"Executing request {request_id}...")
        click.echo(f"Amount: {req.amount} AIT to {req.wallet_address}")
        click.echo("Note: Transaction submission requires integration with blockchain RPC.")
        click.echo("Signed transaction available in database for manual submission.")
        
        # For now, just mark as having been attempted
        # In production, this would call the blockchain RPC
        click.echo("Transaction execution not yet implemented - requires blockchain RPC integration.")


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
        click.echo(f"Amount: {req.amount} AIT")
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
