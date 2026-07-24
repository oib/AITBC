"""TEE lifecycle and attestation commands for the AITBC CLI."""

from __future__ import annotations

import base64
import os

import click

from aitbc.tee import AttestationQuote, Enclave, EnclaveConfig, QuoteGenerator
from aitbc.tee.verification import DualVerificationPolicy, VerificationMode, verify_with_policy

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


@click.group()
def tee():
    """Trusted Execution Environment (TEE) commands."""
    pass


@tee.command()
@click.argument("enclave-id")
@click.option("--measurement", default="", help="Expected enclave measurement")
@click.pass_context
def attest(ctx, enclave_id: str, measurement: str):
    """Generate a local attestation quote for an enclave."""
    try:
        generator = QuoteGenerator(enclave_id)
        quote = generator.generate(measurement=measurement)
        client = _api_client()
        if client is None:
            result = {
                "enclave_id": quote.enclave_id,
                "measurement": quote.measurement,
                "quote_blob": base64.b64encode(quote.quote_blob).decode("ascii"),
                "status": "simulated",
            }
        else:
            result = client.post(
                "/v1/tee/attestations",
                json={
                    "enclave_id": enclave_id,
                    "quote": base64.b64encode(quote.quote_blob).decode("ascii"),
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
    """Verify a TEE attestation quote, optionally with a ZK proof."""
    try:
        quote_blob = base64.b64decode(quote)
        att_quote = AttestationQuote(
            quote_blob=quote_blob,
            measurement=measurement,
        )
        allowed = {measurement} if measurement else set()
        policy = DualVerificationPolicy(mode=VerificationMode(mode), allowed_measurements=allowed)
        zk = None
        if zk_proof:
            from aitbc.tee.verification import ZKProof

            zk = ZKProof(zk_proof, verified=True)
        ok = verify_with_policy(policy, att_quote, zk)
        result = {
            "valid": ok,
            "mode": mode,
            "measurement": measurement,
            "quote_size": len(quote_blob),
        }
        output(result, ctx.obj.get("output_format", "table"), title="TEE Quote Verification")
    except Exception as e:
        abort(ctx, f"Error verifying quote: {e}", from_exception=e)
