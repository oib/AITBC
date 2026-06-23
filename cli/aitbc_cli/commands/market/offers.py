"""
Marketplace offer commands: list, cancel, status, match, providers, offer
"""

import hashlib
import json
import socket
from datetime import datetime

import click

from ...config import get_config
from ...utils import error, info, output, success, warning
from ...utils.http_client import AITBCHTTPClient, NetworkError, get_logger

# Initialize logger
logger = get_logger(__name__)

from . import get_chain_id, get_island_id, get_next_nonce, get_wallet_address, market, safe_load_credentials
from .escrow import _get_blockchain_rpc_url


@market.command()
@click.option("--provider", help="Filter by provider address")
@click.option("--status", help="Filter by status (active, inactive)")
@click.option("--service-type", help="Filter by service type (ollama, whisper, ffmpeg, peertube_pruner)")
@click.pass_context
def list(ctx, provider: str | None, status: str | None, service_type: str | None):
    """List blockchain marketplace offers and bids"""
    try:
        # Load CLI config
        config = get_config()

        # Try marketplace service API first (new approach)
        try:
            # Use the marketplace service API
            hub_url = f"http://{config.hub_discovery_url or 'hub.aitbc.bubuit.net'}"
            http_client = AITBCHTTPClient(base_url=hub_url, timeout=15)

            # Build query parameters
            params = {}
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

                if offers:
                    # Format output for marketplace offers
                    market_data = []
                    for offer in offers:
                        market_data.append(
                            {
                                "Plugin ID": offer.get("plugin_id", "N/A"),
                                "Service Type": offer.get("service_type", "N/A"),
                                "Model": offer.get("model", "N/A"),
                                "Price": f"{offer.get('price', 0)} {offer.get('price_unit', 'units')}",
                                "Provider": offer.get("provider_address", "N/A")[:16] + "..."
                                if len(offer.get("provider_address", "")) > 16
                                else offer.get("provider_address", "N/A"),
                                "Node ID": offer.get("node_id", "N/A"),
                                "GPU": f"{offer.get('gpu_name', 'N/A')} ({offer.get('gpu_device', 'N/A')})",
                                "Endpoint": offer.get("public_endpoint", "N/A")[:30] + "..."
                                if len(offer.get("public_endpoint", "")) > 30
                                else offer.get("public_endpoint", "N/A"),
                                "Status": offer.get("status", "unknown"),
                                "Rating": f"{offer.get('avg_rating', 0):.1f} ({offer.get('rating_count', 0)} reviews)",
                            }
                        )

                    output(market_data, ctx.obj.get("output_format", "table"))
                    success(f"Found {len(offers)} marketplace offers")
                    return
        except NetworkError as e:
            logger.warning("Marketplace service not available: %s", e)
        except Exception as e:
            logger.warning("Error querying marketplace service: %s", e)

        # Fallback to blockchain query (original approach)
        transactions = None
        try:
            # Query hub directly (HTTP) for confirmed GPU_MARKETPLACE transactions
            hub_url = f"http://{config.hub_discovery_url or 'hub.aitbc.bubuit.net'}"
            http_client = AITBCHTTPClient(base_url=hub_url, timeout=15)
            result = http_client.get("/rpc/transactions", params={"limit": 500})
            if result and not isinstance(result, dict):
                # Filter by payload action since hub doesn't store type field
                transactions = [
                    tx
                    for tx in result
                    if isinstance(tx.get("payload"), dict)
                    and tx["payload"].get("action") in ("offer", "bid", "cancel", "accept", "software_offer")
                ]
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
                    transactions = result
            except NetworkError:
                pass

        if not transactions:
            info("No GPU marketplace offers found (blockchain endpoint not available)")
            return

        # Format output for marketplace offers (blockchain data)
        market_data = []
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
                pass  # Marketplace service not available, skip ratings

            market_data.append(
                {
                    "Offer ID": payload.get("offer_id", ""),
                    "Type": payload.get("service_type", "").upper(),
                    "Model": payload.get("model", ""),
                    "GPU": gpu_name_display[:35] + "..." if len(gpu_name_display) > 35 else gpu_name_display,
                    "Price": f"{payload.get('price', 0)} AIT/{payload.get('price_unit', '')}",
                    "Rating": rating_display,
                    "Status": payload.get("status", "active"),
                    "Provider": payload.get("provider_address", "")[:30] + "...",
                    "Description": (payload.get("description", "")[:35] + "...")
                    if len(payload.get("description", "")) > 35
                    else payload.get("description", ""),
                    "Created": payload.get("created_at", "")[:19] if payload.get("created_at") else "N/A",
                }
            )

        output(market_data, ctx.obj.get("output_format", "table"), title="Hardware+Software Bundle Offers")

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

        wallet_address = get_wallet_address()
        cancel_data = {
            "from": wallet_address,
            "to": "0x0000000000000000000000000000000000000000",
            "amount": 0,
            "fee": 36,
            "nonce": get_next_nonce(),
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

        try:
            hub_url = f"http://{config.hub_discovery_url or 'hub.aitbc.bubuit.net'}"
            http_client = AITBCHTTPClient(base_url=hub_url, timeout=10)
            result = http_client.post("/rpc/transactions/marketplace", json=cancel_data)
            success(f"Offer {order_id} cancelled successfully!")
            output(result, ctx.obj.get("output_format", "table"))
        except NetworkError:
            rpc_url = _get_blockchain_rpc_url(config)
            http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
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
            pass

        if not tx_result:
            try:
                http_client = AITBCHTTPClient(base_url=hub_url, timeout=10)
                tx_result = http_client.get(f"/rpc/transactions/marketplace/{order_id}")
            except Exception:
                pass

        # Query escrow state from blockchain node
        escrow_result = None
        try:
            http_client = AITBCHTTPClient(base_url=config.blockchain_rpc_url, timeout=10)
            escrow_result = http_client.get(f"/rpc/escrow/{order_id}")
        except Exception:
            pass

        if not escrow_result:
            try:
                http_client = AITBCHTTPClient(base_url=hub_url, timeout=10)
                escrow_result = http_client.get(f"/rpc/escrow/{order_id}")
            except Exception:
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
# Software marketplace — Ollama inference, Whisper, PeerTube pruner
# ---------------------------------------------------------------------------


@market.command(name="offer")
@click.argument("service_type", type=click.Choice(["ollama", "whisper", "peertube_pruner", "ffmpeg"]))
@click.argument("model_or_variant")
@click.argument("price", type=float)
@click.option(
    "--unit",
    default="per_1k_tokens",
    type=click.Choice(["per_1k_tokens", "per_audio_min", "per_gb", "per_processing_hour"]),
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
    price: float,
    unit: str,
    description: str | None,
    context_window: int,
    gpu_name: str | None,
    gpu_device: str | None,
    gpu_offer_id: str | None,
):
    """List a hardware+software bundle offer (Ollama/Whisper/PeerTube/FFmpeg) in the marketplace"""
    try:
        config = get_config()
        chain_id = get_chain_id()
        island_id = get_island_id()
        wallet_address = get_wallet_address()

        # Auto-detect deployment type from model name suffix
        is_cloud = model_or_variant.endswith(":cloud")
        deployment_type = "cloud" if is_cloud else "local"
        info(f"Auto-detected deployment type: {deployment_type}")

        # Auto-detect GPU info from nvidia-smi if not provided and not cloud
        gpu_uuid = None
        if gpu_name is None and not is_cloud:
            try:
                import subprocess

                # Get GPU name, device ID, and UUID
                result = subprocess.run(["nvidia-smi", "-L"], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    # Parse output: "GPU 0: NVIDIA GeForce RTX 4060 Ti (UUID: GPU-ba5c6553-6396-ab66-5706-17e6de30a93a)"
                    for line in result.stdout.strip().split("\n"):
                        if line.startswith("GPU"):
                            # Extract device ID, name, and UUID
                            parts = line.split(":")
                            device_part = parts[0].strip()  # "GPU 0"
                            gpu_name = parts[1].split("(")[0].strip()  # "NVIDIA GeForce RTX 4060 Ti "
                            uuid_part = parts[1].split("UUID:")[1].rstrip(")") if "UUID:" in parts[1] else None

                            # Use specified device or default to first GPU
                            if gpu_device is None:
                                gpu_device = device_part.split()[1]  # Extract "0" from "GPU 0"
                                gpu_uuid = uuid_part
                                info(f"Auto-detected GPU: {gpu_name} (device {gpu_device}, UUID: {gpu_uuid})")
                                break
                            elif device_part == f"GPU {gpu_device}":
                                gpu_uuid = uuid_part
                                info(f"Auto-detected GPU: {gpu_name} (device {gpu_device}, UUID: {gpu_uuid})")
                                break
            except Exception as e:
                warning(f"Failed to auto-detect GPU info: {e}")
                gpu_name = "Unknown GPU"
                gpu_device = "0"
        elif gpu_name is None and is_cloud:
            gpu_name = "N/A (cloud)"
            gpu_device = "N/A"
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
        elif service_type == "peertube_transcoder":
            try:
                p_client = AITBCHTTPClient(base_url="http://localhost:8220", timeout=5)
                health = p_client.get("/health")
                if health.get("status") != "ok":
                    error("PeerTube transcoder service is not ready at localhost:8220")
                    raise click.Abort()
                info("Verified PeerTube transcoder service")
            except NetworkError as e:
                error(f"PeerTube transcoder service not reachable at localhost:8220: {e}")
                error("Start it with: systemctl start aitbc-peertube-transcoder")
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

        provider_node_id = hashlib.sha256(socket.gethostname().encode()).hexdigest()
        offer_id = f"sw_offer_{datetime.now().strftime('%Y%m%d%H%M%S')}_{hashlib.sha256(f'{service_type}{model_or_variant}{price}'.encode()).hexdigest()[:8]}"

        # Build public endpoint so remote buyers know where to send jobs
        _local_ports = {"ollama": 11434, "whisper": 8110, "peertube_transcoder": 8220, "ffmpeg": 8230}
        _local_port = _local_ports.get(service_type, 8110)
        _hub_hostname = config.hub_discovery_url or "hub.aitbc.bubuit.net"
        _base_domain = _hub_hostname.removeprefix("hub.")
        _node_hostname = socket.getfqdn()
        # If FQDN doesn't include domain, construct it from short hostname + base domain
        if _base_domain and _base_domain not in _node_hostname:
            _node_hostname = f"{socket.gethostname()}.{_base_domain}"
        # nginx routes: /whisper/ → :8110, /ollama/ → :11434, /peertube/ → :8220 (see deployment/nginx-aitbc.conf)
        _nginx_paths = {"ollama": "ollama", "whisper": "whisper", "peertube_transcoder": "peertube", "ffmpeg": "ffmpeg"}
        _nginx_path = _nginx_paths.get(service_type, service_type)
        _public_endpoint = f"https://{_node_hostname}/{_nginx_path}"
        _local_endpoint = f"http://localhost:{_local_port}"

        offer_data = {
            "from": wallet_address,
            "to": "0x0000000000000000000000000000000000000000",
            "amount": 0,
            "fee": 36,
            "nonce": get_next_nonce(),
            "type": "GPU_MARKETPLACE",
            "chain_id": chain_id,
            "payload": {
                "action": "software_offer",
                "offer_id": offer_id,
                "provider_node_id": provider_node_id,
                "provider_address": wallet_address,
                "service_type": service_type,
                "model": model_or_variant,
                "price": float(price),
                "price_unit": unit,
                "context_window": context_window if service_type == "ollama" else None,
                "deployment_type": deployment_type,
                "gpu_name": gpu_name,
                "gpu_device": gpu_device,
                "gpu_uuid": gpu_uuid,
                "gpu_offer_id": gpu_offer_id,
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
        result = http_client.post("/rpc/transactions/marketplace", json=offer_data)
        success("Software offer listed on marketplace!")
        output(result, ctx.obj.get("output_format", "table"))

        # Auto-register in marketplace service so agents can discover it
        _health_urls = {
            "ollama": "http://localhost:11434/api/tags",
            "whisper": "http://localhost:8110/health",
            "peertube_transcoder": "http://localhost:8220/health",
            "ffmpeg": "http://localhost:8230/health",
        }
        try:
            plugin_client = AITBCHTTPClient(base_url="http://localhost:8102", timeout=5)
            plugin_client.post(
                "/v1/marketplace/software-services",
                json={
                    "service_type": service_type,
                    "model": model_or_variant,
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
                    "gpu_device": gpu_device,
                    "gpu_uuid": gpu_uuid,
                    "gpu_offer_id": gpu_offer_id,
                    "description": description or f"{service_type} — {model_or_variant} at {price} AIT/{unit}",
                    "status": "active",
                },
            )
            info(
                f"Software service registered in marketplace (plugin-id: {service_type}-{model_or_variant.replace(':', '-')})"
            )
        except Exception:
            pass  # Non-fatal — marketplace service may not be running

    except Exception as e:
        error(f"Error creating software offer: {e}")
        raise click.Abort() from e
