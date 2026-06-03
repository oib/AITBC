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
            'chain_id': chain_id,  # Set chain_id at top level for RPC validation
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
            'chain_id': chain_id,  # Set chain_id at top level for RPC validation
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
            'chain_id': chain_id,  # Set chain_id at top level for RPC validation
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
            'chain_id': chain_id,  # Set chain_id at top level for RPC validation
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

        # Auto-create blockchain escrow to lock buyer funds
        _escrow_create(bid_id, wallet_address, wallet_address, 0, config)

    except Exception as e:
        error(f"Error accepting bid: {e}")
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
    """Return local blockchain RPC URL (port 8202)"""
    url = getattr(config, 'blockchain_rpc_url', 'http://localhost:8202')
    # Normalise to port 8202 if the stored URL points elsewhere
    if 'localhost' in url or '127.0.0.1' in url:
        url = re.sub(r':\d+', ':8202', url)
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

@market.command(name="software-offer")
@click.argument('service_type', type=click.Choice(['ollama', 'whisper', 'peertube_pruner']))
@click.argument('model_or_variant')
@click.argument('price', type=float)
@click.option('--unit', default='per_1k_tokens',
              type=click.Choice(['per_1k_tokens', 'per_audio_min', 'per_gb']),
              help='Pricing unit')
@click.option('--description', help='Description of the service')
@click.option('--context-window', type=int, default=4096, help='Context window size (ollama)')
@click.pass_context
def software_offer(ctx, service_type: str, model_or_variant: str, price: float,
                   unit: str, description: str | None, context_window: int):
    """List a software service (Ollama/Whisper/PeerTube) in the marketplace"""
    try:
        config = get_config()
        chain_id = get_chain_id()
        island_id = get_island_id()
        wallet_address = get_wallet_address()

        # Verify the service is actually running locally
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

        provider_node_id = hashlib.sha256(socket.gethostname().encode()).hexdigest()
        offer_id = f"sw_offer_{datetime.now().strftime('%Y%m%d%H%M%S')}_{hashlib.sha256(f'{service_type}{model_or_variant}{price}'.encode()).hexdigest()[:8]}"

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
                'status': 'active',
                'description': description or f"{service_type} — {model_or_variant} at {price} AIT/{unit}",
                'island_id': island_id,
                'chain_id': chain_id,
                'created_at': datetime.now().isoformat(),
            }
        }

        hub_url = f"http://{config.hub_discovery_url or 'hub.aitbc.bubuit.net'}"
        http_client = AITBCHTTPClient(base_url=hub_url, timeout=10)
        result = http_client.post("/rpc/transactions/marketplace", json=offer_data)
        success(f"Software offer listed on marketplace!")
        output(result, ctx.obj.get("output_format", "table"))

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
        result = http_client.get("/rpc/transactions", params={"limit": 500})
        offer = None
        if result and not isinstance(result, dict):
            for tx in result:
                p = tx.get('payload', {})
                if p.get('action') == 'software_offer' and p.get('offer_id') == offer_id and p.get('status') == 'active':
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
