#!/usr/bin/env python3
"""
Bitcoin Wallet Integration for AITBC Exchange
Uses RPC to connect to Bitcoin Core (or alternative like Block.io)
"""

import os
import json
import logging
import requests
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Bitcoin wallet configuration (credentials from environment)
WALLET_CONFIG = {
    'testnet': True,
    'rpc_url': os.environ.get('BITCOIN_RPC_URL', 'http://127.0.0.1:18332'),
    'rpc_user': os.environ.get('BITCOIN_RPC_USER', 'aitbc_rpc'),
    'rpc_password': os.environ.get('BITCOIN_RPC_PASSWORD', ''),
    'wallet_name': os.environ.get('BITCOIN_WALLET_NAME', 'aitbc_exchange'),
    'fallback_address': os.environ.get('BITCOIN_FALLBACK_ADDRESS', 'tb1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh'),
}

class BitcoinWallet:
    def __init__(self):
        self.config = WALLET_CONFIG
        self.session = requests.Session()
        self.session.auth = (self.config['rpc_user'], self.config['rpc_password'])
        
    def get_balance(self) -> float:
        """Get the current Bitcoin balance"""
        try:
            result = self._rpc_call('getbalance', ["*", 0, False])
            if result.get('error') is not None:
                logger.error("Bitcoin RPC error: %s", result['error'])
                return 0.0
            return result.get('result', 0.0)
        except Exception as e:
            logger.error("Failed to get balance: %s", e)
            return 0.0
    
    def get_new_address(self) -> str:
        """Generate a new Bitcoin address for deposits"""
        try:
            result = self._rpc_call('getnewaddress', ["", "bech32"])
            if result.get('error') is not None:
                logger.error("Bitcoin RPC error: %s", result['error'])
                return self.config['fallback_address']
            return result.get('result', self.config['fallback_address'])
        except Exception as e:
            logger.error("Failed to get new address: %s", e)
            return self.config['fallback_address']
    
    def list_transactions(self, count: int = 10) -> list:
        """List recent transactions"""
        try:
            result = self._rpc_call('listtransactions', ["*", count, 0, True])
            if result.get('error') is not None:
                logger.error("Bitcoin RPC error: %s", result['error'])
                return []
            return result.get('result', [])
        except Exception as e:
            logger.error("Failed to list transactions: %s", e)
            return []
    
    def _rpc_call(self, method: str, params: list = None) -> Dict:
        """Make an RPC call to Bitcoin Core"""
        if params is None:
            params = []
            
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params
        }
        
        try:
            response = self.session.post(
                self.config['rpc_url'],
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error("RPC call failed: %s", e)
            return {"error": str(e)}

# Create a wallet instance
wallet = BitcoinWallet()

# API endpoints for wallet integration
def get_wallet_balance() -> Dict[str, any]:
    """Get wallet balance for API"""
    balance = wallet.get_balance()
    return {
        "balance": balance,
        "address": wallet.get_new_address(),
        "testnet": wallet.config['testnet']
    }

def get_wallet_info() -> Dict[str, any]:
    """Get comprehensive wallet information"""
    try:
        wallet = BitcoinWallet()
        # Test connection to Bitcoin Core
        blockchain_info = wallet._rpc_call('getblockchaininfo')
        is_connected = blockchain_info.get('error') is None and blockchain_info.get('result') is not None
        
        return {
            "balance": wallet.get_balance(),
            "address": wallet.get_new_address(),
            "transactions": wallet.list_transactions(10),
            "testnet": wallet.config['testnet'],
            "wallet_type": "Bitcoin Core (Real)" if is_connected else "Bitcoin Core (Disconnected)",
            "connected": is_connected,
            "blocks": blockchain_info.get('result', {}).get('blocks', 0) if is_connected else 0
        }
    except Exception as e:
        logger.error("Error getting wallet info: %s", e)
        return {
            "balance": 0.0,
            "address": "tb1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh",
            "transactions": [],
            "testnet": True,
            "wallet_type": "Bitcoin Core (Error)",
            "connected": False,
            "blocks": 0
        }

if __name__ == "__main__":
    # Test the wallet integration
    info = get_wallet_info()
    print(json.dumps(info, indent=2))
