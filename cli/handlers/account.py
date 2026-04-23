"""Account handlers."""

import json
import sys

import requests


def handle_account_get(args, default_rpc_url, output_format):
    """Handle account get command."""
    rpc_url = args.rpc_url or default_rpc_url
    chain_id = getattr(args, "chain_id", None)
    
    if not args.address:
        print("Error: --address is required")
        sys.exit(1)
    
    print(f"Getting account {args.address} from {rpc_url}...")
    try:
        params = {}
        if chain_id:
            params["chain_id"] = chain_id
        
        response = requests.get(f"{rpc_url}/rpc/account/{args.address}", params=params, timeout=10)
        if response.status_code == 200:
            account = response.json()
            if output_format(args) == "json":
                print(json.dumps(account, indent=2))
            else:
                render_mapping(f"Account {args.address}:", account)
        else:
            print(f"Query failed: {response.status_code}")
            print(f"Error: {response.text}")
            sys.exit(1)
    except Exception as e:
        print(f"Error getting account: {e}")
        sys.exit(1)
