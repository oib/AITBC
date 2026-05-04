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
    
    # Get sender address (no password needed for Agent Coordinator)
    from pathlib import Path
    import json
    
    # Get sender address
    keystore_dir = Path("/var/lib/aitbc/keystore")
    sender_keystore = keystore_dir / f"{wallet}.json"
    
    coordinator_url = getattr(args, 'rpc_url', default_coordinator_url) or default_coordinator_url

    # Build AI job request
    job_data = {
        "model": getattr(args, 'model', 'llama2'),
        "prompt": getattr(args, 'prompt', ''),
        "parameters": getattr(args, 'parameters', {})
    }

    print(f"Submitting AI job to {coordinator_url}...")
    try:
        response = requests.post(f"{coordinator_url}/tasks/submit", json=job_data, timeout=30)
        if response.status_code in (200, 201):
            result = response.json()
            print("AI job submitted successfully")
            render_mapping("Job:", result)
        else:
            print(f"Job submission failed: {response.status_code}")
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


def handle_ai_status(args, default_coordinator_url, default_rpc_url, output_format, render_mapping):
    """Handle AI service status check (combined Agent Coordinator and Blockchain AI)."""
    coordinator_url = getattr(args, 'coordinator_url', None) or default_coordinator_url
    rpc_url = args.rpc_url or default_rpc_url
    
    combined_status = {
        "agent_coordinator": {"status": "unavailable"},
        "blockchain_ai": {"status": "unavailable"},
        "overall": "unavailable"
    }
    
    # Check Agent Coordinator health
    print(f"Checking Agent Coordinator at {coordinator_url}...")
    try:
        response = requests.get(f"{coordinator_url}/health", timeout=10)
        if response.status_code == 200:
            coordinator_data = response.json()
            combined_status["agent_coordinator"] = coordinator_data
            print(f"  Agent Coordinator: {coordinator_data.get('status', 'unknown')} (v{coordinator_data.get('version', 'N/A')})")
        else:
            print(f"  Agent Coordinator: Failed (HTTP {response.status_code})")
    except Exception as e:
        print(f"  Agent Coordinator: Error - {e}")
    
    # Check Blockchain AI stats
    print(f"Checking Blockchain AI stats at {rpc_url}...")
    try:
        params = {}
        if hasattr(args, "chain_id") and args.chain_id:
            params["chain_id"] = args.chain_id
        response = requests.get(f"{rpc_url}/rpc/ai/stats", params=params, timeout=10)
        if response.status_code == 200:
            stats_data = response.json()
            combined_status["blockchain_ai"] = stats_data
            print(f"  Blockchain AI Stats: Available")
        else:
            print(f"  Blockchain AI Stats: Not available (HTTP {response.status_code})")
    except Exception as e:
        print(f"  Blockchain AI Stats: Error - {e}")
    
    # Calculate overall status
    if combined_status["agent_coordinator"].get("status") == "healthy" and combined_status["blockchain_ai"].get("status") != "unavailable":
        combined_status["overall"] = "operational"
    elif combined_status["agent_coordinator"].get("status") == "healthy" or combined_status["blockchain_ai"].get("status") != "unavailable":
        combined_status["overall"] = "partially_operational"
    
    # Render output
    if output_format(args) == "json":
        print(json.dumps(combined_status, indent=2))
    else:
        print(f"\nOverall Status: {combined_status['overall']}")
        if combined_status["agent_coordinator"].get("status") == "healthy":
            print("  Agent Coordinator: Operational")
        elif combined_status["agent_coordinator"].get("status") != "unavailable":
            print(f"  Agent Coordinator: {combined_status['agent_coordinator'].get('status')}")
        else:
            print("  Agent Coordinator: Unavailable")
        
        if combined_status["blockchain_ai"].get("status") != "unavailable":
            print("  Blockchain AI: Operational")
        else:
            print("  Blockchain AI: Unavailable")
