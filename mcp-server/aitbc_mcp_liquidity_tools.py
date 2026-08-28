"""Typed MCP tools for the AITBC on-chain liquidity pools."""

from __future__ import annotations

from typing import Annotated, Any

from mcp.types import ToolAnnotations
from pydantic import Field

from aitbc_mcp_server import (
    NodeRole,
    _host_for_role,
    _json,
    _run_http,
    mcp,
)

from aitbc.utils.units import ait_to_units


def _call_liquidity(
    role: str | None,
    host: str | None,
    path: str,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    """Call a blockchain-rpc liquidity endpoint."""
    target = _host_for_role(role, host)
    return _run_http(
        target,
        "blockchain-rpc",
        path,
        method,
        None,
        body,
        timeout,
        auth="none",
    )


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def list_liquidity_pools(
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """List all on-chain liquidity pools."""
    return _json(_call_liquidity(role, host, "liquidity/pools"))


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_liquidity_pool(
    pool_id: Annotated[
        str,
        Field(description="Pool identifier, e.g. 'main'."),
    ] = "main",
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get the state of a single on-chain liquidity pool."""
    return _json(_call_liquidity(role, host, f"liquidity/pools/{pool_id}"))


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_liquidity_stakes(
    address: Annotated[
        str,
        Field(description="Wallet address to query stakes for."),
    ],
    pool_id: Annotated[
        str | None,
        Field(description="Filter stakes by pool identifier."),
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
    """List on-chain liquidity stakes for an address."""
    params: dict[str, str] = {}
    if pool_id:
        params["pool_id"] = pool_id
    # _run_http can take query params, but _call_liquidity currently passes None.
    # Build the path with query string manually to keep the helper simple.
    path = f"liquidity/stakes/{address}"
    if params:
        from urllib.parse import urlencode

        path += "?" + urlencode(params)
    return _json(_call_liquidity(role, host, path))


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def build_liquidity_deposit(
    address: Annotated[
        str,
        Field(description="Sender wallet address."),
    ],
    amount_ait: Annotated[
        str,
        Field(description="Amount to stake in AIT (e.g. '10')."),
    ],
    pool_id: Annotated[
        str,
        Field(description="Pool identifier to deposit into."),
    ] = "main",
    lock_days: Annotated[
        int,
        Field(description="Lock period in days (higher APY).", ge=0),
    ] = 0,
    fee_ait: Annotated[
        str,
        Field(description="Transaction fee in AIT (e.g. '0.01')."),
    ] = "0.01",
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Build an unsigned on-chain liquidity deposit transaction."""
    body = {
        "address": address,
        "amount": ait_to_units(amount_ait),
        "pool_id": pool_id,
        "lock_days": lock_days,
        "fee": ait_to_units(fee_ait),
    }
    return _json(_call_liquidity(role, host, "liquidity/build-deposit", method="POST", body=body))


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def build_liquidity_withdraw(
    address: Annotated[
        str,
        Field(description="Sender wallet address."),
    ],
    stake_id: Annotated[
        str,
        Field(description="Stake identifier to withdraw."),
    ],
    pool_id: Annotated[
        str,
        Field(description="Pool the stake belongs to."),
    ] = "main",
    fee_ait: Annotated[
        str,
        Field(description="Transaction fee in AIT (e.g. '0.01')."),
    ] = "0.01",
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Build an unsigned on-chain liquidity withdraw transaction."""
    body = {
        "address": address,
        "stake_id": stake_id,
        "pool_id": pool_id,
        "fee": ait_to_units(fee_ait),
    }
    return _json(_call_liquidity(role, host, "liquidity/build-withdraw", method="POST", body=body))


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def build_liquidity_claim(
    address: Annotated[
        str,
        Field(description="Sender wallet address."),
    ],
    stake_id: Annotated[
        str,
        Field(description="Stake identifier to claim rewards for."),
    ],
    pool_id: Annotated[
        str,
        Field(description="Pool the stake belongs to."),
    ] = "main",
    fee_ait: Annotated[
        str,
        Field(description="Transaction fee in AIT (e.g. '0.01')."),
    ] = "0.01",
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Build an unsigned on-chain liquidity claim rewards transaction."""
    body = {
        "address": address,
        "stake_id": stake_id,
        "pool_id": pool_id,
        "fee": ait_to_units(fee_ait),
    }
    return _json(_call_liquidity(role, host, "liquidity/build-claim", method="POST", body=body))
