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
from ..utils.island_credentials import load_island_credentials

# Initialize logger
logger = get_logger(__name__)


def safe_load_credentials():
    """Load island credentials - required for production"""
    try:
        return load_island_credentials()
    except FileNotFoundError as e:
        error(f"Island credentials required for marketplace operations: {e}")
        error("Run 'aitbc edge island join' to join an island first")
        return None


def get_chain_id() -> str:
    """Get chain ID from island credentials - required for production"""
    try:
        return load_island_credentials().get('chain_id', 'ait-mainnet')
    except FileNotFoundError as e:
        error(f"Island credentials required for chain ID: {e}")
        raise click.Abort()


def get_island_id() -> str:
    """Get island ID from island credentials - required for production"""
    try:
        return load_island_credentials().get('island_id')
    except FileNotFoundError as e:
        error(f"Island credentials required for island ID: {e}")
        raise click.Abort()


def get_wallet_address() -> str:
    """Get address from wallet service or local wallet file"""
    config = get_config()
    
    # Try wallet service API first
    try:
        http_client = AITBCHTTPClient(base_url="http://localhost:8108", timeout=5)
        wallets = http_client.get("/v1/wallets")
        if wallets and wallets.get('items'):
            # Use genesis wallet address
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
    """Get next transaction nonce from blockchain"""
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
        public_key_pem = None
        keystore_path = '/var/lib/aitbc/keystore/validator_keys.json'
        if os.path.exists(keystore_path):
            with open(keystore_path) as f:
                keys = json.load(f)
                for key_id, key_data in keys.items():
                    public_key_pem = key_data.get('public_key_pem')
                    break
        
        # Fallback to wallet keys
        if not public_key_pem:
            wallet_path = '/root/.aitbc/wallets/my-agent-wallet.json'
            if os.path.exists(wallet_path):
                with open(wallet_path) as f:
                    wallet = json.load(f)
                    public_key_pem = wallet.get('public_key')
        
        if public_key_pem:
            content = f"{hostname}:{local_address}:{p2p_port}:{public_key_pem}"
            provider_node_id = hashlib.sha256(content.encode()).hexdigest()
        else:
            # Use hostname as fallback for testing
            warning("No public key found in keystore or wallet, using hostname as node ID")
            provider_node_id = hashlib.sha256(hostname.encode()).hexdigest()

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
            'fee': 10,  # Non-zero fee to incentivize miners
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

        # Submit transaction to blockchain RPC
        try:
            # Try hub RPC for cross-node propagation
            hub_url = f"http://{config.hub_discovery_url or 'hub.aitbc.bubuit.net'}"
            http_client = AITBCHTTPClient(base_url=hub_url, timeout=10)
            result = http_client.post("/rpc/transactions/marketplace", json=offer_data)
            success("GPU offer created successfully!")
            output(result, ctx.obj.get("output_format", "table"))
        except NetworkError:
            # Fallback to local blockchain RPC
            http_client = AITBCHTTPClient(base_url=config.blockchain_rpc_url, timeout=10)
            result = http_client.post("/rpc/transactions/marketplace", json=offer_data)
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
        public_key_pem = None
        keystore_path = '/var/lib/aitbc/keystore/validator_keys.json'
        if os.path.exists(keystore_path):
            with open(keystore_path) as f:
                keys = json.load(f)
                for key_id, key_data in keys.items():
                    public_key_pem = key_data.get('public_key_pem')
                    break
        
        # Fallback to wallet keys
        if not public_key_pem:
            wallet_path = '/root/.aitbc/wallets/my-agent-wallet.json'
            if os.path.exists(wallet_path):
                with open(wallet_path) as f:
                    wallet = json.load(f)
                    public_key_pem = wallet.get('public_key')
        
        if public_key_pem:
            content = f"{hostname}:{local_address}:{p2p_port}:{public_key_pem}"
            bidder_node_id = hashlib.sha256(content.encode()).hexdigest()
        else:
            # Use hostname as fallback for testing
            warning("No public key found in keystore or wallet, using hostname as node ID")
            bidder_node_id = hashlib.sha256(hostname.encode()).hexdigest()

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
            'fee': 10,  # Non-zero fee to incentivize miners
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
            hub_url = f"http://{config.hub_discovery_url or 'hub.aitbc.bubuit.net'}"
            http_client = AITBCHTTPClient(base_url=hub_url, timeout=10)
            result = http_client.post("/rpc/transactions/marketplace", json=bid_data)
            success("GPU bid created successfully!")
            output(result, ctx.obj.get("output_format", "table"))
        except NetworkError:
            # Fallback to local blockchain RPC
            http_client = AITBCHTTPClient(base_url=config.blockchain_rpc_url, timeout=10)
            result = http_client.post("/rpc/transactions/marketplace", json=bid_data)
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
            
            # Query recent blocks for GPU_MARKETPLACE transactions
            # Remove /rpc prefix if present in base URL
            head_path = "/rpc/head" if not config.blockchain_rpc_url.endswith("/rpc") else "/head"
            head = http_client.get(head_path)
            logger.debug(f"Head response: {head}")
            if head and head.get('height'):
                height = head['height']
                # Query last 20 blocks
                start_height = max(0, height - 20)
                blocks_path = f"/rpc/blocks-range?start={start_height}&end={height}" if not config.blockchain_rpc_url.endswith("/rpc") else f"/blocks-range?start={start_height}&end={height}"
                blocks_response = http_client.get(blocks_path)
                logger.debug(f"Blocks response: {blocks_response}")
                
                if blocks_response and blocks_response.get('blocks'):
                    transactions = []
                    for block in blocks_response['blocks']:
                        for tx in block.get('transactions', []):
                            if isinstance(tx, dict) and tx.get('type') == 'GPU_MARKETPLACE':
                                transactions.append(tx)
                    logger.debug(f"Found {len(transactions)} GPU_MARKETPLACE transactions")
            
            # If no transactions in blocks, try mempool
            if not transactions:
                mempool_path = "/rpc/mempool" if not config.blockchain_rpc_url.endswith("/rpc") else "/mempool"
                mempool = http_client.get(mempool_path)
                logger.debug(f"Mempool response: {mempool}")
                if mempool and isinstance(mempool, dict) and 'transactions' in mempool:
                    transactions = [tx for tx in mempool['transactions'] if tx.get('type') == 'GPU_MARKETPLACE']
        except NetworkError as e:
            # Blockchain endpoint not available
            logger.error(f"Network error querying blockchain: {e}")
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
            'fee': 10,  # Non-zero fee to incentivize miners
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
            hub_url = f"http://{config.hub_discovery_url or 'hub.aitbc.bubuit.net'}"
            http_client = AITBCHTTPClient(base_url=hub_url, timeout=10)
            result = http_client.post("/rpc/transactions/marketplace", json=cancel_data)
            success(f"Order {order_id} cancelled successfully!")
            output(result, ctx.obj.get("output_format", "table"))
        except NetworkError:
            # Fallback to local blockchain RPC
            http_client = AITBCHTTPClient(base_url=config.blockchain_rpc_url, timeout=10)
            result = http_client.post("/rpc/transactions/marketplace", json=cancel_data)
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
            'fee': 10,  # Non-zero fee to incentivize miners
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
            hub_url = f"http://{config.hub_discovery_url or 'hub.aitbc.bubuit.net'}"
            http_client = AITBCHTTPClient(base_url=hub_url, timeout=10)
            result = http_client.post("/rpc/transactions/marketplace", json=accept_data)
            success(f"Bid {bid_id} accepted successfully!")
            output(result, ctx.obj.get("output_format", "table"))
        except NetworkError:
            # Fallback to local blockchain RPC
            http_client = AITBCHTTPClient(base_url=config.blockchain_rpc_url, timeout=10)
            result = http_client.post("/rpc/transactions/marketplace", json=accept_data)
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
            result = http_client.get(f"/rpc/transactions/marketplace/{order_id}")
            
            if not result:
                # Try hub
                hub_url = config.blockchain_rpc_url.replace('localhost', config.hub_discovery_url or 'hub.aitbc.bubuit.net')
                http_client = AITBCHTTPClient(base_url=hub_url, timeout=10)
                result = http_client.get(f"/rpc/transactions/marketplace/{order_id}")
            
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
