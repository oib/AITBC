"""Confidential transaction commands for the AITBC CLI.

These commands are a demonstration of envelope construction, not a wallet. There is no
persistence: each invocation builds a fresh in-memory ``ConfidentialWallet``, so ``send``
seeds the balance it is about to spend and ``balance`` always reports zero. Both are labelled
``"status": "simulated"`` for that reason (V23-19a — previously only the offline branch was).

The remote branch POSTs to ``/v1/confidential/payments``, which no service in this repository
serves; it is retained for out-of-tree coordinators that do.
"""

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


@click.group(
    epilog="""Examples:

  aitbc confidential balance --wallet-id wallet-1

  aitbc confidential send --wallet-id wallet-1 --recipient-id recipient-1 --amount 10"""
)
def confidential():
    """Send and verify confidential TEE-signed transactions and wallet balances."""
    pass


@confidential.command(
    epilog="""Examples:

  aitbc confidential send --wallet-id wallet-1 --recipient-id recipient-1 --amount 10

  aitbc confidential send --wallet-id wallet-1 --recipient-id recipient-1 --amount 10 --output json"""
)
@click.option("--wallet-id", "wallet_id", required=True, help="Wallet ID.")
@click.option("--recipient-id", "recipient_id", required=True, help="Recipient ID.")
@click.option("--amount", "amount", required=True, help="Amount of AIT.")
@click.pass_context
def send(ctx, wallet_id: str, recipient_id: str, amount: str):
    """Send a confidential amount from a wallet to a recipient."""
    try:
        wallet = ConfidentialWallet(wallet_id=wallet_id, owner_id=wallet_id)
        key = _signing_key()
        # No persistence, so there is no balance to spend from. Seed it explicitly rather
        # than letting the wallet's own check pass by accident.
        wallet.deposit(amount)
        tx = wallet.send(recipient_id, amount, key)
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
                "amount_commitment": tx.amount_commitment.hex() if tx.amount_commitment else "",
                "signature": tx.signature.hex() if tx.signature else "",
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
                    "amount_commitment": tx.amount_commitment.hex() if tx.amount_commitment else "",
                },
            )
            # The envelope was still built by an unpersisted local wallet, and no range proof
            # accompanies the commitment. Saying so on this branch too is the V23-19a fix.
            if isinstance(result, dict):
                result.setdefault("status", "simulated")
        output(result, ctx.obj.get("output_format", "table"), title="Confidential Send")
    except NetworkError as e:
        abort(ctx, f"Coordinator API error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error sending confidential transaction: {e}", from_exception=e)


@confidential.command(
    epilog="""Examples:

  aitbc confidential balance --wallet-id wallet-1

  aitbc confidential balance --wallet-id wallet-1 --output json"""
)
@click.option("--wallet-id", "wallet_id", required=True, help="Wallet ID.")
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
