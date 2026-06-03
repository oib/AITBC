"""
Blockchain marketplace commands for GPU trading
"""

import hashlib
import json
import os
import socket
from datetime import datetime

import click

from aitbc import AITBCHTTPClient, NetworkError, get_logger

from ..config import get_config
from ..utils import error, info, output, success, warning
from ..utils.island_credentials import (
    get_chain_id,
    get_island_id,
    load_island_credentials,
)

# Initialize logger
logger = get_logger(__name__)


def safe_load_credentials():
    """Load island credentials with graceful error handling"""
    try:
        return load_island_credentials()
    except FileNotFoundError as e:
        error(f"Island credentials not found: {e}")
        error("Run 'aitbc node island join' to join an island first")
        return None


def get_wallet_address() -> str:
    """Get address from default wallet (use public_key as blockchain address)"""
    wallet_path = '/root/.aitbc/wallets/my-agent-wallet.json'
    if os.path.exists(wallet_path):
        with open(wallet_path) as f:
            wallet = json.load(f)
            # Use public_key as blockchain address (already in hex format)
            return wallet.get('public_key', '0x0000000000000000000000000000000000000000')
    return '0x0000000000000000000000000000000000000000'


def get_account_nonce(address: str, chain_id: str) -> int:
    """Query blockchain for current account nonce"""
    try:
        from aitbc.network.http_client import AITBCHTTPClient
        config = get_config()
        hub_url = config.blockchain_rpc_url.replace('localhost', config.hub_discovery_url or 'hub.aitbc.bubuit.net')
        http_client = AITBCHTTPClient(base_url=hub_url, timeout=10)
        response = http_client.get(f"/rpc/accounts/{address}?chain_id={chain_id}")
        return response.get('nonce', 0)
    except Exception as e:
        error(f"Failed to get account nonce: {e}")
        return 0

def get_next_nonce() -> int:
    """Get next transaction nonce from blockchain"""
    wallet_address = get_wallet_address()
    config = get_config()
    chain_id = 'ait-' + config.hub_discovery_url
    return get_account_nonce(wallet_address, chain_id)


@click.group()
def market():
    """Blockchain marketplace commands for GPU trading"""
    pass


@market.command()
@click.argument('gpu_id')
@click.argument('price_per_hour', type=float)
@click.argument('duration_hours', type=int)
@click.option('--description', help='Description of the GPU offer')
@click.pass_context
def offer(ctx, gpu_id: str, price_per_hour: float, duration_hours: int, description: str | None):
    """Offer a registered GPU for sale in the blockchain marketplace"""
    try:
        # Load CLI config
        config = get_config()

        # Load island credentials
        credentials = safe_load_credentials()
        if not credentials:
            return
        chain_id = get_chain_id()
        island_id = get_island_id()

        # Get provider node ID
        hostname = socket.gethostname()
        local_address = socket.gethostbyname(hostname)
        p2p_port = credentials.get('credentials', {}).get('p2p_port', 8001)

        # Get public key for node ID generation
        keystore_path = '/var/lib/aitbc/keystore/validator_keys.json'
        if os.path.exists(keystore_path):
            with open(keystore_path) as f:
                keys = json.load(f)
                public_key_pem = None
                for key_id, key_data in keys.items():
                    public_key_pem = key_data.get('public_key_pem')
                    break
                if public_key_pem:
                    content = f"{hostname}:{local_address}:{p2p_port}:{public_key_pem}"
                    provider_node_id = hashlib.sha256(content.encode()).hexdigest()
                else:
                    error("No public key found in keystore")
                    raise click.Abort()
        else:
            # Fallback to wallet keys
            wallet_path = '/root/.aitbc/wallets/my-agent-wallet.json'
            if os.path.exists(wallet_path):
                with open(wallet_path) as f:
                    wallet = json.load(f)
                    public_key_pem = wallet.get('public_key')
            
            if public_key_pem:
                content = f"{hostname}:{local_address}:{p2p_port}:{public_key_pem}"
                provider_node_id = hashlib.sha256(content.encode()).hexdigest()
            else:
                error("No public key found in keystore or wallet")
                raise click.Abort()

        # Query GPU service for registered GPU
        try:
            gpu_http_client = AITBCHTTPClient(base_url=config.gpu_service_url, timeout=10)
            gpu_info = gpu_http_client.get(f"/v1/gpu/{gpu_id}")
            
            if not gpu_info or gpu_info.get('status') != 'available':
                error(f"GPU {gpu_id} not found or not available")
                raise click.Abort()
            
            gpu_specs = {
                'model': gpu_info.get('model', 'Unknown'),
                'memory_gb': gpu_info.get('memory_gb', 0),
                'cuda_version': gpu_info.get('cuda_version', ''),
                'capabilities': gpu_info.get('capabilities', [])
            }
            info(f"Using registered GPU: {gpu_specs['model']} ({gpu_specs['memory_gb']} GB)")
        except Exception as e:
            error(f"Failed to query GPU service: {e}")
            raise click.Abort()

        # Calculate total price
        total_price = price_per_hour * duration_hours

        # Generate offer ID
        offer_id = f"gpu_offer_{datetime.now().strftime('%Y%m%d%H%M%S')}_{hashlib.sha256(f'{provider_node_id}{gpu_id}{price_per_hour}'.encode()).hexdigest()[:8]}"

        # Create offer transaction for blockchain
        wallet_address = get_wallet_address()
        offer_data = {
            'from': wallet_address,
            'to': '0x0000000000000000000000000000000000000000',
            'amount': 0,
            'fee': 0,
            'nonce': get_next_nonce(),
            'type': 'GPU_MARKETPLACE',
            'payload': {
                'action': 'offer',
                'offer_id': offer_id,
                'provider_node_id': provider_node_id,
                'gpu_id': gpu_id,
                'price_per_hour': float(price_per_hour),
                'duration_hours': duration_hours,
                'total_price': float(total_price),
                'status': 'active',
                'specs': gpu_specs,
                'description': description or f"{gpu_specs['model']} GPU for {duration_hours} hours",
                'island_id': island_id,
                'chain_id': chain_id,
                'created_at': datetime.now().isoformat()
            }
        }

        # Submit transaction to blockchain RPC (try hub first for block inclusion)
        try:
            # Try hub RPC for cross-node propagation
            hub_url = config.blockchain_rpc_url.replace('localhost', config.hub_discovery_url or 'hub.aitbc.bubuit.net')
            http_client = AITBCHTTPClient(base_url=hub_url, timeout=10)
            result = http_client.post("/transactions/marketplace", json=offer_data)
            success("GPU offer created successfully!")
            output(result, ctx.obj.get("output_format", "table"))
        except NetworkError:
            # Fallback to local blockchain RPC
            http_client = AITBCHTTPClient(base_url=config.blockchain_rpc_url, timeout=10)
            result = http_client.post("/transactions/marketplace", json=offer_data)
            success("GPU offer created successfully!")
            output(result, ctx.obj.get("output_format", "table"))

    except Exception as e:
        error(f"Error creating GPU offer: {e}")
        raise click.Abort()


@market.command()
@click.argument('gpu_count', type=int)
@click.argument('max_price', type=float)
@click.argument('duration_hours', type=int)
@click.option('--description', help='Description of the GPU bid')
@click.pass_context
def bid(ctx, gpu_count: int, max_price: float, duration_hours: int, description: str | None):
    """Bid on GPU power in the marketplace"""
    try:
        # Load CLI config
        config = get_config()

        # Load island credentials
        credentials = safe_load_credentials()
        if not credentials:
            return
        chain_id = get_chain_id()
        island_id = get_island_id()

        # Get bidder node ID
        hostname = socket.gethostname()
        local_address = socket.gethostbyname(hostname)
        p2p_port = credentials.get('credentials', {}).get('p2p_port', 8001)

        # Get public key for node ID generation
        keystore_path = '/var/lib/aitbc/keystore/validator_keys.json'
        if os.path.exists(keystore_path):
            with open(keystore_path) as f:
                keys = json.load(f)
                public_key_pem = None
                for key_id, key_data in keys.items():
                    public_key_pem = key_data.get('public_key_pem')
                    break
                if public_key_pem:
                    content = f"{hostname}:{local_address}:{p2p_port}:{public_key_pem}"
                    bidder_node_id = hashlib.sha256(content.encode()).hexdigest()
                else:
                    error("No public key found in keystore")
                    raise click.Abort()
        else:
            # Fallback to wallet keys
            wallet_path = '/root/.aitbc/wallets/my-agent-wallet.json'
            if os.path.exists(wallet_path):
                with open(wallet_path) as f:
                    wallet = json.load(f)
                    public_key_pem = wallet.get('public_key')
            
            if public_key_pem:
                content = f"{hostname}:{local_address}:{p2p_port}:{public_key_pem}"
                bidder_node_id = hashlib.sha256(content.encode()).hexdigest()
            else:
                error("No public key found in keystore or wallet")
                raise click.Abort()

        # Calculate max total price
        max_total_price = max_price * duration_hours

        # Generate bid ID
        bid_id = f"gpu_bid_{datetime.now().strftime('%Y%m%d%H%M%S')}_{hashlib.sha256(f'{bidder_node_id}{gpu_count}{max_price}'.encode()).hexdigest()[:8]}"

        # Create bid transaction for blockchain
        wallet_address = get_wallet_address()
        bid_data = {
            'from': wallet_address,
            'to': '0x0000000000000000000000000000000000000000',
            'amount': 0,
            'fee': 0,
            'nonce': get_next_nonce(),
            'type': 'GPU_MARKETPLACE',
            'payload': {
                'action': 'bid',
                'bid_id': bid_id,
                'bidder_node_id': bidder_node_id,
                'gpu_count': gpu_count,
                'max_price_per_gpu': float(max_price),
                'duration_hours': duration_hours,
                'max_total_price': float(max_total_price),
                'status': 'pending',
                'description': description or f"Bid for {gpu_count} GPU(s) for {duration_hours} hours",
                'island_id': island_id,
                'chain_id': chain_id,
                'created_at': datetime.now().isoformat()
            }
        }

        # Submit transaction to blockchain RPC
        try:
            # Try hub RPC for cross-node propagation
            hub_url = config.blockchain_rpc_url.replace('localhost', config.hub_discovery_url or 'hub.aitbc.bubuit.net')
            http_client = AITBCHTTPClient(base_url=hub_url, timeout=10)
            result = http_client.post("/transactions/marketplace", json=bid_data)
            success("GPU bid created successfully!")
            output(result, ctx.obj.get("output_format", "table"))
        except NetworkError:
            # Fallback to local blockchain RPC
            http_client = AITBCHTTPClient(base_url=config.blockchain_rpc_url, timeout=10)
            result = http_client.post("/transactions/marketplace", json=bid_data)
            success("GPU bid created successfully!")
            output(result, ctx.obj.get("output_format", "table"))

    except Exception as e:
        error(f"Error creating GPU bid: {e}")
        raise click.Abort()


@market.command()
@click.option('--provider', help='Filter by provider node ID')
@click.option('--status', help='Filter by status (active, pending, accepted, completed, cancelled)')
@click.option('--type', type=click.Choice(['offer', 'bid', 'all']), default='all', help='Filter by type')
@click.pass_context
def list(ctx, provider: str | None, status: str | None, type: str):
    """List blockchain marketplace offers and bids"""
    try:
        # Load CLI config
        config = get_config()

        # Query blockchain for GPU marketplace transactions
        transactions = None
        try:
            # Try local blockchain RPC first, then hub for cross-node data
            http_client = AITBCHTTPClient(base_url=config.blockchain_rpc_url, timeout=10)
            transactions = http_client.get("/transactions/marketplace")
            
            # If local returns empty or error, try hub
            if not transactions:
                hub_url = config.blockchain_rpc_url.replace('localhost', config.hub_discovery_url or 'hub.aitbc.bubuit.net')
                http_client = AITBCHTTPClient(base_url=hub_url, timeout=10)
                transactions = http_client.get("/transactions/marketplace")
        except NetworkError:
            # Blockchain endpoint not available
            pass

        if not transactions:
            info("No GPU marketplace offers found (blockchain endpoint not available)")
            return

        # Format output for marketplace offers (blockchain data)
        market_data = []
        for tx in transactions:
            payload = tx.get('payload', {})
            action = payload.get('action')
            
            if type != 'all' and action != type:
                continue
            if status and payload.get('status') != status:
                continue
            if provider and payload.get('provider_node_id') != provider:
                continue

            if action == 'offer':
                specs = payload.get('specs', {})
                market_data.append({
                    "Offer ID": payload.get('offer_id', '')[:20] + "...",
                    "GPU ID": payload.get('gpu_id'),
                    "Model": specs.get('model', 'Unknown'),
                    "Memory (GB)": specs.get('memory_gb', 0),
                    "Price/Hour": f"{payload.get('price_per_hour', 0):.4f} AIT",
                    "Duration": f"{payload.get('duration_hours')}h",
                    "Total": f"{payload.get('total_price', 0):.2f} AIT",
                    "Status": payload.get('status'),
                    "Provider": payload.get('provider_node_id', '')[:16] + "...",
                    "Description": payload.get('description', '')[:30] + "..." if len(payload.get('description', '')) > 30 else payload.get('description', ''),
                    "Created": payload.get('created_at', '')[:19] if payload.get('created_at') else 'N/A'
                })
            elif action == 'bid':
                market_data.append({
                    "Bid ID": payload.get('bid_id', '')[:20] + "...",
                    "Type": "BID",
                    "GPU Count": payload.get('gpu_count'),
                    "Max Price": f"{payload.get('max_price_per_gpu', 0):.4f} AIT/h",
                    "Duration": f"{payload.get('duration_hours')}h",
                    "Max Total": f"{payload.get('max_total_price', 0):.2f} AIT",
                    "Status": payload.get('status'),
                    "Bidder": payload.get('bidder_node_id', '')[:16] + "...",
                    "Created": payload.get('created_at', '')[:19] if payload.get('created_at') else 'N/A'
                })

        output(market_data, ctx.obj.get('output_format', 'table'), title="GPU Marketplace Offers")

    except Exception as e:
        error(f"Error listing GPU marketplace: {str(e)}")
        raise click.Abort()


@market.command()
@click.argument('order_id')
@click.pass_context
def cancel(ctx, order_id: str):
    """Cancel a GPU offer or bid"""
    try:
        # Load CLI config
        config = get_config()

        # Load island credentials
        credentials = safe_load_credentials()
        if not credentials:
            return
        chain_id = get_chain_id()
        island_id = get_island_id()

        # Create cancel transaction for blockchain
        wallet_address = get_wallet_address()
        cancel_data = {
            'from': wallet_address,
            'to': '0x0000000000000000000000000000000000000000',
            'amount': 0,
            'fee': 0,
            'nonce': get_next_nonce(),
            'type': 'GPU_MARKETPLACE',
            'payload': {
                'action': 'cancel',
                'order_id': order_id,
                'status': 'cancelled',
                'island_id': island_id,
                'chain_id': chain_id,
                'created_at': datetime.now().isoformat()
            }
        }

        # Submit transaction to blockchain RPC
        try:
            # Try hub RPC for cross-node propagation
            hub_url = config.blockchain_rpc_url.replace('localhost', config.hub_discovery_url or 'hub.aitbc.bubuit.net')
            http_client = AITBCHTTPClient(base_url=hub_url, timeout=10)
            result = http_client.post("/transactions/marketplace", json=cancel_data)
            success(f"Order {order_id} cancelled successfully!")
            output(result, ctx.obj.get("output_format", "table"))
        except NetworkError:
            # Fallback to local blockchain RPC
            http_client = AITBCHTTPClient(base_url=config.blockchain_rpc_url, timeout=10)
            result = http_client.post("/transactions/marketplace", json=cancel_data)
            success(f"Order {order_id} cancelled successfully!")
            output(result, ctx.obj.get("output_format", "table"))

    except Exception as e:
        error(f"Error cancelling order: {e}")
        raise click.Abort()


@market.command()
@click.argument('bid_id')
@click.pass_context
def accept(ctx, bid_id: str):
    """Accept a GPU bid (provider only)"""
    try:
        # Load CLI config
        config = get_config()

        # Load island credentials
        credentials = safe_load_credentials()
        if not credentials:
            return
        chain_id = get_chain_id()
        island_id = get_island_id()

        # Create accept transaction for blockchain
        wallet_address = get_wallet_address()
        accept_data = {
            'from': wallet_address,
            'to': '0x0000000000000000000000000000000000000000',
            'amount': 0,
            'fee': 0,
            'nonce': get_next_nonce(),
            'type': 'GPU_MARKETPLACE',
            'payload': {
                'action': 'accept',
                'bid_id': bid_id,
                'status': 'accepted',
                'island_id': island_id,
                'chain_id': chain_id,
                'created_at': datetime.now().isoformat()
            }
        }

        # Submit transaction to blockchain RPC
        try:
            # Try hub RPC for cross-node propagation
            hub_url = config.blockchain_rpc_url.replace('localhost', config.hub_discovery_url or 'hub.aitbc.bubuit.net')
            http_client = AITBCHTTPClient(base_url=hub_url, timeout=10)
            result = http_client.post("/transactions/marketplace", json=accept_data)
            success(f"Bid {bid_id} accepted successfully!")
            output(result, ctx.obj.get("output_format", "table"))
        except NetworkError:
            # Fallback to local blockchain RPC
            http_client = AITBCHTTPClient(base_url=config.blockchain_rpc_url, timeout=10)
            result = http_client.post("/transactions/marketplace", json=accept_data)
            success(f"Bid {bid_id} accepted successfully!")
            output(result, ctx.obj.get("output_format", "table"))

    except Exception as e:
        error(f"Error accepting bid: {e}")
        raise click.Abort()


@market.command()
@click.argument('order_id')
@click.pass_context
def status(ctx, order_id: str):
    """Check the status of a GPU order"""
    try:
        # Load CLI config
        config = get_config()

        # Query blockchain for transaction status
        try:
            # Try local blockchain RPC first, then hub
            http_client = AITBCHTTPClient(base_url=config.blockchain_rpc_url, timeout=10)
            result = http_client.get(f"/transactions/marketplace/{order_id}")
            
            if not result:
                # Try hub
                hub_url = config.blockchain_rpc_url.replace('localhost', config.hub_discovery_url or 'hub.aitbc.bubuit.net')
                http_client = AITBCHTTPClient(base_url=hub_url, timeout=10)
                result = http_client.get(f"/transactions/marketplace/{order_id}")
            
            output(result, ctx.obj.get("output_format", "table"))
        except NetworkError as e:
            error(f"Network error: {e}")
            raise click.Abort()

    except Exception as e:
        error(f"Error checking order status: {e}")
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
            result = http_client.get("/transactions/marketplace/match")
            
            if not result:
                # Try hub
                hub_url = config.blockchain_rpc_url.replace('localhost', config.hub_discovery_url or 'hub.aitbc.bubuit.net')
                http_client = AITBCHTTPClient(base_url=hub_url, timeout=10)
                result = http_client.get("/transactions/marketplace/match")
            
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
