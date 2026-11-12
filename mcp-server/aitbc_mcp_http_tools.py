"""HTTP/RPC pivot MCP tools (split from aitbc_mcp_server, #1867)."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from mcp.types import ToolAnnotations
from pydantic import Field


from aitbc_mcp_server import (
    HTTP_SERVICE_NAMES,
    NodeRole,
    _build_dry_run,
    _execution_context,
    _host_for_role,
    _http_dry_run_command,
    _http_read_tool,
    _json,
    _normalize_http_service_name,
    _run_http,
    mcp,
)

# ---------------------------------------------------------------------------
# HTTP / RPC pivot tools
# ---------------------------------------------------------------------------


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def call_aitbc_http(
    service: Annotated[
        str,
        Field(description="AITBC service name (e.g. 'blockchain-rpc', 'coordinator-api', 'market')."),
    ],
    path: Annotated[
        str,
        Field(description="URL path after the service base, e.g. 'info', 'account/0x...', 'v1/jobs'."),
    ],
    method: Annotated[
        Literal["GET", "POST", "PUT", "PATCH", "DELETE"],
        Field(description="HTTP method."),
    ] = "GET",
    params: Annotated[
        dict[str, str] | None,
        Field(description="Query parameters as key/value pairs."),
    ] = None,
    body: Annotated[
        dict[str, Any] | None,
        Field(description="JSON body for POST/PUT/PATCH requests."),
    ] = None,
    auth: Annotated[
        Literal["none", "miner", "rpc", "trading"],
        Field(
            description="Authentication mode. 'miner' sources the first MINER_API_KEYS from the remote service env file and sends it as X-Api-Key without exposing the value. 'rpc' uses the node's configured blockchain RPC API key (X-API-Key); 'trading' uses the trading API key (X-Trading-Api-Key)."
        ),
    ] = "none",
    auth_env: Annotated[
        str,
        Field(description="Remote env file to source when auth='miner'."),
    ] = "/etc/aitbc/aitbc-coordinator-api.env",
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
    dry_run: Annotated[
        bool,
        Field(description="Show the aitbc CLI command without executing it."),
    ] = False,
    confirm: Annotated[
        bool,
        Field(description="Confirm a mutating HTTP call."),
    ] = False,
    expect_status: Annotated[
        list[int] | None,
        Field(
            description="HTTP status codes to treat as an expected answer (e.g. [404]); the call returns {'status', 'detail'} instead of an error."
        ),
    ] = None,
    timeout: Annotated[
        int,
        Field(description="Timeout in seconds.", ge=5, le=300),
    ] = 30,
) -> str:
    """Call an AITBC HTTP/RPC endpoint on a selected node.

    This is the generic HTTP pivot. GET calls can run directly; mutating methods
    (POST, PUT, PATCH, DELETE) require ``dry_run=false`` and ``confirm=true``.

    Use ``auth='miner'`` to reach endpoints (such as ``/v1/zk/*``) that require
    an API key without passing the key through the tool arguments. Use
    ``auth='rpc'`` for blockchain-RPC-keyed routes such as ``escrow/{job_id}``,
    and ``auth='trading'`` for the trading service's X-Trading-Api-Key gate.

    Examples:
      - service="blockchain-rpc", path="info"
      - service="blockchain-rpc", path="account/0x..."
      - service="blockchain-rpc", path="blocks-range", params={"limit": "3"}
      - service="coordinator-api", path="v1/jobs", params={"limit": "10"}, auth="miner"

    Service names may be logical ("blockchain-rpc") or systemd-style
    ("aitbc-blockchain-rpc"); both are accepted.
    """
    target = _host_for_role(role, host)
    service = _normalize_http_service_name(service)
    if service not in HTTP_SERVICE_NAMES:
        return _json(
            {
                "error": f"unknown HTTP service: {service}",
                "known_services": sorted(HTTP_SERVICE_NAMES),
            }
        )

    if dry_run:
        command = _http_dry_run_command(service, path, method, params, body, auth, expect_status)
        return _json(_build_dry_run("Set dry_run=false to execute.", command, host=target))

    if method != "GET" and not confirm:
        return _json(
            {
                "error": "Confirmation required",
                "command": _http_dry_run_command(service, path, method, params, body, auth, expect_status),
                **_execution_context(target),
                "note": "Mutating HTTP calls require dry_run=false and confirm=true.",
            }
        )

    return _json(
        _run_http(
            target,
            service,
            path,
            method,
            params,
            body,
            timeout,
            auth,
            auth_env,
            expect_status,
        )
    )


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_blockchain_info(
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get comprehensive blockchain information (height, tx count, accounts, genesis)."""
    return _http_read_tool(role, host, "blockchain-rpc", "info")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_blockchain_head(
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get the current chain head block."""
    return _http_read_tool(role, host, "blockchain-rpc", "head")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def list_blocks(
    start: Annotated[
        int | None,
        Field(description="Start height (inclusive).", ge=0),
    ] = None,
    end: Annotated[
        int | None,
        Field(description="End height (inclusive).", ge=0),
    ] = None,
    limit: Annotated[
        int | None,
        Field(description="Return the most recent N blocks.", ge=1),
    ] = None,
    include_tx: Annotated[
        bool,
        Field(description="Include transactions in each block."),
    ] = True,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get a range of blocks by height or the most recent N blocks."""
    params: dict[str, str] = {}
    if start is not None:
        params["start"] = str(start)
    if end is not None:
        params["end"] = str(end)
    if limit is not None:
        params["limit"] = str(limit)
    params["include_tx"] = "true" if include_tx else "false"
    return _http_read_tool(role, host, "blockchain-rpc", "blocks-range", params)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_block_info(
    height: Annotated[
        int,
        Field(description="Block height to retrieve.", ge=0),
    ],
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get a single block by height."""
    return _http_read_tool(role, host, "blockchain-rpc", f"blocks/{height}")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_account_info(
    address: Annotated[
        str,
        Field(description="Account address or bech32 address."),
    ],
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get account balance and nonce from the blockchain RPC."""
    return _http_read_tool(role, host, "blockchain-rpc", f"account/{address}")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_transaction_info(
    tx_hash: Annotated[
        str,
        Field(description="Transaction hash with 0x prefix."),
    ],
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get a transaction by hash from the blockchain RPC."""
    return _http_read_tool(role, host, "blockchain-rpc", f"transaction/{tx_hash}")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_mempool(
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get pending transactions in the mempool."""
    return _http_read_tool(role, host, "blockchain-rpc", "mempool")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_network_info(
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get P2P, chain, and network configuration."""
    return _http_read_tool(role, host, "blockchain-rpc", "network-info")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_blockchain_status(
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get the blockchain node status."""
    return _http_read_tool(role, host, "blockchain-rpc", "status")


# ---------------------------------------------------------------------------
