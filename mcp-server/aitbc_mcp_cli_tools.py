"""Additional typed AITBC CLI wrappers for the MCP server.

This module is imported by ``aitbc_mcp_server.py`` after the core helpers are
defined.  It adds read-only and mutating MCP tools that map directly to common
``aitbc`` CLI subcommands for exchange, island, market, ipfs and wallet
operations.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal

from mcp.types import ToolAnnotations
from pydantic import Field

from aitbc_mcp_server import (
    _aitbc_cli_read_tool,
    _build_aitbc_cli_command,
    _host_for_role,
    _json,
    _require_confirm,
    _run_aitbc_cli,
    mcp,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _run_aitbc_cli_write(
    role: str | None,
    host: str | None,
    group: str,
    subcommand: str | None,
    args: list[str] | None,
    options: dict[str, str | None],
    dry_run: bool,
    confirm: bool,
    timeout: int = 120,
) -> str:
    """Build and run a mutating aitbc CLI command, honouring dry_run/confirm."""
    target = _host_for_role(role, host)
    command = _build_aitbc_cli_command(group, subcommand, args, options, "json")
    guard = _require_confirm(dry_run, confirm, command)
    if guard is not None:
        return _json(guard)
    return _json(_run_aitbc_cli(target, group, subcommand, args, options, "json", timeout))


# ---------------------------------------------------------------------------
# Exchange (island)
# ---------------------------------------------------------------------------


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_exchange_orderbook(
    pair: Annotated[str, Field(description="Trading pair, e.g. 'AIT/ETH'.")] = "AIT/ETH",
    limit: Annotated[int | None, Field(description="Order book depth.", ge=1)] = None,
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """View the island exchange order book for a trading pair."""
    options: dict[str, str | None] = {}
    if limit is not None:
        options["limit"] = str(limit)
    return _aitbc_cli_read_tool(role, host, "exchange-island", "orderbook", args=[pair], options=options)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_exchange_rates(
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """View current island exchange rates for AIT/ETH."""
    return _aitbc_cli_read_tool(role, host, "exchange-island", "rates")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_exchange_orders(
    user: Annotated[str | None, Field(description="Filter by user address.")] = None,
    status: Annotated[
        str | None,
        Field(description="Filter by status (open, filled, partially_filled, cancelled)."),
    ] = None,
    pair: Annotated[str | None, Field(description="Filter by trading pair.")] = None,
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """List island exchange orders."""
    options: dict[str, str | None] = {}
    if user is not None:
        options["user"] = user
    if status is not None:
        options["status"] = status
    if pair is not None:
        options["pair"] = pair
    return _aitbc_cli_read_tool(role, host, "exchange-island", "orders", options=options)


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def buy_ait_exchange(
    amount: Annotated[Decimal, Field(description="Amount of AIT to buy.", gt=0)],
    max_price: Annotated[
        Decimal,
        Field(description="Maximum price to pay per AIT in ETH.", gt=0),
    ],
    wallet: Annotated[str, Field(description="Wallet name or file path for signing.")] = "genesis",
    dry_run: Annotated[bool, Field(description="Show the command without executing it.")] = True,
    confirm: Annotated[bool, Field(description="Confirm the destructive action.")] = False,
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to run the command on."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Buy AIT with ETH on the island exchange."""
    options: dict[str, str | None] = {
        "max-price": str(max_price),
        "wallet": wallet,
    }
    return _run_aitbc_cli_write(role, host, "exchange-island", "buy", [str(amount), "ETH"], options, dry_run, confirm)


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def sell_ait_exchange(
    amount: Annotated[Decimal, Field(description="Amount of AIT to sell.", gt=0)],
    min_price: Annotated[
        Decimal,
        Field(description="Minimum price to accept per AIT in ETH.", gt=0),
    ],
    wallet: Annotated[str, Field(description="Wallet name or file path for signing.")] = "genesis",
    dry_run: Annotated[bool, Field(description="Show the command without executing it.")] = True,
    confirm: Annotated[bool, Field(description="Confirm the destructive action.")] = False,
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to run the command on."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Sell AIT for ETH on the island exchange."""
    options: dict[str, str | None] = {
        "min-price": str(min_price),
        "wallet": wallet,
    }
    return _run_aitbc_cli_write(role, host, "exchange-island", "sell", [str(amount), "ETH"], options, dry_run, confirm)


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def cancel_exchange_order(
    order_id: Annotated[str, Field(description="Exchange order ID to cancel.")],
    wallet: Annotated[str, Field(description="Wallet name or file path for signing.")] = "genesis",
    dry_run: Annotated[bool, Field(description="Show the command without executing it.")] = True,
    confirm: Annotated[bool, Field(description="Confirm the destructive action.")] = False,
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to run the command on."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Cancel an island exchange order."""
    options: dict[str, str | None] = {"wallet": wallet}
    return _run_aitbc_cli_write(role, host, "exchange-island", "cancel", [order_id], options, dry_run, confirm)


# ---------------------------------------------------------------------------
# Islands / node membership
# ---------------------------------------------------------------------------


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def create_island(
    island_id: Annotated[str | None, Field(description="Island ID (generates one if omitted.")] = None,
    island_name: Annotated[str | None, Field(description="Human-readable island name.")] = None,
    chain_id: Annotated[str | None, Field(description="Chain ID for the island.")] = None,
    dry_run: Annotated[bool, Field(description="Show the command without executing it.")] = True,
    confirm: Annotated[bool, Field(description="Confirm the destructive action.")] = False,
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to run the command on."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Create a new AITBC island on the node."""
    options: dict[str, str | None] = {}
    if island_id is not None:
        options["island-id"] = island_id
    if island_name is not None:
        options["island-name"] = island_name
    if chain_id is not None:
        options["chain-id"] = chain_id
    return _run_aitbc_cli_write(role, host, "node", "island-create", None, options, dry_run, confirm)


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def join_island(
    island_id: Annotated[str, Field(description="Island ID to join.")],
    island_name: Annotated[str, Field(description="Human-readable island name.")],
    chain_id: Annotated[str, Field(description="Chain ID for the island.")],
    hub: Annotated[str | None, Field(description="Hub domain name to connect to.")] = None,
    is_hub: Annotated[bool, Field(description="Register this node as the island hub.")] = False,
    rpc_url: Annotated[str | None, Field(description="RPC base URL for the join request.")] = None,
    dry_run: Annotated[bool, Field(description="Show the command without executing it.")] = True,
    confirm: Annotated[bool, Field(description="Confirm the destructive action.")] = False,
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to run the command on."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Join an existing AITBC island."""
    options: dict[str, str | None] = {}
    if hub is not None:
        options["hub"] = hub
    if is_hub:
        options["is-hub"] = None
    if rpc_url is not None:
        options["rpc-url"] = rpc_url
    return _run_aitbc_cli_write(
        role, host, "node", "island-join", [island_id, island_name, chain_id], options, dry_run, confirm
    )


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def leave_island(
    island_id: Annotated[str, Field(description="Island ID to leave.")],
    dry_run: Annotated[bool, Field(description="Show the command without executing it.")] = True,
    confirm: Annotated[bool, Field(description="Confirm the destructive action.")] = False,
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to run the command on."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Leave an AITBC island."""
    return _run_aitbc_cli_write(role, host, "node", "island-leave", [island_id], {}, dry_run, confirm)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def list_node_islands(
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """List all known islands from a node's island manager."""
    return _aitbc_cli_read_tool(role, host, "node", "island-list-islands")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_node_island_info(
    island_id: Annotated[str, Field(description="Island ID.")],
    node_url: Annotated[str | None, Field(description="Local node RPC URL override.")] = None,
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get island information from a node's island manager."""
    options: dict[str, str | None] = {}
    if node_url is not None:
        options["node-url"] = node_url
    return _aitbc_cli_read_tool(role, host, "node", "island-island-info", args=[island_id], options=options)


# ---------------------------------------------------------------------------
# Marketplace (local CLI)
# ---------------------------------------------------------------------------


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def create_market_offer(
    service_type: Annotated[
        Literal["ollama", "whisper", "ffmpeg", "ipfs"],
        Field(description="Service type for the offer."),
    ],
    model: Annotated[str, Field(description="Model or variant, e.g. 'llama3.2:3b' or 'ipfs-host'.")],
    price: Annotated[Decimal, Field(description="Offer price in AIT.", ge=0)],
    unit: Annotated[
        Literal[
            "per_1k_tokens",
            "per_audio_min",
            "per_gb",
            "per_processing_hour",
            "per_day",
        ],
        Field(description="Pricing unit."),
    ] = "per_day",
    description: Annotated[str | None, Field(description="Offer description.")] = None,
    context_window: Annotated[int | None, Field(description="Context window for ollama offers.", ge=1)] = None,
    gpu_name: Annotated[str | None, Field(description="GPU name (auto-detected if omitted).")] = None,
    gpu_device: Annotated[str | None, Field(description="GPU device ID for multi-GPU servers.")] = None,
    wallet: Annotated[str, Field(description="Wallet name for offer payments/signing.")] = "genesis",
    dry_run: Annotated[bool, Field(description="Show the command without executing it.")] = True,
    confirm: Annotated[bool, Field(description="Confirm the destructive action.")] = False,
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to run the command on."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """List a hardware/software marketplace offer."""
    options: dict[str, str | None] = {
        "unit": unit,
        "wallet": wallet,
    }
    if description is not None:
        options["description"] = description
    if context_window is not None:
        options["context-window"] = str(context_window)
    if gpu_name is not None:
        options["gpu-name"] = gpu_name
    if gpu_device is not None:
        options["gpu-device"] = gpu_device
    return _run_aitbc_cli_write(role, host, "market", "offer", [service_type, model, str(price)], options, dry_run, confirm)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def list_market_offers_cli(
    provider: Annotated[str | None, Field(description="Filter by provider address.")] = None,
    status: Annotated[str | None, Field(description="Filter by status (active, inactive).")] = None,
    service_type: Annotated[str | None, Field(description="Filter by service type.")] = None,
    sort: Annotated[
        Literal["reputation", "price", "availability", "default"],
        Field(description="Sort order."),
    ] = "default",
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """List blockchain marketplace offers and bids (local CLI view)."""
    options: dict[str, str | None] = {"sort": sort}
    if provider is not None:
        options["provider"] = provider
    if status is not None:
        options["status"] = status
    if service_type is not None:
        options["service-type"] = service_type
    return _aitbc_cli_read_tool(role, host, "market", "list", options=options)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def list_my_market_offers(
    sort: Annotated[
        Literal["reputation", "price", "availability", "default"],
        Field(description="Sort order."),
    ] = "default",
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """List software offers published by the local wallet/node."""
    return _aitbc_cli_read_tool(role, host, "market", "offers", options={"sort": sort})


# ---------------------------------------------------------------------------
# IPFS
# ---------------------------------------------------------------------------


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def upload_ipfs(
    file: Annotated[str, Field(description="Remote file path to upload.")],
    name: Annotated[str | None, Field(description="Human-readable name for the upload.")] = None,
    pin: Annotated[bool, Field(description="Pin the uploaded content.")] = True,
    dry_run: Annotated[bool, Field(description="Show the command without executing it.")] = True,
    confirm: Annotated[bool, Field(description="Confirm the destructive action.")] = False,
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to run the command on."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Upload a remote file to IPFS and return its CID."""
    options: dict[str, str | None] = {"file": file}
    if name is not None:
        options["name"] = name
    if pin:
        options["pin"] = None
    return _run_aitbc_cli_write(role, host, "ipfs", "upload", None, options, dry_run, confirm)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def download_ipfs(
    cid: Annotated[str, Field(description="CID to download.")],
    output: Annotated[str | None, Field(description="Write retrieved content to this remote path.")] = None,
    wait: Annotated[bool, Field(description="Wait for the CID to become available on the network.")] = False,
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Download IPFS content by CID."""
    options: dict[str, str | None] = {}
    if output is not None:
        options["output"] = output
    if wait:
        options["wait"] = None
    return _aitbc_cli_read_tool(role, host, "ipfs", "download", args=[cid], options=options, timeout=120)


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def pin_ipfs(
    cid: Annotated[str, Field(description="CID to pin locally.")],
    dry_run: Annotated[bool, Field(description="Show the command without executing it.")] = True,
    confirm: Annotated[bool, Field(description="Confirm the destructive action.")] = False,
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to run the command on."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Pin a CID on the local IPFS daemon or filesystem index."""
    return _run_aitbc_cli_write(role, host, "ipfs", "pin", [cid], {}, dry_run, confirm)


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def unpin_ipfs(
    rental_id: Annotated[str, Field(description="Rental ID to unpin.")],
    refund: Annotated[bool, Field(description="Refund the escrow for this rental.")] = False,
    reason: Annotated[str, Field(description="Reason for refund.")] = "buyer_requested",
    dry_run: Annotated[bool, Field(description="Show the command without executing it.")] = True,
    confirm: Annotated[bool, Field(description="Confirm the destructive action.")] = False,
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to run the command on."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Unpin a CID and end an IPFS rental."""
    options: dict[str, str | None] = {"reason": reason}
    if refund:
        options["refund"] = None
    return _run_aitbc_cli_write(role, host, "ipfs", "unpin", [rental_id], options, dry_run, confirm)


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def host_ipfs(
    offer_id_or_plugin_id: Annotated[str, Field(description="IPFS marketplace offer or plugin ID.")],
    cid_or_file: Annotated[str, Field(description="CID or file path to host.")],
    days: Annotated[int, Field(description="Rental duration in days.", ge=1)] = 1,
    wallet: Annotated[str, Field(description="Wallet to pay for the rental.")] = "genesis",
    pin: Annotated[bool, Field(description="Pin the CID after paying the rental.")] = True,
    dry_run: Annotated[bool, Field(description="Show the command without executing it.")] = True,
    confirm: Annotated[bool, Field(description="Confirm the destructive action.")] = False,
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to run the command on."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Rent IPFS hosting for a CID or file through a marketplace offer."""
    options: dict[str, str | None] = {
        "days": str(days),
        "wallet": wallet,
    }
    if pin:
        options["pin"] = None
    return _run_aitbc_cli_write(
        role,
        host,
        "ipfs",
        "host",
        [offer_id_or_plugin_id, cid_or_file],
        options,
        dry_run,
        confirm,
    )


# ---------------------------------------------------------------------------
# Wallet
# ---------------------------------------------------------------------------


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def create_wallet(
    name: Annotated[str, Field(description="Wallet name.")],
    wallet_type: Annotated[
        Literal["hd", "simple"],
        Field(description="Wallet type."),
    ] = "simple",
    encrypt: Annotated[bool, Field(description="Encrypt the wallet.")] = True,
    dry_run: Annotated[bool, Field(description="Show the command without executing it.")] = True,
    confirm: Annotated[bool, Field(description="Confirm the destructive action.")] = False,
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to run the command on."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Create a new file wallet on the node."""
    options: dict[str, str | None] = {"type": wallet_type}
    if not encrypt:
        options["no-encrypt"] = None
    return _run_aitbc_cli_write(role, host, "wallet", "create", [name], options, dry_run, confirm)


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def fund_wallet(
    address: Annotated[str, Field(description="Wallet address to fund.")],
    amount_ait: Annotated[str, Field(description="Amount to request from faucet in AIT.")] = "1.0",
    chain_id: Annotated[str | None, Field(description="Chain ID override.")] = None,
    dry_run: Annotated[bool, Field(description="Show the command without executing it.")] = True,
    confirm: Annotated[bool, Field(description="Confirm the destructive action.")] = False,
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to run the command on."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Fund a wallet address using the blockchain faucet."""
    options: dict[str, str | None] = {"amount-ait": amount_ait}
    if chain_id is not None:
        options["chain-id"] = chain_id
    return _run_aitbc_cli_write(role, host, "wallet", "fund", [address], options, dry_run, confirm)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_wallet_info(
    wallet_name: Annotated[str, Field(description="Wallet name.")] = "genesis",
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Show wallet information (address, balance, nonce, etc.)."""
    return _aitbc_cli_read_tool(role, host, "wallet", "info", args=[wallet_name])


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_wallet_address(
    wallet_name: Annotated[str, Field(description="Wallet name.")] = "genesis",
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Show the address for a named wallet."""
    return _aitbc_cli_read_tool(role, host, "wallet", "address", args=[wallet_name])
