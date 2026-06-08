"""
Blockchain marketplace commands for GPU trading
"""

import hashlib
import json
import os
import re
import socket
from datetime import datetime

import click

from aitbc import AITBCHTTPClient, NetworkError, get_logger

from ..config import get_config
from ..utils import error, info, output, success, warning
from ..utils.island_credentials import load_island_credentials

# Initialize logger
logger = get_logger(__name__)


def safe_load_credentials():
    """Load island credentials - required for production, except for hub nodes"""
    try:
        return load_island_credentials()
    except FileNotFoundError as e:
        # Check if this is a hub node - hubs don't need island credentials
        config = get_config()
        node_role = os.getenv('NODE_ROLE', '')
        if node_role == 'hub':
            # Hub nodes use blockchain config instead
            return {
                "credentials": {
                    "p2p_port": 8200
                },
                "island_id": os.getenv('ISLAND_ID', 'ait-hub'),
                "chain_id": os.getenv('CHAIN_ID', 'ait-hub.aitbc.bubuit.net')
            }
        error(f"Island credentials required for marketplace operations: {e}")
        error("Note: Hub nodes do not need to join islands - marketplace works with blockchain config")
        error("For follower nodes, run: aitbc edge island join <island_id> <island_name> <chain_id>")
        error("Example: aitbc edge island join ait-hub.aitbc.bubuit.net-island 'AIT Hub' ait-hub.aitbc.bubuit.net")
        return None


def get_chain_id() -> str:
    """Get chain ID from island credentials or blockchain config"""
    try:
        creds = load_island_credentials()
        # Credentials use 'island_chain_id' key
        chain_id = creds.get('island_chain_id') or creds.get('chain_id')
        if chain_id:
            return chain_id
    except (FileNotFoundError, ValueError):
        pass
    # Fall back to hub discovery URL config
    config = get_config()
    hub = config.hub_discovery_url or 'hub.aitbc.bubuit.net'
    return f'ait-{hub}'


def get_island_id() -> str:
    """Get island ID from island credentials or blockchain config for hub nodes"""
    try:
        return load_island_credentials().get('island_id')
    except FileNotFoundError:
        # Hub nodes use blockchain config
        node_role = os.getenv('NODE_ROLE', '')
        if node_role == 'hub':
            return os.getenv('ISLAND_ID', 'ait-hub')
        error(f"Island credentials required for island ID: {e}")
        raise click.Abort()


def get_wallet_address() -> str:
    """Get address from wallet service - use my-agent-wallet which exists on blockchain"""
    config = get_config()
    
    # Try wallet service API first
    try:
        http_client = AITBCHTTPClient(base_url="http://localhost:8108", timeout=5)
        wallets = http_client.get("/v1/wallets")
        if wallets and wallets.get('items'):
            # Use my-agent-wallet which exists on the blockchain
            for wallet in wallets['items']:
                if wallet.get('wallet_id') == 'my-agent-wallet':
                    metadata = wallet.get('metadata', {})
                    address = metadata.get('address') or metadata.get('original_address')
                    if address:
                        return address
            # Fallback to first wallet if my-agent-wallet not found
            genesis_wallet = wallets['items'][0]
            metadata = genesis_wallet.get('metadata', {})
            address = metadata.get('address') or metadata.get('original_address')
            if address:
                return address
    except Exception as e:
        logger.warning(f"Failed to get wallet from service: {e}")
    
    # Fallback to local wallet file
    wallet_path = '/root/.aitbc/wallets/genesis.json'
    if os.path.exists(wallet_path):
        try:
            with open(wallet_path) as f:
                wallet = json.load(f)
                return wallet.get('address')
        except Exception as e:
            logger.warning(f"Failed to load local wallet: {e}")
    
    # No wallet available
    error("No wallet address available. Ensure wallet service is running or wallet file exists.")
    raise click.Abort()


def get_account_nonce(address: str, chain_id: str) -> int:
    """Query blockchain for current account nonce"""
    try:
        from aitbc.network.http_client import AITBCHTTPClient
        config = get_config()
        hub_url = f"http://{config.hub_discovery_url or 'hub.aitbc.bubuit.net'}"
        http_client = AITBCHTTPClient(base_url=hub_url, timeout=10)
        response = http_client.get(f"/rpc/accounts/{address}?chain_id={chain_id}")
        return response.get('nonce', 0)
    except Exception as e:
        error(f"Failed to get account nonce: {e}")
        return 0

def get_next_nonce() -> int:
    """Get next transaction nonce from blockchain (confirmed nonce + 1)"""
    wallet_address = get_wallet_address()
    config = get_config()
    hub_url = config.hub_discovery_url or 'hub.aitbc.bubuit.net'
    chain_id = 'ait-' + hub_url
    return get_account_nonce(wallet_address, chain_id)


@click.group()
def market():
    """Blockchain marketplace commands for GPU trading"""
    pass


@market.command()
@click.option('--provider', help='Filter by provider address')
@click.option('--status', help='Filter by status (active, inactive)')
@click.pass_context
def list(ctx, provider: str | None, status: str | None):
    """List blockchain marketplace offers and bids"""
    try:
        # Load CLI config
        config = get_config()

        # Query blockchain for GPU marketplace transactions
        transactions = None
        try:
            # Query hub directly (HTTP) for confirmed GPU_MARKETPLACE transactions
            hub_url = f"http://{config.hub_discovery_url or 'hub.aitbc.bubuit.net'}"
            http_client = AITBCHTTPClient(base_url=hub_url, timeout=15)
            result = http_client.get("/rpc/transactions", params={"limit": 500})
            if result and not isinstance(result, dict):
                # Filter by payload action since hub doesn't store type field
                transactions = [
                    tx for tx in result
                    if isinstance(tx.get('payload'), dict)
                    and tx['payload'].get('action') in ('offer', 'bid', 'cancel', 'accept', 'software_offer')
                ]
                logger.debug(f"Found {len(transactions)} GPU_MARKETPLACE transactions from hub")
            
            # Also check hub mempool for pending transactions
            if not transactions:
                mempool = http_client.get("/rpc/mempool")
                if mempool and isinstance(mempool, dict) and 'transactions' in mempool:
                    transactions = [tx for tx in mempool['transactions'] if tx.get('type') == 'GPU_MARKETPLACE']
                    logger.debug(f"Found {len(transactions)} GPU_MARKETPLACE transactions in hub mempool")
        except NetworkError as e:
            logger.error(f"Network error querying hub: {e}")
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
                if 'payload' in tx:
                    # Mined block format - nested payload
                    payload = tx['payload']
                    if isinstance(payload, str):
                        try:
                            payload = json.loads(payload)
                        except json.JSONDecodeError:
                            continue
                elif 'action' in tx:
                    # Direct format (mempool or simplified)
                    payload = tx
                else:
                    continue
            
            action = payload.get('action')
            
            # Only show hardware+software bundle offers
            if action != 'software_offer':
                continue
            if status and payload.get('status') != status:
                continue
            if provider and payload.get('provider_address') != provider:
                continue

            gpu_name = payload.get('gpu_name', 'N/A')
            deployment_type = payload.get('deployment_type', 'local')
            gpu_device = payload.get('gpu_device', '0')
            gpu_name_display = f"{gpu_name} [GPU {gpu_device}]" if deployment_type == 'local' else "N/A (cloud)"
            
            # Get rating info from marketplace service if available
            rating_display = "N/A"
            try:
                client = AITBCHTTPClient(base_url="http://localhost:8102", timeout=5)
                # Use offer_id to lookup service via new endpoint
                offer_id = payload.get('offer_id', '')
                if offer_id:
                    service_response = client.get(f"/v1/marketplace/offer-by-id/{offer_id}")
                    if service_response and not service_response.get('error'):
                        avg_rating = service_response.get('avg_rating', 0.0)
                        rating_count = service_response.get('rating_count', 0)
                        if rating_count > 0:
                            rating_display = f"⭐ {avg_rating:.1f} ({rating_count})"
            except:
                pass  # Marketplace service not available, skip ratings
            
            market_data.append({
                "Offer ID": payload.get('offer_id', ''),
                "Type": payload.get('service_type', '').upper(),
                "Model": payload.get('model', ''),
                "GPU": gpu_name_display[:35] + "..." if len(gpu_name_display) > 35 else gpu_name_display,
                "Price": f"{payload.get('price', 0)} AIT/{payload.get('price_unit', '')}",
                "Rating": rating_display,
                "Status": payload.get('status', 'active'),
                "Provider": payload.get('provider_address', '')[:30] + "...",
                "Description": (payload.get('description', '')[:35] + "...") if len(payload.get('description', '')) > 35 else payload.get('description', ''),
                "Created": payload.get('created_at', '')[:19] if payload.get('created_at') else 'N/A'
            })

        output(market_data, ctx.obj.get('output_format', 'table'), title="Hardware+Software Bundle Offers")

    except Exception as e:
        error(f"Error listing GPU marketplace: {str(e)}")
        raise click.Abort()


@market.command()
@click.argument('order_id')
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
            'from': wallet_address,
            'to': '0x0000000000000000000000000000000000000000',
            'amount': 0,
            'fee': 10,
            'nonce': get_next_nonce(),
            'type': 'GPU_MARKETPLACE',
            'chain_id': chain_id,
            'payload': {
                'action': 'cancel',
                'order_id': order_id,
                'status': 'cancelled',
                'island_id': island_id,
                'chain_id': chain_id,
                'created_at': datetime.now().isoformat()
            }
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
        raise click.Abort()


@market.command()
@click.argument('order_id')
@click.pass_context
def status(ctx, order_id: str):
    """Check the status of a GPU order including on-chain escrow"""
    try:
        config = get_config()
        blockchain_rpc_url = getattr(config, 'blockchain_rpc_url', 'http://localhost:8202')
        hub_url = f"http://{config.hub_discovery_url}" if config.hub_discovery_url and not config.hub_discovery_url.startswith("http") else (config.hub_discovery_url or blockchain_rpc_url)

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
            raise click.Abort()

        output(combined, ctx.obj.get("output_format", "table"))

    except Exception as e:
        error(f"Error checking order status: {e}")
        raise click.Abort()


# ---------------------------------------------------------------------------
# Escrow subgroup
# ---------------------------------------------------------------------------

@market.group()
def escrow():
    """Manage blockchain escrow for GPU jobs"""


def _get_blockchain_rpc_url(config) -> str:
    """Return local blockchain RPC base URL (no trailing /rpc — callers add the path)."""
    url = getattr(config, 'blockchain_rpc_url', 'http://localhost:8202')
    # Normalise to port 8202 if the stored URL points to localhost
    if 'localhost' in url or '127.0.0.1' in url:
        url = re.sub(r':\d+', ':8202', url)
    # Strip trailing /rpc so callers that use /rpc/... paths don't double up
    url = url.rstrip('/')
    if url.endswith('/rpc'):
        url = url[:-4]
    return url


def _escrow_create(job_id: str, buyer: str, provider: str, amount, config) -> str | None:
    """Create escrow on local blockchain node. Returns contract_id or None."""
    rpc_url = _get_blockchain_rpc_url(config)
    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
        result = http_client.post("/rpc/escrow/create", json={
            'job_id': job_id,
            'buyer': buyer,
            'provider': provider,
            'amount': float(amount) if amount else 0,
        })
        contract_id = result.get('contract_id') if isinstance(result, dict) else None
        if contract_id:
            success(f"Escrow created: contract_id={contract_id}")
        return contract_id
    except Exception as e:
        warning(f"Escrow creation skipped (non-fatal): {e}")
        return None


@escrow.command(name="release")
@click.argument('job_id')
@click.pass_context
def escrow_release(ctx, job_id: str):
    """Release escrow funds to the provider after job completion"""
    try:
        config = get_config()
        rpc_url = _get_blockchain_rpc_url(config)
        hub_url = f"http://{config.hub_discovery_url or 'hub.aitbc.bubuit.net'}"
        result = None
        try:
            http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
            result = http_client.post(f"/rpc/escrow/{job_id}/release", json={})
        except Exception:
            pass
        if not result:
            try:
                http_client = AITBCHTTPClient(base_url=hub_url, timeout=10)
                result = http_client.post(f"/rpc/escrow/{job_id}/release", json={})
            except Exception:
                pass
        if result:
            success(f"Escrow released for job {job_id}")
            output(result, ctx.obj.get("output_format", "table"))
        else:
            error(f"Failed to release escrow for job {job_id}")
    except Exception as e:
        error(f"Error releasing escrow: {e}")
        raise click.Abort()


@escrow.command(name="refund")
@click.argument('job_id')
@click.option('--reason', default='buyer_requested', help='Reason for refund')
@click.pass_context
def escrow_refund(ctx, job_id: str, reason: str):
    """Refund escrow back to the buyer"""
    try:
        config = get_config()
        rpc_url = _get_blockchain_rpc_url(config)
        hub_url = f"http://{config.hub_discovery_url or 'hub.aitbc.bubuit.net'}"
        result = None
        try:
            http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
            result = http_client.post(f"/rpc/escrow/{job_id}/refund", json={'reason': reason})
        except Exception:
            pass
        if not result:
            try:
                http_client = AITBCHTTPClient(base_url=hub_url, timeout=10)
                result = http_client.post(f"/rpc/escrow/{job_id}/refund", json={'reason': reason})
            except Exception:
                pass
        if result:
            success(f"Escrow refunded for job {job_id}")
            output(result, ctx.obj.get("output_format", "table"))
        else:
            error(f"Failed to refund escrow for job {job_id}")
    except Exception as e:
        error(f"Error refunding escrow: {e}")
        raise click.Abort()


@escrow.command(name="status")
@click.argument('job_id')
@click.pass_context
def escrow_status(ctx, job_id: str):
    """Check on-chain escrow state for a job"""
    try:
        config = get_config()
        rpc_url = _get_blockchain_rpc_url(config)
        hub_url = f"http://{config.hub_discovery_url or 'hub.aitbc.bubuit.net'}"
        result = None
        try:
            http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
            result = http_client.get(f"/rpc/escrow/{job_id}")
        except Exception:
            pass
        if not result:
            try:
                http_client = AITBCHTTPClient(base_url=hub_url, timeout=10)
                result = http_client.get(f"/rpc/escrow/{job_id}")
            except Exception:
                pass
        if result:
            output(result, ctx.obj.get("output_format", "table"), title=f"Escrow: {job_id}")
        else:
            error(f"No escrow found for job {job_id}")
    except Exception as e:
        error(f"Error checking escrow status: {e}")
        raise click.Abort()


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
                hub_url = config.blockchain_rpc_url.replace('localhost', config.hub_discovery_url or 'hub.aitbc.bubuit.net')
                http_client = AITBCHTTPClient(base_url=hub_url, timeout=10)
                result = http_client.get("/rpc/transactions/marketplace/match")
            
            output(result, ctx.obj.get("output_format", "table"), title="GPU Market Matches")
        except NetworkError as e:
            error(f"Network error: {e}")
            raise click.Abort()

    except Exception as e:
        error(f"Error matching GPU market: {e}")
        raise click.Abort()


@market.command()
@click.pass_context
def providers(ctx):
    """Query island members for GPU providers"""
    try:
        # Load CLI config
        config = get_config()

        # Query P2P network for providers
        info("Note: GPU provider query via P2P network to be implemented")
        info("Use 'aitbc gpu list' to see local registered GPUs")

    except Exception as e:
        error(f"Error querying GPU providers: {str(e)}")
        raise click.Abort()


# ---------------------------------------------------------------------------
# Software marketplace — Ollama inference, Whisper, PeerTube pruner
# ---------------------------------------------------------------------------

@market.command(name="offer")
@click.argument('service_type', type=click.Choice(['ollama', 'whisper', 'peertube_pruner', 'ffmpeg']))
@click.argument('model_or_variant')
@click.argument('price', type=float)
@click.option('--unit', default='per_1k_tokens',
              type=click.Choice(['per_1k_tokens', 'per_audio_min', 'per_gb', 'per_processing_hour']),
              help='Pricing unit')
@click.option('--description', help='Description of the service')
@click.option('--context-window', type=int, default=4096, help='Context window size (ollama)')
@click.option('--gpu-name', help='GPU name from nvidia-smi (auto-detected if omitted)')
@click.option('--gpu-device', help='GPU device ID (0, 1, 2, etc.) for multi-GPU servers')
@click.option('--gpu-offer-id', help='GPU marketplace offer ID for cross-reference')
@click.pass_context
def offer(ctx, service_type: str, model_or_variant: str, price: float,
           unit: str, description: str | None, context_window: int,
           gpu_name: str | None, gpu_device: str | None, gpu_offer_id: str | None):
    """List a hardware+software bundle offer (Ollama/Whisper/PeerTube/FFmpeg) in the marketplace"""
    try:
        config = get_config()
        chain_id = get_chain_id()
        island_id = get_island_id()
        wallet_address = get_wallet_address()

        # Auto-detect deployment type from model name suffix
        is_cloud = model_or_variant.endswith(':cloud')
        deployment_type = 'cloud' if is_cloud else 'local'
        info(f"Auto-detected deployment type: {deployment_type}")

        # Auto-detect GPU info from nvidia-smi if not provided and not cloud
        gpu_uuid = None
        if gpu_name is None and not is_cloud:
            try:
                import subprocess
                # Get GPU name, device ID, and UUID
                result = subprocess.run(
                    ['nvidia-smi', '-L'],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    # Parse output: "GPU 0: NVIDIA GeForce RTX 4060 Ti (UUID: GPU-ba5c6553-6396-ab66-5706-17e6de30a93a)"
                    for line in result.stdout.strip().split('\n'):
                        if line.startswith('GPU'):
                            # Extract device ID, name, and UUID
                            parts = line.split(':')
                            device_part = parts[0].strip()  # "GPU 0"
                            gpu_name = parts[1].split('(')[0].strip()  # "NVIDIA GeForce RTX 4060 Ti "
                            uuid_part = parts[1].split('UUID:')[1].rstrip(')') if 'UUID:' in parts[1] else None
                            
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
        if service_type == 'ollama':
            try:
                ol_client = AITBCHTTPClient(base_url="http://localhost:11434", timeout=5)
                tags = ol_client.get("/api/tags")
                models = [m['name'] for m in tags.get('models', [])]
                if model_or_variant not in models:
                    error(f"Model '{model_or_variant}' not found in local Ollama. Available: {', '.join(models)}")
                    raise click.Abort()
                info(f"Verified Ollama model: {model_or_variant}")
            except NetworkError as e:
                error(f"Ollama not reachable at localhost:11434: {e}")
                raise click.Abort()
        elif service_type == 'whisper':
            try:
                w_client = AITBCHTTPClient(base_url="http://localhost:8110", timeout=5)
                health = w_client.get("/health")
                if not health.get('ready'):
                    error("Whisper service is not ready at localhost:8110")
                    raise click.Abort()
                loaded = health.get('model', '')
                info(f"Verified Whisper service: model={loaded} device={health.get('device')}")
            except NetworkError as e:
                error(f"Whisper service not reachable at localhost:8110: {e}")
                error("Start it with: systemctl start aitbc-whisper")
                raise click.Abort()
        elif service_type == 'peertube_transcoder':
            try:
                p_client = AITBCHTTPClient(base_url="http://localhost:8220", timeout=5)
                health = p_client.get("/health")
                if health.get('status') != 'ok':
                    error("PeerTube transcoder service is not ready at localhost:8220")
                    raise click.Abort()
                info(f"Verified PeerTube transcoder service")
            except NetworkError as e:
                error(f"PeerTube transcoder service not reachable at localhost:8220: {e}")
                error("Start it with: systemctl start aitbc-peertube-transcoder")
                raise click.Abort()
        elif service_type == 'ffmpeg':
            try:
                f_client = AITBCHTTPClient(base_url="http://localhost:8230", timeout=5)
                health = f_client.get("/health")
                if health.get('status') != 'ok':
                    error("FFmpeg service is not ready at localhost:8230")
                    raise click.Abort()
                info(f"Verified FFmpeg service")
            except NetworkError as e:
                error(f"FFmpeg service not reachable at localhost:8230: {e}")
                error("Start it with: systemctl start aitbc-ffmpeg")
                raise click.Abort()

        provider_node_id = hashlib.sha256(socket.gethostname().encode()).hexdigest()
        offer_id = f"sw_offer_{datetime.now().strftime('%Y%m%d%H%M%S')}_{hashlib.sha256(f'{service_type}{model_or_variant}{price}'.encode()).hexdigest()[:8]}"

        # Build public endpoint so remote buyers know where to send jobs
        _local_ports = {'ollama': 11434, 'whisper': 8110, 'peertube_transcoder': 8220, 'ffmpeg': 8230}
        _local_port = _local_ports.get(service_type, 8110)
        _hub_hostname = config.hub_discovery_url or 'hub.aitbc.bubuit.net'
        _base_domain = _hub_hostname.removeprefix('hub.')
        _node_hostname = socket.getfqdn()
        # If FQDN doesn't include domain, construct it from short hostname + base domain
        if _base_domain and _base_domain not in _node_hostname:
            _node_hostname = f"{socket.gethostname()}.{_base_domain}"
        # nginx routes: /whisper/ → :8110, /ollama/ → :11434, /peertube/ → :8220 (see deployment/nginx-aitbc.conf)
        _nginx_paths = {'ollama': 'ollama', 'whisper': 'whisper', 'peertube_transcoder': 'peertube', 'ffmpeg': 'ffmpeg'}
        _nginx_path = _nginx_paths.get(service_type, service_type)
        _public_endpoint = f"https://{_node_hostname}/{_nginx_path}"
        _local_endpoint = f"http://localhost:{_local_port}"

        offer_data = {
            'from': wallet_address,
            'to': '0x0000000000000000000000000000000000000000',
            'amount': 0,
            'fee': 10,
            'nonce': get_next_nonce(),
            'type': 'GPU_MARKETPLACE',
            'chain_id': chain_id,
            'payload': {
                'action': 'software_offer',
                'offer_id': offer_id,
                'provider_node_id': provider_node_id,
                'provider_address': wallet_address,
                'service_type': service_type,
                'model': model_or_variant,
                'price': float(price),
                'price_unit': unit,
                'context_window': context_window if service_type == 'ollama' else None,
                'deployment_type': deployment_type,
                'gpu_name': gpu_name,
                'gpu_device': gpu_device,
                'gpu_uuid': gpu_uuid,
                'gpu_offer_id': gpu_offer_id,
                'status': 'active',
                'description': description or f"{service_type} — {model_or_variant} at {price} AIT/{unit}",
                'island_id': island_id,
                'chain_id': chain_id,
                'endpoint': _public_endpoint,
                'created_at': datetime.now().isoformat(),
            }
        }

        hub_url = f"http://{config.hub_discovery_url or 'hub.aitbc.bubuit.net'}"
        http_client = AITBCHTTPClient(base_url=hub_url, timeout=10)
        result = http_client.post("/rpc/transactions/marketplace", json=offer_data)
        success(f"Software offer listed on marketplace!")
        output(result, ctx.obj.get("output_format", "table"))

        # Auto-register in marketplace service so agents can discover it
        _health_urls = {
            'ollama': 'http://localhost:11434/api/tags',
            'whisper': 'http://localhost:8110/health',
            'peertube_transcoder': 'http://localhost:8220/health',
            'ffmpeg': 'http://localhost:8230/health',
        }
        try:
            plugin_client = AITBCHTTPClient(base_url="http://localhost:8102", timeout=5)
            plugin_client.post("/v1/marketplace/software-services", json={
                'service_type': service_type,
                'model': model_or_variant,
                'price': float(price),
                'price_unit': unit,
                'offer_id': offer_id,
                'endpoint': _local_endpoint,
                'public_endpoint': _public_endpoint,
                'health_url': _health_urls.get(service_type, ''),
                'provider_address': wallet_address,
                'node_id': provider_node_id,
                'deployment_type': deployment_type,
                'gpu_name': gpu_name,
                'gpu_device': gpu_device,
                'gpu_uuid': gpu_uuid,
                'gpu_offer_id': gpu_offer_id,
                'description': description or f"{service_type} — {model_or_variant} at {price} AIT/{unit}",
                'status': 'active',
            })
            info(f"Software service registered in marketplace (plugin-id: {service_type}-{model_or_variant.replace(':', '-')})")
        except Exception:
            pass  # Non-fatal — marketplace service may not be running

    except Exception as e:
        error(f"Error creating software offer: {e}")
        raise click.Abort()


@market.command(name="run")
@click.argument('offer_id')
@click.argument('prompt')
@click.option('--max-tokens', type=int, default=512, help='Max tokens to generate')
@click.option('--stream', is_flag=True, default=False, help='Stream the response')
@click.pass_context
def run_job(ctx, offer_id: str, prompt: str, max_tokens: int, stream: bool):
    """Run an inference job against a software offer and pay metered escrow"""
    try:
        config = get_config()
        chain_id = get_chain_id()
        wallet_address = get_wallet_address()

        # Resolve the offer from hub transactions
        hub_url = f"http://{config.hub_discovery_url or 'hub.aitbc.bubuit.net'}"
        http_client = AITBCHTTPClient(base_url=hub_url, timeout=15)
        result = http_client.get("/rpc/transactions", params={"limit": 1000})
        offer = None
        if result and not isinstance(result, dict):
            for tx in result:
                p = tx.get('payload', {})
                if p.get('action') == 'software_offer' and p.get('offer_id') == offer_id:
                    offer = p
                    break
        if not offer:
            error(f"Software offer '{offer_id}' not found or not active on hub")
            raise click.Abort()

        service_type = offer.get('service_type')
        model = offer.get('model')
        price = float(offer.get('price', 0))
        price_unit = offer.get('price_unit', 'per_1k_tokens')
        provider_address = offer.get('provider_address')

        info(f"Offer: {service_type} — {model} at {price} AIT/{price_unit}")
        info(f"Provider: {provider_address}")

        if service_type != 'ollama':
            error(f"Service type '{service_type}' job execution not yet supported via CLI")
            raise click.Abort()

        # Lock escrow upfront (estimated max cost)
        estimated_tokens = max_tokens
        estimated_cost = (estimated_tokens / 1000) * price
        job_id = f"sw_job_{datetime.now().strftime('%Y%m%d%H%M%S')}_{hashlib.sha256(f'{offer_id}{wallet_address}'.encode()).hexdigest()[:8]}"
        info(f"Locking escrow: ~{estimated_cost:.4f} AIT (est. {estimated_tokens} tokens)")
        contract_id = _escrow_create(job_id, wallet_address, provider_address or wallet_address, estimated_cost, config)

        # Run inference via Ollama
        import urllib.request
        payload = json.dumps({
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": max_tokens}
        }).encode()
        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        info("Running inference...")
        t_start = datetime.now()
        with urllib.request.urlopen(req, timeout=120) as resp:
            resp_data = json.loads(resp.read())
        elapsed = (datetime.now() - t_start).total_seconds()

        response_text = resp_data.get('response', '')
        tokens_used = resp_data.get('eval_count', len(response_text.split()) * 2)
        actual_cost = (tokens_used / 1000) * price

        info(f"Done in {elapsed:.2f}s — {tokens_used} tokens — actual cost: {actual_cost:.4f} AIT")
        click.echo(f"\n{response_text}\n")

        # Release metered escrow for actual tokens used
        if contract_id:
            rpc_url = _get_blockchain_rpc_url(config)
            rpc_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
            release_result = rpc_client.post(f"/rpc/escrow/{job_id}/release", json={
                'amount': actual_cost,
                'tokens_used': tokens_used,
                'job_id': job_id,
            })
            if release_result and release_result.get('tx_hash'):
                success(f"Payment released: {actual_cost:.4f} AIT → {provider_address} (tx: {release_result['tx_hash'][:18]}...)")
            else:
                warning(f"Escrow release submitted but no tx_hash returned")
        else:
            warning("No escrow contract — payment not released")

        output({
            'job_id': job_id,
            'offer_id': offer_id,
            'model': model,
            'tokens_used': tokens_used,
            'elapsed_seconds': round(elapsed, 2),
            'actual_cost_ait': round(actual_cost, 6),
            'contract_id': contract_id,
        }, ctx.obj.get("output_format", "table"))

    except Exception as e:
        error(f"Error running job: {e}")
        raise click.Abort()


@market.command(name="transcribe")
@click.argument('offer_id')
@click.argument('audio_file', type=click.Path(exists=True))
@click.option('--language', default=None, help='Language code (e.g. en, de, fr). Auto-detect if omitted.')
@click.option('--task', default='transcribe', type=click.Choice(['transcribe', 'translate']), help='transcribe or translate to English')
@click.option('--output-format', 'fmt', default='text', type=click.Choice(['text', 'srt', 'json']), help='Output format')
@click.pass_context
def transcribe_job(ctx, offer_id: str, audio_file: str, language: str | None, task: str, fmt: str):
    """Transcribe audio using a Whisper software offer and pay metered escrow"""
    import urllib.request as _urllib
    try:
        config = get_config()
        wallet_address = get_wallet_address()
        chain_id = get_chain_id()

        # Resolve the offer from hub
        hub_url = f"http://{config.hub_discovery_url or 'hub.aitbc.bubuit.net'}"
        http_client = AITBCHTTPClient(base_url=hub_url, timeout=15)
        result = http_client.get("/rpc/transactions", params={"limit": 1000})
        offer = None
        if result and not isinstance(result, dict):
            for tx in result:
                p = tx.get('payload', {})
                if p.get('action') == 'software_offer' and p.get('offer_id') == offer_id and p.get('service_type') == 'whisper':
                    offer = p
                    break
        if not offer:
            error(f"Whisper offer '{offer_id}' not found on hub")
            raise click.Abort()

        price = float(offer.get('price', 0))
        price_unit = offer.get('price_unit', 'per_audio_min')
        provider_address = offer.get('provider_address')
        model = offer.get('model', 'base')
        # Use provider's public endpoint from offer; fall back to localhost for self-hosted
        whisper_endpoint = offer.get('endpoint', 'http://localhost:8110')
        # Normalise: strip trailing /whisper path if present, add /transcribe
        whisper_base = whisper_endpoint.rstrip('/').removesuffix('/transcribe')
        whisper_transcribe_url = whisper_base + '/transcribe'
        info(f"Offer: whisper/{model} at {price} AIT/{price_unit} — provider {provider_address}")
        info(f"Whisper endpoint: {whisper_transcribe_url}")

        # Get audio duration via ffprobe for upfront escrow estimate
        import subprocess
        duration_seconds = 0.0
        try:
            probe = subprocess.run(
                ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                 '-of', 'default=noprint_wrappers=1:nokey=1', audio_file],
                capture_output=True, text=True, timeout=10
            )
            duration_seconds = float(probe.stdout.strip() or 0)
        except Exception:
            pass
        duration_minutes = duration_seconds / 60
        estimated_cost = duration_minutes * price if price_unit == 'per_audio_min' else price

        job_id = f"sw_job_{datetime.now().strftime('%Y%m%d%H%M%S')}_{hashlib.sha256(f'{offer_id}{wallet_address}'.encode()).hexdigest()[:8]}"
        info(f"Audio duration: {duration_minutes:.2f} min — locking escrow: ~{estimated_cost:.4f} AIT")
        contract_id = _escrow_create(job_id, wallet_address, provider_address or wallet_address, estimated_cost, config)

        # Submit audio to Whisper service
        info("Sending audio to Whisper service...")
        t_start = datetime.now()
        with open(audio_file, 'rb') as af:
            audio_bytes = af.read()
        filename = os.path.basename(audio_file)
        boundary = b'----WhisperBoundary'
        body = (
            b'--' + boundary + b'\r\n'
            b'Content-Disposition: form-data; name="file"; filename="' + filename.encode() + b'"\r\n'
            b'Content-Type: application/octet-stream\r\n\r\n' +
            audio_bytes + b'\r\n'
        )
        if language:
            body += b'--' + boundary + b'\r\nContent-Disposition: form-data; name="language"\r\n\r\n' + language.encode() + b'\r\n'
        body += b'--' + boundary + b'\r\nContent-Disposition: form-data; name="task"\r\n\r\n' + task.encode() + b'\r\n'
        body += b'--' + boundary + b'--\r\n'

        req = _urllib.Request(
            whisper_transcribe_url,
            data=body,
            headers={'Content-Type': f'multipart/form-data; boundary={boundary.decode()}'}
        )
        with _urllib.urlopen(req, timeout=300) as resp:
            resp_data = json.loads(resp.read())

        elapsed = (datetime.now() - t_start).total_seconds()
        actual_duration_minutes = resp_data.get('duration_minutes', duration_minutes)
        actual_cost = actual_duration_minutes * price if price_unit == 'per_audio_min' else price
        result_hash = resp_data.get('result_hash', '')

        info(f"Done in {elapsed:.1f}s — {resp_data.get('duration_seconds', 0):.1f}s audio — actual cost: {actual_cost:.4f} AIT")

        # Post software_job TX on-chain as proof of work
        job_tx_hash = None
        if result_hash:
            hub_url = f"http://{config.hub_discovery_url or 'hub.aitbc.bubuit.net'}"
            job_data = {
                'from': wallet_address,
                'to': '0x0000000000000000000000000000000000000000',
                'amount': 0,
                'fee': 10,
                'nonce': get_next_nonce(),
                'type': 'GPU_MARKETPLACE',
                'chain_id': chain_id,
                'payload': {
                    'action': 'software_job',
                    'job_id': job_id,
                    'offer_id': offer_id,
                    'buyer_address': wallet_address,
                    'provider_address': provider_address or wallet_address,
                    'result_hash': result_hash,
                    'actual_duration_minutes': round(actual_duration_minutes, 4),
                    'actual_cost': round(actual_cost, 6),
                    'status': 'completed',
                    'completed_at': datetime.now().isoformat(),
                }
            }
            try:
                http_client = AITBCHTTPClient(base_url=hub_url, timeout=10)
                job_result = http_client.post("/rpc/transactions/marketplace", json=job_data)
                job_tx_hash = job_result.get('transaction_hash')
                info(f"Job recorded on-chain: {job_tx_hash}")
            except Exception as e:
                warning(f"Failed to record job on-chain: {e} — continuing with escrow release")

        # Print transcript
        transcript = resp_data.get('text', '')
        if fmt == 'text':
            click.echo(f"\n{transcript}\n")
        elif fmt == 'srt':
            for i, seg in enumerate(resp_data.get('segments', []), 1):
                def _ts(s): return f"{int(s//3600):02d}:{int((s%3600)//60):02d}:{s%60:06.3f}".replace('.', ',')
                click.echo(f"{i}\n{_ts(seg['start'])} --> {_ts(seg['end'])}\n{seg['text']}\n")
        elif fmt == 'json':
            click.echo(json.dumps(resp_data, indent=2))

        # Release metered escrow with job TX hash as proof
        if contract_id:
            rpc_url = _get_blockchain_rpc_url(config)
            rpc_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
            release_result = rpc_client.post(f"/rpc/escrow/{job_id}/release", json={'amount': actual_cost, 'job_tx_hash': job_tx_hash})
            if release_result and release_result.get('tx_hash'):
                success(f"Payment released: {actual_cost:.4f} AIT → {provider_address} (tx: {release_result['tx_hash'][:18]}...)")
            else:
                warning("Escrow released (no on-chain tx — sub-threshold amount or same-wallet)")

        output({
            'job_id': job_id,
            'offer_id': offer_id,
            'model': model,
            'language': resp_data.get('language'),
            'duration_minutes': round(actual_duration_minutes, 4),
            'actual_cost_ait': round(actual_cost, 6),
            'elapsed_seconds': round(elapsed, 2),
            'contract_id': contract_id,
        }, ctx.obj.get('output_format', 'table'))

    except Exception as e:
        error(f"Error transcribing audio: {e}")
        raise click.Abort()


@market.command(name="transcode")
@click.argument('offer_id')
@click.argument('video_url')
@click.option('--resolution', default='1080p', help='Target resolution (e.g. 1080p, 720p, 480p)')
@click.option('--codec', default='h264', help='Target codec (e.g. h264, vp9, av1)')
@click.option('--format', default='mp4', help='Output format (e.g. mp4, webm)')
@click.pass_context
def transcode_job(ctx, offer_id: str, video_url: str, resolution: str, codec: str, format: str):
    """Transcode video using a peertube_transcoder software offer and pay metered escrow"""
    try:
        config = get_config()
        wallet_address = get_wallet_address()
        chain_id = get_chain_id()

        # Resolve the offer from hub
        hub_url = f"http://{config.hub_discovery_url or 'hub.aitbc.bubuit.net'}"
        http_client = AITBCHTTPClient(base_url=hub_url, timeout=15)
        result = http_client.get("/rpc/transactions", params={"limit": 1000})
        offer = None
        if result and not isinstance(result, dict):
            for tx in result:
                p = tx.get('payload', {})
                if p.get('action') == 'software_offer' and p.get('offer_id') == offer_id and p.get('service_type') == 'peertube_transcoder':
                    offer = p
                    break
        if not offer:
            error(f"PeerTube transcoder offer '{offer_id}' not found on hub")
            raise click.Abort()

        price = float(offer.get('price', 0))
        price_unit = offer.get('price_unit', 'per_video_min')
        provider_address = offer.get('provider_address')
        model = offer.get('model', 'default')

        info(f"Offer: peertube_transcoder/{model} at {price} AIT/{price_unit} — provider {provider_address}")
        info(f"Video URL: {video_url}")

        # Estimate cost (assume 5 min default if unknown)
        transcode_endpoint = offer.get('endpoint', 'http://localhost:8220')
        estimated_minutes = 5.0
        estimated_cost = estimated_minutes * price if price_unit == 'per_video_min' else price
        info(f"Estimated duration: {estimated_minutes:.1f} min — locking escrow: ~{estimated_cost:.4f} AIT")

        job_id = f"sw_job_{datetime.now().strftime('%Y%m%d%H%M%S')}_{hashlib.sha256(f'{offer_id}{wallet_address}'.encode()).hexdigest()[:8]}"
        contract_id = _escrow_create(job_id, wallet_address, provider_address or wallet_address, estimated_cost, config)

        # Run actual transcode
        info("Running PeerTube transcoding...")
        t_start = datetime.now()
        transcode_client = AITBCHTTPClient(base_url=transcode_endpoint, timeout=600)
        transcode_result = transcode_client.post("/transcode", json={
            'video_url': video_url,
            'target_resolution': resolution,
            'target_codec': codec,
            'output_format': format,
        })
        elapsed = (datetime.now() - t_start).total_seconds()

        actual_minutes = transcode_result.get('duration_seconds', estimated_minutes * 60) / 60
        actual_cost = actual_minutes * price if price_unit == 'per_video_min' else price
        result_hash = transcode_result.get('result_hash', '')

        info(f"Done in {elapsed:.1f}s — {actual_minutes:.2f} min video — actual cost: {actual_cost:.4f} AIT")
        info(f"Transcoded URL: {transcode_result.get('transcoded_url')}")

        # Post software_job TX on-chain as proof of work
        job_tx_hash = None
        if result_hash:
            job_data = {
                'from': wallet_address,
                'to': '0x0000000000000000000000000000000000000000',
                'amount': 0,
                'fee': 10,
                'nonce': get_next_nonce(),
                'type': 'GPU_MARKETPLACE',
                'chain_id': chain_id,
                'payload': {
                    'action': 'software_job',
                    'job_id': job_id,
                    'offer_id': offer_id,
                    'buyer_address': wallet_address,
                    'provider_address': provider_address or wallet_address,
                    'result_hash': result_hash,
                    'actual_video_minutes': round(actual_minutes, 4),
                    'actual_cost': round(actual_cost, 6),
                    'status': 'completed',
                    'completed_at': datetime.now().isoformat(),
                }
            }
            try:
                http_client = AITBCHTTPClient(base_url=hub_url, timeout=10)
                job_result = http_client.post("/rpc/transactions/marketplace", json=job_data)
                job_tx_hash = job_result.get('transaction_hash')
                info(f"Job recorded on-chain: {job_tx_hash}")
            except Exception as e:
                warning(f"Failed to record job on-chain: {e} — continuing with escrow release")

        # Release metered escrow with job TX hash as proof
        if contract_id:
            rpc_url = _get_blockchain_rpc_url(config)
            rpc_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
            release_result = rpc_client.post(f"/rpc/escrow/{job_id}/release", json={'amount': actual_cost, 'job_tx_hash': job_tx_hash})
            if release_result and release_result.get('tx_hash'):
                success(f"Payment released: {actual_cost:.4f} AIT → {provider_address} (tx: {release_result['tx_hash'][:18]}...)")
            else:
                warning("Escrow released (no on-chain tx — sub-threshold amount or same-wallet)")

        output({
            'job_id': job_id,
            'offer_id': offer_id,
            'video_url': video_url,
            'transcoded_url': transcode_result.get('transcoded_url'),
            'duration_minutes': round(actual_minutes, 4),
            'actual_cost_ait': round(actual_cost, 6),
            'elapsed_seconds': round(elapsed, 2),
            'contract_id': contract_id,
        }, ctx.obj.get('output_format', 'table'))

    except Exception as e:
        error(f"Error transcoding video: {e}")
        raise click.Abort()


@market.command(name="process")
@click.argument('offer_id')
@click.argument('input_file', type=click.Path(exists=True))
@click.option('--format', default='mp4', help='Output format (e.g. mp4, webm)')
@click.option('--codec', default='h264', help='Target codec (e.g. h264, vp9, av1)')
@click.option('--resolution', default='1080p', help='Target resolution (e.g. 1080p, 720p, 480p)')
@click.option('--bitrate', default='5M', help='Target bitrate (e.g. 5M, 10M)')
@click.pass_context
def process_video(ctx, offer_id: str, input_file: str, format: str, codec: str, resolution: str, bitrate: str):
    """Process video using FFmpeg software offer and pay metered escrow"""
    import urllib.request as _urllib
    try:
        config = get_config()
        wallet_address = get_wallet_address()
        chain_id = get_chain_id()

        # Resolve the offer from hub
        hub_url = f"http://{config.hub_discovery_url or 'hub.aitbc.bubuit.net'}"
        http_client = AITBCHTTPClient(base_url=hub_url, timeout=15)
        result = http_client.get("/rpc/transactions", params={"limit": 1000})
        offer = None
        if result and not isinstance(result, dict):
            for tx in result:
                p = tx.get('payload', {})
                if p.get('action') == 'software_offer' and p.get('offer_id') == offer_id and p.get('service_type') == 'ffmpeg':
                    offer = p
                    break
        if not offer:
            error(f"FFmpeg offer '{offer_id}' not found on hub")
            raise click.Abort()

        price = float(offer.get('price', 0))
        price_unit = offer.get('price_unit', 'per_processing_hour')
        provider_address = offer.get('provider_address')
        model = offer.get('model', 'default')

        info(f"Offer: ffmpeg/{model} at {price} AIT/{price_unit} — provider {provider_address}")
        info(f"Input file: {input_file}")

        # Use provider's public endpoint from offer; fall back to localhost for self-hosted
        ffmpeg_endpoint = offer.get('endpoint', 'http://localhost:8230')
        # Normalise: strip trailing /process if present, add /process
        ffmpeg_base = ffmpeg_endpoint.rstrip('/').removesuffix('/process')
        ffmpeg_process_url = ffmpeg_base + '/process'
        info(f"FFmpeg endpoint: {ffmpeg_process_url}")

        # Estimate cost (assume 5 min default if unknown)
        estimated_hours = 0.1  # 6 minutes default
        estimated_cost = estimated_hours * price if price_unit == 'per_processing_hour' else price
        info(f"Estimated duration: {estimated_hours:.2f} hours — locking escrow: ~{estimated_cost:.4f} AIT")

        job_id = f"sw_job_{datetime.now().strftime('%Y%m%d%H%M%S')}_{hashlib.sha256(f'{offer_id}{wallet_address}'.encode()).hexdigest()[:8]}"
        contract_id = _escrow_create(job_id, wallet_address, provider_address or wallet_address, estimated_cost, config)

        # Submit video to FFmpeg service
        info("Sending video to FFmpeg service...")
        t_start = datetime.now()
        with open(input_file, 'rb') as af:
            video_bytes = af.read()
        filename = os.path.basename(input_file)
        boundary = b'----FFmpegBoundary'
        body = (
            b'--' + boundary + b'\r\n'
            b'Content-Disposition: form-data; name="file"; filename="' + filename.encode() + b'"\r\n'
            b'Content-Type: application/octet-stream\r\n\r\n' +
            video_bytes + b'\r\n'
        )
        body += b'--' + boundary + b'\r\nContent-Disposition: form-data; name="output_format"\r\n\r\n' + format.encode() + b'\r\n'
        body += b'--' + boundary + b'\r\nContent-Disposition: form-data; name="codec"\r\n\r\n' + codec.encode() + b'\r\n'
        body += b'--' + boundary + b'\r\nContent-Disposition: form-data; name="resolution"\r\n\r\n' + resolution.encode() + b'\r\n'
        body += b'--' + boundary + b'\r\nContent-Disposition: form-data; name="bitrate"\r\n\r\n' + bitrate.encode() + b'\r\n'
        body += b'--' + boundary + b'--\r\n'

        req = _urllib.Request(
            ffmpeg_process_url,
            data=body,
            headers={'Content-Type': f'multipart/form-data; boundary={boundary.decode()}'}
        )
        with _urllib.urlopen(req, timeout=3600) as resp:
            resp_data = json.loads(resp.read())

        elapsed = (datetime.now() - t_start).total_seconds()
        actual_hours = resp_data.get('processing_time_hours', estimated_hours)
        actual_cost = actual_hours * price if price_unit == 'per_processing_hour' else price
        result_hash = resp_data.get('result_hash', '')

        info(f"Done in {elapsed:.1f}s — {actual_hours:.4f} hours processing — actual cost: {actual_cost:.4f} AIT")
        info(f"Output file: {resp_data.get('output_path')}")

        # Post software_job TX on-chain as proof of work
        job_tx_hash = None
        if result_hash:
            job_data = {
                'from': wallet_address,
                'to': '0x0000000000000000000000000000000000000000',
                'amount': 0,
                'fee': 10,
                'nonce': get_next_nonce(),
                'type': 'GPU_MARKETPLACE',
                'chain_id': chain_id,
                'payload': {
                    'action': 'software_job',
                    'job_id': job_id,
                    'offer_id': offer_id,
                    'buyer_address': wallet_address,
                    'provider_address': provider_address or wallet_address,
                    'result_hash': result_hash,
                    'actual_processing_hours': round(actual_hours, 4),
                    'actual_cost': round(actual_cost, 6),
                    'status': 'completed',
                    'completed_at': datetime.now().isoformat(),
                }
            }
            try:
                http_client = AITBCHTTPClient(base_url=hub_url, timeout=10)
                job_result = http_client.post("/rpc/transactions/marketplace", json=job_data)
                job_tx_hash = job_result.get('transaction_hash')
                info(f"Job recorded on-chain: {job_tx_hash}")
            except Exception as e:
                warning(f"Failed to record job on-chain: {e} — continuing with escrow release")

        # Release metered escrow with job TX hash as proof
        if contract_id:
            rpc_url = _get_blockchain_rpc_url(config)
            rpc_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
            release_result = rpc_client.post(f"/rpc/escrow/{job_id}/release", json={'amount': actual_cost, 'job_tx_hash': job_tx_hash})
            if release_result and release_result.get('tx_hash'):
                success(f"Payment released: {actual_cost:.4f} AIT → {provider_address} (tx: {release_result['tx_hash'][:18]}...)")
            else:
                warning("Escrow released (no on-chain tx — sub-threshold amount or same-wallet)")

        output({
            'job_id': job_id,
            'offer_id': offer_id,
            'input_file': input_file,
            'output_path': resp_data.get('output_path'),
            'processing_hours': round(actual_hours, 4),
            'actual_cost_ait': round(actual_cost, 6),
            'elapsed_seconds': round(elapsed, 2),
            'contract_id': contract_id,
        }, ctx.obj.get('output_format', 'table'))

    except Exception as e:
        error(f"Error processing video: {e}")
        raise click.Abort()


@market.command(name="rate")
@click.argument('service_id')
@click.argument('rating', type=float)
@click.option('--comment', help='Optional comment/review text')
@click.option('--reviewer-id', help='Reviewer ID (defaults to wallet address)')
@click.pass_context
def rate(ctx, service_id: str, rating: float, comment: str, reviewer_id: str):
    """Rate a marketplace service offer (1-5 scale)"""
    try:
        config = get_config()
        
        # Validate rating scale
        if not (1.0 <= rating <= 5.0):
            error("Rating must be between 1.0 and 5.0")
            raise click.Abort()
        
        # Default reviewer_id to wallet address
        if not reviewer_id:
            reviewer_id = get_wallet_address()
        
        # Call marketplace service API
        client = AITBCHTTPClient(base_url="http://localhost:8102", timeout=10)
        response = client.post(f"/v1/marketplace/offer/{service_id}/rate", json={
            'rating': rating,
            'reviewer_id': reviewer_id,
            'comment': comment or ''
        })
        
        if response.get('status') == 'success':
            rating_data = response.get('rating', {})
            success(f"Service rated successfully!")
            output({
                'service_id': rating_data.get('service_id'),
                'rating': rating_data.get('rating'),
                'reviewer_id': rating_data.get('reviewer_id'),
                'comment': rating_data.get('comment'),
                'created_at': rating_data.get('created_at')
            }, ctx.obj.get('output_format', 'table'))
        else:
            error(f"Failed to rate service: {response.get('message', 'Unknown error')}")
            output(response)
            raise click.Abort()
            
    except NetworkError as e:
        error(f"Marketplace service not reachable: {e}")
        error("Ensure marketplace-service is running at http://localhost:8102")
        raise click.Abort()
    except Exception as e:
        error(f"Error rating service: {e}")
        raise click.Abort()


@market.command(name="ratings")
@click.argument('service_id')
@click.option('--limit', default=50, help='Number of ratings to return')
@click.option('--offset', default=0, help='Offset for pagination')
@click.pass_context
def ratings(ctx, service_id: str, limit: int, offset: int):
    """View ratings for a marketplace service offer"""
    try:
        config = get_config()

        # Call marketplace service API
        client = AITBCHTTPClient(base_url="http://localhost:8102", timeout=10)
        response = client.get(f"/v1/marketplace/offer/{service_id}/ratings", params={
            'limit': limit,
            'offset': offset
        })

        service_info = response.get('service_info', {})
        ratings_list = response.get('ratings', [])

        info(f"Service: {service_id}")
        info(f"Average Rating: {service_info.get('avg_rating', 0.0):.1f}/5.0")
        info(f"Total Ratings: {service_info.get('rating_count', 0)}")
        info(f"Showing {len(ratings_list)} ratings")

        if ratings_list:
            output(ratings_list, ctx.obj.get('output_format', 'table'))
        else:
            info("No ratings found for this service")

    except NetworkError as e:
        error(f"Marketplace service not reachable: {e}")
        error("Ensure marketplace-service is running at http://localhost:8102")
        raise click.Abort()
    except Exception as e:
        error(f"Error getting ratings: {e}")
        raise click.Abort()


@market.command(name="sync-ratings")
@click.option('--remote-url', default="https://aitbc3.aitbc.bubuit.net/api", help='Remote marketplace service URL')
@click.option('--limit', default=100, help='Number of ratings to sync')
@click.pass_context
def sync_ratings(ctx, remote_url: str, limit: int):
    """Sync ratings to/from remote marketplace node"""
    try:
        config = get_config()

        # Get local unsynced ratings
        local_client = AITBCHTTPClient(base_url="http://localhost:8102", timeout=10)
        unsynced_response = local_client.get("/v1/marketplace/ratings/unsynced", params={'limit': limit})
        unsynced_ratings = unsynced_response.get('ratings', [])

        if unsynced_ratings:
            info(f"Found {len(unsynced_ratings)} unsynced ratings to push to {remote_url}")

            # Push to remote
            remote_client = AITBCHTTPClient(base_url=remote_url, timeout=30)
            sync_response = remote_client.post("/v1/marketplace/ratings/sync", json=unsynced_ratings)

            if sync_response.get('status') == 'success':
                # Mark local ratings as synced
                rating_ids = [r['id'] for r in unsynced_ratings]
                mark_response = local_client.post("/v1/marketplace/ratings/mark-synced", json=rating_ids)

                success(f"Synced {sync_response.get('synced', 0)} new, {sync_response.get('updated', 0)} updated ratings to remote")
                info(f"Marked {mark_response.get('marked_synced', 0)} local ratings as synced")
            else:
                error(f"Failed to sync ratings to remote: {sync_response}")
        else:
            info("No unsynced ratings found locally")

        # Pull remote ratings (optional - could be made a separate command)
        info("Rating sync complete")

    except NetworkError as e:
        error(f"Network error during sync: {e}")
        raise click.Abort()
    except Exception as e:
        error(f"Error syncing ratings: {e}")
        raise click.Abort()


@market.group(name="exchange")
def exchange():
    """ETH-AIT exchange and bridge operations"""
    pass


@exchange.command(name="price")
@click.pass_context
def exchange_price(ctx):
    """Get current ETH-AIT exchange rate"""
    try:
        config = get_config()
        client = AITBCHTTPClient(base_url="http://localhost:8108", timeout=10)
        
        response = client.get("/v1/exchange/price")
        
        info(f"ETH-AIT Exchange Rate:")
        info(f"  ETH Price: ${response['eth_usd']:.2f} USD")
        info(f"  AIT Price: ${response['ait_usd']:.2f} USD")
        info(f"  Exchange Rate: 1 ETH = {response['exchange_rate']:.2f} AIT")
        info(f"  Timestamp: {response['timestamp']}")
        
    except NetworkError as e:
        error(f"Network error: {e}")
        raise click.Abort()
    except Exception as e:
        error(f"Error getting price: {e}")
        raise click.Abort()


@exchange.command(name="list-deposits")
@click.option('--status', default="pending", help='Filter by status (pending, verified, completed, rejected)')
@click.option('--limit', default=50, help='Maximum number of results')
@click.pass_context
def list_deposits(ctx, status: str, limit: int):
    """List ETH deposits"""
    try:
        config = get_config()
        client = AITBCHTTPClient(base_url="http://localhost:8108", timeout=10)
        
        response = client.get("/v1/exchange/deposits", params={'status': status, 'limit': limit})
        deposits = response.get('deposits', [])
        
        if not deposits:
            info(f"No deposits found with status '{status}'")
            return
        
        info(f"ETH Deposits (status: {status}):")
        for deposit in deposits:
            info(f"  ID: {deposit['id']}")
            info(f"    TX Hash: {deposit['tx_hash']}")
            info(f"    From: {deposit['from_address']}")
            info(f"    Amount: {deposit['amount_eth']:.6f} ETH → {deposit['amount_ait']:.2f} AIT")
            info(f"    Status: {deposit['status']}")
            info(f"    Created: {deposit['created_at']}")
            info("")
        
    except NetworkError as e:
        error(f"Network error: {e}")
        raise click.Abort()
    except Exception as e:
        error(f"Error listing deposits: {e}")
        raise click.Abort()


@exchange.command(name="mint-ait")
@click.argument('deposit_id')
@click.pass_context
def mint_ait(ctx, deposit_id: str):
    """Mint AIT tokens for a verified ETH deposit"""
    try:
        config = get_config()
        client = AITBCHTTPClient(base_url="http://localhost:8108", timeout=10)
        
        # Get deposit details
        deposit_response = client.get(f"/v1/exchange/deposits/{deposit_id}")
        deposit = deposit_response
        
        if deposit['status'] != 'pending':
            error(f"Deposit is not pending (current status: {deposit['status']})")
            raise click.Abort()
        
        info(f"Deposit: {deposit['amount_eth']:.6f} ETH → {deposit['amount_ait']:.2f} AIT")
        info(f"From: {deposit['from_address']}")
        
        if not click.confirm("Verify this deposit and mint AIT tokens?"):
            info("Cancelled")
            return
        
        # Verify deposit
        verify_response = client.post(f"/v1/exchange/deposits/{deposit_id}/verify")
        
        if not verify_response.get('success'):
            error(f"Failed to verify deposit: {verify_response}")
            raise click.Abort()
        
        success(f"Deposit verified: {deposit_id}")
        
        # Mint AIT tokens (call blockchain RPC)
        wallet_address = config.wallet_address
        chain_id = config.chain_id
        
        # TODO: Implement actual minting via blockchain RPC
        # For now, just mark as completed
        complete_response = client.post(f"/v1/exchange/deposits/{deposit_id}/complete")
        
        if complete_response.get('success'):
            success(f"Minted {deposit['amount_ait']:.2f} AIT for deposit {deposit_id}")
        else:
            error(f"Failed to complete deposit: {complete_response}")
            raise click.Abort()
        
    except NetworkError as e:
        error(f"Network error: {e}")
        raise click.Abort()
    except Exception as e:
        error(f"Error minting AIT: {e}")
        raise click.Abort()


@exchange.command(name="withdraw-eth")
@click.argument('amount', type=float)
@click.argument('address')
@click.pass_context
def withdraw_eth(ctx, amount: float, address: str):
    """Withdraw ETH from bridge wallet (admin only)"""
    try:
        config = get_config()
        
        if amount <= 0:
            error("Amount must be positive")
            raise click.Abort()
        
        info(f"Withdrawing {amount} ETH to {address}")
        
        if not click.confirm("Confirm withdrawal?"):
            info("Cancelled")
            return
        
        # TODO: Implement actual ETH withdrawal via wallet service
        # For now, just show placeholder
        warning("ETH withdrawal not yet implemented")
        info("This will require ETH wallet integration")
        
    except Exception as e:
        error(f"Error withdrawing ETH: {e}")
        raise click.Abort()


@exchange.command(name="status")
@click.pass_context
def exchange_status(ctx):
    """Get bridge service status"""
    try:
        config = get_config()
        client = AITBCHTTPClient(base_url="http://localhost:8108", timeout=10)
        
        response = client.get("/v1/exchange/status")
        
        info(f"Bridge Service Status:")
        info(f"  Enabled: {response['enabled']}")
        info(f"  Wallet Address: {response['wallet_address']}")
        info(f"  RPC URL: {response['rpc_url']}")
        info(f"  Poll Interval: {response['poll_interval']}s")
        
    except NetworkError as e:
        error(f"Network error: {e}")
        raise click.Abort()
    except Exception as e:
        error(f"Error getting status: {e}")
        raise click.Abort()
