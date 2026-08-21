"""Zero-knowledge proof commands for AITBC CLI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click

from ..config import get_config
from ..utils import output, success
from ..utils.error_handling import abort
from ..utils.http_client import AITBCHTTPClient, NetworkError, get_logger

logger = get_logger(__name__)


def _auth_headers(ctx) -> dict[str, str] | None:
    """Return Authorization header if the CLI was invoked with --api-key."""
    token = ctx.obj.get("api_key")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return None


def _looks_like_jwt(token: str) -> bool:
    """A JWT is three base64url segments separated by dots."""
    return token.startswith("ey") and token.count(".") == 2


def _coordinator_client(ctx, coordinator_url: str | None) -> AITBCHTTPClient:
    """Build an HTTP client for the coordinator API."""
    config = get_config()
    coord_url = coordinator_url or config.coordinator_api_url
    if not coord_url:
        abort(ctx, "Coordinator URL not configured")

    # Public nginx mounts the coordinator under /v1; the app itself also prefixes
    # all routes with /v1.  Strip a trailing /v1 from the configured URL so the
    # endpoints below can use the canonical /v1/... paths without doubling.
    coord_url = coord_url.rstrip("/")
    if coord_url.endswith("/v1"):
        coord_url = coord_url[:-3]

    token = ctx.obj.get("api_key")
    headers: dict[str, str] | None = _auth_headers(ctx)
    if token and not _looks_like_jwt(token):
        # Miner API keys authenticate through the X-Api-Key header.
        if headers is None:
            headers = {}
        headers["X-Api-Key"] = token

    return AITBCHTTPClient(base_url=coord_url, timeout=60, headers=headers)


@click.group()
def zk():
    """Zero-knowledge proof commands"""
    pass


@zk.command()
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def health(ctx, coordinator_url, format):
    """Check ZK proof service health"""
    try:
        client = _coordinator_client(ctx, coordinator_url)
        result = client.get("/v1/zk/health")
        output(result, ctx.obj.get("output_format", format), title="ZK Health")
    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error checking ZK health: {e}", from_exception=e)


@zk.command()
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def circuits(ctx, coordinator_url, format):
    """List available ZK circuits"""
    try:
        client = _coordinator_client(ctx, coordinator_url)
        result = client.get("/v1/zk/info")
        output(result, ctx.obj.get("output_format", format), title="ZK Circuits")
    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error listing ZK circuits: {e}", from_exception=e)


@zk.command()
@click.option("--proof-id", help="Coordinator proof/job identifier to verify")
@click.option("--job-id", "proof_id", hidden=True, help="Alias for --proof-id")
@click.option("--proof-file", type=click.Path(exists=True), help="JSON file with proof and public_signals")
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def verify(ctx, proof_id, proof_file, coordinator_url, format):
    """Verify a ZK proof by job/proof id or from a proof file"""
    try:
        client = _coordinator_client(ctx, coordinator_url)

        if proof_file:
            path = Path(proof_file)
            data = json.loads(path.read_text())
            proof = data.get("proof") or data
            public_signals = data.get("public_signals", [])
            circuit_name = data.get("circuit_name") or data.get("circuit")
        elif proof_id:
            # Fetch the job result; the receipt contains the stored ZK proof.
            result = client.get(f"/v1/jobs/{proof_id}/result")
            receipt = result.get("receipt") or {}
            zk_proof = receipt.get("zk_proof")
            if not zk_proof:
                abort(ctx, f"No ZK proof found for job {proof_id}")
            proof = zk_proof.get("proof")
            public_signals = zk_proof.get("public_signals", [])
            circuit_name = zk_proof.get("circuit") or "receipt_public"
        else:
            abort(ctx, "Either --proof-id/--job-id or --proof-file is required")

        if not proof:
            abort(ctx, "No proof data found")
        if not public_signals:
            abort(ctx, "No public signals found")

        verify_payload = {
            "proof": proof,
            "public_signals": public_signals,
            "circuit_name": circuit_name,
        }
        result = client.post("/v1/zk/verify", json=verify_payload)

        success(f"ZK proof verification result for {proof_id or proof_file}")
        output(result, ctx.obj.get("output_format", format), title="ZK Verification")

    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except json.JSONDecodeError as e:
        abort(ctx, f"Invalid JSON in proof file: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error verifying ZK proof: {e}", from_exception=e)
