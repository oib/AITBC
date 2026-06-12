# mypy: ignore-errors
"""
ETH-AIT Bridge Monitor
Polls Ethereum RPC for incoming ETH transactions to the bridge wallet address.
"""

import os
import threading
import time

import requests

from .bridge_db import get_deposit_by_tx_hash, init_db, insert_deposit
from .price_api import calculate_ait_amount

# Configuration
ETH_RPC_URL = os.getenv("ETH_RPC_URL", "https://eth.llamarpc.com")
ETH_WALLET_ADDRESS = os.getenv("ETH_WALLET_ADDRESS", "")
POLL_INTERVAL = int(os.getenv("BRIDGE_POLL_INTERVAL", "30"))  # seconds
BRIDGE_ENABLED = os.getenv("BRIDGE_ENABLED", "false").lower() == "true"


def get_eth_transactions(address: str) -> list:
    """
    Fetch recent transactions for an Ethereum address using RPC.
    Returns list of transaction objects.
    """
    try:
        # Use etherscan-like API or RPC to get transactions
        # For MVP, we'll use a simple RPC call to get latest block and filter
        # In production, use proper block explorer API or indexer
        
        payload = {
            "jsonrpc": "2.0",
            "method": "eth_getBlockByNumber",
            "params": ["latest", False],
            "id": 1
        }
        
        response = requests.post(ETH_RPC_URL, json=payload, timeout=10)
        response.raise_for_status()
        
        block_data = response.json()
        if "result" not in block_data:
            return []
        
        transactions = block_data["result"].get("transactions", [])
        
        # Filter transactions to our wallet address
        relevant_txs = []
        for tx in transactions:
            if tx.get("to", "").lower() == address.lower():
                relevant_txs.append(tx)
        
        return relevant_txs
    except Exception as e:
        print(f"Error fetching ETH transactions: {e}")
        return []


def process_transaction(tx: dict) -> bool:
    """
    Process a single ETH transaction and record it as a deposit.
    Returns True if deposit was recorded, False if already exists.
    """
    tx_hash = tx.get("hash", "")
    from_address = tx.get("from", "")
    
    # Parse ETH amount (hex wei to ETH)
    value_hex = tx.get("value", "0x0")
    value_wei = int(value_hex, 16)
    amount_eth = value_wei / 1e18  # Convert wei to ETH
    
    if amount_eth <= 0:
        return False
    
    # Check if already recorded
    existing = get_deposit_by_tx_hash(tx_hash)
    if existing:
        return False
    
    # Calculate AIT amount
    amount_ait = calculate_ait_amount(amount_eth)
    if amount_ait is None:
        print(f"Failed to calculate AIT amount for tx {tx_hash}")
        return False
    
    # Record deposit
    try:
        deposit_id = insert_deposit(tx_hash, from_address, amount_eth, amount_ait)
        print(f"Recorded deposit {deposit_id}: {amount_eth} ETH → {amount_ait} AIT (tx: {tx_hash})")
        return True
    except ValueError as e:
        print(f"Deposit already exists: {e}")
        return False
    except Exception as e:
        print(f"Error recording deposit: {e}")
        return False


def monitor_loop():
    """
    Main monitoring loop that polls for new transactions.
    """
    if not BRIDGE_ENABLED:
        print("Bridge monitoring disabled (BRIDGE_ENABLED=false)")
        return
    
    if not ETH_WALLET_ADDRESS:
        print("Bridge monitoring disabled (ETH_WALLET_ADDRESS not set)")
        return
    
    print(f"Starting bridge monitor for address {ETH_WALLET_ADDRESS}")
    print(f"Polling interval: {POLL_INTERVAL}s")
    
    init_db()
    
    while True:
        try:
            transactions = get_eth_transactions(ETH_WALLET_ADDRESS)
            
            for tx in transactions:
                process_transaction(tx)
            
        except Exception as e:
            print(f"Error in monitor loop: {e}")
        
        time.sleep(POLL_INTERVAL)


def start_monitoring():
    """
    Start the bridge monitoring in a background thread.
    """
    if not BRIDGE_ENABLED:
        return None
    
    monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
    monitor_thread.start()
    return monitor_thread


if __name__ == "__main__":
    # For testing
    print("Testing bridge monitor...")
    start_monitoring()
    time.sleep(60)  # Run for 1 minute
