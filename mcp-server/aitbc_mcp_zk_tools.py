"""Typed MCP tools for the AITBC coordinator ZK proof service."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from mcp.types import ToolAnnotations
from pydantic import Field

from aitbc_mcp_server import (
    _host_for_role,
    _json,
    _run_http,
    mcp,
)


def _call_zk(
    role: str | None,
    host: str | None,
    path: str,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    timeout: int = 60,
) -> dict[str, Any]:
    """Call a coordinator ZK endpoint using the remote miner API key."""
    target = _host_for_role(role, host)
    return _run_http(
        target,
        "coordinator-api",
        path,
        method,
        None,
        body,
        timeout,
        auth="miner",
        auth_env="/etc/aitbc/aitbc-coordinator-api.env",
    )


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_zk_health(
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Check the ZK proof service health and list available circuits."""
    return _json(_call_zk(role, host, "v1/zk/health"))


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_zk_info(
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get ZK circuit information and setup parameters."""
    return _json(_call_zk(role, host, "v1/zk/info"))


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def generate_zk_proof(
    circuit_name: Annotated[
        str,
        Field(description="Circuit to generate a proof for (e.g. 'receipt_model', 'receipt_public')."),
    ],
    inputs: Annotated[
        dict[str, Any],
        Field(description="Public/known circuit inputs."),
    ],
    private_inputs: Annotated[
        dict[str, Any] | None,
        Field(description="Private circuit inputs, if any."),
    ] = None,
    timeout: Annotated[
        int,
        Field(description="Timeout in seconds; proof generation can take 60-180s.", ge=30, le=300),
    ] = 180,
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Generate a Groth16 ZK proof for the given circuit and inputs."""
    body = {
        "circuit_name": circuit_name,
        "inputs": inputs,
    }
    if private_inputs:
        body["private_inputs"] = private_inputs
    return _json(_call_zk(role, host, "v1/zk/generate", method="POST", body=body, timeout=timeout))


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def verify_zk_proof(
    proof: Annotated[
        dict[str, Any],
        Field(description="Groth16 proof object (pi_a, pi_b, pi_c, protocol, curve)."),
    ],
    public_signals: Annotated[
        list[str],
        Field(description="Public signals used when generating the proof."),
    ],
    circuit_name: Annotated[
        str | None,
        Field(description="Circuit to verify against (uses proof metadata if omitted)."),
    ] = None,
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Verify a ZK proof against the coordinator's verification key."""
    body: dict[str, Any] = {
        "proof": proof,
        "public_signals": public_signals,
    }
    if circuit_name:
        body["circuit_name"] = circuit_name
    return _json(_call_zk(role, host, "v1/zk/verify", method="POST", body=body, timeout=120))


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def verify_zk_job_receipt(
    job_id: Annotated[
        str,
        Field(description="Completed AI job ID whose stored ZK receipt proof should be verified."),
    ],
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Verify the ZK receipt proof attached to a completed AI job."""
    return _json(
        _call_zk(
            role,
            host,
            "v1/zk/receipt/verify",
            method="POST",
            body={"job_id": job_id},
            timeout=120,
        )
    )
