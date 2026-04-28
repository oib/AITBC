"""Marketplace command handlers."""

import json
import sys
import requests


def handle_market_listings(args, default_coordinator_url, output_format, render_mapping):
    """Handle marketplace listings command."""
    coordinator_url = getattr(args, 'coordinator_url', default_coordinator_url)
    chain_id = getattr(args, "chain_id", None)
    
    print(f"Getting marketplace listings from {coordinator_url}...")
    try:
        params = {}
        if chain_id:
            params["chain_id"] = chain_id
        
        response = requests.get(f"{coordinator_url}/v1/marketplace/gpu/list", params=params, timeout=10)
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
                            print(f"    Price: ${listing.get('price_per_hour', 0)}/hour")
                            print(f"    Status: {listing.get('status', 'N/A')}")
                    else:
                        print("  No GPU listings found")
                else:
                    render_mapping("Listings:", listings)
        else:
            print(f"Query failed: {response.status_code}")
            print(f"Error: {response.text}")
            sys.exit(1)
    except Exception as e:
        print(f"Error getting listings: {e}")
        sys.exit(1)


def handle_market_create(args, default_coordinator_url, read_password, render_mapping):
    """Handle marketplace create command."""
    coordinator_url = getattr(args, 'coordinator_url', default_coordinator_url)
    chain_id = getattr(args, "chain_id", None)
    
    if not args.wallet or not args.item_type or not args.price:
        print("Error: --wallet, --type, and --price are required")
        sys.exit(1)
    
    # Get auth headers
    password = read_password(args)
    from ..keystore_auth import get_auth_headers
    headers = get_auth_headers(args.wallet, password, args.password_file)
    
    listing_data = {
        "wallet": args.wallet,
        "item_type": args.item_type,
        "price": args.price,
        "description": getattr(args, "description", ""),
    }
    if chain_id:
        listing_data["chain_id"] = chain_id
    
    print(f"Creating marketplace listing on {coordinator_url}...")
    try:
        response = requests.post(f"{coordinator_url}/v1/marketplace/create", json=listing_data, headers=headers, timeout=30)
        if response.status_code == 200:
            result = response.json()
            print("Listing created successfully")
            render_mapping("Listing:", result)
        else:
            print(f"Creation failed: {response.status_code}")
            print(f"Error: {response.text}")
            sys.exit(1)
    except Exception as e:
        print(f"Error creating listing: {e}")
        sys.exit(1)


def handle_market_get(args, default_rpc_url):
    """Handle marketplace get command."""
    rpc_url = args.rpc_url or default_rpc_url
    chain_id = getattr(args, "chain_id", None)
    
    if not args.listing_id:
        print("Error: --listing-id is required")
        sys.exit(1)
    
    print(f"Getting listing {args.listing_id} from {rpc_url}...")
    try:
        import requests
        response = requests.get(f"{rpc_url}/marketplace/get/{args.listing_id}", timeout=10)
        if response.status_code == 200:
            listing = response.json()
            print(json.dumps(listing, indent=2))
        else:
            print(f"Query failed: {response.status_code}")
            print(f"Error: {response.text}")
            sys.exit(1)
    except Exception as e:
        print(f"Error getting listing: {e}")
        sys.exit(1)


def handle_market_delete(args, default_coordinator_url, read_password, render_mapping):
    """Handle marketplace delete command."""
    coordinator_url = getattr(args, 'coordinator_url', default_coordinator_url)
    chain_id = getattr(args, "chain_id", None)
    
    if not args.listing_id or not args.wallet:
        print("Error: --listing-id and --wallet are required")
        sys.exit(1)
    
    # Get auth headers
    password = read_password(args)
    from ..keystore_auth import get_auth_headers
    headers = get_auth_headers(args.wallet, password, args.password_file)
    
    delete_data = {
        "listing_id": args.listing_id,
        "wallet": args.wallet,
    }
    if chain_id:
        delete_data["chain_id"] = chain_id
    
    print(f"Deleting listing {args.listing_id} on {coordinator_url}...")
    try:
        response = requests.delete(f"{coordinator_url}/v1/marketplace/delete", json=delete_data, headers=headers, timeout=30)
        if response.status_code == 200:
            result = response.json()
            print("Listing deleted successfully")
            render_mapping("Delete result:", result)
        else:
            print(f"Deletion failed: {response.status_code}")
            print(f"Error: {response.text}")
            sys.exit(1)
    except Exception as e:
        print(f"Error deleting listing: {e}")
        sys.exit(1)


def handle_market_gpu_register(args, default_coordinator_url):
    """Handle GPU registration command with nvidia-smi auto-detection."""
    coordinator_url = getattr(args, 'coordinator_url', default_coordinator_url)
    
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
        sys.exit(1)
    
    if not args.price_per_hour:
        print("Error: --price-per-hour is required")
        sys.exit(1)
    
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
    
    print(f"Registering GPU on {coordinator_url}...")
    try:
        response = requests.post(
            f"{coordinator_url}/v1/marketplace/gpu/register",
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
            sys.exit(1)
    except Exception as e:
        print(f"Error registering GPU: {e}")
        sys.exit(1)


def handle_market_gpu_list(args, default_coordinator_url, output_format):
    """Handle GPU list command."""
    coordinator_url = getattr(args, 'coordinator_url', default_coordinator_url)
    
    print(f"Listing GPUs from {coordinator_url}...")
    try:
        params = {}
        if getattr(args, "available", None):
            params["available"] = True
        if getattr(args, "price_max", None):
            params["price_max"] = args.price_max
        if getattr(args, "region", None):
            params["region"] = args.region
        if getattr(args, "model", None):
            params["model"] = args.model
        if getattr(args, "limit", None):
            params["limit"] = args.limit
        
        response = requests.get(f"{coordinator_url}/v1/marketplace/gpu/list", params=params, timeout=10)
        if response.status_code == 200:
            gpus = response.json()
            if output_format(args) == "json":
                print(json.dumps(gpus, indent=2))
            else:
                print("GPU Listings:")
                if isinstance(gpus, list):
                    if gpus:
                        for gpu in gpus:
                            print(f"  - ID: {gpu.get('id', 'N/A')}")
                            print(f"    Model: {gpu.get('model', 'N/A')}")
                            print(f"    Memory: {gpu.get('memory_gb', 'N/A')} GB")
                            print(f"    Price: ${gpu.get('price_per_hour', 0)}/hour")
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
            sys.exit(1)
    except Exception as e:
        print(f"Error listing GPUs: {e}")
        sys.exit(1)


def handle_market_buy(args, default_rpc_url, read_password, render_mapping):
    """Handle marketplace buy command with blockchain transaction."""
    rpc_url = getattr(args, 'rpc_url', default_rpc_url)
    
    if not args.item or not args.wallet:
        print("Error: --item and --wallet are required")
        sys.exit(1)
    
    # Get password for signing
    password = read_password(args)
    if not password:
        print("Error: Password is required for signing")
        sys.exit(1)
    
    # Load wallet and get address
    from pathlib import Path
    import json
    from cryptography.hazmat.primitives.asymmetric import ed25519
    
    keystore_dir = Path("/var/lib/aitbc/keystore")
    sender_keystore = keystore_dir / f"{args.wallet}.json"
    
    if not sender_keystore.exists():
        print(f"Error: Wallet '{args.wallet}' not found")
        sys.exit(1)
    
    with open(sender_keystore) as f:
        sender_data = json.load(f)
    sender_address = sender_data['address']
    
    # Decrypt private key for signing
    try:
        sys.path.insert(0, "/opt/aitbc/cli")
        from aitbc_cli import decrypt_private_key
        private_key_hex = decrypt_private_key(sender_keystore, password)
        private_key = ed25519.Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private_key_hex))
    except Exception as e:
        print(f"Error decrypting wallet: {e}")
        sys.exit(1)
    
    # Get chain_id
    try:
        from sys.path import insert
        insert(0, "/opt/aitbc")
        from aitbc_cli.utils.chain_id import get_chain_id
        chain_id = get_chain_id(rpc_url, override=None, timeout=5)
    except Exception:
        chain_id = "ait-testnet"
    
    # Get actual nonce from blockchain
    actual_nonce = 0
    try:
        account_data = requests.get(f"{rpc_url}/rpc/account/{sender_address}", timeout=5).json()
        actual_nonce = account_data.get("nonce", 0)
    except Exception:
        actual_nonce = 0
    
    # Get GPU listing details
    try:
        coordinator_url = "http://localhost:8000"
        gpu_response = requests.get(f"{coordinator_url}/v1/marketplace/gpu/{args.item}", timeout=10)
        if gpu_response.status_code == 200:
            gpu_data = gpu_response.json()
            price = int(gpu_data.get('price_per_hour', 0) * 1000000)  # Convert to AIT
        else:
            price = 1000000  # Default price
    except Exception:
        price = 1000000  # Default price
    
    # Create transaction with marketplace purchase payload
    transaction = {
        "type": "TRANSFER",
        "chain_id": chain_id,
        "from": sender_address,
        "nonce": actual_nonce,
        "fee": 10,
        "payload": {
            "recipient": gpu_data.get('owner_address', 'ait0000000000000000000000000000000000000000'),
            "amount": price,
            "item_id": args.item,
            "action": "buy"
        }
    }
    
    # Sign transaction
    message = json.dumps(transaction, sort_keys=True).encode()
    signature = private_key.sign(message)
    transaction["signature"] = signature.hex()
    
    print(f"Submitting purchase transaction to {rpc_url}...")
    try:
        response = requests.post(f"{rpc_url}/rpc/transaction", json=transaction, timeout=30)
        if response.status_code == 200:
            result = response.json()
            print("Purchase transaction submitted successfully")
            render_mapping("Transaction:", result)
        else:
            print(f"Purchase failed: {response.status_code}")
            print(f"Error: {response.text}")
            sys.exit(1)
    except Exception as e:
        print(f"Error submitting purchase: {e}")
        sys.exit(1)
