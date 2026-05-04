"""Contract command handlers for AITBC CLI"""

import requests
from typing import Optional, Dict, Any


def handle_contract_list(args, default_rpc_url: str):
    """Handle contract list command"""
    rpc_url = args.rpc_url if hasattr(args, 'rpc_url') and args.rpc_url else default_rpc_url
    
    try:
        response = requests.get(f"{rpc_url}/rpc/contracts", timeout=30)
        if response.status_code == 200:
            data = response.json()
            # Handle both response formats: with or without "success" field
            if data.get("success") is not False:
                contracts = data.get("contracts", [])
                if contracts:
                    print(f"Deployed contracts ({len(contracts)}):")
                    for contract in contracts:
                        print(f"  - Address: {contract.get('address', 'N/A')}")
                        print(f"    Type: {contract.get('type', 'N/A')}")
                        print(f"    Deployed: {contract.get('deployed_at', 'N/A')}")
                else:
                    print("No contracts deployed")
            else:
                print(f"Error: {data.get('error', 'Unknown error')}")
        else:
            print(f"Error: RPC returned {response.status_code}")
    except Exception as e:
        print(f"Error listing contracts: {e}")


def handle_contract_deploy(args, default_rpc_url: str, read_password, render_mapping):
    """Handle contract deploy command"""
    rpc_url = args.rpc_url if hasattr(args, 'rpc_url') and args.rpc_url else default_rpc_url
    contract_name = getattr(args, 'name', None)
    contract_type = getattr(args, 'type', 'zk-verifier')
    
    if not contract_name:
        print("Error: Contract name is required (--name)")
        return
    
    password = read_password(args)
    if not password:
        print("Error: Wallet password is required (--password or --password-file)")
        return
    
    try:
        payload = {
            "name": contract_name,
            "type": contract_type
        }
        
        response = requests.post(
            f"{rpc_url}/rpc/contracts/deploy",
            json=payload,
            headers={"X-Wallet-Password": password},
            timeout=60
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                render_mapping("Contract deployed successfully", data)
            else:
                print(f"Error: {data.get('error', 'Unknown error')}")
        else:
            print(f"Error: RPC returned {response.status_code}")
    except Exception as e:
        print(f"Error deploying contract: {e}")


def handle_contract_call(args, default_rpc_url: str, read_password):
    """Handle contract call command"""
    rpc_url = args.rpc_url if hasattr(args, 'rpc_url') and args.rpc_url else default_rpc_url
    contract_address = getattr(args, 'address', None)
    method = getattr(args, 'method', None)
    
    if not contract_address:
        print("Error: Contract address is required (--address)")
        return
    
    if not method:
        print("Error: Method name is required (--method)")
        return
    
    password = read_password(args)
    
    try:
        payload = {
            "address": contract_address,
            "method": method
        }
        
        # Add optional parameters
        if hasattr(args, 'params') and args.params:
            payload["params"] = args.params
        
        headers = {}
        if password:
            headers["X-Wallet-Password"] = password
        
        response = requests.post(
            f"{rpc_url}/rpc/contracts/call",
            json=payload,
            headers=headers,
            timeout=60
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                result = data.get("result")
                print(f"Contract call result:")
                print(f"  Address: {contract_address}")
                print(f"  Method: {method}")
                print(f"  Result: {result}")
            else:
                print(f"Error: {data.get('error', 'Unknown error')}")
        else:
            print(f"Error: RPC returned {response.status_code}")
    except Exception as e:
        print(f"Error calling contract: {e}")


def handle_contract_verify(args, default_rpc_url: str, read_password):
    """Handle contract verify command (for ZK proofs)"""
    rpc_url = args.rpc_url if hasattr(args, 'rpc_url') and args.rpc_url else default_rpc_url
    contract_address = getattr(args, 'address', None)
    
    if not contract_address:
        print("Error: Contract address is required (--address)")
        return
    
    password = read_password(args)
    
    try:
        payload = {
            "address": contract_address
        }
        
        # Add proof data if available
        if hasattr(args, 'proof_file') and args.proof_file:
            import json
            with open(args.proof_file) as f:
                proof_data = json.load(f)
            payload["proof"] = proof_data
        
        headers = {}
        if password:
            headers["X-Wallet-Password"] = password
        
        response = requests.post(
            f"{rpc_url}/rpc/contracts/verify",
            json=payload,
            headers=headers,
            timeout=60
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                result = data.get("result")
                print(f"Verification result:")
                print(f"  Address: {contract_address}")
                print(f"  Valid: {result.get('valid', False)}")
                if result.get('receipt_hash'):
                    print(f"  Receipt Hash: {result.get('receipt_hash')}")
            else:
                print(f"Error: {data.get('error', 'Unknown error')}")
        else:
            print(f"Error: RPC returned {response.status_code}")
    except Exception as e:
        print(f"Error verifying contract: {e}")
