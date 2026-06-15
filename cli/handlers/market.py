"""Marketplace command handlers."""

import json
import os

import requests

from aitbc import get_logger

logger = get_logger(__name__)


def _marketplace_url(args, fallback=None):
    explicit_url = getattr(args, "marketplace_url", None)
    if explicit_url:
        return explicit_url
    env_url = os.getenv("AITBC_MARKETPLACE_URL") or os.getenv("EXCHANGE_API_URL")
    if env_url:
        return env_url
    if fallback and not fallback.endswith(":8011") and not fallback.endswith(":8102"):
        return fallback
    return "http://localhost:8102"


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

    print("Getting marketplace listings from %s...", marketplace_url)
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
                            print("  - ID: %s", listing.get("id", "N/A"))
                            print("    Model: %s", listing.get("model", "N/A"))
                            print("    Price: %s AIT/hour", listing.get("price_per_hour", 0))
                            print("    Status: %s", listing.get("status", "N/A"))
                    else:
                        print("  No GPU listings found")
                else:
                    render_mapping("Listings:", listings)
        else:
            print(f"Query failed: {response.status_code}")
            print(f"Error: {response.text}")
            return
    except Exception as e:
        print("Error getting listings: %s", e)
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
        logger.error("Error: --wallet and --price are required")
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

    logger.info("Creating marketplace listing on %s...", marketplace_url)
    try:
        response = requests.post(f"{marketplace_url}/v1/marketplace/offers", json=listing_data, headers=headers, timeout=30)
        if response.status_code in (200, 201):
            result = response.json()
            logger.info("Listing created successfully")
            render_mapping("Listing:", result)
        else:
            logger.error("Creation failed: %s", response.status_code)
            logger.error("Error: %s", response.text)
            return
    except Exception as e:
        logger.error("Error creating listing: %s", e)
        return


def handle_market_get(args, default_rpc_url):
    """Handle marketplace get command."""
    marketplace_url = _marketplace_url(args, default_rpc_url)
    _ = getattr(args, "chain_id", None)

    if not args.listing_id:
        logger.error("Error: --listing-id is required")
        return

    logger.info("Getting listing %s from %s...", args.listing_id, marketplace_url)
    try:
        import requests

        response = requests.get(f"{marketplace_url}/v1/marketplace/offers/{args.listing_id}", timeout=10)
        if response.status_code == 200:
            listing = response.json()
            logger.info(json.dumps(listing, indent=2))
        else:
            logger.error("Query failed: %s", response.status_code)
            logger.error("Error: %s", response.text)
            return
    except Exception as e:
        logger.error("Error getting listing: %s", e)
        return


def handle_market_delete(args, default_coordinator_url, read_password, render_mapping):
    """Handle marketplace delete command."""
    marketplace_url = _marketplace_url(args, default_coordinator_url)
    listing_id = getattr(args, "listing_id", None) or getattr(args, "order", None)

    if not listing_id:
        logger.error("Error: --listing-id or --order is required")
        return

    headers = _auth_headers(args, read_password)
    endpoint_type = "orders" if str(listing_id).startswith("order_") else "offers"

    logger.info("Deleting %s %s on %s...", endpoint_type[:-1], listing_id, marketplace_url)
    try:
        response = requests.delete(
            f"{marketplace_url}/v1/marketplace/{endpoint_type}/{listing_id}", headers=headers, timeout=30
        )
        if response.status_code == 200:
            result = response.json()
            logger.info("Marketplace item deleted successfully")
            render_mapping("Delete result:", result)
        else:
            logger.error("Deletion failed: %s", response.status_code)
            logger.error("Error: %s", response.text)
            return
    except Exception as e:
        logger.error("Error deleting listing: %s", e)
        return


def handle_market_gpu_register(args, default_coordinator_url):
    """Handle GPU registration command with mandatory nvidia-smi auto-detection."""
    # Use GPU service URL instead of coordinator URL
    gpu_url = getattr(args, "gpu_url", "http://localhost:8101")

    # Mandatory nvidia-smi auto-detection
    logger.info("Auto-detecting GPU specifications from nvidia-smi...")
    try:
        import subprocess

        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,compute_cap", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            logger.error("Error: nvidia-smi command failed")
            logger.error("GPU registration requires nvidia-smi to detect actual hardware")
            return

        # Parse output: "NVIDIA GeForce RTX 4060 Ti, 16380 MiB, 8.9"
        parts = result.stdout.strip().split(", ")
        if len(parts) < 3:
            logger.error("Error: Could not parse nvidia-smi output")
            logger.error("Output: %s", result.stdout)
            return

        detected_name = parts[0]
        detected_memory = parts[1].strip()  # "16380 MiB"
        detected_compute = parts[2].strip()  # "8.9"

        # Convert memory to GB
        memory_value = int(detected_memory.split()[0])  # 16380
        memory_gb = round(memory_value / 1024, 1)  # 16.0

        gpu_name = detected_name
        compute_capability = detected_compute

        logger.info("  Detected GPU: %s", gpu_name)
        logger.info("  Detected Memory: %s GB", memory_gb)
        logger.info("  Detected Compute Capability: %s", compute_capability)

    except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
        logger.error("Error: Could not run nvidia-smi: %s", e)
        logger.error("GPU registration requires nvidia-smi to detect actual hardware")
        logger.error("Please ensure NVIDIA drivers and nvidia-smi are installed")
        return

    if not args.price_per_hour:
        logger.error("Error: --price-per-hour is required (in AIT coins)")
        return

    # Build GPU specs from nvidia-smi detection only
    gpu_specs = {
        "name": gpu_name,
        "memory_gb": memory_gb,
        "cuda_cores": getattr(args, "cuda_cores", None),
        "compute_capability": compute_capability,
        "price_per_hour": args.price_per_hour,
        "description": getattr(args, "description", ""),
        "miner_id": getattr(args, "miner_id", "default_miner"),
        "registered_at": __import__("datetime").datetime.now().isoformat(),
    }

    logger.info("Registering GPU on %s...", gpu_url)
    try:
        # Prepare blockchain transaction data
        gpu_transaction = {
            "type": "gpu_marketplace",
            "action": "offer",
            "provider_node_id": gpu_specs["miner_id"],
            "provider_address": getattr(args, "wallet", ""),
            "price_per_gpu": gpu_specs["price_per_hour"],
            "specs": {
                "model": gpu_name,
                "memory_gb": memory_gb,
                "cuda_cores": getattr(args, "cuda_cores", 0),
                "compute_capability": compute_capability,
                "description": gpu_specs["description"],
                "region": getattr(args, "region", ""),
                "capabilities": [],
            },
            "status": "available",
            "offer_id": f"gpu_{gpu_specs['miner_id']}_{__import__('time').time()}",
            "signature": getattr(args, "signature", ""),
        }

        response = requests.post(
            f"{gpu_url}/v1/transactions",
            headers={"Content-Type": "application/json", "X-Miner-ID": gpu_specs["miner_id"]},
            json=gpu_transaction,
            timeout=30,
        )
        if response.status_code in (200, 201):
            result = response.json()
            # Handle both dict and list responses
            if isinstance(result, list) and len(result) > 0:
                result = result[0]  # Take first element if it's a list

            if isinstance(result, dict) and result.get("blockchain_registered"):
                print("GPU registered successfully on blockchain")
                print("  GPU ID: %s", result.get("transaction_id", "N/A"))
                print("  Blockchain TX: %s", result.get("blockchain_tx_hash", "N/A"))
            elif isinstance(result, dict):
                print("GPU registered locally: %s", result.get("transaction_id", "N/A"))
            else:
                print("GPU registration completed: %s", result)
            print("Registration result:")
            print(result)
        else:
            logger.error("Registration failed: %s", response.status_code)
            logger.error("Error: %s", response.text)
            return
    except Exception as e:
        logger.error("Error registering GPU: %s", e)
        return


def handle_market_gpu_list(args, default_coordinator_url, output_format):
    """Handle GPU list command."""
    # Use GPU service URL instead of coordinator URL
    gpu_url = getattr(args, "gpu_url", "http://localhost:8101")

    print("Listing GPUs from %s...", gpu_url)
    try:
        params = {"action": "offer", "status": "active"}
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
                                print("  - ID: %s", gpu.get("id", "N/A"))
                                print("    Model: %s", gpu.get("model", "N/A"))
                                print("    Memory: %s GB", gpu.get("memory_gb", "N/A"))
                                print("    Price: %s AIT/hour", gpu.get("price_per_hour", 0))
                                print("    Status: %s", gpu.get("status", "N/A"))
                                print("    Region: %s", gpu.get("region", "N/A"))
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
        print("Error listing GPUs: %s", e)
        return


def handle_market_buy(args, default_coordinator_url, read_password, render_mapping):
    """Handle marketplace buy command via marketplace service."""
    marketplace_url = _marketplace_url(args, default_coordinator_url)

    if not args.item or not args.wallet:
        logger.error("Error: --item and --wallet are required")
        return

    purchase_data = {"duration_hours": 1.0, "wallet": args.wallet, "price": getattr(args, "price", None)}

    logger.info("Submitting purchase to %s...", marketplace_url)
    try:
        response = requests.post(
            f"{marketplace_url}/v1/marketplace/offers/{args.item}/book",
            json=purchase_data,
            headers=_auth_headers(args, read_password),
            timeout=30,
        )
        if response.status_code in (200, 201):
            result = response.json()
            logger.info("Purchase submitted successfully")
            render_mapping("Purchase:", result)
        else:
            logger.error("Purchase failed: %s", response.status_code)
            logger.error("Error: %s", response.text)
            return
    except Exception as e:
        logger.error("Error submitting purchase: %s", e)
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

    logger.info("Getting marketplace orders from %s...", marketplace_url)
    try:
        response = requests.get(f"{marketplace_url}/v1/marketplace/orders", params=params, timeout=10)
        if response.status_code == 200:
            orders = response.json()
            if output_format(args) == "json":
                logger.info(json.dumps(orders, indent=2))
                return
            if isinstance(orders, dict):
                orders = orders.get("orders", [])
            logger.info("Active marketplace orders:")
            if not orders:
                logger.info("  No active orders found")
                return
            for order in orders:
                logger.info("  - ID: %s", order.get("id", "N/A"))
                logger.info("    Type: %s", order.get("order_type", "N/A"))
                logger.info("    Item: %s", order.get("item", "N/A"))
                logger.info("    Price: %s AIT", order.get("price", 0))
                logger.info("    Status: %s", order.get("status", "N/A"))
        else:
            logger.error("Query failed: %s", response.status_code)
            logger.error("Error: %s", response.text)
            return
    except Exception as e:
        logger.error("Error getting orders: %s", e)
        return


def handle_market_list_plugins(args, default_coordinator_url, output_format, render_mapping):
    """Handle marketplace plugin listing command."""
    marketplace_url = _marketplace_url(args, default_coordinator_url)

    logger.info("Getting marketplace plugins from %s...", marketplace_url)
    try:
        response = requests.get(f"{marketplace_url}/v1/marketplace/plugins", timeout=10)
        if response.status_code == 200:
            plugins = response.json()
            if output_format(args) == "json":
                logger.info(json.dumps(plugins, indent=2))
                return
            if isinstance(plugins, dict):
                plugins = plugins.get("plugins", [])
            logger.info("Available marketplace plugins:")
            if not plugins:
                logger.info("  No plugins found")
                return
            for plugin in plugins:
                logger.info("  - ID: %s", plugin.get("id", "N/A"))
                logger.info("    Name: %s", plugin.get("name", "N/A"))
                logger.info("    Type: %s", plugin.get("type", "N/A"))
                logger.info("    Author: %s", plugin.get("author", "N/A"))
                logger.info("    Description: %s", plugin.get("description", "N/A"))
                logger.info("    Version: %s", plugin.get("version", "N/A"))
        else:
            logger.error("Query failed: %s", response.status_code)
            logger.error("Error: %s", response.text)
            return
    except Exception as e:
        logger.error("Error getting plugins: %s", e)
        return
