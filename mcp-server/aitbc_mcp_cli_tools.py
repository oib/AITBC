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
        NodeRole | None,
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
        NodeRole | None,
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
        NodeRole | None,
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
        NodeRole | None,
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
    return _run_aitbc_cli_write(
        role,
        host,
        "market",
        "offer",
        [service_type, model, str(price)],
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
    return _run_aitbc_cli_write(role, host, "ipfs", "pin", [cid], {}, dry_run, confirm)


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
        NodeRole | None,
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


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def fund_wallet(
    address: Annotated[str, Field(description="Wallet address to fund.")],
    amount_ait: Annotated[str, Field(description="Amount to request from faucet in AIT.")] = "1.0",
    chain_id: Annotated[str | None, Field(description="Chain ID override.")] = None,
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
    """Fund a wallet address using the blockchain faucet."""
    _validate_evm_address(address, "wallet address")
    options: dict[str, str | None] = {"address": address, "amount-ait": amount_ait}
    if chain_id is not None:
        options["chain-id"] = chain_id
    return _run_aitbc_cli_write(role, host, "wallet", "fund", None, options, dry_run, confirm)


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
    """Run a software offer (Ollama/Whisper/FFmpeg) and pay metered escrow."""
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
    if track:
        subcommand_options["track"] = None
    return _run_aitbc_cli_write(
        role,
        host,
        "market",
        "run",
        [offer_id_or_plugin_id, prompt],
        None,
        dry_run,
        confirm,
        group_options={"wallet": wallet},
        subcommand_options=subcommand_options,
        env={"AITBC_WALLET_DIR": DEFAULT_WALLET_DIR},
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
    return _run_aitbc_cli_write(
        role,
        host,
        "market",
        "transcribe",
        [offer_id_or_plugin_id, audio_file],
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
    return _run_aitbc_cli_write(
        role,
        host,
        "market",
        "process",
        [offer_id_or_plugin_id, input_file],
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
    return _run_aitbc_cli_write(
        role,
        host,
        "market",
        "rate",
        [service_id, str(rating)],
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
