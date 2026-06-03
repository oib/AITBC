"""
GPU Marketplace CLI Commands
Commands for bidding on and offering GPU power in the AITBC island marketplace
"""

import hashlib
import json
import os
import socket
from datetime import datetime

import click

# Import shared modules
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
def gpu():
    """GPU marketplace commands for bidding and offering GPU power"""
    pass


@gpu.command()
@click.argument('gpu_id')
@click.argument('price_per_hour', type=float)
@click.argument('duration_hours', type=int)
@click.option('--description', help='Description of the GPU offer')
@click.pass_context
def offer(ctx, gpu_id: str, price_per_hour: float, duration_hours: int, description: str | None):
    """Offer a registered GPU for sale in the marketplace"""
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
            success(f"Offer ID: {offer_id}")
            success(f"GPU: {gpu_id} ({gpu_specs['model']})")
            success(f"Total Price: {total_price:.2f} AIT")

            offer_info = {
                "Offer ID": offer_id,
                "GPU ID": gpu_id,
                "GPU Model": gpu_specs['model'],
                "Price per Hour": f"{price_per_hour:.4f} AIT/hour",
                "Duration": f"{duration_hours} hours",
                "Total Price": f"{total_price:.2f} AIT",
                "Status": "active",
                "Provider Node": provider_node_id[:16] + "...",
                "Island": island_id[:16] + "..."
            }

            output(offer_info, ctx.obj.get('output_format', 'table'))
        except NetworkError as e:
            error(f"Network error submitting transaction: {e}")
            raise click.Abort()

    except Exception as e:
        error(f"Error creating GPU offer: {str(e)}")
        raise click.Abort()


@gpu.command()
@click.argument('gpu_count', type=int)
@click.argument('max_price', type=float)
@click.argument('duration_hours', type=int)
@click.pass_context
def bid(ctx, gpu_count: int, max_price: float, duration_hours: int):
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
        max_total_price = max_price * gpu_count * duration_hours

        # Generate bid ID
        bid_id = f"gpu_bid_{datetime.now().strftime('%Y%m%d%H%M%S')}_{hashlib.sha256(f'{bidder_node_id}{gpu_count}{max_price}'.encode()).hexdigest()[:8]}"

        # Parse specifications
        gpu_specs = {}
        if specs:
            try:
                gpu_specs = json.loads(specs)
            except json.JSONDecodeError:
                error("Invalid JSON specifications")
                raise click.Abort()

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
                'specs': gpu_specs,
                'island_id': island_id,
                'chain_id': chain_id,
                'created_at': datetime.now().isoformat()
            }
        }

        # Submit transaction to blockchain RPC (hub for cross-node propagation)
        try:
            hub_url = config.blockchain_rpc_url.replace('localhost', config.hub_discovery_url or 'hub.aitbc.bubuit.net')
            http_client = AITBCHTTPClient(base_url=hub_url, timeout=10)
            result = http_client.post("/transactions/marketplace", json=bid_data)
            success("GPU bid created successfully!")
            success(f"Bid ID: {bid_id}")
            success(f"Max Total Price: {max_total_price:.2f} AIT")

            bid_info = {
                "Bid ID": bid_id,
                "GPU Count": gpu_count,
                "Max Price per GPU": f"{max_price:.4f} AIT/hour",
                "Duration": f"{duration_hours} hours",
                "Max Total Price": f"{max_total_price:.2f} AIT",
                "Status": "pending",
                "Bidder Node": bidder_node_id[:16] + "...",
                "Island": island_id[:16] + "..."
            }

            output(bid_info, ctx.obj.get('output_format', 'table'))
        except NetworkError as e:
            error(f"Network error submitting transaction: {e}")
            raise click.Abort()

    except Exception as e:
        error(f"Error creating GPU bid: {str(e)}")
        raise click.Abort()


@gpu.command()
@click.option('--provider', help='Filter by provider node ID')
@click.option('--status', help='Filter by status (active, pending, accepted, completed, cancelled)')
@click.option('--type', type=click.Choice(['offer', 'bid', 'all']), default='all', help='Filter by type')
@click.pass_context
def list(ctx, provider: str | None, status: str | None, type: str):
    """List GPU marketplace offers and bids (no island credentials required)"""
    try:
        # Load CLI config
        config = get_config()

        # Query GPU service for registered GPUs
        try:
            http_client = AITBCHTTPClient(base_url=config.gpu_service_url, timeout=10)
            transactions = http_client.get("/v1/transactions")

            if not transactions:
                info("No registered GPUs found")
                return

            # Format output for GPU registry data
            gpu_data = []
            for gpu in transactions:
                gpu_data.append({
                    "GPU ID": gpu.get('id'),
                    "Model": gpu.get('model'),
                    "Memory (GB)": gpu.get('memory_gb'),
                    "Price/Hour": f"{gpu.get('price_per_hour', 0):.4f} AIT",
                    "Status": gpu.get('status'),
                    "Region": gpu.get('region') or 'N/A',
                    "Miner ID": gpu.get('miner_id', '')[:16] + "...",
                    "Created": gpu.get('created_at', '')[:19] if gpu.get('created_at') else 'N/A'
                })

            output(gpu_data, ctx.obj.get('output_format', 'table'), title="Registered GPUs")
        except NetworkError as e:
            error(f"Network error querying GPU service: {e}")
            raise click.Abort()

    except Exception as e:
        error(f"Error listing GPU marketplace: {str(e)}")
        raise click.Abort()


@gpu.command()
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

        # Get local node ID
        hostname = socket.gethostname()
        local_address = socket.gethostbyname(hostname)
        p2p_port = credentials.get('credentials', {}).get('p2p_port', 8001)

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
                    local_node_id = hashlib.sha256(content.encode()).hexdigest()
        else:
            # Fallback to wallet keys
            wallet_path = '/root/.aitbc/wallets/my-agent-wallet.json'
            if os.path.exists(wallet_path):
                with open(wallet_path) as f:
                    wallet = json.load(f)
                    public_key_pem = wallet.get('public_key')
            
            if public_key_pem:
                content = f"{hostname}:{local_address}:{p2p_port}:{public_key_pem}"
                local_node_id = hashlib.sha256(content.encode()).hexdigest()
            else:
                error("No public key found in keystore or wallet")
                raise click.Abort()

        # Determine if it's an offer or bid
        if order_id.startswith('gpu_offer'):
            action = 'cancel'
        elif order_id.startswith('gpu_bid'):
            action = 'cancel'
        else:
            error("Invalid order ID format. Must start with 'gpu_offer' or 'gpu_bid'")
            raise click.Abort()

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
                'action': action,
                'order_id': order_id,
                'node_id': local_node_id,
                'status': 'cancelled',
                'cancelled_at': datetime.now().isoformat(),
                'island_id': island_id,
                'chain_id': chain_id
            }
        }

        # Submit transaction to blockchain RPC (hub for cross-node propagation)
        try:
            hub_url = config.blockchain_rpc_url.replace('localhost', config.hub_discovery_url or 'hub.aitbc.bubuit.net')
            http_client = AITBCHTTPClient(base_url=hub_url, timeout=10)
            result = http_client.post("/transactions/marketplace", json=cancel_data)
            success(f"Order {order_id} cancelled successfully!")
        except NetworkError as e:
            error(f"Network error submitting transaction: {e}")
            raise click.Abort()

    except Exception as e:
        error(f"Error cancelling order: {str(e)}")
        raise click.Abort()


@gpu.command()
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

        # Get provider node ID
        hostname = socket.gethostname()
        local_address = socket.gethostbyname(hostname)
        p2p_port = credentials.get('credentials', {}).get('p2p_port', 8001)

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
                'provider_node_id': provider_node_id,
                'status': 'accepted',
                'accepted_at': datetime.now().isoformat(),
                'island_id': island_id,
                'chain_id': chain_id
            }
        }

        # Submit transaction to blockchain RPC (hub for cross-node propagation)
        try:
            hub_url = config.blockchain_rpc_url.replace('localhost', config.hub_discovery_url or 'hub.aitbc.bubuit.net')
            http_client = AITBCHTTPClient(base_url=hub_url, timeout=10)
            result = http_client.post("/transactions/marketplace", json=accept_data)
            success(f"Bid {bid_id} accepted successfully!")
        except NetworkError as e:
            error(f"Network error submitting transaction: {e}")
            raise click.Abort()

    except Exception as e:
        error(f"Error accepting bid: {str(e)}")
        raise click.Abort()


@gpu.command()
@click.argument('order_id')
@click.pass_context
def status(ctx, order_id: str):
    """Check the status of a GPU order"""
    try:
        # Load CLI config
        config = get_config()

        # Load island credentials
        credentials = safe_load_credentials()
        if not credentials:
            return
        island_id = get_island_id()

        # Query blockchain RPC for the order
        try:
            params = {
                'transaction_type': 'GPU_MARKETPLACE',
                'island_id': island_id,
                'order_id': order_id
            }

            http_client = AITBCHTTPClient(base_url=config.blockchain_rpc_url, timeout=10)
            transactions = http_client.get("/transactions", params=params)

            if not transactions:
                error(f"Order {order_id} not found")
                raise click.Abort()

            tx = transactions[0]
            action = tx.get('action')

            order_info = {
                "Order ID": order_id,
                "Type": action.upper(),
                "Status": tx.get('status'),
                "Created": tx.get('created_at'),
            }

            if action == 'offer':
                order_info.update({
                    "GPU Count": tx.get('gpu_count'),
                    "Price per GPU": f"{tx.get('price_per_gpu', 0):.4f} AIT/h",
                    "Duration": f"{tx.get('duration_hours')}h",
                    "Total Price": f"{tx.get('total_price', 0):.2f} AIT",
                    "Provider": tx.get('provider_node_id', '')[:16] + "..."
                })
            elif action == 'bid':
                order_info.update({
                    "GPU Count": tx.get('gpu_count'),
                    "Max Price": f"{tx.get('max_price_per_gpu', 0):.4f} AIT/h",
                    "Duration": f"{tx.get('duration_hours')}h",
                    "Max Total": f"{tx.get('max_total_price', 0):.2f} AIT",
                    "Bidder": tx.get('bidder_node_id', '')[:16] + "..."
                })

            if 'accepted_at' in tx:
                order_info["Accepted"] = tx['accepted_at']
            if 'cancelled_at' in tx:
                order_info["Cancelled"] = tx['cancelled_at']

            output(order_info, ctx.obj.get('output_format', 'table'), title=f"Order Status: {order_id}")
        except NetworkError as e:
            error(f"Network error querying blockchain: {e}")
            raise click.Abort()

    except Exception as e:
        error(f"Error checking order status: {str(e)}")
        raise click.Abort()


@gpu.command()
@click.pass_context
def match(ctx):
    """Match GPU bids with offers (price discovery)"""
    try:
        # Load CLI config
        config = get_config()

        # Load island credentials
        credentials = safe_load_credentials()
        if not credentials:
            return
        island_id = get_island_id()

        # Query GPU service for open offers and bids
        try:
            params = {
                'transaction_type': 'gpu_marketplace',
                'island_id': island_id,
                'status': 'active'
            }

            http_client = AITBCHTTPClient(base_url=config.gpu_service_url, timeout=10)
            transactions = http_client.get("/v1/transactions", params=params)

            # Separate offers and bids
            offers = []
            bids = []

            for tx in transactions:
                if tx.get('action') == 'offer':
                    offers.append(tx)
                elif tx.get('action') == 'bid':
                    bids.append(tx)

            if not offers or not bids:
                info("No active offers or bids to match")
                return

            # Sort offers by price (lowest first)
            offers.sort(key=lambda x: x.get('price_per_gpu', float('inf')))
            # Sort bids by price (highest first)
            bids.sort(key=lambda x: x.get('max_price_per_gpu', 0), reverse=True)

            # Match bids with offers
            matches = []
            for bid in bids:
                for offer in offers:
                    # Check if bid price >= offer price
                    if bid.get('max_price_per_gpu', 0) >= offer.get('price_per_gpu', float('inf')):
                        # Check if GPU count matches
                        if bid.get('gpu_count') == offer.get('gpu_count'):
                            # Check if duration matches
                            if bid.get('duration_hours') == offer.get('duration_hours'):
                                # Create match transaction
                                match_data = {
                                    'type': 'gpu_marketplace',
                                    'action': 'match',
                                    'bid_id': bid.get('bid_id'),
                                    'offer_id': offer.get('offer_id'),
                                    'bidder_node_id': bid.get('bidder_node_id'),
                                    'provider_node_id': offer.get('provider_node_id'),
                                    'gpu_count': bid.get('gpu_count'),
                                    'matched_price': offer.get('price_per_gpu'),
                                    'duration_hours': bid.get('duration_hours'),
                                    'total_price': offer.get('total_price'),
                                    'status': 'matched',
                                    'matched_at': datetime.now().isoformat(),
                                    'island_id': island_id,
                                    'chain_id': get_chain_id()
                                }

                                # Submit match transaction
                                match_result = http_client.post("/v1/transactions", json=match_data)
                                matches.append({
                                    "Bid ID": bid.get('bid_id')[:16] + "...",
                                    "Offer ID": offer.get('offer_id')[:16] + "...",
                                    "GPU Count": bid.get('gpu_count'),
                                    "Matched Price": f"{offer.get('price_per_gpu', 0):.4f} AIT/h",
                                    "Total Price": f"{offer.get('total_price', 0):.2f} AIT",
                                    "Duration": f"{bid.get('duration_hours')}h"
                                })

            if matches:
                success(f"Matched {len(matches)} GPU orders!")
                output(matches, ctx.obj.get('output_format', 'table'), title="GPU Order Matches")
            else:
                info("No matching orders found")
        except NetworkError as e:
            error(f"Network error querying blockchain: {e}")
            raise click.Abort()

    except Exception as e:
        error(f"Error matching orders: {str(e)}")
        raise click.Abort()


@gpu.command()
@click.pass_context
def providers(ctx):
    """Query island members for GPU providers"""
    try:
        # Load island credentials
        credentials = safe_load_credentials()
        if not credentials:
            return
        island_id = get_island_id()

        # Load island members from credentials
        members = credentials.get('members', [])

        if not members:
            warning("No island members found in credentials")
            return

        # Query each member for GPU availability via P2P
        info(f"Querying {len(members)} island members for GPU availability...")

        # For now, display the members
        # In a full implementation, this would use P2P network to query each member
        provider_data = []
        for member in members:
            provider_data.append({
                "Node ID": member.get('node_id', '')[:16] + "...",
                "Address": member.get('address', 'N/A'),
                "Port": member.get('port', 'N/A'),
                "Is Hub": member.get('is_hub', False),
                "Public Address": member.get('public_address', 'N/A'),
                "Public Port": member.get('public_port', 'N/A')
            })

        output(provider_data, ctx.obj.get('output_format', 'table'), title=f"Island Members ({island_id[:16]}...)")
        info("Note: GPU availability query via P2P network to be implemented")

    except Exception as e:
        error(f"Error querying GPU providers: {str(e)}")
        raise click.Abort()


@gpu.command()
@click.argument('gpu_id')
@click.option('--specs', help='GPU specifications (JSON string) - auto-discovered if not provided')
@click.pass_context
def register(ctx, gpu_id: str, specs: str | None):
    """Register a GPU with the gpu-service (no island credentials required)"""
    config = get_config()

    try:
        http_client = AITBCHTTPClient(base_url=config.gpu_service_url, timeout=10)

        gpu_data = {"gpu_id": gpu_id}

        if specs:
            try:
                gpu_data["specs"] = json.loads(specs)
            except json.JSONDecodeError:
                error("Invalid JSON specifications")
                raise click.Abort()

        result = http_client.post("/v1/gpu/register", json=gpu_data)
        success(f"GPU {gpu_id} registered successfully")
        output(result, ctx.obj.get("output_format", "table"))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error registering GPU: {e}")


@gpu.command()
@click.argument('gpu_id')
@click.pass_context
def unregister(ctx, gpu_id: str):
    """Unregister/delete a GPU from the gpu-service"""
    config = get_config()

    try:
        http_client = AITBCHTTPClient(base_url=config.gpu_service_url, timeout=10)
        result = http_client.delete(f"/v1/gpu/{gpu_id}")
        success(f"GPU {gpu_id} unregistered successfully")
        output(result, ctx.obj.get("output_format", "table"))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error unregistering GPU: {e}")


@gpu.command()
@click.argument('gpu_id')
@click.option('--pricing', help='Updated pricing model (JSON string)')
@click.option('--status', help='Update GPU status')
@click.pass_context
def update(ctx, gpu_id: str, pricing: str | None, status: str | None):
    """Update GPU registration with the gpu-service (no island credentials required)"""
    config = get_config()

    try:
        http_client = AITBCHTTPClient(base_url=config.gpu_service_url, timeout=10)

        update_data = {}

        if pricing:
            try:
                pricing_data = json.loads(pricing)
                update_data["price_per_hour"] = pricing_data.get("price_per_hour", pricing_data)
            except json.JSONDecodeError:
                # Try as direct number
                try:
                    update_data["price_per_hour"] = float(pricing)
                except ValueError:
                    error("Invalid pricing value")
                    raise click.Abort()

        if status:
            update_data["status"] = status

        if not update_data:
            error("No updates provided. Specify --pricing or --status")
            raise click.Abort()

        result = http_client.put(f"/v1/gpu/{gpu_id}", json=update_data)
        success(f"GPU {gpu_id} updated successfully")
        output(result, ctx.obj.get("output_format", "table"))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error updating GPU: {e}")


@gpu.command()
@click.pass_context
def discover(ctx):
    """Auto-discover GPU specifications using nvidia-smi"""
    try:
        import subprocess
        
        info("Discovering GPUs using nvidia-smi...")
        
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,name,memory.total,driver_version,compute_cap", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            error(f"nvidia-smi failed: {result.stderr}")
            raise click.Abort()
        
        gpus = []
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue
            parts = [p.strip() for p in line.split(',')]
            if len(parts) >= 3:
                gpu_info = {
                    "index": int(parts[0]),
                    "name": parts[1],
                    "memory_mb": int(parts[2]),
                    "driver_version": parts[3] if len(parts) > 3 else "unknown",
                    "compute_capability": parts[4] if len(parts) > 4 else "unknown"
                }
                gpus.append(gpu_info)
        
        if not gpus:
            warning("No GPUs discovered")
            return
        
        # Format output
        gpu_data = []
        for gpu in gpus:
            gpu_data.append({
                "GPU ID": f"gpu_{gpu['index']}",
                "Model": gpu['name'],
                "Memory (MB)": gpu['memory_mb'],
                "Memory (GB)": f"{gpu['memory_mb'] / 1024:.1f}",
                "Driver": gpu['driver_version'],
                "Compute Cap": gpu['compute_capability']
            })
        
        output(gpu_data, ctx.obj.get('output_format', 'table'), title="Discovered GPUs")
        success(f"Found {len(gpus)} GPU(s)")
        
    except FileNotFoundError:
        error("nvidia-smi not found. Please ensure NVIDIA drivers are installed.")
        raise click.Abort()
    except subprocess.TimeoutExpired:
        error("nvidia-smi timeout")
        raise click.Abort()
    except Exception as e:
        error(f"Error discovering GPUs: {e}")
        raise click.Abort()


