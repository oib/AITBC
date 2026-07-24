"""Confidential transaction commands for the AITBC CLI."""

from __future__ import annotations

import os

import click

from aitbc.agent_economics.confidential_payments import ConfidentialPayment, settle_payment, validate_payment
from aitbc.wallet.confidential import ConfidentialWallet

from ..config import get_config
from ..utils import output
from ..utils.error_handling import abort
from ..utils.http_client import AITBCHTTPClient, NetworkError


def _api_client() -> AITBCHTTPClient | None:
    """Return a client for the coordinator API if a URL is configured."""
    config = get_config()
    url = config.coordinator_api_url or os.getenv("COORDINATOR_API_URL", "")
    if not url:
        return None
    return AITBCHTTPClient(base_url=url, timeout=config.timeout, api_key=config.api_key or "")


def _signing_key() -> bytes:
    """Return a deterministic test signing key for simulated confidential transactions."""
    return os.getenv("CONFIDENTIAL_SIGNING_KEY", "simulated-tee-key").encode("utf-8")


@click.group()
def confidential():
    """Confidential TEE-signed transaction commands."""
    pass


@confidential.command()
@click.argument("wallet-id")
@click.argument("recipient-id")
@click.argument("amount-commitment")
@click.pass_context
def send(ctx, wallet_id: str, recipient_id: str, amount_commitment: str):
    """Send a confidential amount commitment to a recipient."""
    try:
        wallet = ConfidentialWallet(wallet_id=wallet_id, owner_id=wallet_id)
        key = _signing_key()
        tx = wallet.send(recipient_id, amount_commitment, key)
        payment = ConfidentialPayment(
            payment_id=tx.tx_id,
            sender_id=tx.sender_id,
            recipient_id=tx.recipient_id,
            amount_commitment=tx.amount_commitment,
            tx=tx,
        )
        validate_payment(payment)
        receipt = settle_payment(payment)
        client = _api_client()
        if client is None:
            result = {
                "tx_id": tx.tx_id,
                "sender_id": tx.sender_id,
                "recipient_id": tx.recipient_id,
                "amount_commitment": tx.amount_commitment,
                "signature": tx.signature.decode("utf-8", errors="replace") if tx.signature else "",
                "settled": receipt["settled"],
                "status": "simulated",
            }
        else:
            result = client.post(
                "/v1/confidential/payments",
                json={
                    "payment_id": tx.tx_id,
                    "sender_id": tx.sender_id,
                    "recipient_id": tx.recipient_id,
                    "amount_commitment": tx.amount_commitment,
                },
            )
        output(result, ctx.obj.get("output_format", "table"), title="Confidential Send")
    except NetworkError as e:
        abort(ctx, f"Coordinator API error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error sending confidential transaction: {e}", from_exception=e)


@confidential.command()
@click.argument("wallet-id")
@click.pass_context
def balance(ctx, wallet_id: str):
    """Show a confidential wallet balance proof."""
    try:
        wallet = ConfidentialWallet(wallet_id=wallet_id, owner_id=wallet_id)
        proof = wallet.balance_proof()
        proof["wallet_id"] = wallet_id
        proof["status"] = "simulated"
        output(proof, ctx.obj.get("output_format", "table"), title="Confidential Balance")
    except Exception as e:
        abort(ctx, f"Error fetching confidential balance for {wallet_id}: {e}", from_exception=e)
