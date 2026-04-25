"""
GPU Marketplace CLI Commands
Commands for bidding on and offering GPU power in the AITBC island marketplace
"""

import click
import json
import hashlib
import socket
import os
import asyncio
from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from ..utils import output, error, success, info, warning
from ..utils.island_credentials import (
    load_island_credentials, get_rpc_endpoint, get_chain_id,
    get_island_id, get_island_name
)

# Import shared modules
from aitbc import get_logger, AITBCHTTPClient, NetworkError

# Initialize logger
logger = get_logger(__name__)


@click.group()
def gpu():
    """GPU marketplace commands for bidding and offering GPU power"""
    pass


@gpu.command()
@click.argument('gpu_count', type=int)
@click.argument('price_per_gpu', type=float)
@click.argument('duration_hours', type=int)
@click.option('--specs', help='GPU specifications (JSON string)')
@click.option('--description', help='Description of the GPU offer')
@click.pass_context
def offer(ctx, gpu_count: int, price_per_gpu: float, duration_hours: int, specs: Optional[str], description: Optional[str]):
    """Offer GPU power for sale in the marketplace"""
    try:
        # Load island credentials
        credentials = load_island_credentials()
        rpc_endpoint = get_rpc_endpoint()
        chain_id = get_chain_id()
        island_id = get_island_id()

        # Get provider node ID
        hostname = socket.gethostname()
        local_address = socket.gethostbyname(hostname)
        p2p_port = credentials.get('credentials', {}).get('p2p_port', 8001)
        
        # Get public key for node ID generation
        keystore_path = '/var/lib/aitbc/keystore/validator_keys.json'
        if os.path.exists(keystore_path):
            with open(keystore_path, 'r') as f:
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
            error(f"Keystore not found at {keystore_path}")
            raise click.Abort()

        # Calculate total price
        total_price = price_per_gpu * gpu_count * duration_hours

        # Generate offer ID
        offer_id = f"gpu_offer_{datetime.now().strftime('%Y%m%d%H%M%S')}_{hashlib.sha256(f'{provider_node_id}{gpu_count}{price_per_gpu}'.encode()).hexdigest()[:8]}"

        # Parse specifications
        gpu_specs = {}
        if specs:
            try:
                gpu_specs = json.loads(specs)
            except json.JSONDecodeError:
                error("Invalid JSON specifications")
                raise click.Abort()

        # Create offer transaction
        offer_data = {
            'type': 'gpu_marketplace',
            'action': 'offer',
            'offer_id': offer_id,
            'provider_node_id': provider_node_id,
            'gpu_count': gpu_count,
            'price_per_gpu': float(price_per_gpu),
            'duration_hours': duration_hours,
            'total_price': float(total_price),
            'status': 'active',
            'specs': gpu_specs,
            'description': description or f"{gpu_count} GPUs for {duration_hours} hours",
            'island_id': island_id,
            'chain_id': chain_id,
            'created_at': datetime.now().isoformat()
        }

        # Submit transaction to blockchain
        try:
            http_client = AITBCHTTPClient(base_url=rpc_endpoint, timeout=10)
            result = http_client.post("/transaction", json=offer_data)
            success(f"GPU offer created successfully!")
            success(f"Offer ID: {offer_id}")
            success(f"Total Price: {total_price:.2f} AIT")
            
            offer_info = {
                "Offer ID": offer_id,
                "GPU Count": gpu_count,
                "Price per GPU": f"{price_per_gpu:.4f} AIT/hour",
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
@click.option('--specs', help='Required GPU specifications (JSON string)')
@click.pass_context
def bid(ctx, gpu_count: int, max_price: float, duration_hours: int, specs: Optional[str]):
    """Bid on GPU power in the marketplace"""
    try:
        # Load island credentials
        credentials = load_island_credentials()
        rpc_endpoint = get_rpc_endpoint()
        chain_id = get_chain_id()
        island_id = get_island_id()

        # Get bidder node ID
        hostname = socket.gethostname()
        local_address = socket.gethostbyname(hostname)
        p2p_port = credentials.get('credentials', {}).get('p2p_port', 8001)
        
        # Get public key for node ID generation
        keystore_path = '/var/lib/aitbc/keystore/validator_keys.json'
        if os.path.exists(keystore_path):
            with open(keystore_path, 'r') as f:
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
            error(f"Keystore not found at {keystore_path}")
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

        # Create bid transaction
        bid_data = {
            'type': 'gpu_marketplace',
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

        # Submit transaction to blockchain
        try:
            http_client = AITBCHTTPClient(base_url=rpc_endpoint, timeout=10)
            result = http_client.post("/v1/transactions", json=bid_data)
            success(f"GPU bid created successfully!")
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
def list(ctx, provider: Optional[str], status: Optional[str], type: str):
    """List GPU marketplace offers and bids"""
    try:
        # Load island credentials
        credentials = load_island_credentials()
        rpc_endpoint = get_rpc_endpoint()
        island_id = get_island_id()

        # Query blockchain for GPU marketplace transactions
        try:
            params = {
                'transaction_type': 'gpu_marketplace',
                'island_id': island_id
            }
            if provider:
                params['provider_node_id'] = provider
            if status:
                params['status'] = status
            if type != 'all':
                params['action'] = type

            http_client = AITBCHTTPClient(base_url=rpc_endpoint, timeout=10)
            transactions = http_client.get("/transactions", params=params)
            
            if not transactions:
                info("No GPU marketplace transactions found")
                return
            
            # Format output
            market_data = []
            for tx in transactions:
                action = tx.get('action')
                if action == 'offer':
                    market_data.append({
                        "ID": tx.get('offer_id', tx.get('transaction_id', 'N/A'))[:20] + "...",
                        "Type": "OFFER",
                        "GPU Count": tx.get('gpu_count'),
                        "Price": f"{tx.get('price_per_gpu', 0):.4f} AIT/h",
                        "Duration": f"{tx.get('duration_hours')}h",
                        "Total": f"{tx.get('total_price', 0):.2f} AIT",
                        "Status": tx.get('status'),
                        "Provider": tx.get('provider_node_id', '')[:16] + "...",
                        "Created": tx.get('created_at', '')[:19]
                    })
                elif action == 'bid':
                    market_data.append({
                        "ID": tx.get('bid_id', tx.get('transaction_id', 'N/A'))[:20] + "...",
                        "Type": "BID",
                        "GPU Count": tx.get('gpu_count'),
                        "Max Price": f"{tx.get('max_price_per_gpu', 0):.4f} AIT/h",
                        "Duration": f"{tx.get('duration_hours')}h",
                        "Max Total": f"{tx.get('max_total_price', 0):.2f} AIT",
                        "Status": tx.get('status'),
                        "Bidder": tx.get('bidder_node_id', '')[:16] + "...",
                        "Created": tx.get('created_at', '')[:19]
                    })
            
            output(market_data, ctx.obj.get('output_format', 'table'), title=f"GPU Marketplace ({island_id[:16]}...)")
        except NetworkError as e:
            error(f"Network error querying blockchain: {e}")
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
        # Load island credentials
        credentials = load_island_credentials()
        rpc_endpoint = get_rpc_endpoint()
        chain_id = get_chain_id()
        island_id = get_island_id()

        # Get local node ID
        hostname = socket.gethostname()
        local_address = socket.gethostbyname(hostname)
        p2p_port = credentials.get('credentials', {}).get('p2p_port', 8001)
        
        keystore_path = '/var/lib/aitbc/keystore/validator_keys.json'
        if os.path.exists(keystore_path):
            with open(keystore_path, 'r') as f:
                keys = json.load(f)
                public_key_pem = None
                for key_id, key_data in keys.items():
                    public_key_pem = key_data.get('public_key_pem')
                    break
                if public_key_pem:
                    content = f"{hostname}:{local_address}:{p2p_port}:{public_key_pem}"
                    local_node_id = hashlib.sha256(content.encode()).hexdigest()

        # Determine if it's an offer or bid
        if order_id.startswith('gpu_offer'):
            action = 'cancel_offer'
            node_id_field = 'provider_node_id'
        elif order_id.startswith('gpu_bid'):
            action = 'cancel_bid'
            node_id_field = 'bidder_node_id'
        else:
            error("Invalid order ID format. Must start with 'gpu_offer' or 'gpu_bid'")
            raise click.Abort()

        # Create cancel transaction
        cancel_data = {
            'type': 'gpu_marketplace',
            'action': action,
            'order_id': order_id,
            'node_id': local_node_id,
            'status': 'cancelled',
            'cancelled_at': datetime.now().isoformat(),
            'island_id': island_id,
            'chain_id': chain_id
        }

        # Submit transaction to blockchain
        try:
            http_client = AITBCHTTPClient(base_url=rpc_endpoint, timeout=10)
            result = http_client.post("/transaction", json=cancel_data)
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
        # Load island credentials
        credentials = load_island_credentials()
        rpc_endpoint = get_rpc_endpoint()
        chain_id = get_chain_id()
        island_id = get_island_id()

        # Get provider node ID
        hostname = socket.gethostname()
        local_address = socket.gethostbyname(hostname)
        p2p_port = credentials.get('credentials', {}).get('p2p_port', 8001)
        
        keystore_path = '/var/lib/aitbc/keystore/validator_keys.json'
        if os.path.exists(keystore_path):
            with open(keystore_path, 'r') as f:
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
            error(f"Keystore not found at {keystore_path}")
            raise click.Abort()

        # Create accept transaction
        accept_data = {
            'type': 'gpu_marketplace',
            'action': 'accept',
            'bid_id': bid_id,
            'provider_node_id': provider_node_id,
            'status': 'accepted',
            'accepted_at': datetime.now().isoformat(),
            'island_id': island_id,
            'chain_id': chain_id
        }

        # Submit transaction to blockchain
        try:
            http_client = AITBCHTTPClient(base_url=rpc_endpoint, timeout=10)
            result = http_client.post("/transaction", json=accept_data)
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
        # Load island credentials
        credentials = load_island_credentials()
        rpc_endpoint = get_rpc_endpoint()
        island_id = get_island_id()

        # Query blockchain for the order
        try:
            params = {
                'transaction_type': 'gpu_marketplace',
                'island_id': island_id,
                'order_id': order_id
            }

            http_client = AITBCHTTPClient(base_url=rpc_endpoint, timeout=10)
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
        # Load island credentials
        credentials = load_island_credentials()
        rpc_endpoint = get_rpc_endpoint()
        island_id = get_island_id()

        # Query blockchain for open offers and bids
        try:
            params = {
                'transaction_type': 'gpu_marketplace',
                'island_id': island_id,
                'status': 'active'
            }

            http_client = AITBCHTTPClient(base_url=rpc_endpoint, timeout=10)
            transactions = http_client.get("/transactions", params=params)
            
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
                                match_result = http_client.post("/transaction", json=match_data)
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
        credentials = load_island_credentials()
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
