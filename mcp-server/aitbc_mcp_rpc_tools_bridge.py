"""Bridge / cross-chain / ETH-AITBC bridge RPC tools.

Split from ``aitbc_mcp_rpc_tools.py`` (#1860 phase 2). Imported at the
bottom of that module, after its helpers are defined, so the
``aitbc_mcp_server`` names used here are available exactly as in the
parent module. ``_http_write_tool`` is imported back from
``aitbc_mcp_rpc_tools`` — import this module via ``aitbc_mcp_rpc_tools``
(or ``aitbc_mcp_server``), not directly.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Annotated, Any

from mcp.types import ToolAnnotations
from pydantic import Field

from aitbc_mcp_server import (
    NodeRole,
    _host_for_role,
    _http_read_tool,
    _json,
    _run_http,
    mcp,
)
from aitbc_mcp_rpc_tools import _http_write_tool


# ---------------------------------------------------------------------------
# Bridge
# ---------------------------------------------------------------------------


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_bridge_transfer_proof(
    transfer_id: Annotated[
        str,
        Field(description="Bridge transfer ID."),
    ],
    source_chain: Annotated[
        str | None,
        Field(description="Source chain ID (defaults to this node)."),
    ] = None,
    block_height: Annotated[
        int | None,
        Field(description="Block height to anchor the proof.", ge=0),
    ] = None,
    block_hash: Annotated[
        str | None,
        Field(description="Block hash to anchor the proof."),
    ] = None,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Build a Merkle proof for a locked bridge transfer."""
    params: dict[str, str] = {}
    if source_chain is not None:
        params["source_chain"] = source_chain
    if block_height is not None:
        params["block_height"] = str(block_height)
    if block_hash is not None:
        params["block_hash"] = block_hash
    return _http_read_tool(role, host, "blockchain-rpc", f"bridge/transfer/{transfer_id}/proof", params)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_bridge_balance(
    chain_id: Annotated[
        str,
        Field(description="Chain ID."),
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
    """Get bridge balance for a chain."""
    return _http_read_tool(role, host, "blockchain-rpc", f"bridge/balance/{chain_id}")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_bridge_validators(
    chain_id: Annotated[
        str,
        Field(description="Chain ID."),
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
    """Get bridge validator set for a chain."""
    return _http_read_tool(role, host, "blockchain-rpc", f"bridge/validators/{chain_id}")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_bridge_security_status(
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get bridge security status."""
    return _http_read_tool(role, host, "blockchain-rpc", "bridge/security/status")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_bridge_oracle_status(
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get bridge oracle/verification status."""
    return _http_read_tool(role, host, "blockchain-rpc", "bridge/oracle/status")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_bridge_block_header(
    chain_id: Annotated[
        str,
        Field(description="Chain ID."),
    ],
    height: Annotated[
        int,
        Field(description="Block height.", ge=0),
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
    """Get a bridge block header with finality status."""
    return _http_read_tool(role, host, "blockchain-rpc", f"bridge/block-headers/{chain_id}/{height}")


# ---------------------------------------------------------------------------
# Cross-chain
# ---------------------------------------------------------------------------


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def list_cross_chain_swaps(
    user_address: Annotated[
        str | None,
        Field(description="Filter by user address."),
    ] = None,
    status: Annotated[
        str | None,
        Field(description="Filter by status."),
    ] = None,
    limit: Annotated[
        int | None,
        Field(description="Maximum number of swaps.", ge=1),
    ] = None,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """List cross-chain swaps with optional filters."""
    params: dict[str, str] = {}
    if user_address is not None:
        params["user_address"] = user_address
    if status is not None:
        params["status"] = status
    if limit is not None:
        params["limit"] = str(limit)
    return _http_read_tool(role, host, "blockchain-rpc", "cross-chain/swaps", params)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_cross_chain_swap(
    swap_id: Annotated[
        str,
        Field(description="Swap ID."),
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
    """Get a cross-chain swap by ID."""
    return _http_read_tool(role, host, "blockchain-rpc", f"cross-chain/swap/{swap_id}")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_cross_chain_bridge(
    bridge_id: Annotated[
        str,
        Field(description="Bridge transaction ID."),
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
    """Get cross-chain bridge transaction status."""
    return _http_read_tool(role, host, "blockchain-rpc", f"cross-chain/bridge/{bridge_id}")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_cross_chain_stats(
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Show cross-chain trading statistics."""
    return _http_read_tool(role, host, "blockchain-rpc", "cross-chain/stats")


# ---------------------------------------------------------------------------
# ETH-AITBC bridge (wallet service)
# ---------------------------------------------------------------------------


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_eth_bridge_status(
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get the active ETH-AITBC bridge status and deposit address."""
    return _http_read_tool(role, host, "wallet", "v1/bridge/status")


# Safe fields to expose for bridge preflight checks.  Anything outside this
# allowlist (in particular ``rpc_url``) is withheld so that bridge status
# queries do not leak credentials into the MCP conversation.
_BRIDGE_STATUS_SAFE_KEYS = {
    "status",
    "message",
    "enabled",
    "ready",
    "network",
    "deposit_address",
    "wallet_address",
    "fee_rate",
    "min_deposit",
    "minimum_deposit",
    "poll_interval",
    "auto_poll",
}


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_eth_bridge_status_redacted(
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get the ETH-AITBC bridge status with RPC credentials redacted.

    Returns a safe subset of the bridge status needed for preflight checks:
    status, enabled/ready, network, deposit address, minimum deposit, fee rate,
    and polling state.  The full ``rpc_url`` and any other credential-bearing
    fields are omitted.
    """
    target = _host_for_role(role, host)
    result = _run_http(target, "wallet", "v1/bridge/status", "GET", None, None, 30)

    if not isinstance(result, dict) or result.get("returncode") != 0:
        error: dict[str, Any] = {
            "error": "Bridge status query failed",
            "returncode": result.get("returncode") if isinstance(result, dict) else None,
        }
        return _json(error)

    raw = result.get("json")
    if raw is None and isinstance(result.get("stdout"), str):
        try:
            raw = json.loads(result["stdout"])
        except json.JSONDecodeError:
            raw = None  # falls through to the invalid-response error below

    if not isinstance(raw, dict):
        return _json(
            {
                "error": "Invalid bridge status response",
                "returncode": result.get("returncode"),
            }
        )

    redacted = {k: v for k, v in raw.items() if k in _BRIDGE_STATUS_SAFE_KEYS}
    redacted.pop("rpc_url", None)
    return _json(redacted)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_eth_bridge_deposit_instructions(
    eth_amount: Annotated[
        Decimal,
        Field(description="Amount of ETH to deposit.", gt=0),
    ],
    ait_address: Annotated[
        str,
        Field(description="AIT address that will receive minted AIT."),
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
    """Get ETH-AITBC bridge deposit instructions and AIT estimate."""
    body = {"eth_amount": str(eth_amount), "ait_address": ait_address}
    return _json(_run_http(_host_for_role(role, host), "wallet", "v1/bridge/deposit", "POST", None, body))


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def eth_bridge_withdraw_estimate(
    ait_amount: Annotated[
        Decimal,
        Field(description="Amount of AIT to withdraw.", gt=0),
    ],
    eth_address: Annotated[
        str,
        Field(description="Destination Ethereum address."),
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
    """Estimate ETH payout for an AIT->ETH withdrawal."""
    body = {"ait_amount": str(ait_amount), "eth_address": eth_address}
    return _json(_run_http(_host_for_role(role, host), "wallet", "v1/bridge/withdraw/estimate", "POST", None, body))


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def eth_bridge_withdraw_build(
    ait_amount: Annotated[
        Decimal,
        Field(description="Amount of AIT to withdraw.", gt=0),
    ],
    eth_address: Annotated[
        str,
        Field(description="Destination Ethereum address."),
    ],
    from_address: Annotated[
        str,
        Field(description="Source AIT address."),
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
    """Build an unsigned BRIDGE_WITHDRAW transaction for AIT->ETH."""
    body = {
        "ait_amount": str(ait_amount),
        "eth_address": eth_address,
        "from_address": from_address,
    }
    return _json(_run_http(_host_for_role(role, host), "wallet", "v1/bridge/withdraw/build", "POST", None, body))


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def eth_bridge_withdraw_submit(
    signed_tx: Annotated[
        dict[str, Any],
        Field(description="Signed BRIDGE_WITHDRAW transaction object."),
    ],
    dry_run: Annotated[
        bool,
        Field(description="Show the command without executing it."),
    ] = True,
    confirm: Annotated[
        bool,
        Field(description="Confirm execution of the destructive call."),
    ] = False,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Submit a signed BRIDGE_WITHDRAW transaction to the AITBC chain."""
    return _http_write_tool(role, host, "wallet", "v1/bridge/withdraw/submit", {"signed_tx": signed_tx}, dry_run, confirm)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_eth_bridge_withdrawal(
    ait_tx_hash: Annotated[
        str,
        Field(description="AIT withdrawal transaction hash."),
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
    """Get the status of an AIT->ETH withdrawal."""
    return _http_read_tool(role, host, "wallet", f"v1/bridge/withdraw/{ait_tx_hash}")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def list_eth_bridge_withdrawals(
    status: Annotated[
        str | None,
        Field(description="Filter by status (pending, completed, refunded, failed)."),
    ] = None,
    limit: Annotated[
        int,
        Field(description="Maximum number of withdrawals to return.", gt=0),
    ] = 50,
    offset: Annotated[
        int,
        Field(description="Number of withdrawals to skip.", ge=0),
    ] = 0,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """List AIT->ETH withdrawals tracked by the bridge wallet."""
    params: dict[str, str] = {"limit": str(limit), "offset": str(offset)}
    if status:
        params["status"] = status
    return _http_read_tool(role, host, "wallet", "v1/bridge/withdrawals", params)
