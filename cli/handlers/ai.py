"""AI job submission and management handlers."""

import json
import sys

import requests


def handle_ai_submit(args, default_rpc_url, first, read_password, render_mapping):
    """Handle AI job submission."""
    rpc_url = args.rpc_url or default_rpc_url
    chain_id = getattr(args, "chain_id", None)
    
    wallet = first(getattr(args, "wallet_name", None), getattr(args, "wallet", None))
    model = first(getattr(args, "job_type_arg", None), getattr(args, "job_type", None))
    prompt = first(getattr(args, "prompt_arg", None), getattr(args, "prompt", None))
    payment = first(getattr(args, "payment_arg", None), getattr(args, "payment", None))
    
    if not wallet or not model or not prompt:
        print("Error: --wallet, --type, and --prompt are required")
        sys.exit(1)
    
    # Get password for signing
    password = read_password(args)
    if not password:
        print("Error: Password is required for signing")
        sys.exit(1)
    
    # Get auth headers using correct decryption
    from pathlib import Path
    import json
    from cryptography.hazmat.primitives.asymmetric import ed25519
    
    keystore_dir = Path("/var/lib/aitbc/keystore")
    sender_keystore = keystore_dir / f"{wallet}.json"
    
    if not sender_keystore.exists():
        print(f"Error: Wallet '{wallet}' not found")
        sys.exit(1)
    
    # Decrypt private key using the correct method
    try:
        sys.path.insert(0, "/opt/aitbc/cli")
        from aitbc_cli import decrypt_private_key
        private_key_hex = decrypt_private_key(sender_keystore, password)
        private_key = ed25519.Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private_key_hex))
    except Exception as e:
        print(f"Error decrypting wallet: {e}")
        sys.exit(1)
    
    # Get sender address
    with open(sender_keystore) as f:
        sender_data = json.load(f)
    sender_address = sender_data['address']
    
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
    
    # Create transaction with AI job payload
    transaction = {
        "type": "TRANSFER",
        "chain_id": chain_id,
        "from": sender_address,
        "nonce": actual_nonce,
        "fee": 10,
        "payload": {
            "recipient": "ait0000000000000000000000000000000000000000",  # AI service address
            "amount": payment if payment else 50,
            "job_type": model,
            "prompt": prompt
        }
    }
    
    # Sign transaction
    import json
    message = json.dumps(transaction, sort_keys=True).encode()
    signature = private_key.sign(message)
    transaction["signature"] = signature.hex()
    
    job_data = {
        "wallet": sender_address,
        "model": model,
        "prompt": prompt,
        "transaction": transaction
    }
    if payment:
        job_data["payment"] = payment
    if chain_id:
        job_data["chain_id"] = chain_id
    
    print(f"Submitting AI job to {rpc_url}...")
    try:
        response = requests.post(f"{rpc_url}/rpc/ai/submit", json=job_data, timeout=30)
        if response.status_code == 200:
            result = response.json()
            print("AI job submitted successfully")
            render_mapping("Job:", result)
        else:
            print(f"Submission failed: {response.status_code}")
            print(f"Error: {response.text}")
            sys.exit(1)
    except Exception as e:
        print(f"Error submitting AI job: {e}")
        sys.exit(1)


def handle_ai_jobs(args, default_rpc_url, output_format, render_mapping):
    """Handle AI jobs list query."""
    rpc_url = args.rpc_url or default_rpc_url
    chain_id = getattr(args, "chain_id", None)
    
    print(f"Getting AI jobs from {rpc_url}...")
    try:
        params = {}
        if chain_id:
            params["chain_id"] = chain_id
        if args.limit:
            params["limit"] = args.limit
        
        response = requests.get(f"{rpc_url}/rpc/ai/jobs", params=params, timeout=10)
        if response.status_code == 200:
            jobs = response.json()
            if output_format(args) == "json":
                print(json.dumps(jobs, indent=2))
            else:
                print("AI jobs:")
                if isinstance(jobs, list):
                    for job in jobs:
                        print(f"  Job ID: {job.get('job_id', 'N/A')}, Model: {job.get('model', 'N/A')}, Status: {job.get('status', 'N/A')}")
                else:
                    render_mapping("Jobs:", jobs)
        else:
            print(f"Query failed: {response.status_code}")
            print(f"Error: {response.text}")
            sys.exit(1)
    except Exception as e:
        print(f"Error getting AI jobs: {e}")
        sys.exit(1)


def handle_ai_job(args, default_rpc_url, output_format, render_mapping, first):
    """Handle AI job details query."""
    rpc_url = args.rpc_url or default_rpc_url
    chain_id = getattr(args, "chain_id", None)
    
    job_id = first(getattr(args, "job_id_arg", None), getattr(args, "job_id", None))
    
    if not job_id:
        print("Error: --job-id is required")
        sys.exit(1)
    
    print(f"Getting AI job {job_id} from {rpc_url}...")
    try:
        params = {}
        if chain_id:
            params["chain_id"] = chain_id
        
        response = requests.get(f"{rpc_url}/rpc/ai/job/{job_id}", params=params, timeout=10)
        if response.status_code == 200:
            job = response.json()
            if output_format(args) == "json":
                print(json.dumps(job, indent=2))
            else:
                render_mapping(f"Job {job_id}:", job)
        else:
            print(f"Query failed: {response.status_code}")
            print(f"Error: {response.text}")
            sys.exit(1)
    except Exception as e:
        print(f"Error getting AI job: {e}")
        sys.exit(1)


def handle_ai_cancel(args, default_rpc_url, read_password, render_mapping, first):
    """Handle AI job cancellation."""
    rpc_url = args.rpc_url or default_rpc_url
    chain_id = getattr(args, "chain_id", None)
    
    job_id = first(getattr(args, "job_id_arg", None), getattr(args, "job_id", None))
    wallet = getattr(args, "wallet", None)
    
    if not job_id or not wallet:
        print("Error: --job-id and --wallet are required")
        sys.exit(1)
    
    # Get auth headers
    password = read_password(args)
    from keystore_auth import get_auth_headers
    headers = get_auth_headers(wallet, password, args.password_file)
    
    cancel_data = {
        "job_id": job_id,
        "wallet": wallet,
    }
    if chain_id:
        cancel_data["chain_id"] = chain_id
    
    print(f"Cancelling AI job {job_id} on {rpc_url}...")
    try:
        response = requests.post(f"{rpc_url}/rpc/ai/job/{job_id}/cancel", json=cancel_data, headers=headers, timeout=30)
        if response.status_code == 200:
            result = response.json()
            print("AI job cancelled successfully")
            render_mapping("Cancel result:", result)
        else:
            print(f"Cancellation failed: {response.status_code}")
            print(f"Error: {response.text}")
            sys.exit(1)
    except Exception as e:
        print(f"Error cancelling AI job: {e}")
        sys.exit(1)


def handle_ai_stats(args, default_rpc_url, output_format, render_mapping):
    """Handle AI service statistics query."""
    rpc_url = args.rpc_url or default_rpc_url
    chain_id = getattr(args, "chain_id", None)
    
    print(f"Getting AI service statistics from {rpc_url}...")
    try:
        params = {}
        if chain_id:
            params["chain_id"] = chain_id
        
        response = requests.get(f"{rpc_url}/rpc/ai/stats", params=params, timeout=10)
        if response.status_code == 200:
            stats = response.json()
            if output_format(args) == "json":
                print(json.dumps(stats, indent=2))
            else:
                render_mapping("AI service statistics:", stats)
        else:
            print(f"Query failed: {response.status_code}")
            print(f"Error: {response.text}")
            sys.exit(1)
    except Exception as e:
        print(f"Error getting AI stats: {e}")
        sys.exit(1)


def handle_ai_service_list(args, ai_operations, render_mapping):
    """Handle AI service list command."""
    result = ai_operations("service_list")
    if result:
        render_mapping("AI Services:", result)
    else:
        sys.exit(1)


def handle_ai_service_status(args, ai_operations, render_mapping):
    """Handle AI service status command."""
    kwargs = {}
    if hasattr(args, "name") and args.name:
        kwargs["name"] = args.name
    result = ai_operations("service_status", **kwargs)
    if result:
        render_mapping("Service Status:", result)
    else:
        sys.exit(1)


def handle_ai_service_test(args, ai_operations, render_mapping):
    """Handle AI service test command."""
    kwargs = {}
    if hasattr(args, "name") and args.name:
        kwargs["name"] = args.name
    result = ai_operations("service_test", **kwargs)
    if result:
        render_mapping("Service Test:", result)
    else:
        sys.exit(1)
