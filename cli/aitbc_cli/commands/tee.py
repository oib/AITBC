"""TEE lifecycle and attestation commands for the AITBC CLI."""

from __future__ import annotations

from datetime import UTC, datetime
import base64
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


def _resolve_quote_from_cli(ctx, quote: str, attestation_id: str, job_id: str) -> str:
    """Return a base64 quote from --quote, --attestation-id, or --job-id."""
    if quote:
        return quote
    client = _api_client(ctx)
    if client is None:
        abort(ctx, "Coordinator API URL not configured")
    if attestation_id:
        att = client.get(f"/v1/tee/attestations/{attestation_id}")
        return att.get("quote", "")
    if job_id:
        job = client.get(f"/v1/jobs/{job_id}")
        att_id = (job or {}).get("tee_attestation_id")
        if not att_id:
            abort(ctx, f"Job {job_id} has no tee_attestation_id")
        att = client.get(f"/v1/tee/attestations/{att_id}")
        return att.get("quote", "")
    return ""


@tee.command()
@click.option("--quote", default="", help="Base64-encoded attestation quote")
@click.option("--attestation-id", default="", help="Stored TEE attestation ID to verify")
@click.option("--job-id", default="", help="Job whose tee_attestation_id will be verified")
@click.option("--measurement", default="", help="Expected measurement to verify against")
@click.option("--zk-proof", default="", help="Optional ZK proof identifier for dual verification")
@click.option("--mode", type=click.Choice(["zk_only", "tee_only", "both"]), default="tee_only", help="Verification mode")
@click.pass_context
def verify(ctx, quote: str, attestation_id: str, job_id: str, measurement: str, zk_proof: str, mode: str):
    """Verify a signed TEE attestation quote from a job, attestation ID, or raw quote."""
    try:
        if not (quote or attestation_id or job_id):
            abort(ctx, "Provide --quote, --attestation-id, or --job-id")

        quote = _resolve_quote_from_cli(ctx, quote, attestation_id, job_id)
        if not quote:
            abort(ctx, "Could not resolve TEE quote")

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
            "source_attestation_id": attestation_id if attestation_id else None,
            "source_job_id": job_id if job_id else None,
        }
        output(result, ctx.obj.get("output_format", "table"), title="TEE Quote Verification")
    except Exception as e:
        abort(ctx, f"Error verifying quote: {e}", from_exception=e)


@tee.command()
@click.argument("enclave-id")
@click.option("--public-key", help="Public key for the enclave (auto-generated if omitted)")
@click.option("--agent-id", default="", help="Agent / miner ID that owns the enclave")
@click.pass_context
def register(ctx, enclave_id: str, public_key: str, agent_id: str):
    """Register a TEE enclave identity with the coordinator."""
    try:
        client = _api_client(ctx)
        if client is None:
            abort(ctx, "Coordinator API URL not configured")
        if not public_key:
            public_key = base64.b64encode(os.urandom(32)).decode("ascii")
        result = client.post(
            "/v1/tee/enclaves",
            json={
                "enclave_id": enclave_id,
                "public_key": public_key,
                "agent_id": agent_id,
                "status": "active",
            },
        )
        output(result, ctx.obj.get("output_format", "table"), title="TEE Enclave Registration")
    except NetworkError as e:
        abort(ctx, f"Coordinator API error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error registering enclave {enclave_id}: {e}", from_exception=e)


@tee.command()
@click.argument("enclave-id")
@click.pass_context
def status(ctx, enclave_id: str):
    """Get the registered status of a TEE enclave."""
    try:
        client = _api_client(ctx)
        if client is None:
            abort(ctx, "Coordinator API URL not configured")
        result = client.get(f"/v1/tee/enclaves/{enclave_id}")
        output(result, ctx.obj.get("output_format", "table"), title="TEE Enclave Status")
    except NetworkError as e:
        abort(ctx, f"Coordinator API error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error fetching enclave {enclave_id}: {e}", from_exception=e)
