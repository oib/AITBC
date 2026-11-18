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
import httpx

from aitbc.agent_economics.confidential_payments import ConfidentialPayment, settle_payment, validate_payment
from aitbc.wallet.confidential import ConfidentialWallet

from aitbc.exceptions import AITBCError
from ..config import get_config
from ..utils import output
from ..utils.error_handling import CLIError, abort
from ..utils.http_client import AITBCHTTPClient, NetworkError, auth_client_kwargs

# Expected failure surface for the command handlers below: filesystem/JSON,
# data-shape, runtime, optional-dependency imports, HTTP-client errors and
# both error hierarchies (CLIError, aitbc_errors.AITBCError). RuntimeError
# covers generic runtime failures; abort() raises CLIError (already listed),
# preserving the previous re-abort behaviour. BaseExceptions still propagate
# (#1864).
_OPS_ERRORS = (
    OSError,
    ValueError,
    KeyError,
    TypeError,
    AttributeError,
    RuntimeError,
    ImportError,
    CLIError,
    AITBCError,
    httpx.HTTPError,
)


def _api_client(explicit_key: str | None = None) -> AITBCHTTPClient | None:
    """Return a client for the coordinator API if a URL is configured.

    The coordinator API may be configured with a trailing ``/v1`` path
    (e.g. ``https://hub/c/v1``). Since the endpoints below already start
    with ``/v1/``, strip any trailing ``/v1`` to avoid doubling it.
    """
    config = get_config()
    url = config.coordinator_api_url or os.getenv("COORDINATOR_API_URL", "")
    if not url:
        return None
    url = url.rstrip("/")
    if url.endswith("/v1"):
        url = url[:-3]

    # /v1/confidential/payments is authenticated as a client/admin route, not a
    # miner API-key route, so a JWT client credential is required. #2246:
    # explicit --api-key > stored `auth login` credential > config.api_key.
    auth_kwargs = auth_client_kwargs(explicit_key, config.api_key)
    if not auth_kwargs:
        return None

    return AITBCHTTPClient(base_url=url, timeout=config.timeout, **auth_kwargs)


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
        client = _api_client(ctx.obj.get("api_key") if ctx.obj else None)
        simulated_result = {
            "tx_id": tx.tx_id,
            "sender_id": tx.sender_id,
            "recipient_id": tx.recipient_id,
            "amount_commitment": tx.amount_commitment.hex() if tx.amount_commitment else "",
            "signature": tx.signature.hex() if tx.signature else "",
            "settled": receipt["settled"],
            "status": "simulated",
            "confidential": True,
        }
        if client is None:
            result = simulated_result
        else:
            try:
                result = client.post(
                    "/v1/confidential/payments",
                    json={
                        "payment_id": tx.tx_id,
                        "sender_id": tx.sender_id,
                        "recipient_id": tx.recipient_id,
                        "amount_commitment": tx.amount_commitment.hex() if tx.amount_commitment else "",
                    },
                )
            except NetworkError as e:
                # A 503 from the coordinator means confidential TEE settlement is not enabled;
                # fall back to the local simulated settlement rather than failing outright.
                if "503" in str(e) or "Service Unavailable" in str(e):
                    click.echo(
                        "Coordinator does not have confidential TEE enabled; using simulated local settlement.",
                        err=True,
                    )
                    result = simulated_result
                else:
                    raise
            # The envelope was still built by an unpersisted local wallet, and no range proof
            # accompanies the commitment. Saying so on this branch too is the V23-19a fix.
            if isinstance(result, dict):
                result.setdefault("status", "simulated")
                result.setdefault("confidential", True)
        output(result, ctx.obj.get("output_format", "table"), title="Confidential Send")
    except NetworkError as e:
        abort(ctx, f"Coordinator API error: {e}", from_exception=e)
    except _OPS_ERRORS as e:
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
    except _OPS_ERRORS as e:
        abort(ctx, f"Error fetching confidential balance for {wallet_id}: {e}", from_exception=e)
