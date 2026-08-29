"""Zero-knowledge proof commands for the AITBC CLI."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

import click

from ..config import get_config
from ..utils import output
from ..utils.error_handling import abort
from ..utils.http_client import AITBCHTTPClient, NetworkError


def _coordinator_base_url(ctx, coordinator_url: str | None = None) -> str:
    """Return the coordinator base URL without a trailing /v1 path."""
    config = get_config()
    url = coordinator_url or ctx.obj.get("url") or config.coordinator_api_url or os.getenv("COORDINATOR_API_URL", "")
    if not url:
        return ""
    url = url.rstrip("/")
    if url.endswith("/v1"):
        url = url[:-3]
    return url


def _auth_headers(ctx) -> dict[str, str] | None:
    """Return Authorization header from --api-key."""
    token = ctx.obj.get("api_key")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return None


def _load_json_or_file(value: str) -> Any:
    """Load JSON from a string or from a file path."""
    value = value.strip()
    if value.startswith("{") or value.startswith("["):
        return json.loads(value)
    if value.startswith("@"):
        path = Path(value[1:])
    else:
        path = Path(value)
    if path.is_file():
        return json.loads(path.read_text())
    # Fallback to base64-decoded JSON (some quote fields are base64 blobs).
    try:
        decoded = base64.b64decode(value)
        return json.loads(decoded)
    except (ValueError, json.JSONDecodeError):
        pass
    raise ValueError(f"Could not parse JSON from {value}")


@click.group(
    epilog="""Examples:

  aitbc zk circuits

  aitbc zk health"""
)
def zk():
    """Manage zero-knowledge proof circuits, verify proofs, and check service health."""
    pass


@zk.command(
    epilog="""Examples:

  aitbc zk circuits

  aitbc zk circuits --coordinator-url http://localhost:8203"""
)
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def circuits(ctx, coordinator_url: str | None, format: str):
    """List available zero-knowledge circuits and their verification status."""
    get_config()
    try:
        coord_url = _coordinator_base_url(ctx, coordinator_url)
        if not coord_url:
            abort(ctx, "Coordinator URL not configured")

        headers = _auth_headers(ctx)
        http_client = AITBCHTTPClient(base_url=coord_url, timeout=30, headers=headers)
        result = http_client.get("/v1/zk/info")
        output(result, ctx.obj.get("output_format", format), title="ZK Circuits")
    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error listing ZK circuits: {e}", from_exception=e)


@zk.command(
    epilog="""Examples:

  aitbc zk verify --job-id job-123

  aitbc zk verify --proof '{"a":"b"}' --public-signals '{"x":1}'"""
)
@click.option("--job-id", help="Job ID whose receipt proof should be re-verified")
@click.option("--proof", help="Proof JSON, @file, or base64 string")
@click.option("--public-signals", help="Public signals JSON, @file, or base64 string")
@click.option("--circuit", default="receipt_public", help="Circuit name to verify against")
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def verify(
    ctx,
    job_id: str | None,
    proof: str | None,
    public_signals: str | None,
    circuit: str,
    coordinator_url: str | None,
    format: str,
):
    """Verify a zero-knowledge proof against a circuit and public signals."""
    get_config()
    try:
        coord_url = _coordinator_base_url(ctx, coordinator_url)
        if not coord_url:
            abort(ctx, "Coordinator URL not configured")

        if not job_id and not (proof and public_signals):
            abort(ctx, "Either --job-id or both --proof and --public-signals are required")

        headers = _auth_headers(ctx)
        http_client = AITBCHTTPClient(base_url=coord_url, timeout=60, headers=headers)

        if job_id:
            receipt = http_client.get(f"/v1/jobs/{job_id}/result")
            if not receipt:
                abort(ctx, f"No receipt found for job {job_id}")
            proof_data = receipt.get("receipt", {}).get("zk_proof")
            if not proof_data:
                abort(ctx, f"No ZK proof in receipt for job {job_id}")
            proof = proof_data.get("proof")
            public_signals = proof_data.get("public_signals")
            circuit = proof_data.get("circuit", circuit)
        else:
            proof = _load_json_or_file(proof)
            public_signals = _load_json_or_file(public_signals)

        result = http_client.post(
            "/v1/zk/verify",
            json={
                "proof": proof,
                "public_signals": public_signals,
                "circuit_name": circuit,
            },
        )
        output(result, ctx.obj.get("output_format", format), title="ZK Proof Verification")
    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error verifying ZK proof: {e}", from_exception=e)


@zk.command(
    epilog="""Examples:

  aitbc zk health

  aitbc zk health --coordinator-url http://localhost:8203"""
)
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def health(ctx, coordinator_url: str | None, format: str):
    """Check the zero-knowledge proof service health."""
    get_config()
    try:
        coord_url = _coordinator_base_url(ctx, coordinator_url)
        if not coord_url:
            abort(ctx, "Coordinator URL not configured")

        headers = _auth_headers(ctx)
        http_client = AITBCHTTPClient(base_url=coord_url, timeout=30, headers=headers)
        result = http_client.get("/v1/zk/health")
        output(result, ctx.obj.get("output_format", format), title="ZK Service Health")
    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error checking ZK health: {e}", from_exception=e)
