"""
Marketplace offer commands: list, cancel, status, match, providers, offer
"""

import hashlib
import json
import re
import subprocess
import socket
from datetime import datetime
from decimal import Decimal
from typing import Any

import click

from ...config import get_config
from ...utils import DECIMAL, OUTPUT_FORMAT_OPTION, error, info, output, resolve_output_format, success, warning
from ...utils.http_client import AITBCHTTPClient, NetworkError, get_logger
from aitbc.crypto.crypto import sign_transaction_data

# Initialize logger
logger = get_logger(__name__)

from . import get_chain_id, get_island_id, get_market_wallet, get_next_nonce, market, safe_load_credentials
from .escrow import _get_blockchain_rpc_url


def _is_wallet_address(value: str | None) -> bool:
    """Return True if value looks like a wallet address, not an agent/miner id."""
    if not value:
        return False
    value = str(value).strip()
    return value.startswith("0x") or (value.startswith("aitbc1") and len(value) > 12)


def _compute_plugin_id(service_type: str, model: str) -> str:
    """Derive the plugin_id used by the marketplace service."""
    return f"{service_type}-{model.replace(':', '-')}"


def _to_decimal(value: Any) -> Decimal:
    """Convert an offer price to Decimal for stable sorting."""
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (TypeError, ValueError, ArithmeticError):
        return Decimal("0")


def _is_active(status: Any) -> bool:
    return str(status).lower() in ("active", "available", "open")


def _reputation_for_offer(http_client: AITBCHTTPClient, coordinator_url: str, offer: dict[str, Any]) -> None:
    """Enrich an offer with coordinator trust score, if available."""
    agent_id = offer.get("provider_address") or offer.get("node_id") or ""
    if not agent_id or _is_wallet_address(agent_id):
        return
    for candidate in (agent_id, offer.get("node_id", "")):
        if not candidate or _is_wallet_address(candidate):
            continue
        if candidate in ("aitbc3", "aitbc3-provider") or "-provider" in candidate:
            continue
        try:
            profile = http_client.get(f"{coordinator_url}/reputation/profile/{candidate}")
            if profile and "error" not in profile:
                offer["trust_score"] = float(profile.get("trust_score", 0) or 0)
                offer["reputation_level"] = profile.get("reputation_level", "")
                offer["jobs_completed"] = int(profile.get("jobs_completed", 0) or 0)
                return
        except (NetworkError, Exception) as e:
            logger.debug("No reputation profile for %s: %s", candidate, e)


def _reputation_score(offer: dict[str, Any]) -> tuple[float, float, int, int]:
    """Return normalized reputation and supporting count.

    Prefer canonical coordinator trust score (0-1000) when available; otherwise
    fall back to marketplace avg_rating (0-5) and rating_count.
    """
    trust_score = offer.get("trust_score")
    if trust_score is not None:
        return (float(trust_score) / 1000.0, 1.0, int(offer.get("jobs_completed", 0) or 0), 0)
    avg_rating = float(offer.get("avg_rating", 0) or 0)
    rating_count = int(offer.get("rating_count", 0) or 0)
    return (avg_rating / 5.0, 0.0, rating_count, 0)


def _reputation_key(offer: dict[str, Any]) -> tuple[float, float, int, Decimal, bool, int]:
    """Sort by reputation desc, then price asc, then availability desc."""
    reputation, has_trust, count, _ = _reputation_score(offer)
    price = _to_decimal(offer.get("price", 0))
    available = _is_active(offer.get("status"))
    capacity = int(offer.get("capacity", 0) or 0)
    return (-reputation, -has_trust, -count, price, not available, -capacity)


def _price_key(offer: dict[str, Any]) -> tuple[Decimal, float, float, float, bool, int]:
    """Sort by price asc, then reputation desc, availability desc."""
    price = _to_decimal(offer.get("price", 0))
    reputation, has_trust, count, _ = _reputation_score(offer)
    available = _is_active(offer.get("status"))
    capacity = int(offer.get("capacity", 0) or 0)
    return (price, -reputation, -has_trust, -count, not available, -capacity)


def _availability_key(offer: dict[str, Any]) -> tuple[bool, int, float, float, float, Decimal]:
    """Sort by availability (active first), then capacity desc, reputation, price."""
    available = _is_active(offer.get("status"))
    capacity = int(offer.get("capacity", 0) or 0)
    reputation, has_trust, count, _ = _reputation_score(offer)
    price = _to_decimal(offer.get("price", 0))
    return (not available, -capacity, -reputation, -has_trust, -count, price)


def _sort_offers(offers: list[dict[str, Any]], sort: str) -> list[dict[str, Any]]:
    """Sort marketplace offers according to the selected sort mode."""
    if sort == "reputation":
        return sorted(offers, key=_reputation_key)
    if sort == "price":
        return sorted(offers, key=_price_key)
    if sort == "availability":
        return sorted(offers, key=_availability_key)
    # default is the same as reputation, but we keep a named branch above
    return sorted(offers, key=_reputation_key)


def _discover_local_gpus() -> list[dict[str, Any]]:
    """Discover local NVIDIA GPUs with full specs via nvidia-smi."""
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,name,memory.total,compute_cap,uuid",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            logger.debug("nvidia-smi query failed: %s", result.stderr)
            return []
        gpus = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 3:
                continue
            gpus.append(
                {
                    "index": str(int(parts[0])),
                    "name": parts[1],
                    "memory_gb": int(parts[2]) // 1024,
                    "compute_capability": parts[3] if len(parts) > 3 else "",
                    "uuid": parts[4] if len(parts) > 4 else "",
                }
            )
        return gpus
    except FileNotFoundError:
        logger.debug("nvidia-smi not found - GPU discovery skipped")
        return []
    except subprocess.TimeoutExpired:
        logger.debug("nvidia-smi timeout - GPU discovery skipped")
        return []
    except Exception as e:
        logger.debug("Error running nvidia-smi: %s", e)
        return []


@market.command(name="list")
@click.option("--provider", help="Filter by provider address")
@click.option("--status", help="Filter by status (active, inactive)")
@click.option("--service-type", help="Filter by service type (ollama, whisper, ffmpeg)")
@click.option(
    "--sort",
    type=click.Choice(["reputation", "price", "availability", "default"]),
    default="default",
    help="Sort order: reputation (rating desc, then price), price (asc), availability (active first, capacity), default (reputation, price, availability)",
)
@click.option("--mine", is_flag=True, help="Show only offers published by the local wallet/node")
@OUTPUT_FORMAT_OPTION
@click.pass_context
def list_offers(
    ctx,
    provider: str | None,
    status: str | None,
    service_type: str | None,
    sort: str,
    mine: bool,
    output_format: str,
):
    """List blockchain marketplace offers and bids"""
    try:
        fmt = resolve_output_format(ctx, output_format)
        config = get_config()
        hub_url = f"http://{config.hub_discovery_url or 'hub.aitbc.bubuit.net'}"

        # Resolve the local identity when --mine is used.
        my_address: str | None = None
        my_node_id: str | None = None
        if mine:
            try:
                my_address, _, _ = get_market_wallet(ctx, require_private_key=False)
            except Exception:
                my_address = None
            my_node_id = hashlib.sha256(socket.gethostname().encode()).hexdigest()

        # Try marketplace service API first (new approach)
        try:
            http_client = AITBCHTTPClient(base_url=hub_url, timeout=15)

            # Build query parameters
            params: dict[str, Any] = {}
            if service_type:
                params["service_type"] = service_type
            if status:
                params["status"] = status

            result = http_client.get("/v1/marketplace/offer", params=params)

            if result and "offers" in result and result["offers"]:
                offers = result["offers"]

                # Apply additional filters
                if provider:
                    offers = [o for o in offers if o.get("provider_address") == provider]
                if status:
                    offers = [o for o in offers if o.get("status") == status]
                if service_type:
                    offers = [o for o in offers if o.get("service_type") == service_type]
                if mine:
                    offers = [o for o in offers if o.get("provider_address") == my_address or o.get("node_id") == my_node_id]

                if offers:
                    # Enrich offers with canonical coordinator reputation data.
                    coordinator_url = config.coordinator_api_url or hub_url
                    for offer in offers:
                        _reputation_for_offer(http_client, coordinator_url, offer)

                    # Sort deterministically by live reputation (trust score > avg rating).
                    offers = _sort_offers(offers, sort)

                    # Format output for marketplace offers
                    market_data = []
                    for offer in offers:
                        provider_addr = offer.get("provider_address", "N/A") or "N/A"
                        public_ep = offer.get("public_endpoint", "N/A") or "N/A"
                        market_data.append(
                            {
                                "Offer ID": offer.get("offer_id", "N/A"),
                                "Plugin ID": offer.get("plugin_id", "N/A"),
                                "Service Type": offer.get("service_type", "N/A"),
                                "Model": offer.get("model", "N/A"),
                                "Price": f"{offer.get('price', 0)} {offer.get('price_unit', 'units')}",
                                "Provider": provider_addr[:16] + "..." if len(provider_addr) > 16 else provider_addr,
                                "Node ID": offer.get("node_id", "N/A"),
                                "GPU": f"{offer.get('gpu_name', 'N/A')} ({offer.get('gpu_device', 'N/A')})",
                                "Memory (GB)": offer.get("gpu_memory_gb") or "N/A",
                                "Endpoint": public_ep[:30] + "..." if len(public_ep) > 30 else public_ep,
                                "Status": offer.get("status", "unknown"),
                                "Rating": f"{offer.get('trust_score', 0) / 1000:.2f} trust"
                                if offer.get("trust_score") is not None
                                else f"{offer.get('avg_rating', 0):.1f} ({offer.get('rating_count', 0)} reviews)",
                            }
                        )

                    output(market_data, fmt)
                    success(f"Found {len(offers)} marketplace offers")
                    return
        except NetworkError as e:
            logger.warning("Marketplace service not available: %s", e)
        except Exception as e:
            logger.warning("Error querying marketplace service: %s", e)

        # Fallback to blockchain query (original approach)
        transactions: list[dict[str, Any]] = []
        try:
            # Query hub directly (HTTP) for confirmed GPU_MARKETPLACE transactions
            http_client = AITBCHTTPClient(base_url=hub_url, timeout=15)
            result = http_client.get("/rpc/transactions", params={"limit": 500})
            if result and not isinstance(result, dict):
                # Filter by payload action since hub doesn't store type field
                tx_list = [  # type: ignore[unreachable]
                    tx
                    for tx in result
                    if isinstance(tx.get("payload"), dict)
                    and tx["payload"].get("action") in ("offer", "bid", "cancel", "accept", "software_offer")
                ]
                transactions = tx_list
                logger.debug("Found %s GPU_MARKETPLACE transactions from hub", len(transactions))

            # Also check hub mempool for pending transactions
            if not transactions:
                mempool = http_client.get("/rpc/mempool")
                if mempool and isinstance(mempool, dict) and "transactions" in mempool:
                    transactions = [tx for tx in mempool["transactions"] if tx.get("type") == "GPU_MARKETPLACE"]
                    logger.debug("Found %s GPU_MARKETPLACE transactions in hub mempool", len(transactions))
        except NetworkError as e:
            logger.error("Network error querying hub: %s", e)
            # Fallback to local blockchain RPC
            try:
                http_client = AITBCHTTPClient(base_url=config.blockchain_rpc_url, timeout=10)
                result = http_client.get("/rpc/transactions", params={"transaction_type": "GPU_MARKETPLACE", "limit": 200})
                if result and not isinstance(result, dict):
                    transactions = result  # type: ignore[unreachable]
            except NetworkError:
                logger.debug("Local blockchain RPC unavailable for transactions", exc_info=True)
                pass

        if not transactions:
            info("No GPU marketplace offers found (blockchain endpoint not available)")
            return

        # Format output for marketplace offers (blockchain data)
        blockchain_data: list[dict[str, Any]] = []
        for tx in transactions:
            # Handle both mempool format (payload is dict) and mined block format (nested payload)
            if isinstance(tx, dict):
                if "payload" in tx:
                    # Mined block format - nested payload
                    payload = tx["payload"]
                    if isinstance(payload, str):
                        try:
                            payload = json.loads(payload)
                        except json.JSONDecodeError:
                            logger.debug("Failed to parse transaction payload JSON", exc_info=True)
                            continue
                elif "action" in tx:
                    # Direct format (mempool or simplified)
                    payload = tx
                else:
                    continue

            action = payload.get("action")

            # Only show hardware+software bundle offers
            if action != "software_offer":
                continue
            if status and payload.get("status") != status:
                continue
            if provider and payload.get("provider_address") != provider:
                continue
            if mine:
                if payload.get("provider_address") != my_address and payload.get("provider_node_id") != my_node_id:
                    continue

            gpu_name = payload.get("gpu_name", "N/A")
            deployment_type = payload.get("deployment_type", "local")
            gpu_device = payload.get("gpu_device", "0")
            gpu_name_display = f"{gpu_name} [GPU {gpu_device}]" if deployment_type == "local" else "N/A (cloud)"

            # Get rating info from marketplace service if available
            rating_display = "N/A"
            try:
                client = AITBCHTTPClient(base_url="http://localhost:8102", timeout=5)
                # Use offer_id to lookup service via new endpoint
                offer_id = payload.get("offer_id", "")
                if offer_id:
                    service_response = client.get(f"/v1/marketplace/offer-by-id/{offer_id}")
                    if service_response and not service_response.get("error"):
                        avg_rating = service_response.get("avg_rating", 0.0)
                        rating_count = service_response.get("rating_count", 0)
                        if rating_count > 0:
                            rating_display = f"⭐ {avg_rating:.1f} ({rating_count})"
            except Exception:
                logger.debug("Marketplace service not available, skip ratings", exc_info=True)
                pass  # Marketplace service not available, skip ratings

            blockchain_data.append(
                {
                    "Offer ID": payload.get("offer_id", ""),
                    "Plugin ID": payload.get("offer_id", ""),
                    "Type": payload.get("service_type", "").upper(),
                    "Model": payload.get("model", ""),
                    "GPU": gpu_name_display[:35] + "..." if len(gpu_name_display) > 35 else gpu_name_display,
                    "Memory (GB)": payload.get("memory_gb", "N/A"),
                    "Price": f"{payload.get('price', 0)} AIT/{payload.get('price_unit', '')}",
                    "Rating": rating_display,
                    "Status": payload.get("status", "active"),
                    "Provider": (payload.get("provider_address", "") or "")[:30] + "...",
                    "Description": (payload.get("description", "")[:35] + "...")
                    if len(payload.get("description", "")) > 35
                    else payload.get("description", ""),
                    "Created": payload.get("created_at", "")[:19] if payload.get("created_at") else "N/A",
                }
            )

        output(blockchain_data, fmt, title="Hardware+Software Bundle Offers")

    except Exception as e:
        error(f"Error listing GPU marketplace: {str(e)}")
        raise click.Abort() from e


@market.command()
@click.argument("order_id")
@click.pass_context
def cancel(ctx, order_id: str):
    """Cancel a hardware+software bundle offer"""
    try:
        config = get_config()
        credentials = safe_load_credentials()
        if not credentials:
            return
        chain_id = get_chain_id()
        island_id = get_island_id()

        wallet_address, private_key, _ = get_market_wallet(ctx, require_private_key=True)
        if not private_key:
            error("Cancelling an offer requires a wallet private key")
            raise click.Abort()

        cancel_data = {
            "from": wallet_address,
            "to": "0x0000000000000000000000000000000000000000",
            "amount": 0,
            "fee": 36,
            "nonce": get_next_nonce(wallet_address),
            "type": "GPU_MARKETPLACE",
            "chain_id": chain_id,
            "payload": {
                "action": "cancel",
                "order_id": order_id,
                "status": "cancelled",
                "island_id": island_id,
                "chain_id": chain_id,
                "created_at": datetime.now().isoformat(),
            },
        }

        cancel_data["signature"] = sign_transaction_data(cancel_data, private_key)

        try:
            rpc_url = _get_blockchain_rpc_url(config)
            http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
            result = http_client.post("/rpc/transactions/marketplace", json=cancel_data)
            success(f"Offer {order_id} cancelled successfully!")
            output(result, ctx.obj.get("output_format", "table"))
        except NetworkError:
            hub_url = f"http://{config.hub_discovery_url or 'hub.aitbc.bubuit.net'}"
            http_client = AITBCHTTPClient(base_url=hub_url, timeout=10)
            result = http_client.post("/rpc/transactions/marketplace", json=cancel_data)
            success(f"Offer {order_id} cancelled successfully!")
            output(result, ctx.obj.get("output_format", "table"))

    except Exception as e:
        error(f"Error cancelling offer: {e}")
        raise click.Abort() from e


@market.command()
@click.argument("order_id")
@click.pass_context
def status(ctx, order_id: str):
    """Check the status of a GPU order including on-chain escrow"""
    try:
        config = get_config()
        blockchain_rpc_url = getattr(config, "blockchain_rpc_url", "http://localhost:8202")
        hub_url = (
            f"http://{config.hub_discovery_url}"
            if config.hub_discovery_url and not config.hub_discovery_url.startswith("http")
            else (config.hub_discovery_url or blockchain_rpc_url)
        )

        # Query blockchain for transaction status
        tx_result = None
        try:
            http_client = AITBCHTTPClient(base_url=config.blockchain_rpc_url, timeout=10)
            tx_result = http_client.get(f"/rpc/transactions/marketplace/{order_id}")
        except Exception:
            logger.debug("Offer lookup request failed", exc_info=True)
            pass

        if not tx_result:
            try:
                http_client = AITBCHTTPClient(base_url=hub_url, timeout=10)
                tx_result = http_client.get(f"/rpc/transactions/marketplace/{order_id}")
            except Exception:
                logger.debug("Hub offer lookup request failed", exc_info=True)
                pass

        # Query escrow state from blockchain node
        escrow_result = None
        try:
            http_client = AITBCHTTPClient(base_url=config.blockchain_rpc_url, timeout=10)
            escrow_result = http_client.get(f"/rpc/escrow/{order_id}")
        except Exception:
            logger.debug("Offer lookup request failed", exc_info=True)
            pass

        if not escrow_result:
            try:
                http_client = AITBCHTTPClient(base_url=hub_url, timeout=10)
                escrow_result = http_client.get(f"/rpc/escrow/{order_id}")
            except Exception:
                logger.debug("Hub offer lookup request failed", exc_info=True)
                pass

        combined: dict = {}
        if tx_result and isinstance(tx_result, dict):
            combined.update(tx_result)
        if escrow_result and isinstance(escrow_result, dict):
            combined["escrow"] = {
                "state": escrow_result.get("state"),
                "amount": escrow_result.get("amount"),
                "released_amount": escrow_result.get("released_amount"),
                "buyer": escrow_result.get("buyer"),
                "provider": escrow_result.get("provider"),
                "created_at": escrow_result.get("created_at"),
                "released_at": escrow_result.get("released_at"),
            }

        if not combined:
            error(f"No data found for order/job: {order_id}")
            raise click.Abort() from None

        output(combined, ctx.obj.get("output_format", "table"))

    except Exception as e:
        error(f"Error checking order status: {e}")
        raise click.Abort() from e


@market.command()
@click.pass_context
def match(ctx):
    """Match GPU bids with offers (price discovery)"""
    try:
        # Load CLI config
        config = get_config()

        # Query blockchain for matching
        try:
            http_client = AITBCHTTPClient(base_url=config.blockchain_rpc_url, timeout=10)
            result = http_client.get("/rpc/transactions/marketplace/match")

            if not result:
                # Try hub
                hub_url = config.blockchain_rpc_url.replace("localhost", config.hub_discovery_url or "hub.aitbc.bubuit.net")
                http_client = AITBCHTTPClient(base_url=hub_url, timeout=10)
                result = http_client.get("/rpc/transactions/marketplace/match")

            output(result, ctx.obj.get("output_format", "table"), title="GPU Market Matches")
        except NetworkError as e:
            error(f"Network error: {e}")
            raise click.Abort() from e

    except Exception as e:
        error(f"Error matching GPU market: {e}")
        raise click.Abort() from e


@market.command()
@click.pass_context
def providers(ctx):
    """Query island members for GPU providers"""
    try:
        # Load CLI config
        _ = get_config()

        # Query P2P network for providers
        info("Note: GPU provider query via P2P network to be implemented")
        info("Use 'aitbc gpu list' to see local registered GPUs")

    except Exception as e:
        error(f"Error querying GPU providers: {str(e)}")
        raise click.Abort() from e


# ---------------------------------------------------------------------------
# Software marketplace — Ollama inference, Whisper, FFmpeg
# ---------------------------------------------------------------------------


@market.command(name="offer")
@click.argument("service_type", type=click.Choice(["ollama", "whisper", "ffmpeg", "ipfs"]))
@click.argument("model_or_variant")
@click.argument("price", type=DECIMAL)
@click.option(
    "--unit",
    default="per_1k_tokens",
    type=click.Choice(["per_1k_tokens", "per_audio_min", "per_gb", "per_processing_hour", "per_day"]),
    help="Pricing unit",
)
@click.option("--description", help="Description of the service")
@click.option("--context-window", type=int, default=4096, help="Context window size (ollama)")
@click.option("--gpu-name", help="GPU name from nvidia-smi (auto-detected if omitted)")
@click.option("--gpu-device", help="GPU device ID (0, 1, 2, etc.) for multi-GPU servers")
@click.option("--gpu-offer-id", help="GPU marketplace offer ID for cross-reference")
@click.pass_context
def offer(
    ctx,
    service_type: str,
    model_or_variant: str,
    price: Decimal,
    unit: str,
    description: str | None,
    context_window: int,
    gpu_name: str | None,
    gpu_device: str | None,
    gpu_offer_id: str | None,
):
    """List a hardware+software bundle offer (Ollama/Whisper/FFmpeg/IPFS) in the marketplace"""
    try:
        config = get_config()
        chain_id = get_chain_id()
        island_id = get_island_id()
        wallet_address, _, _ = get_market_wallet(ctx, require_private_key=False)

        # Auto-detect deployment type from model name suffix
        is_cloud = model_or_variant.endswith(":cloud")
        deployment_type = "cloud" if is_cloud else "local"
        info(f"Auto-detected deployment type: {deployment_type}")

        # IPFS hosting offers use a Kubo daemon, not a GPU
        ipfs_port = 0
        ipfs_peer_id = ""
        ipfs_public_multiaddr = ""

        # Auto-detect GPU info from nvidia-smi if not provided and not cloud
        gpu_uuid = None
        gpu_memory_gb = 0
        compute_capability = ""
        gpu_model = ""
        if service_type == "ipfs":
            gpu_name = "N/A (IPFS)"
            gpu_device = "N/A"
            gpu_uuid = "N/A"
            gpu_memory_gb = 0
            compute_capability = "N/A"
            gpu_model = "N/A"
        if not is_cloud and service_type != "ipfs":
            discovered_gpus = _discover_local_gpus()
            selected_gpu = None
            if discovered_gpus:
                if gpu_device is not None:
                    selected_gpu = next((g for g in discovered_gpus if g["index"] == gpu_device), discovered_gpus[0])
                elif gpu_name is not None:
                    selected_gpu = next((g for g in discovered_gpus if g["name"] == gpu_name), discovered_gpus[0])
                else:
                    selected_gpu = discovered_gpus[0]
            if selected_gpu:
                gpu_name = selected_gpu["name"]
                gpu_device = selected_gpu["index"]
                gpu_uuid = selected_gpu["uuid"]
                gpu_memory_gb = selected_gpu["memory_gb"]
                compute_capability = selected_gpu["compute_capability"]
                gpu_model = gpu_name
                info(
                    f"Auto-detected GPU: {gpu_name} ({gpu_memory_gb} GB, compute {compute_capability}, "
                    f"device {gpu_device}, UUID: {gpu_uuid})"
                )
            elif gpu_name is None:
                warning("Failed to auto-detect GPU info")
                gpu_name = "Unknown GPU"
                gpu_device = "0"
                gpu_model = "Unknown GPU"
            else:
                gpu_model = gpu_name
                if gpu_device is None:
                    gpu_device = "0"
        elif gpu_name is None and is_cloud:
            gpu_name = "N/A (cloud)"
            gpu_device = "N/A"
            gpu_uuid = "N/A"
            gpu_memory_gb = 0
            compute_capability = "N/A"
            gpu_model = "N/A"
        elif gpu_device is None and not is_cloud:
            gpu_device = "0"  # Default to first GPU

        # Verify the service is actually running locally or reachable for cloud
        if service_type == "ollama":
            try:
                ol_client = AITBCHTTPClient(base_url="http://localhost:11434", timeout=5)
                tags = ol_client.get("/api/tags")
                models = [m["name"] for m in tags.get("models", [])]
                if model_or_variant not in models:
                    error(f"Model '{model_or_variant}' not found in local Ollama. Available: {', '.join(models)}")
                    raise click.Abort()
                info(f"Verified Ollama model: {model_or_variant}")
            except NetworkError as e:
                error(f"Ollama not reachable at localhost:11434: {e}")
                raise click.Abort() from e
        elif service_type == "whisper":
            try:
                w_client = AITBCHTTPClient(base_url="http://localhost:8110", timeout=5)
                health = w_client.get("/health")
                if not health.get("ready"):
                    error("Whisper service is not ready at localhost:8110")
                    raise click.Abort()
                loaded = health.get("model", "")
                info(f"Verified Whisper service: model={loaded} device={health.get('device')}")
            except NetworkError as e:
                error(f"Whisper service not reachable at localhost:8110: {e}")
                error("Start it with: systemctl start aitbc-whisper")
                raise click.Abort() from e
        elif service_type == "ffmpeg":
            try:
                f_client = AITBCHTTPClient(base_url="http://localhost:8230", timeout=5)
                health = f_client.get("/health")
                if health.get("status") != "ok":
                    error("FFmpeg service is not ready at localhost:8230")
                    raise click.Abort()
                info("Verified FFmpeg service")
            except NetworkError as e:
                error(f"FFmpeg service not reachable at localhost:8230: {e}")
                error("Start it with: systemctl start aitbc-ffmpeg")
                raise click.Abort() from e
        elif service_type == "ipfs":
            # Try island IPFS API (5002) then default IPFS API (5001)
            for _candidate_port in (5002, 5001):
                try:
                    ipfs_client = AITBCHTTPClient(base_url=f"http://localhost:{_candidate_port}", timeout=5)
                    _version = ipfs_client.post("/api/v0/version")
                    if _version.get("Version"):
                        ipfs_port = _candidate_port
                        info(f"Verified IPFS daemon on localhost:{ipfs_port}")
                        break
                except NetworkError:
                    continue
            if not ipfs_port:
                error("IPFS daemon not reachable at localhost:5001 or localhost:5002")
                error("Start it with: systemctl start aitbc-island-ipfs")
                raise click.Abort()
            try:
                _id = ipfs_client.post("/api/v0/id")
                ipfs_peer_id = _id.get("ID", "")
                _addrs = _id.get("Addresses", [])
                # Pick the first non-loopback, non-private /ip4/ address as the public multiaddr
                for _addr in _addrs:
                    _m = re.match(r"/ip4/(\d+\.\d+\.\d+\.\d+)", _addr)
                    if _m:
                        _octets = _m.group(1).split(".")
                        _first = int(_octets[0])
                        _second = int(_octets[1])
                        if _first == 127:
                            continue
                        if _first == 10 or (_first == 172 and 16 <= _second <= 31) or (_first == 192 and _second == 168):
                            continue
                        ipfs_public_multiaddr = _addr
                        break
                if not ipfs_public_multiaddr and _addrs:
                    ipfs_public_multiaddr = _addrs[-1]
                info(f"IPFS peer id: {ipfs_peer_id}")
            except NetworkError as e:
                error(f"Could not query IPFS peer identity: {e}")
                raise click.Abort() from e

        provider_node_id = hashlib.sha256(socket.gethostname().encode()).hexdigest()
        offer_id = f"sw_offer_{datetime.now().strftime('%Y%m%d%H%M%S')}_{hashlib.sha256(f'{service_type}{model_or_variant}{price}'.encode()).hexdigest()[:8]}"

        # Build public endpoint so remote buyers know where to send jobs
        _local_ports = {"ollama": 11434, "whisper": 8110, "ffmpeg": 8230, "ipfs": 0}
        _local_port = _local_ports.get(service_type, 8110)
        if service_type == "ipfs" and ipfs_port:
            _local_port = ipfs_port
        _hub_hostname = config.hub_discovery_url or "hub.aitbc.bubuit.net"
        _base_domain = _hub_hostname.removeprefix("hub.")
        _node_hostname = socket.getfqdn()
        # If FQDN doesn't include domain, construct it from short hostname + base domain
        if _base_domain and _base_domain not in _node_hostname:
            _node_hostname = f"{socket.gethostname()}.{_base_domain}"
        # nginx routes: /whisper/ → :8110, /ollama/ → :11434 (see deployment/nginx-aitbc.conf)
        _nginx_paths = {"ollama": "ollama", "whisper": "whisper", "ffmpeg": "ffmpeg", "ipfs": "ipfs"}
        _nginx_path = _nginx_paths.get(service_type, service_type)
        if service_type == "ipfs":
            _public_endpoint = ipfs_public_multiaddr or f"https://{_node_hostname}/{_nginx_path}"
            _local_endpoint = f"http://localhost:{_local_port}"
        else:
            _public_endpoint = f"https://{_node_hostname}/{_nginx_path}"
            _local_endpoint = f"http://localhost:{_local_port}"

        offer_data = {
            "from": wallet_address,
            "to": "0x0000000000000000000000000000000000000000",
            "amount": 0,
            "fee": 36,
            "nonce": get_next_nonce(wallet_address),
            "type": "GPU_MARKETPLACE",
            "chain_id": chain_id,
            "payload": {
                "action": "software_offer",
                "offer_id": offer_id,
                "provider_node_id": provider_node_id,
                "provider_address": wallet_address,
                "service_type": service_type,
                "model": model_or_variant,
                # not-money: wire format. This is the payload of a GPU_MARKETPLACE
                # transaction; the node hashes it for the tx id and reads "price" back
                # as a JSON number. Decimal is not JSON-serializable and a string would
                # change the hash, so this stays float until the protocol changes.
                "price": float(price),
                "price_unit": unit,
                "context_window": context_window if service_type == "ollama" else None,
                "deployment_type": deployment_type,
                "gpu_name": gpu_name,
                "gpu_model": gpu_model,
                "gpu_device": gpu_device,
                "gpu_uuid": gpu_uuid,
                "gpu_offer_id": gpu_offer_id,
                "memory_gb": gpu_memory_gb,
                "compute_capability": compute_capability,
                "status": "active",
                "description": description or f"{service_type} — {model_or_variant} at {price} AIT/{unit}",
                "island_id": island_id,
                "chain_id": chain_id,
                "endpoint": _public_endpoint,
                "created_at": datetime.now().isoformat(),
            },
        }

        hub_url = f"http://{config.hub_discovery_url or 'hub.aitbc.bubuit.net'}"
        http_client = AITBCHTTPClient(base_url=hub_url, timeout=10)
        tx_result = http_client.post("/rpc/transactions/marketplace", json=offer_data)
        success("Software offer listed on marketplace!")
        output(tx_result, ctx.obj.get("output_format", "table"))

        # Auto-register in hub marketplace service so agents can discover it.
        _health_urls = {
            "ollama": "http://localhost:11434/api/tags",
            "whisper": "http://localhost:8110/health",
            "ffmpeg": "http://localhost:8230/health",
            "ipfs": f"http://localhost:{ipfs_port}/api/v0/version" if ipfs_port else "",
        }
        try:
            # P2.5: register the offer with the same marketplace service that `market list`
            # queries, otherwise the offer is visible only on the local node.
            marketplace_url = hub_url.replace("http://", "https://") if not hub_url.startswith("https://") else hub_url
            plugin_client = AITBCHTTPClient(base_url=marketplace_url, timeout=10)
            plugin_id = f"{service_type}-{model_or_variant.replace(':', '-')}"
            plugin_client.post(
                "/v1/marketplace/offer",
                json={
                    "plugin_id": plugin_id,
                    "service_type": service_type,
                    "model": model_or_variant,
                    # not-money: wire format. This is the payload of a GPU_MARKETPLACE
                    # transaction; the node hashes it for the tx id and reads "price" back
                    # as a JSON number. Decimal is not JSON-serializable and a string would
                    # change the hash, so this stays float until the protocol changes.
                    "price": float(price),
                    "price_unit": unit,
                    "offer_id": offer_id,
                    "endpoint": _local_endpoint,
                    "public_endpoint": _public_endpoint,
                    "health_url": _health_urls.get(service_type, ""),
                    "provider_address": wallet_address,
                    "node_id": provider_node_id,
                    "deployment_type": deployment_type,
                    "gpu_name": gpu_name,
                    "gpu_model": gpu_model,
                    "gpu_device": gpu_device,
                    "gpu_uuid": gpu_uuid,
                    "gpu_offer_id": gpu_offer_id,
                    "gpu_memory_gb": gpu_memory_gb,
                    "compute_capability": compute_capability,
                    "description": description or f"{service_type} — {model_or_variant} at {price} AIT/{unit}",
                    "status": "active",
                },
            )
            info(
                f"Software service registered in marketplace (plugin-id: {service_type}-{model_or_variant.replace(':', '-')})"
            )
        except Exception:
            logger.debug("Offer lookup request failed", exc_info=True)
            pass  # Non-fatal — marketplace service may not be running

    except Exception as e:
        error(f"Error creating software offer: {e}")
        raise click.Abort() from e
