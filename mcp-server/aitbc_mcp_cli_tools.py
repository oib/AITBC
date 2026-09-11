"""Additional typed AITBC CLI wrappers for the MCP server.

This module is imported by ``aitbc_mcp_server.py`` after the core helpers are
defined.  It adds read-only and mutating MCP tools that map directly to common
``aitbc`` CLI subcommands for exchange, island, market, ipfs and wallet
operations.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any, Literal

from mcp.types import ToolAnnotations
from pydantic import Field

from aitbc_mcp_server import (
    DEFAULT_WALLET_DIR,
    NodeRole,
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


def _validate_evm_address(address: str, field: str = "address") -> str:
    """Reject legacy ait1/aitbc1 prefixes and ensure a 0x + 40 hex format.

    The check is intentionally local: the MCP server runs without the aitbc
    package on its PYTHONPATH, but it can still guard against legacy spellings
    before they reach the remote CLI.
    """
    import re

    value = address.strip()
    if not value.startswith("0x"):
        raise ValueError(f"{field} must be a 0x-prefixed secp256k1 address: {address}")
    if not re.fullmatch(r"0x[0-9a-fA-F]{40}", value):
        raise ValueError(f"{field} must be 0x followed by 40 hex characters: {address}")
    return value


def _run_aitbc_cli_write(
    role: str | None,
    host: str | None,
    group: str,
    subcommand: str | list[str] | None,
    args: list[str] | None,
    options: dict[str, str | None] | None,
    dry_run: bool,
    confirm: bool,
    timeout: int = 120,
    *,
    group_options: dict[str, str | None] | None = None,
    subcommand_options: dict[str, str | None] | None = None,
    env: dict[str, str] | None = None,
) -> str:
    """Build and run a mutating aitbc CLI command, honouring dry_run/confirm."""
    target = _host_for_role(role, host)
    command = _build_aitbc_cli_command(
        group,
        subcommand,
        args,
        options,
        "json",
        group_options=group_options,
        subcommand_options=subcommand_options,
        env=env,
    )
    guard = _require_confirm(dry_run, confirm, command)
    if guard is not None:
        return _json(guard)
    return _json(
        _run_aitbc_cli(
            target,
            group,
            subcommand,
            args,
            options,
            "json",
            timeout,
            group_options=group_options,
            subcommand_options=subcommand_options,
            env=env,
        )
    )


# ---------------------------------------------------------------------------
# Exchange (island)
# ---------------------------------------------------------------------------


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_exchange_orderbook(
    pair: Annotated[str, Field(description="Trading pair, e.g. 'AIT/ETH'.")] = "AIT/ETH",
    limit: Annotated[int | None, Field(description="Order book depth.", ge=1)] = None,
    role: Annotated[
        NodeRole | None,
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
    options["pair"] = pair
    return _aitbc_cli_read_tool(role, host, "exchange-island", "orderbook", options=options)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_exchange_rates(
    role: Annotated[
        NodeRole | None,
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
        NodeRole | None,
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
        NodeRole | None,
        Field(description="Node role to run the command on."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Buy AIT with ETH on the island exchange."""
    return _run_aitbc_cli_write(
        role,
        host,
        "exchange-island",
        "buy",
        None,
        None,
        dry_run,
        confirm,
        subcommand_options={
            "ait-amount": str(amount),
            "quote-currency": "ETH",
            "max-price": str(max_price),
            "wallet": wallet,
        },
    )


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
        NodeRole | None,
        Field(description="Node role to run the command on."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Sell AIT for ETH on the island exchange."""
    return _run_aitbc_cli_write(
        role,
        host,
        "exchange-island",
        "sell",
        None,
        None,
        dry_run,
        confirm,
        subcommand_options={
            "ait-amount": str(amount),
            "quote-currency": "ETH",
            "min-price": str(min_price),
            "wallet": wallet,
        },
    )


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def cancel_exchange_order(
    order_id: Annotated[str, Field(description="Exchange order ID to cancel.")],
    wallet: Annotated[str, Field(description="Wallet name or file path for signing.")] = "genesis",
    dry_run: Annotated[bool, Field(description="Show the command without executing it.")] = True,
    confirm: Annotated[bool, Field(description="Confirm the destructive action.")] = False,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to run the command on."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Cancel an island exchange order."""
    return _run_aitbc_cli_write(
        role, host, "exchange-island", "cancel", None, None, dry_run, confirm, subcommand_options={"order-id": order_id}
    )


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
        NodeRole | None,
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
    return _run_aitbc_cli_write(role, host, "node", ["island", "create"], None, options, dry_run, confirm)


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
        NodeRole | None,
        Field(description="Node role to run the command on."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Join an existing AITBC island."""
    subcommand_options: dict[str, str | None] = {
        "island-id": island_id,
        "island-name": island_name,
        "chain-id": chain_id,
    }
    if hub is not None:
        subcommand_options["hub"] = hub
    if is_hub:
        subcommand_options["is-hub"] = None
    if rpc_url is not None:
        subcommand_options["rpc-url"] = rpc_url
    return _run_aitbc_cli_write(
        role, host, "node", ["island", "join"], None, None, dry_run, confirm, subcommand_options=subcommand_options
    )


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def leave_island(
    island_id: Annotated[str, Field(description="Island ID to leave.")],
    dry_run: Annotated[bool, Field(description="Show the command without executing it.")] = True,
    confirm: Annotated[bool, Field(description="Confirm the destructive action.")] = False,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to run the command on."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Leave an AITBC island."""
    return _run_aitbc_cli_write(
        role, host, "node", ["island", "leave"], None, None, dry_run, confirm, subcommand_options={"island-id": island_id}
    )


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def list_node_islands(
    role: Annotated[
        NodeRole | None,
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
        NodeRole | None,
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
    options["island-id"] = island_id
    return _aitbc_cli_read_tool(role, host, "node", ["island", "island-info"], options=options)


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
        NodeRole | None,
        Field(description="Node role to run the command on."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """List a hardware/software marketplace offer."""
    group_options: dict[str, str | None] = {"wallet": wallet}
    subcommand_options: dict[str, str | None] = {"unit": unit}
    if description is not None:
        subcommand_options["description"] = description
    if context_window is not None:
        subcommand_options["context-window"] = str(context_window)
    if gpu_name is not None:
        subcommand_options["gpu-name"] = gpu_name
    if gpu_device is not None:
        subcommand_options["gpu-device"] = gpu_device
    subcommand_options["service-type"] = service_type
    subcommand_options["model-or-variant"] = model
    subcommand_options["price"] = str(price)
    return _run_aitbc_cli_write(
        role,
        host,
        "market",
        "offer",
        None,
        None,
        dry_run,
        confirm,
        group_options=group_options,
        subcommand_options=subcommand_options,
        env={"AITBC_WALLET_DIR": DEFAULT_WALLET_DIR},
    )


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
        NodeRole | None,
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
        NodeRole | None,
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
        NodeRole | None,
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
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Download IPFS content by CID."""
    subcommand_options: dict[str, str | None] = {"cid": cid}
    if output is not None:
        subcommand_options["output"] = output
    if wait:
        subcommand_options["wait"] = None
    return _aitbc_cli_read_tool(role, host, "ipfs", "download", options=subcommand_options, timeout=120)


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def pin_ipfs(
    cid: Annotated[str, Field(description="CID to pin locally.")],
    dry_run: Annotated[bool, Field(description="Show the command without executing it.")] = True,
    confirm: Annotated[bool, Field(description="Confirm the destructive action.")] = False,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to run the command on."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Pin a CID on the local IPFS daemon or filesystem index."""
    return _run_aitbc_cli_write(role, host, "ipfs", "pin", None, None, dry_run, confirm, subcommand_options={"cid": cid})


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def unpin_ipfs(
    rental_id: Annotated[str, Field(description="Rental ID to unpin.")],
    refund: Annotated[bool, Field(description="Refund the escrow for this rental.")] = False,
    reason: Annotated[str, Field(description="Reason for refund.")] = "buyer_requested",
    dry_run: Annotated[bool, Field(description="Show the command without executing it.")] = True,
    confirm: Annotated[bool, Field(description="Confirm the destructive action.")] = False,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to run the command on."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Unpin a CID and end an IPFS rental."""
    subcommand_options: dict[str, str | None] = {"rental-id": rental_id, "reason": reason}
    if refund:
        subcommand_options["refund"] = None
    return _run_aitbc_cli_write(
        role, host, "ipfs", "unpin", None, None, dry_run, confirm, subcommand_options=subcommand_options
    )


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
        NodeRole | None,
        Field(description="Node role to run the command on."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Rent IPFS hosting for a CID or file through a marketplace offer."""
    subcommand_options: dict[str, str | None] = {
        "offer-id-or-plugin-id": offer_id_or_plugin_id,
        "cid-or-file": cid_or_file,
        "days": str(days),
    }
    if pin:
        subcommand_options["pin"] = None
    return _run_aitbc_cli_write(
        role,
        host,
        "market",
        "host",
        None,
        None,
        dry_run,
        confirm,
        group_options={"wallet": wallet},
        subcommand_options=subcommand_options,
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
        NodeRole | None,
        Field(description="Node role to run the command on."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Create a new file wallet on the node."""
    options: dict[str, str | None] = {"name": name, "type": wallet_type}
    if not encrypt:
        options["no-encrypt"] = None
    return _run_aitbc_cli_write(role, host, "wallet", "create", None, options, dry_run, confirm)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_wallet_info(
    wallet_name: Annotated[str, Field(description="Wallet name.")] = "genesis",
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Show wallet information (address, balance, nonce, etc.)."""
    return _aitbc_cli_read_tool(role, host, "wallet", "info", group_options={"wallet-name": wallet_name})


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_wallet_address(
    wallet_name: Annotated[str, Field(description="Wallet name.")] = "genesis",
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Show the address for a named wallet."""
    return _aitbc_cli_read_tool(role, host, "wallet", "address", group_options={"wallet-name": wallet_name})


# ---------------------------------------------------------------------------
# Market execution, ratings and shop management
# ---------------------------------------------------------------------------


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def run_market_offer(
    offer_id_or_plugin_id: Annotated[
        str,
        Field(description="Marketplace offer ID or plugin ID to run."),
    ],
    prompt: Annotated[str, Field(description="Prompt or input for the offer.")],
    wallet: Annotated[str, Field(description="Wallet name to sign payment.")] = "genesis",
    max_tokens: Annotated[int | None, Field(description="Max tokens for Ollama.", ge=1)] = None,
    stream: Annotated[bool, Field(description="Stream the Ollama response.")] = False,
    language: Annotated[str | None, Field(description="Language code for Whisper (e.g. 'en').")] = None,
    task: Annotated[
        Literal["transcribe", "translate"] | None,
        Field(description="Whisper task."),
    ] = None,
    transcript_format: Annotated[
        Literal["text", "srt", "json"] | None,
        Field(description="Whisper output format."),
    ] = None,
    media_format: Annotated[str | None, Field(description="FFmpeg output container (e.g. 'mp4').")] = None,
    codec: Annotated[str | None, Field(description="FFmpeg target codec (e.g. 'h264').")] = None,
    resolution: Annotated[str | None, Field(description="FFmpeg target resolution (e.g. '1080p').")] = None,
    bitrate: Annotated[str | None, Field(description="FFmpeg target bitrate (e.g. '5M').")] = None,
    days: Annotated[int | None, Field(description="Rental duration in days for IPFS hosting.", ge=1)] = None,
    pin: Annotated[bool, Field(description="Pin the CID for IPFS hosting.")] = True,
    track: Annotated[bool, Field(description="Create a coordinator job record.")] = False,
    dry_run: Annotated[bool, Field(description="Show the command without executing it.")] = True,
    confirm: Annotated[bool, Field(description="Confirm the destructive action.")] = False,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to run the command on."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Run a software offer (Ollama/Whisper/FFmpeg/IPFS) and pay metered escrow."""
    subcommand_options: dict[str, str | None] = {}
    if max_tokens is not None:
        subcommand_options["max-tokens"] = str(max_tokens)
    if stream:
        subcommand_options["stream"] = None
    if language is not None:
        subcommand_options["language"] = language
    if task is not None:
        subcommand_options["task"] = task
    if transcript_format is not None:
        subcommand_options["transcript-format"] = transcript_format
    if media_format is not None:
        subcommand_options["media-format"] = media_format
    if codec is not None:
        subcommand_options["codec"] = codec
    if resolution is not None:
        subcommand_options["resolution"] = resolution
    if bitrate is not None:
        subcommand_options["bitrate"] = bitrate
    if days is not None:
        subcommand_options["days"] = str(days)
    if not pin:
        subcommand_options["no-pin"] = None
    if track:
        subcommand_options["track"] = None
    subcommand_options["offer-id-or-plugin-id"] = offer_id_or_plugin_id
    subcommand_options["prompt"] = prompt
    return _run_aitbc_cli_write(
        role,
        host,
        "market",
        "run",
        None,
        None,
        dry_run,
        confirm,
        group_options={"wallet": wallet},
        subcommand_options=subcommand_options,
        env={"AITBC_WALLET_DIR": DEFAULT_WALLET_DIR},
    )


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def download_market_ipfs(
    cid: Annotated[str | None, Field(description="Free CID to retrieve.")] = None,
    rental_id: Annotated[str | None, Field(description="Marketplace job ID for a paid rental.")] = None,
    access_key: Annotated[str | None, Field(description="Rental access key.")] = None,
    access_secret: Annotated[str | None, Field(description="Rental access secret.")] = None,
    output: Annotated[str | None, Field(description="Output file path.")] = None,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to run the command on."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Download IPFS content by CID, marketplace job ID, or access token."""
    subcommand_options: dict[str, str | None] = {}
    if cid:
        subcommand_options["cid"] = cid
    if rental_id:
        subcommand_options["rental-id"] = rental_id
    if access_key:
        subcommand_options["access-key"] = access_key
    if access_secret:
        subcommand_options["access-secret"] = access_secret
    if output:
        subcommand_options["output"] = output
    return _aitbc_cli_read_tool(
        role,
        host,
        "market",
        "download",
        group_options={},
        subcommand_options=subcommand_options,
    )


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def transcribe_market_offer(
    offer_id_or_plugin_id: Annotated[
        str,
        Field(description="Marketplace offer ID or plugin ID to run."),
    ],
    audio_file: Annotated[str, Field(description="Remote audio file path to transcribe.")],
    wallet: Annotated[str, Field(description="Wallet name to sign payment.")] = "genesis",
    language: Annotated[str | None, Field(description="Language code (e.g. 'en').")] = None,
    task: Annotated[
        Literal["transcribe", "translate"] | None,
        Field(description="Whisper task."),
    ] = None,
    output_format: Annotated[
        Literal["text", "srt", "json"] | None,
        Field(description="Transcript output format."),
    ] = None,
    dry_run: Annotated[bool, Field(description="Show the command without executing it.")] = True,
    confirm: Annotated[bool, Field(description="Confirm the destructive action.")] = False,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to run the command on."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Run a Whisper transcription offer on a remote audio file."""
    subcommand_options: dict[str, str | None] = {}
    if language is not None:
        subcommand_options["language"] = language
    if task is not None:
        subcommand_options["task"] = task
    if output_format is not None:
        subcommand_options["output-format"] = output_format
    subcommand_options["offer-id-or-plugin-id"] = offer_id_or_plugin_id
    subcommand_options["audio-file"] = audio_file
    return _run_aitbc_cli_write(
        role,
        host,
        "market",
        "transcribe",
        None,
        None,
        dry_run,
        confirm,
        group_options={"wallet": wallet},
        subcommand_options=subcommand_options,
        env={"AITBC_WALLET_DIR": DEFAULT_WALLET_DIR},
    )


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def process_market_offer(
    offer_id_or_plugin_id: Annotated[
        str,
        Field(description="Marketplace offer ID or plugin ID to run."),
    ],
    input_file: Annotated[str, Field(description="Remote input media file to process.")],
    wallet: Annotated[str, Field(description="Wallet name to sign payment.")] = "genesis",
    output_format: Annotated[str | None, Field(description="Output container (e.g. 'mp4').")] = None,
    codec: Annotated[str | None, Field(description="Target codec (e.g. 'h264').")] = None,
    resolution: Annotated[str | None, Field(description="Target resolution (e.g. '1080p').")] = None,
    bitrate: Annotated[str | None, Field(description="Target bitrate (e.g. '5M').")] = None,
    dry_run: Annotated[bool, Field(description="Show the command without executing it.")] = True,
    confirm: Annotated[bool, Field(description="Confirm the destructive action.")] = False,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to run the command on."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Run an FFmpeg media processing offer on a remote input file."""
    subcommand_options: dict[str, str | None] = {}
    if output_format is not None:
        subcommand_options["format"] = output_format
    if codec is not None:
        subcommand_options["codec"] = codec
    if resolution is not None:
        subcommand_options["resolution"] = resolution
    if bitrate is not None:
        subcommand_options["bitrate"] = bitrate
    subcommand_options["offer-id-or-plugin-id"] = offer_id_or_plugin_id
    subcommand_options["input-file"] = input_file
    return _run_aitbc_cli_write(
        role,
        host,
        "market",
        "process",
        None,
        None,
        dry_run,
        confirm,
        group_options={"wallet": wallet},
        subcommand_options=subcommand_options,
        env={"AITBC_WALLET_DIR": DEFAULT_WALLET_DIR},
    )


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def rate_market_service(
    service_id: Annotated[str, Field(description="Service or offer ID to rate.")],
    rating: Annotated[int, Field(description="Rating from 1 (poor) to 5 (excellent).", ge=1, le=5)],
    wallet: Annotated[str, Field(description="Wallet name to sign the rating.")] = "genesis",
    comment: Annotated[str | None, Field(description="Optional review comment.")] = None,
    reviewer_id: Annotated[str | None, Field(description="Optional reviewer identifier.")] = None,
    dry_run: Annotated[bool, Field(description="Show the command without executing it.")] = True,
    confirm: Annotated[bool, Field(description="Confirm the destructive action.")] = False,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to run the command on."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Submit a 1-5 star rating for a marketplace service."""
    subcommand_options: dict[str, str | None] = {}
    if comment is not None:
        subcommand_options["comment"] = comment
    if reviewer_id is not None:
        subcommand_options["reviewer-id"] = reviewer_id
    subcommand_options["service-id"] = service_id
    subcommand_options["rating"] = str(rating)
    return _run_aitbc_cli_write(
        role,
        host,
        "market",
        "rate",
        None,
        None,
        dry_run,
        confirm,
        group_options={"wallet": wallet},
        subcommand_options=subcommand_options,
        env={"AITBC_WALLET_DIR": DEFAULT_WALLET_DIR},
    )


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_market_service_ratings(
    service_id: Annotated[str, Field(description="Service or offer ID.")],
    limit: Annotated[int | None, Field(description="Maximum number of ratings to return.", ge=1)] = None,
    offset: Annotated[int | None, Field(description="Pagination offset.", ge=0)] = None,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """List ratings for a marketplace service."""
    options: dict[str, str | None] = {}
    if limit is not None:
        options["limit"] = str(limit)
    if offset is not None:
        options["offset"] = str(offset)
    options["service-id"] = service_id
    return _aitbc_cli_read_tool(role, host, "market", "ratings", options=options)


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def disable_market_offer(
    offer_id: Annotated[str, Field(description="Offer ID to disable.")],
    wallet: Annotated[str, Field(description="Wallet name that owns the offer.")] = "genesis",
    dry_run: Annotated[bool, Field(description="Show the command without executing it.")] = True,
    confirm: Annotated[bool, Field(description="Confirm the destructive action.")] = False,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to run the command on."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Deactivate a local marketplace offer."""
    return _run_aitbc_cli_write(
        role,
        host,
        "market",
        "offer-disable",
        [offer_id],
        None,
        dry_run,
        confirm,
        group_options={"wallet": wallet},
        env={"AITBC_WALLET_DIR": DEFAULT_WALLET_DIR},
    )


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def cancel_market_order(
    order_id: Annotated[str, Field(description="Order ID to cancel.")],
    wallet: Annotated[str, Field(description="Wallet name that placed the order.")] = "genesis",
    dry_run: Annotated[bool, Field(description="Show the command without executing it.")] = True,
    confirm: Annotated[bool, Field(description="Confirm the destructive action.")] = False,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to run the command on."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Cancel a marketplace order."""
    return _run_aitbc_cli_write(
        role,
        host,
        "market",
        "cancel",
        [order_id],
        None,
        dry_run,
        confirm,
        group_options={"wallet": wallet},
        env={"AITBC_WALLET_DIR": DEFAULT_WALLET_DIR},
    )


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_market_order_status(
    order_id: Annotated[str, Field(description="Order ID.")],
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Show the status of a marketplace order."""
    return _aitbc_cli_read_tool(role, host, "market", "status", options={"order-id": order_id})


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def market_match(
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Match GPU bids with offers (price discovery)."""
    return _aitbc_cli_read_tool(role, host, "market", "match")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def market_providers(
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Query island members for GPU providers."""
    return _aitbc_cli_read_tool(role, host, "market", "providers")


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def sync_market_ratings(
    wallet: Annotated[str, Field(description="Wallet name to sign the sync.")] = "genesis",
    remote_url: Annotated[str | None, Field(description="Remote marketplace service URL.")] = None,
    limit: Annotated[int | None, Field(description="Number of ratings to sync.", ge=1)] = None,
    dry_run: Annotated[bool, Field(description="Show the command without executing it.")] = True,
    confirm: Annotated[bool, Field(description="Confirm the destructive action.")] = False,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to run the command on."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Sync marketplace ratings to/from a remote marketplace node."""
    subcommand_options: dict[str, str | None] = {}
    if remote_url is not None:
        subcommand_options["remote-url"] = remote_url
    if limit is not None:
        subcommand_options["limit"] = str(limit)
    return _run_aitbc_cli_write(
        role,
        host,
        "market",
        "sync-ratings",
        None,
        None,
        dry_run,
        confirm,
        group_options={"wallet": wallet},
        subcommand_options=subcommand_options,
        env={"AITBC_WALLET_DIR": DEFAULT_WALLET_DIR},
    )


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def create_market_escrow(
    job_id: Annotated[str, Field(description="Job ID.")],
    buyer: Annotated[str, Field(description="Buyer/customer address.")],
    provider: Annotated[str, Field(description="Provider address.")],
    amount: Annotated[str, Field(description="Amount to escrow.")],
    wallet: Annotated[str, Field(description="Wallet name to sign the escrow lock.")] = "genesis",
    dry_run: Annotated[bool, Field(description="Show the command without executing it.")] = True,
    confirm: Annotated[bool, Field(description="Confirm the destructive action.")] = False,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to run the command on."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Create an on-chain escrow for a marketplace job."""
    _validate_evm_address(buyer, "buyer")
    _validate_evm_address(provider, "provider")
    return _run_aitbc_cli_write(
        role,
        host,
        "market",
        ["escrow", "create"],
        [job_id, buyer, provider, amount],
        None,
        dry_run,
        confirm,
        group_options={"wallet": wallet},
        env={"AITBC_WALLET_DIR": DEFAULT_WALLET_DIR},
    )


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def release_market_escrow(
    job_id: Annotated[str, Field(description="Job ID.")],
    wallet: Annotated[str, Field(description="Wallet name to release funds.")] = "genesis",
    dry_run: Annotated[bool, Field(description="Show the command without executing it.")] = True,
    confirm: Annotated[bool, Field(description="Confirm the destructive action.")] = False,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to run the command on."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Release escrow funds to the provider after a job completes."""
    return _run_aitbc_cli_write(
        role,
        host,
        "market",
        ["escrow", "release"],
        [job_id],
        None,
        dry_run,
        confirm,
        group_options={"wallet": wallet},
        env={"AITBC_WALLET_DIR": DEFAULT_WALLET_DIR},
    )


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def refund_market_escrow(
    job_id: Annotated[str, Field(description="Job ID.")],
    wallet: Annotated[str, Field(description="Wallet name to sign the refund.")] = "genesis",
    reason: Annotated[str | None, Field(description="Reason for refund.")] = None,
    dry_run: Annotated[bool, Field(description="Show the command without executing it.")] = True,
    confirm: Annotated[bool, Field(description="Confirm the destructive action.")] = False,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to run the command on."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Refund a marketplace escrow back to the buyer."""
    subcommand_options: dict[str, str | None] = {}
    if reason is not None:
        subcommand_options["reason"] = reason
    return _run_aitbc_cli_write(
        role,
        host,
        "market",
        ["escrow", "refund"],
        [job_id],
        None,
        dry_run,
        confirm,
        group_options={"wallet": wallet},
        subcommand_options=subcommand_options,
        env={"AITBC_WALLET_DIR": DEFAULT_WALLET_DIR},
    )


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_market_escrow_status(
    job_id: Annotated[str, Field(description="Job ID.")],
    wallet: Annotated[str, Field(description="Wallet name to use.")] = "genesis",
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Show the on-chain escrow state for a job."""
    return _aitbc_cli_read_tool(
        role,
        host,
        "market",
        ["escrow", "status"],
        options={"job-id": job_id},
        group_options={"wallet": wallet},
    )


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_market_exchange_price(
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get the current ETH-AIT exchange rate."""
    return _aitbc_cli_read_tool(role, host, "market", ["exchange", "price"])


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_market_exchange_status(
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get the bridge service status."""
    return _aitbc_cli_read_tool(role, host, "market", ["exchange", "status"])


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def list_market_exchange_deposits(
    status: Annotated[
        Literal["pending", "verified", "completed", "rejected"] | None,
        Field(description="Filter by deposit status."),
    ] = None,
    limit: Annotated[int | None, Field(description="Maximum number of deposits.", ge=1)] = None,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """List ETH bridge deposits."""
    options: dict[str, str | None] = {}
    if status is not None:
        options["status"] = status
    if limit is not None:
        options["limit"] = str(limit)
    return _aitbc_cli_read_tool(
        role,
        host,
        "market",
        ["exchange", "list-deposits"],
        options=options,
    )


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def mint_ait_from_eth_deposit(
    deposit_id: Annotated[str, Field(description="Verified ETH deposit ID.")],
    wallet: Annotated[str, Field(description="Wallet name to sign the mint.")] = "genesis",
    dry_run: Annotated[bool, Field(description="Show the command without executing it.")] = True,
    confirm: Annotated[bool, Field(description="Confirm the destructive action.")] = False,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to run the command on."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Mint AIT tokens for a verified ETH bridge deposit."""
    return _run_aitbc_cli_write(
        role,
        host,
        "market",
        ["exchange", "mint-ait"],
        [deposit_id],
        None,
        dry_run,
        confirm,
        group_options={"wallet": wallet},
        env={"AITBC_WALLET_DIR": DEFAULT_WALLET_DIR},
    )


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def withdraw_eth_from_bridge(
    amount: Annotated[Decimal, Field(description="Amount of ETH to withdraw.", gt=0)],
    address: Annotated[str, Field(description="Destination ETH address.")],
    wallet: Annotated[str, Field(description="Admin wallet to sign the withdrawal.")] = "genesis",
    dry_run: Annotated[bool, Field(description="Show the command without executing it.")] = True,
    confirm: Annotated[bool, Field(description="Confirm the destructive action.")] = False,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to run the command on."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Withdraw ETH from the bridge wallet (admin only)."""
    _validate_evm_address(address, "ETH address")
    return _run_aitbc_cli_write(
        role,
        host,
        "market",
        ["exchange", "withdraw-eth"],
        [str(amount), address],
        None,
        dry_run,
        confirm,
        group_options={"wallet": wallet},
        env={"AITBC_WALLET_DIR": DEFAULT_WALLET_DIR},
    )


# ---------------------------------------------------------------------------
# Wallet payments
# ---------------------------------------------------------------------------


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def send_aitbc_from_wallet(
    to_address: Annotated[str, Field(description="Recipient address.")],
    amount: Annotated[Decimal, Field(description="Amount of AIT to send.", gt=0)],
    wallet_name: Annotated[str, Field(description="Wallet name to send from.")] = "genesis",
    wallet_path: Annotated[str | None, Field(description="Path to a wallet file override.")] = None,
    use_daemon: Annotated[bool, Field(description="Use the wallet daemon instead of a file.")] = False,
    fee: Annotated[Decimal | None, Field(description="Transaction fee.", ge=0)] = None,
    rpc_url: Annotated[str | None, Field(description="Blockchain RPC URL override.")] = None,
    dry_run: Annotated[bool, Field(description="Show the command without executing it.")] = True,
    confirm: Annotated[bool, Field(description="Confirm the destructive action.")] = False,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to run the command on."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Send AIT from a local wallet to another address."""
    _validate_evm_address(to_address, "to_address")
    group_options: dict[str, str | None] = {"wallet-name": wallet_name}
    if wallet_path is not None:
        group_options["wallet-path"] = wallet_path
    if use_daemon:
        group_options["use-daemon"] = None
    subcommand_options: dict[str, str | None] = {
        "to-address": to_address,
        "amount": str(amount),
    }
    if fee is not None:
        subcommand_options["fee"] = str(fee)
    if rpc_url is not None:
        subcommand_options["rpc-url"] = rpc_url
    return _run_aitbc_cli_write(
        role,
        host,
        "wallet",
        "send",
        None,
        None,
        dry_run,
        confirm,
        group_options=group_options,
        subcommand_options=subcommand_options,
        env={"AITBC_WALLET_DIR": DEFAULT_WALLET_DIR},
    )


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def spend_aitbc_from_wallet(
    amount: Annotated[Decimal, Field(description="Amount to spend.", gt=0)],
    description: Annotated[str, Field(description="Description of the spend.")],
    wallet_name: Annotated[str, Field(description="Wallet name to spend from.")] = "genesis",
    wallet_path: Annotated[str | None, Field(description="Path to a wallet file override.")] = None,
    use_daemon: Annotated[bool, Field(description="Use the wallet daemon instead of a file.")] = False,
    dry_run: Annotated[bool, Field(description="Show the command without executing it.")] = True,
    confirm: Annotated[bool, Field(description="Confirm the destructive action.")] = False,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to run the command on."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Record an AIT spend from a local wallet."""
    group_options: dict[str, str | None] = {"wallet-name": wallet_name}
    if wallet_path is not None:
        group_options["wallet-path"] = wallet_path
    if use_daemon:
        group_options["use-daemon"] = None
    subcommand_options: dict[str, str | None] = {
        "amount": str(amount),
        "description": description,
    }
    return _run_aitbc_cli_write(
        role,
        host,
        "wallet",
        "spend",
        None,
        None,
        dry_run,
        confirm,
        group_options=group_options,
        subcommand_options=subcommand_options,
        env={"AITBC_WALLET_DIR": DEFAULT_WALLET_DIR},
    )


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def record_wallet_earnings(
    amount: Annotated[Decimal, Field(description="Amount earned.", gt=0)],
    job_id: Annotated[str, Field(description="Job ID the earnings are for.")],
    wallet_name: Annotated[str, Field(description="Wallet name to credit.")] = "genesis",
    wallet_path: Annotated[str | None, Field(description="Path to a wallet file override.")] = None,
    use_daemon: Annotated[bool, Field(description="Use the wallet daemon instead of a file.")] = False,
    desc: Annotated[str | None, Field(description="Optional earning description.")] = None,
    dry_run: Annotated[bool, Field(description="Show the command without executing it.")] = True,
    confirm: Annotated[bool, Field(description="Confirm the destructive action.")] = False,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to run the command on."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Record earned AIT for a job into a local wallet."""
    group_options: dict[str, str | None] = {"wallet-name": wallet_name}
    if wallet_path is not None:
        group_options["wallet-path"] = wallet_path
    if use_daemon:
        group_options["use-daemon"] = None
    subcommand_options: dict[str, str | None] = {
        "amount": str(amount),
        "job-id": job_id,
    }
    if desc is not None:
        subcommand_options["desc"] = desc
    return _run_aitbc_cli_write(
        role,
        host,
        "wallet",
        "earn",
        None,
        None,
        dry_run,
        confirm,
        group_options=group_options,
        subcommand_options=subcommand_options,
        env={"AITBC_WALLET_DIR": DEFAULT_WALLET_DIR},
    )


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def login_aitbc(
    wallet: Annotated[str, Field(description="Wallet name to sign the login.")] = "genesis",
    wallet_address: Annotated[str | None, Field(description="Override wallet address.")] = None,
    coordinator_url: Annotated[str | None, Field(description="Coordinator URL.")] = None,
    environment: Annotated[str | None, Field(description="Credential environment name.")] = None,
    dry_run: Annotated[bool, Field(description="Show the command without executing it.")] = True,
    confirm: Annotated[bool, Field(description="Confirm the destructive action.")] = False,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to run the command on."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Log in to the AITBC coordinator and store credentials on the node."""
    subcommand_options: dict[str, str | None] = {"wallet": wallet}
    if wallet_address is not None:
        subcommand_options["wallet-address"] = wallet_address
    if coordinator_url is not None:
        subcommand_options["coordinator-url"] = coordinator_url
    if environment is not None:
        subcommand_options["environment"] = environment
    return _run_aitbc_cli_write(
        role,
        host,
        "auth",
        "login",
        None,
        None,
        dry_run,
        confirm,
        subcommand_options=subcommand_options,
        env={"AITBC_WALLET_DIR": DEFAULT_WALLET_DIR},
    )


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def logout_aitbc(
    environment: Annotated[str | None, Field(description="Credential environment name.")] = None,
    dry_run: Annotated[bool, Field(description="Show the command without executing it.")] = True,
    confirm: Annotated[bool, Field(description="Confirm the destructive action.")] = False,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to run the command on."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Log out from the AITBC coordinator."""
    subcommand_options: dict[str, str | None] = {}
    if environment is not None:
        subcommand_options["environment"] = environment
    return _run_aitbc_cli_write(
        role,
        host,
        "auth",
        "logout",
        None,
        None,
        dry_run,
        confirm,
        subcommand_options=subcommand_options,
    )


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def show_aitbc_config(
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Show the current AITBC configuration."""
    return _aitbc_cli_read_tool(role, host, "config", "show")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_aitbc_config(
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get the current AITBC configuration (alias for show)."""
    return _aitbc_cli_read_tool(role, host, "config", "get")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_aitbc_config_path(
    global_config: Annotated[bool, Field(description="Show global config path.")] = False,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Show the configuration file path."""
    options: dict[str, str | None] = {}
    if global_config:
        options["global"] = None
    return _aitbc_cli_read_tool(role, host, "config", "path", options=options)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def check_aitbc_config(
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Check configuration and environment API keys."""
    return _aitbc_cli_read_tool(role, host, "config", "check")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def validate_aitbc_config(
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Validate the AITBC configuration."""
    return _aitbc_cli_read_tool(role, host, "config", "validate")


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def set_aitbc_config(
    key: Annotated[str, Field(description="Configuration key to set.")],
    value: Annotated[str, Field(description="Configuration value.")],
    global_config: Annotated[bool, Field(description="Set in the global config file.")] = False,
    dry_run: Annotated[bool, Field(description="Show the command without executing it.")] = True,
    confirm: Annotated[bool, Field(description="Confirm the destructive action.")] = False,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to run the command on."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Set an AITBC configuration value."""
    subcommand_options: dict[str, str | None] = {}
    if global_config:
        subcommand_options["global"] = None
    return _run_aitbc_cli_write(
        role,
        host,
        "config",
        "set",
        [key, value],
        None,
        dry_run,
        confirm,
        subcommand_options=subcommand_options,
    )


# ---------------------------------------------------------------------------
# Auto-generated CLI tool extensions
# ---------------------------------------------------------------------------


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def aitbc_wallet_rewards(
    role: Annotated[NodeRole | None, Field(description="Node role to query.")] = None,
    host: Annotated[str | None, Field(description="Override the host for this call.")] = None,
    timeout: Annotated[int, Field(description="Timeout in seconds.", ge=5, le=600)] = 120,
) -> str:
    """Run `aitbc wallet rewards`."""
    options: dict[str, Any] = {}
    return _aitbc_cli_read_tool(
        role,
        host,
        "wallet",
        subcommand="rewards",
        options=options,
        timeout=timeout,
    )


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def aitbc_wallet_staking_info(
    role: Annotated[NodeRole | None, Field(description="Node role to query.")] = None,
    host: Annotated[str | None, Field(description="Override the host for this call.")] = None,
    timeout: Annotated[int, Field(description="Timeout in seconds.", ge=5, le=600)] = 120,
) -> str:
    """Run `aitbc wallet staking-info`."""
    options: dict[str, Any] = {}
    return _aitbc_cli_read_tool(
        role,
        host,
        "wallet",
        subcommand="staking-info",
        options=options,
        timeout=timeout,
    )


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def aitbc_ai_distribution_stats(
    coordinator_url: Annotated[str | None, Field(description="Coordinator URL")] = None,
    role: Annotated[NodeRole | None, Field(description="Node role to query.")] = None,
    host: Annotated[str | None, Field(description="Override the host for this call.")] = None,
    timeout: Annotated[int, Field(description="Timeout in seconds.", ge=5, le=600)] = 120,
) -> str:
    """Run `aitbc ai distribution-stats`."""
    options: dict[str, Any] = {}
    if coordinator_url is not None:
        options["coordinator-url"] = coordinator_url
    return _aitbc_cli_read_tool(
        role,
        host,
        "ai",
        subcommand="distribution-stats",
        options=options,
        timeout=timeout,
    )


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def aitbc_ai_service_list(
    coordinator_url: Annotated[str | None, Field(description="Coordinator URL")] = None,
    role: Annotated[NodeRole | None, Field(description="Node role to query.")] = None,
    host: Annotated[str | None, Field(description="Override the host for this call.")] = None,
    timeout: Annotated[int, Field(description="Timeout in seconds.", ge=5, le=600)] = 120,
) -> str:
    """Run `aitbc ai service list`."""
    options: dict[str, Any] = {}
    if coordinator_url is not None:
        options["coordinator-url"] = coordinator_url
    return _aitbc_cli_read_tool(
        role,
        host,
        "ai",
        subcommand=["service", "list"],
        options=options,
        timeout=timeout,
    )


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def aitbc_ai_service_service_status(
    coordinator_url: Annotated[str | None, Field(description="Coordinator URL")] = None,
    name: Annotated[str | None, Field(description="Service name")] = None,
    role: Annotated[NodeRole | None, Field(description="Node role to query.")] = None,
    host: Annotated[str | None, Field(description="Override the host for this call.")] = None,
    timeout: Annotated[int, Field(description="Timeout in seconds.", ge=5, le=600)] = 120,
) -> str:
    """Run `aitbc ai service service-status`."""
    options: dict[str, Any] = {}
    if coordinator_url is not None:
        options["coordinator-url"] = coordinator_url
    if name is not None:
        options["name"] = name
    return _aitbc_cli_read_tool(
        role,
        host,
        "ai",
        subcommand=["service", "service-status"],
        options=options,
        timeout=timeout,
    )


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def aitbc_blockchain_sync_status(
    all_chains: Annotated[
        bool | None, Field(description="Show status for all supported chains (default: node's configured chains)")
    ] = None,
    chain_id: Annotated[str | None, Field(description="Show status for a specific chain only")] = None,
    node_url: Annotated[str | None, Field(description="Local node RPC URL")] = None,
    role: Annotated[NodeRole | None, Field(description="Node role to query.")] = None,
    host: Annotated[str | None, Field(description="Override the host for this call.")] = None,
    timeout: Annotated[int, Field(description="Timeout in seconds.", ge=5, le=600)] = 120,
) -> str:
    """Run `aitbc blockchain sync-status`."""
    options: dict[str, Any] = {}
    if all_chains:
        options["all-chains"] = None
    if chain_id is not None:
        options["chain-id"] = chain_id
    if node_url is not None:
        options["node-url"] = node_url
    return _aitbc_cli_read_tool(
        role,
        host,
        "blockchain",
        subcommand="sync-status",
        options=options,
        timeout=timeout,
    )


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def aitbc_blockchain_monitor(
    chain_id: Annotated[str, Field(description="The Chain id.")],
    export: Annotated[str | None, Field(description="Export monitoring data to file")] = None,
    interval: Annotated[int | None, Field(description="Update interval in seconds")] = None,
    realtime: Annotated[bool | None, Field(description="Real-time monitoring")] = None,
    role: Annotated[NodeRole | None, Field(description="Node role to query.")] = None,
    host: Annotated[str | None, Field(description="Override the host for this call.")] = None,
    timeout: Annotated[int, Field(description="Timeout in seconds.", ge=5, le=600)] = 120,
) -> str:
    """Run `aitbc blockchain monitor`."""
    options: dict[str, Any] = {}
    if chain_id is not None:
        options["chain-id"] = chain_id
    if export is not None:
        options["export"] = export
    if interval is not None:
        options["interval"] = interval
    if realtime:
        options["realtime"] = None
    return _aitbc_cli_read_tool(
        role,
        host,
        "blockchain",
        subcommand="monitor",
        options=options,
        timeout=timeout,
    )


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def aitbc_node_monitor(
    node_id: Annotated[str, Field(description="The Node id.")],
    interval: Annotated[int | None, Field(description="Update interval in seconds")] = None,
    realtime: Annotated[bool | None, Field(description="Real-time monitoring")] = None,
    role: Annotated[NodeRole | None, Field(description="Node role to query.")] = None,
    host: Annotated[str | None, Field(description="Override the host for this call.")] = None,
    timeout: Annotated[int, Field(description="Timeout in seconds.", ge=5, le=600)] = 120,
) -> str:
    """Run `aitbc node monitor`."""
    options: dict[str, Any] = {}
    if node_id is not None:
        options["node-id"] = node_id
    if interval is not None:
        options["interval"] = interval
    if realtime:
        options["realtime"] = None
    return _aitbc_cli_read_tool(
        role,
        host,
        "node",
        subcommand="monitor",
        options=options,
        timeout=timeout,
    )


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def aitbc_system_status(
    service: Annotated[str | None, Field(description="Show full systemctl status for a specific service")] = None,
    role: Annotated[NodeRole | None, Field(description="Node role to query.")] = None,
    host: Annotated[str | None, Field(description="Override the host for this call.")] = None,
    timeout: Annotated[int, Field(description="Timeout in seconds.", ge=5, le=600)] = 120,
) -> str:
    """Run `aitbc system status`."""
    options: dict[str, Any] = {}
    if service is not None:
        options["service"] = service
    return _aitbc_cli_read_tool(
        role,
        host,
        "system",
        subcommand="status",
        options=options,
        timeout=timeout,
    )


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def aitbc_system_logs(
    service: Annotated[str, Field(description="Service to show logs for")],
    lines: Annotated[int | None, Field(description="Number of log lines to show")] = None,
    role: Annotated[NodeRole | None, Field(description="Node role to query.")] = None,
    host: Annotated[str | None, Field(description="Override the host for this call.")] = None,
    timeout: Annotated[int, Field(description="Timeout in seconds.", ge=5, le=600)] = 120,
) -> str:
    """Run `aitbc system logs`."""
    options: dict[str, Any] = {}
    if service is not None:
        options["service"] = service
    if lines is not None:
        options["lines"] = lines
    return _aitbc_cli_read_tool(
        role,
        host,
        "system",
        subcommand="logs",
        options=options,
        timeout=timeout,
    )


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def aitbc_system_cron(
    role: Annotated[NodeRole | None, Field(description="Node role to query.")] = None,
    host: Annotated[str | None, Field(description="Override the host for this call.")] = None,
    timeout: Annotated[int, Field(description="Timeout in seconds.", ge=5, le=600)] = 120,
) -> str:
    """Run `aitbc system cron`."""
    options: dict[str, Any] = {}
    return _aitbc_cli_read_tool(
        role,
        host,
        "system",
        subcommand="cron",
        options=options,
        timeout=timeout,
    )


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def aitbc_system_config(
    show_secrets: Annotated[bool | None, Field(description="Show sensitive values like API keys")] = None,
    role: Annotated[NodeRole | None, Field(description="Node role to query.")] = None,
    host: Annotated[str | None, Field(description="Override the host for this call.")] = None,
    timeout: Annotated[int, Field(description="Timeout in seconds.", ge=5, le=600)] = 120,
) -> str:
    """Run `aitbc system config`."""
    options: dict[str, Any] = {}
    if show_secrets:
        options["show-secrets"] = None
    return _aitbc_cli_read_tool(
        role,
        host,
        "system",
        subcommand="config",
        options=options,
        timeout=timeout,
    )


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def aitbc_system_file(
    path: Annotated[
        str,
        Field(
            description="Absolute path to a file under /opt/aitbc, /etc/aitbc, /etc/systemd, /var/log/aitbc, or /var/lib/aitbc"
        ),
    ],
    role: Annotated[NodeRole | None, Field(description="Node role to query.")] = None,
    host: Annotated[str | None, Field(description="Override the host for this call.")] = None,
    timeout: Annotated[int, Field(description="Timeout in seconds.", ge=5, le=600)] = 120,
) -> str:
    """Run `aitbc system file`."""
    options: dict[str, Any] = {}
    if path is not None:
        options["path"] = path
    return _aitbc_cli_read_tool(
        role,
        host,
        "system",
        subcommand="file",
        options=options,
        timeout=timeout,
    )


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def aitbc_explorer_block(
    height: Annotated[int, Field(description="The Height.")],
    chain_id: Annotated[str | None, Field(description="Chain ID to query")] = None,
    role: Annotated[NodeRole | None, Field(description="Node role to query.")] = None,
    host: Annotated[str | None, Field(description="Override the host for this call.")] = None,
    timeout: Annotated[int, Field(description="Timeout in seconds.", ge=5, le=600)] = 120,
) -> str:
    """Run `aitbc explorer block`."""
    options: dict[str, Any] = {}
    if height is not None:
        options["height"] = height
    if chain_id is not None:
        options["chain-id"] = chain_id
    return _aitbc_cli_read_tool(
        role,
        host,
        "explorer",
        subcommand="block",
        options=options,
        timeout=timeout,
    )


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def aitbc_explorer_transaction(
    tx_hash: Annotated[str, Field(description="The Tx hash.")],
    chain_id: Annotated[str | None, Field(description="Chain ID to query")] = None,
    role: Annotated[NodeRole | None, Field(description="Node role to query.")] = None,
    host: Annotated[str | None, Field(description="Override the host for this call.")] = None,
    timeout: Annotated[int, Field(description="Timeout in seconds.", ge=5, le=600)] = 120,
) -> str:
    """Run `aitbc explorer transaction`."""
    options: dict[str, Any] = {}
    if tx_hash is not None:
        options["tx-hash"] = tx_hash
    if chain_id is not None:
        options["chain-id"] = chain_id
    return _aitbc_cli_read_tool(
        role,
        host,
        "explorer",
        subcommand="transaction",
        options=options,
        timeout=timeout,
    )


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def aitbc_explorer_chain_head(
    chain_id: Annotated[str | None, Field(description="Chain ID to query")] = None,
    role: Annotated[NodeRole | None, Field(description="Node role to query.")] = None,
    host: Annotated[str | None, Field(description="Override the host for this call.")] = None,
    timeout: Annotated[int, Field(description="Timeout in seconds.", ge=5, le=600)] = 120,
) -> str:
    """Run `aitbc explorer chain-head`."""
    options: dict[str, Any] = {}
    if chain_id is not None:
        options["chain-id"] = chain_id
    return _aitbc_cli_read_tool(
        role,
        host,
        "explorer",
        subcommand="chain-head",
        options=options,
        timeout=timeout,
    )


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def aitbc_explorer_latest_blocks(
    chain_id: Annotated[str | None, Field(description="Chain ID to query")] = None,
    limit: Annotated[int | None, Field(description="Number of blocks to return")] = None,
    offset: Annotated[int | None, Field(description="Offset for pagination")] = None,
    role: Annotated[NodeRole | None, Field(description="Node role to query.")] = None,
    host: Annotated[str | None, Field(description="Override the host for this call.")] = None,
    timeout: Annotated[int, Field(description="Timeout in seconds.", ge=5, le=600)] = 120,
) -> str:
    """Run `aitbc explorer latest-blocks`."""
    options: dict[str, Any] = {}
    if chain_id is not None:
        options["chain-id"] = chain_id
    if limit is not None:
        options["limit"] = limit
    if offset is not None:
        options["offset"] = offset
    return _aitbc_cli_read_tool(
        role,
        host,
        "explorer",
        subcommand="latest-blocks",
        options=options,
        timeout=timeout,
    )


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def aitbc_governance_list(
    category: Annotated[str | None, Field(description="Filter by category")] = None,
    proposer_id: Annotated[str | None, Field(description="Filter by proposer ID")] = None,
    status: Annotated[
        str | None, Field(description="Filter by status (draft, active, succeeded, defeated, executed, cancelled)")
    ] = None,
    role: Annotated[NodeRole | None, Field(description="Node role to query.")] = None,
    host: Annotated[str | None, Field(description="Override the host for this call.")] = None,
    timeout: Annotated[int, Field(description="Timeout in seconds.", ge=5, le=600)] = 120,
) -> str:
    """Run `aitbc governance list`."""
    options: dict[str, Any] = {}
    if category is not None:
        options["category"] = category
    if proposer_id is not None:
        options["proposer-id"] = proposer_id
    if status is not None:
        options["status"] = status
    return _aitbc_cli_read_tool(
        role,
        host,
        "governance",
        subcommand="list",
        options=options,
        timeout=timeout,
    )


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def aitbc_governance_status(
    role: Annotated[NodeRole | None, Field(description="Node role to query.")] = None,
    host: Annotated[str | None, Field(description="Override the host for this call.")] = None,
    timeout: Annotated[int, Field(description="Timeout in seconds.", ge=5, le=600)] = 120,
) -> str:
    """Run `aitbc governance status`."""
    options: dict[str, Any] = {}
    return _aitbc_cli_read_tool(
        role,
        host,
        "governance",
        subcommand="status",
        options=options,
        timeout=timeout,
    )


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def aitbc_reputation_leaderboard(
    category: Annotated[str | None, Field(description="Category to rank by")] = None,
    limit: Annotated[int | None, Field(description="Number of results")] = None,
    region: Annotated[str | None, Field(description="Filter by region")] = None,
    role: Annotated[NodeRole | None, Field(description="Node role to query.")] = None,
    host: Annotated[str | None, Field(description="Override the host for this call.")] = None,
    timeout: Annotated[int, Field(description="Timeout in seconds.", ge=5, le=600)] = 120,
) -> str:
    """Run `aitbc reputation leaderboard`."""
    options: dict[str, Any] = {}
    if category is not None:
        options["category"] = category
    if limit is not None:
        options["limit"] = limit
    if region is not None:
        options["region"] = region
    return _aitbc_cli_read_tool(
        role,
        host,
        "reputation",
        subcommand="leaderboard",
        options=options,
        timeout=timeout,
    )


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def aitbc_monitor_dashboard(
    duration: Annotated[int | None, Field(description="Duration in seconds (0 = indefinite)")] = None,
    refresh: Annotated[int | None, Field(description="Refresh interval in seconds")] = None,
    role: Annotated[NodeRole | None, Field(description="Node role to query.")] = None,
    host: Annotated[str | None, Field(description="Override the host for this call.")] = None,
    timeout: Annotated[int, Field(description="Timeout in seconds.", ge=5, le=600)] = 120,
) -> str:
    """Run `aitbc monitor dashboard`."""
    options: dict[str, Any] = {}
    if duration is not None:
        options["duration"] = duration
    if refresh is not None:
        options["refresh"] = refresh
    return _aitbc_cli_read_tool(
        role,
        host,
        "monitor",
        subcommand="dashboard",
        options=options,
        timeout=timeout,
    )


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def aitbc_monitor_metrics(
    export_path: Annotated[str | None, Field(description="Export metrics to file")] = None,
    period: Annotated[str | None, Field(description="Time period (1h, 24h, 7d, 30d)")] = None,
    role: Annotated[NodeRole | None, Field(description="Node role to query.")] = None,
    host: Annotated[str | None, Field(description="Override the host for this call.")] = None,
    timeout: Annotated[int, Field(description="Timeout in seconds.", ge=5, le=600)] = 120,
) -> str:
    """Run `aitbc monitor metrics`."""
    options: dict[str, Any] = {}
    if export_path is not None:
        options["export"] = export_path
    if period is not None:
        options["period"] = period
    return _aitbc_cli_read_tool(
        role,
        host,
        "monitor",
        subcommand="metrics",
        options=options,
        timeout=timeout,
    )


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def aitbc_analytics_summary(
    chain_id: Annotated[str | None, Field(description="Specific chain ID to analyze")] = None,
    hours: Annotated[int | None, Field(description="Time range in hours")] = None,
    role: Annotated[NodeRole | None, Field(description="Node role to query.")] = None,
    host: Annotated[str | None, Field(description="Override the host for this call.")] = None,
    timeout: Annotated[int, Field(description="Timeout in seconds.", ge=5, le=600)] = 120,
) -> str:
    """Run `aitbc analytics summary`."""
    options: dict[str, Any] = {}
    if chain_id is not None:
        options["chain-id"] = chain_id
    if hours is not None:
        options["hours"] = hours
    return _aitbc_cli_read_tool(
        role,
        host,
        "analytics",
        subcommand="summary",
        options=options,
        timeout=timeout,
    )


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def aitbc_analytics_dashboard(
    role: Annotated[NodeRole | None, Field(description="Node role to query.")] = None,
    host: Annotated[str | None, Field(description="Override the host for this call.")] = None,
    timeout: Annotated[int, Field(description="Timeout in seconds.", ge=5, le=600)] = 120,
) -> str:
    """Run `aitbc analytics dashboard`."""
    options: dict[str, Any] = {}
    return _aitbc_cli_read_tool(
        role,
        host,
        "analytics",
        subcommand="dashboard",
        options=options,
        timeout=timeout,
    )


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def aitbc_crosschain_status(
    swap_id: Annotated[str, Field(description="The Swap id.")],
    role: Annotated[NodeRole | None, Field(description="Node role to query.")] = None,
    host: Annotated[str | None, Field(description="Override the host for this call.")] = None,
    timeout: Annotated[int, Field(description="Timeout in seconds.", ge=5, le=600)] = 120,
) -> str:
    """Run `aitbc crosschain status`."""
    options: dict[str, Any] = {}
    if swap_id is not None:
        options["swap-id"] = swap_id
    return _aitbc_cli_read_tool(
        role,
        host,
        "crosschain",
        subcommand="status",
        options=options,
        timeout=timeout,
    )


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def aitbc_crosschain_swaps(
    limit: Annotated[int | None, Field(description="Number of swaps to show")] = None,
    status: Annotated[str | None, Field(description="Filter by status")] = None,
    user_address: Annotated[str | None, Field(description="Filter by user address")] = None,
    role: Annotated[NodeRole | None, Field(description="Node role to query.")] = None,
    host: Annotated[str | None, Field(description="Override the host for this call.")] = None,
    timeout: Annotated[int, Field(description="Timeout in seconds.", ge=5, le=600)] = 120,
) -> str:
    """Run `aitbc crosschain swaps`."""
    options: dict[str, Any] = {}
    if limit is not None:
        options["limit"] = limit
    if status is not None:
        options["status"] = status
    if user_address is not None:
        options["user-address"] = user_address
    return _aitbc_cli_read_tool(
        role,
        host,
        "crosschain",
        subcommand="swaps",
        options=options,
        timeout=timeout,
    )


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def aitbc_crosschain_rates(
    from_chain: Annotated[str | None, Field(description="Source chain ID")] = None,
    from_token: Annotated[str | None, Field(description="Source token symbol")] = None,
    to_chain: Annotated[str | None, Field(description="Target chain ID")] = None,
    to_token: Annotated[str | None, Field(description="Target token symbol")] = None,
    role: Annotated[NodeRole | None, Field(description="Node role to query.")] = None,
    host: Annotated[str | None, Field(description="Override the host for this call.")] = None,
    timeout: Annotated[int, Field(description="Timeout in seconds.", ge=5, le=600)] = 120,
) -> str:
    """Run `aitbc crosschain rates`."""
    options: dict[str, Any] = {}
    if from_chain is not None:
        options["from-chain"] = from_chain
    if from_token is not None:
        options["from-token"] = from_token
    if to_chain is not None:
        options["to-chain"] = to_chain
    if to_token is not None:
        options["to-token"] = to_token
    return _aitbc_cli_read_tool(
        role,
        host,
        "crosschain",
        subcommand="rates",
        options=options,
        timeout=timeout,
    )


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def aitbc_crosschain_pools(
    role: Annotated[NodeRole | None, Field(description="Node role to query.")] = None,
    host: Annotated[str | None, Field(description="Override the host for this call.")] = None,
    timeout: Annotated[int, Field(description="Timeout in seconds.", ge=5, le=600)] = 120,
) -> str:
    """Run `aitbc crosschain pools`."""
    options: dict[str, Any] = {}
    return _aitbc_cli_read_tool(
        role,
        host,
        "crosschain",
        subcommand="pools",
        options=options,
        timeout=timeout,
    )
