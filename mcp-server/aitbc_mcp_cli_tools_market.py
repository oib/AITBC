"""Market execution, ratings and shop management CLI tools for the MCP server.

Split out of ``aitbc_mcp_cli_tools.py`` (issue #1860 Phase 2).  Imported by
``aitbc_mcp_server.py`` after ``aitbc_mcp_cli_tools`` so the shared private
helpers (``_run_aitbc_cli_write``, ``_validate_evm_address``) remain
importable from the original module.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal

from mcp.types import ToolAnnotations
from pydantic import Field

from aitbc_mcp_cli_tools import _run_aitbc_cli_write, _validate_evm_address
from aitbc_mcp_server import (
    DEFAULT_WALLET_DIR,
    NodeRole,
    _aitbc_cli_read_tool,
    mcp,
)


# ---------------------------------------------------------------------------
# Market execution, ratings and shop management
# ---------------------------------------------------------------------------


def _merge_market_run_string_options(options: dict[str, str | None], fields: dict[str, str | None]) -> None:
    for cli_key, value in fields.items():
        if value is not None:
            options[cli_key] = value


def _run_market_offer_cli_options(
    *,
    offer_id_or_plugin_id: str,
    prompt: str,
    max_tokens: int | None,
    stream: bool,
    language: str | None,
    task: str | None,
    transcript_format: str | None,
    media_format: str | None,
    codec: str | None,
    resolution: str | None,
    bitrate: str | None,
    days: int | None,
    pin: bool,
    track: bool,
) -> dict[str, str | None]:
    """Map ``run_market_offer`` parameters to ``aitbc market run`` CLI options."""
    from aitbc_mcp_mutating_tools import _merge_cli_flag_options, _merge_cli_numeric_options

    subcommand_options: dict[str, str | None] = {}
    _merge_cli_numeric_options(subcommand_options, {"max-tokens": max_tokens, "days": days})
    _merge_market_run_string_options(
        subcommand_options,
        {
            "language": language,
            "task": task,
            "transcript-format": transcript_format,
            "media-format": media_format,
            "codec": codec,
            "resolution": resolution,
            "bitrate": bitrate,
            "offer-id-or-plugin-id": offer_id_or_plugin_id,
            "prompt": prompt,
        },
    )
    _merge_cli_flag_options(subcommand_options, {"stream": stream, "track": track})
    if not pin:
        subcommand_options["no-pin"] = None
    return subcommand_options


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def run_market_offer(
    offer_id_or_plugin_id: Annotated[
        str,
        Field(description="Market offer ID or plugin ID to run."),
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
    subcommand_options = _run_market_offer_cli_options(
        offer_id_or_plugin_id=offer_id_or_plugin_id,
        prompt=prompt,
        max_tokens=max_tokens,
        stream=stream,
        language=language,
        task=task,
        transcript_format=transcript_format,
        media_format=media_format,
        codec=codec,
        resolution=resolution,
        bitrate=bitrate,
        days=days,
        pin=pin,
        track=track,
    )
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


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def download_market_ipfs(
    cid: Annotated[str | None, Field(description="Free CID to retrieve.")] = None,
    rental_id: Annotated[str | None, Field(description="Market job ID for a paid rental.")] = None,
    access_key: Annotated[str | None, Field(description="Rental access key.")] = None,
    output: Annotated[str | None, Field(description="Output file path.")] = None,
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
    """Download IPFS content by CID, market job ID, or access token.

    Writes the retrieved content to a file on the remote host (a tempfile when
    ``output`` is not given), so it is gated like ``aitbc_market_download``.

    MCP-SECRETS-1: the ``access_secret`` value parameter was removed — secret
    values must never appear as MCP call arguments. The access-token route
    stays unavailable until the CLI leaf gains an ``--access-secret-file``
    form (follow-up); ``access_key`` is kept for parity with the generated
    twin.
    """
    subcommand_options: dict[str, str | None] = {}
    if cid:
        subcommand_options["cid"] = cid
    if rental_id:
        subcommand_options["rental-id"] = rental_id
    if access_key:
        subcommand_options["access-key"] = access_key
    if output:
        subcommand_options["output"] = output
    return _run_aitbc_cli_write(
        role,
        host,
        "market",
        "download",
        None,
        None,
        dry_run,
        confirm,
        group_options={},
        subcommand_options=subcommand_options,
    )


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def transcribe_market_offer(
    offer_id_or_plugin_id: Annotated[
        str,
        Field(description="Market offer ID or plugin ID to run."),
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
        Field(description="Market offer ID or plugin ID to run."),
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
    """Submit a 1-5 star rating for a market service."""
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
    """List ratings for a market service."""
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
    """Deactivate a local market offer."""
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
    """Cancel a market order."""
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
    """Show the status of a market order."""
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
    remote_url: Annotated[str | None, Field(description="Remote market service URL.")] = None,
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
    """Sync market ratings to/from a remote market node."""
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
    """Create an on-chain escrow for a market job."""
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
    """Refund a market escrow back to the buyer."""
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
