"""TEE lifecycle and attestation commands for the AITBC CLI."""

from __future__ import annotations

from datetime import UTC, datetime
import os

import click

from aitbc.tee import AttestationQuote, AttestationVerifier, Enclave, EnclaveConfig, QuoteGenerator
from aitbc.tee.verification import DualVerificationPolicy, VerificationMode, verify_with_policy

from typing import Any

from ..auth import AuthManager
from ..config import get_config
from ..utils import output
from ..utils.error_handling import abort
from ..utils.http_client import AITBCHTTPClient, NetworkError


def _looks_like_jwt(token: str) -> bool:
    """A JWT is three base64url segments separated by dots."""
    return token.startswith("ey") and token.count(".") == 2


def _api_client(ctx) -> AITBCHTTPClient | None:
    """Return a client for the coordinator API if a URL is configured."""
    config = get_config()
    url = config.coordinator_api_url or os.getenv("COORDINATOR_API_URL", "")
    if not url:
        return None

    url = url.rstrip("/")
    if url.endswith("/v1"):
        url = url[:-3]

    token = ctx.obj.get("api_key") if ctx and hasattr(ctx, "obj") else None
    if not token:
        token = config.api_key or ""
    if not token:
        token = AuthManager().get_credential("client")
    headers: dict[str, str] | None = None
    client_kwargs: dict[str, Any] = {"base_url": url, "timeout": config.timeout, "headers": headers}
    if token and _looks_like_jwt(token):
        client_kwargs["headers"] = {"Authorization": f"Bearer {token}"}
    elif token:
        client_kwargs["api_key"] = token

    return AITBCHTTPClient(**client_kwargs)


@click.group()
def tee():
    """Trusted Execution Environment (TEE) commands."""
    pass


@tee.command()
@click.argument("enclave-id")
@click.option("--measurement", default="", help="Expected enclave measurement")
@click.pass_context
def attest(ctx, enclave_id: str, measurement: str):
    """Generate a signed attestation quote for an enclave and submit it."""
    try:
        generator = QuoteGenerator(enclave_id)
        quote_id = f"tee-{enclave_id}-{datetime.now(UTC).isoformat()}"
        quote = generator.generate(quote_id=quote_id, enclave_id=enclave_id, measurement=measurement)
        quote_b64 = quote.to_base64()
        client = _api_client(ctx)
        if client is None:
            result = {
                "enclave_id": quote.enclave_id,
                "measurement": quote.measurement,
                "quote_id": quote.quote_id,
                "quote": quote_b64,
                "verified": quote.verify_signature(),
                "status": "generated",
            }
        else:
            result = client.post(
                "/v1/tee/attestations",
                json={
                    "enclave_id": enclave_id,
                    "quote": quote_b64,
                    "measurement": measurement,
                },
            )
        output(result, ctx.obj.get("output_format", "table"), title="TEE Attestation")
    except NetworkError as e:
        abort(ctx, f"Coordinator API error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error generating attestation for {enclave_id}: {e}", from_exception=e)


@tee.command()
@click.argument("enclave-id")
@click.option("--image", default="", help="Enclave image identifier")
@click.pass_context
def launch(ctx, enclave_id: str, image: str):
    """Launch a TEE enclave (simulated when no TEE runtime is present)."""
    try:
        config = EnclaveConfig(enclave_id=enclave_id, image=image)
        enclave = Enclave(config=config)
        enclave.build()
        enclave.launch()
        result = {
            "enclave_id": enclave_id,
            "image": image,
            "status": enclave.status.value,
            "measurement": enclave.measurement,
        }
        output(result, ctx.obj.get("output_format", "table"), title="TEE Enclave Launch")
    except Exception as e:
        abort(ctx, f"Error launching enclave {enclave_id}: {e}", from_exception=e)


@tee.command()
@click.option("--quote", required=True, help="Base64-encoded attestation quote")
@click.option("--measurement", default="", help="Expected measurement to verify against")
@click.option("--zk-proof", default="", help="Optional ZK proof identifier for dual verification")
@click.option("--mode", type=click.Choice(["zk_only", "tee_only", "both"]), default="tee_only", help="Verification mode")
@click.pass_context
def verify(ctx, quote: str, measurement: str, zk_proof: str, mode: str):
    """Verify a signed TEE attestation quote, optionally with a ZK proof."""
    try:
        att_quote = AttestationQuote.from_base64(quote)

        # v0.14.3: TEE-only verification must be a real quote path, so the
        # signature is always checked. The measurement must match the quote.
        tee_verifier = AttestationVerifier(
            allowed_measurements={measurement} if measurement else None,
            require_signature=True,
        )
        tee_ok = tee_verifier.verify(att_quote, expected_measurement=measurement or None)

        # Optional dual-verification policy may include a ZK proof.
        allowed = {measurement} if measurement else set()
        policy = DualVerificationPolicy(mode=VerificationMode(mode), allowed_measurements=allowed)
        zk = None
        if zk_proof:
            from aitbc.tee.verification import ZKProof

            zk = ZKProof(zk_proof, verified=True)
        policy_ok = verify_with_policy(policy, att_quote, zk)

        result = {
            "valid": tee_ok and (policy_ok if zk else tee_ok),
            "tee_signature_valid": tee_ok,
            "policy_valid": policy_ok,
            "mode": mode,
            "measurement": att_quote.measurement,
            "enclave_id": att_quote.enclave_id,
            "quote_id": att_quote.quote_id,
            "quote_size": len(att_quote.quote_blob),
        }
        output(result, ctx.obj.get("output_format", "table"), title="TEE Quote Verification")
    except Exception as e:
        abort(ctx, f"Error verifying quote: {e}", from_exception=e)
