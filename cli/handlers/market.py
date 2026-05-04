"""Marketplace command handlers."""

import json
import os
import sys
import requests


def _marketplace_url(args, fallback=None):
    explicit_url = getattr(args, "marketplace_url", None)
    if explicit_url:
        return explicit_url
    env_url = os.getenv("AITBC_MARKETPLACE_URL") or os.getenv("EXCHANGE_API_URL")
    if env_url:
        return env_url
    if fallback and not fallback.endswith(":8011") and not fallback.endswith(":8102"):
        return fallback
    return "http://localhost:8001"


def _auth_headers(args, read_password):
    wallet = getattr(args, "wallet", None)
    password = read_password(args)
    password_file = getattr(args, "password_file", None)
    if wallet and (password or password_file):
        try:
            from keystore_auth import get_auth_headers
            return get_auth_headers(wallet, password, password_file)
        except Exception:
            return {"X-Wallet": wallet}
    if wallet:
        return {"X-Wallet": wallet}
    return {}


def handle_market_listings(args, default_coordinator_url, output_format, render_mapping):
    """Handle marketplace listings command."""
    marketplace_url = _marketplace_url(args, default_coordinator_url)
    chain_id = getattr(args, "chain_id", None)
    
    print(f"Getting marketplace listings from {marketplace_url}...")
    try:
        params = {}
        if chain_id:
            params["chain_id"] = chain_id
        
        response = requests.get(f"{marketplace_url}/v1/marketplace/offers", params=params, timeout=10)
        if response.status_code == 200:
            listings = response.json()
            if output_format(args) == "json":
                print(json.dumps(listings, indent=2))
            else:
                print("Marketplace listings:")
                if isinstance(listings, list):
                    if listings:
                        for listing in listings:
                            print(f"  - ID: {listing.get('id', 'N/A')}")
                            print(f"    Model: {listing.get('model', 'N/A')}")
                            print(f"    Price: {listing.get('price_per_hour', 0)} AIT/hour")
                            print(f"    Status: {listing.get('status', 'N/A')}")
                    else:
                        print("  No GPU listings found")
                else:
                    render_mapping("Listings:", listings)
        else:
            print(f"Query failed: {response.status_code}")
            print(f"Error: {response.text}")
            return
    except Exception as e:
        print(f"Error getting listings: {e}")
        return


def handle_market_create(args, default_coordinator_url, read_password, render_mapping):
    """Handle marketplace create command."""
    marketplace_url = _marketplace_url(args, default_coordinator_url)
    chain_id = getattr(args, "chain_id", None)
    wallet = getattr(args, "wallet", None)
    item = getattr(args, "item", None)
    item_type = getattr(args, "item_type", None) or item or "service"
    price = getattr(args, "price", None)
    
    if not wallet or price is None:
        print("Error: --wallet and --price are required")
        return
    
    headers = _auth_headers(args, read_password)
    
    listing_data = {
        "wallet": wallet,
        "item": item or item_type,
        "item_type": item_type,
        "price": price,
        "description": getattr(args, "description", ""),
    }
    if chain_id:
        listing_data["chain_id"] = chain_id
    
    print(f"Creating marketplace listing on {marketplace_url}...")
    try:
        response = requests.post(f"{marketplace_url}/v1/marketplace/offers", json=listing_data, headers=headers, timeout=30)
        if response.status_code in (200, 201):
            result = response.json()
            print("Listing created successfully")
            render_mapping("Listing:", result)
        else:
            print(f"Creation failed: {response.status_code}")
            print(f"Error: {response.text}")
            return
    except Exception as e:
        print(f"Error creating listing: {e}")
        return


def handle_market_get(args, default_rpc_url):
    """Handle marketplace get command."""
    marketplace_url = _marketplace_url(args, default_rpc_url)
    chain_id = getattr(args, "chain_id", None)
    
    if not args.listing_id:
        print("Error: --listing-id is required")
        return
    
    print(f"Getting listing {args.listing_id} from {marketplace_url}...")
    try:
        import requests
        response = requests.get(f"{marketplace_url}/v1/marketplace/offers/{args.listing_id}", timeout=10)
        if response.status_code == 200:
            listing = response.json()
            print(json.dumps(listing, indent=2))
        else:
            print(f"Query failed: {response.status_code}")
            print(f"Error: {response.text}")
            return
    except Exception as e:
        print(f"Error getting listing: {e}")
        return


def handle_market_delete(args, default_coordinator_url, read_password, render_mapping):
    """Handle marketplace delete command."""
    marketplace_url = _marketplace_url(args, default_coordinator_url)
    listing_id = getattr(args, "listing_id", None) or getattr(args, "order", None)
    
    if not listing_id:
        print("Error: --listing-id or --order is required")
        return
    
    headers = _auth_headers(args, read_password)
    endpoint_type = "orders" if str(listing_id).startswith("order_") else "offers"
    
    print(f"Deleting {endpoint_type[:-1]} {listing_id} on {marketplace_url}...")
    try:
        response = requests.delete(f"{marketplace_url}/v1/marketplace/{endpoint_type}/{listing_id}", headers=headers, timeout=30)
        if response.status_code == 200:
            result = response.json()
            print("Marketplace item deleted successfully")
            render_mapping("Delete result:", result)
        else:
            print(f"Deletion failed: {response.status_code}")
            print(f"Error: {response.text}")
            return
    except Exception as e:
        print(f"Error deleting listing: {e}")
        return


def handle_market_gpu_register(args, default_coordinator_url):
    """Handle GPU registration command with nvidia-smi auto-detection."""
    # Use GPU service URL instead of coordinator URL
    gpu_url = getattr(args, 'gpu_url', 'http://localhost:8101')
    
    # Auto-detect GPU specs from nvidia-smi
    gpu_name = args.name
    memory_gb = args.memory
    compute_capability = getattr(args, "compute_capability", None)
    
    if not gpu_name or memory_gb is None:
        print("Auto-detecting GPU specifications from nvidia-smi...")
        try:
            import subprocess
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total,compute_cap", "--format=csv,noheader"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                # Parse output: "NVIDIA GeForce RTX 4060 Ti, 16380 MiB, 8.9"
                parts = result.stdout.strip().split(", ")
                if len(parts) >= 3:
                    detected_name = parts[0]
                    detected_memory = parts[1].strip()  # "16380 MiB"
                    detected_compute = parts[2].strip()  # "8.9"
                    
                    # Convert memory to GB
                    memory_value = int(detected_memory.split()[0])  # 16380
                    memory_gb_detected = round(memory_value / 1024, 1)  # 16.0
                    
                    if not gpu_name:
                        gpu_name = detected_name
                        print(f"  Detected GPU: {gpu_name}")
                    if memory_gb is None:
                        memory_gb = memory_gb_detected
                        print(f"  Detected Memory: {memory_gb} GB")
                    if not compute_capability:
                        compute_capability = detected_compute
                        print(f"  Detected Compute Capability: {compute_capability}")
            else:
                print("  Warning: nvidia-smi failed, using manual input or defaults")
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
            print(f"  Warning: Could not run nvidia-smi: {e}")
    
    # Fallback to manual input if auto-detection failed
    if not gpu_name or memory_gb is None:
        print("Error: Could not auto-detect GPU specs. Please provide --name and --memory manually.")
        print("  Example: aitbc-cli market gpu register --name 'NVIDIA GeForce RTX 4060 Ti' --memory 16 --price-per-hour 0.05")
        return
    
    if not args.price_per_hour:
        print("Error: --price-per-hour is required (in AIT coins)")
        return
    
    # Build GPU specs
    gpu_specs = {
        "name": gpu_name,
        "memory_gb": memory_gb,
        "cuda_cores": getattr(args, "cuda_cores", None),
        "compute_capability": compute_capability,
        "price_per_hour": args.price_per_hour,
        "description": getattr(args, "description", ""),
        "miner_id": getattr(args, "miner_id", "default_miner"),
        "registered_at": __import__("datetime").datetime.now().isoformat()
    }
    
    print(f"Registering GPU on {gpu_url}...")
    try:
        response = requests.post(
            f"{gpu_url}/v1/marketplace/gpu/register",
            headers={
                "Content-Type": "application/json",
                "X-Miner-ID": gpu_specs["miner_id"]
            },
            json={"gpu": gpu_specs},
            timeout=30
        )
        if response.status_code in (200, 201):
            result = response.json()
            print(f"GPU registered successfully: {result.get('gpu_id', 'N/A')}")
            from ..utils import render_mapping
            render_mapping("Registration result:", result)
        else:
            print(f"Registration failed: {response.status_code}")
            print(f"Error: {response.text}")
            return
    except Exception as e:
        print(f"Error registering GPU: {e}")
        return


def handle_market_gpu_list(args, default_coordinator_url, output_format):
    """Handle GPU list command."""
    # Use GPU service URL instead of coordinator URL
    gpu_url = getattr(args, 'gpu_url', 'http://localhost:8101')
    
    print(f"Listing GPUs from {gpu_url}...")
    try:
        params = {
            "action": "offer",
            "status": "active"
        }
        if getattr(args, "available", None):
            params["status"] = "active"
        if getattr(args, "price_max", None):
            params["price_max"] = args.price_max
        if getattr(args, "region", None):
            params["region"] = args.region
        if getattr(args, "model", None):
            params["model"] = args.model
        if getattr(args, "limit", None):
            params["limit"] = args.limit
        
        response = requests.get(f"{gpu_url}/v1/transactions", params=params, timeout=10)
        if response.status_code == 200:
            gpus = response.json()
            if output_format(args) == "json":
                print(json.dumps(gpus, indent=2))
            else:
                print("GPU Listings:")
                if isinstance(gpus, list):
                    if gpus:
                        for gpu in gpus:
                            if isinstance(gpu, dict):
                                print(f"  - ID: {gpu.get('id', 'N/A')}")
                                print(f"    Model: {gpu.get('model', 'N/A')}")
                                print(f"    Memory: {gpu.get('memory_gb', 'N/A')} GB")
                                print(f"    Price: {gpu.get('price_per_hour', 0)} AIT/hour")
                                print(f"    Status: {gpu.get('status', 'N/A')}")
                                print(f"    Region: {gpu.get('region', 'N/A')}")
                    else:
                        print("  No GPUs found")
                else:
                    from ..utils import render_mapping
                    render_mapping("GPUs:", gpus)
        else:
            print(f"Query failed: {response.status_code}")
            print(f"Error: {response.text}")
            return
    except Exception as e:
        print(f"Error listing GPUs: {e}")
        return


def handle_market_buy(args, default_coordinator_url, read_password, render_mapping):
    """Handle marketplace buy command via marketplace service."""
    marketplace_url = _marketplace_url(args, default_coordinator_url)

    if not args.item or not args.wallet:
        print("Error: --item and --wallet are required")
        return

    purchase_data = {
        "duration_hours": 1.0,
        "wallet": args.wallet,
        "price": getattr(args, "price", None)
    }

    print(f"Submitting purchase to {marketplace_url}...")
    try:
        response = requests.post(f"{marketplace_url}/v1/marketplace/offers/{args.item}/book", json=purchase_data, headers=_auth_headers(args, read_password), timeout=30)
        if response.status_code in (200, 201):
            result = response.json()
            print("Purchase submitted successfully")
            render_mapping("Purchase:", result)
        else:
            print(f"Purchase failed: {response.status_code}")
            print(f"Error: {response.text}")
            return
    except Exception as e:
        print(f"Error submitting purchase: {e}")
        return


def handle_market_sell(args, default_coordinator_url, read_password, render_mapping):
    """Handle marketplace sell command."""
    handle_market_create(args, default_coordinator_url, read_password, render_mapping)


def handle_market_orders(args, default_coordinator_url, output_format, render_mapping):
    """Handle marketplace orders command."""
    marketplace_url = _marketplace_url(args, default_coordinator_url)
    params = {}
    wallet = getattr(args, "wallet", None)
    if wallet:
        params["wallet"] = wallet

    print(f"Getting marketplace orders from {marketplace_url}...")
    try:
        response = requests.get(f"{marketplace_url}/v1/marketplace/orders", params=params, timeout=10)
        if response.status_code == 200:
            orders = response.json()
            if output_format(args) == "json":
                print(json.dumps(orders, indent=2))
                return
            if isinstance(orders, dict):
                orders = orders.get("orders", [])
            print("Active marketplace orders:")
            if not orders:
                print("  No active orders found")
                return
            for order in orders:
                print(f"  - ID: {order.get('id', 'N/A')}")
                print(f"    Type: {order.get('order_type', 'N/A')}")
                print(f"    Item: {order.get('item', 'N/A')}")
                print(f"    Price: {order.get('price', 0)} AIT")
                print(f"    Status: {order.get('status', 'N/A')}")
        else:
            print(f"Query failed: {response.status_code}")
            print(f"Error: {response.text}")
            return
    except Exception as e:
        print(f"Error getting orders: {e}")
        return
