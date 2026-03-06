#!/usr/bin/env python3
"""
Bitcoin Wallet Integration for AITBC Trade Exchange
"""

import os
import json
import hashlib
 import hmac
import time
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
import requests

@dataclass
class BitcoinWallet:
    """Bitcoin wallet configuration"""
    address: str
    private_key: Optional[str] = None
    testnet: bool = True
    
class BitcoinProcessor:
    """Bitcoin payment processor"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.testnet = config.get('testnet', True)
        self.api_key = config.get('api_key')
        self.webhook_secret = config.get('webhook_secret')
        
    def generate_payment_address(self, user_id: str, amount_btc: float) -> str:
        """Generate a unique payment address for each transaction"""
        # In production, use HD wallet to generate unique addresses
        # For demo, we'll use a fixed address with payment tracking
        
        # Create payment hash
        payment_data = f"{user_id}:{amount_btc}:{int(time.time())}"
        hash_bytes = hashlib.sha256(payment_data.encode()).hexdigest()

        
        # For demo, return the main wallet address
        # In production, generate unique address from HD wallet
        return self.config['main_address']
    
    def check_payment(self, address: str, amount_btc: float) -> Tuple[bool, float]:
        """Check if payment has been received"""
        # In production, integrate with blockchain API
        # For demo, simulate payment check
        
        # Mock API call to check blockchain
        if self.testnet:
            # Testnet blockchain API
            api_url = f"https://blockstream.info/testnet/api/address/{address}"
        else:
            # Mainnet blockchain API
            api_url = f"https://blockstream.info/api/address/{address}"
        
        try:
            response = requests.get(api_url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                # Check recent transactions
                # In production, implement proper transaction verification
                return False, 0.0
        except Exception as e:
            print(f"Error checking payment: {e}")
        
        return False, 0.0
    
    def verify_webhook(self, payload: str, signature: str) -> bool:
        """Verify webhook signature from payment processor"""
        if not self.webhook_secret:
            return True  # Skip verification if no secret
        
        expected_signature = hmac.new(
            self.webhook_secret.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(expected_signature, signature)

class WalletManager:
    """Manages Bitcoin wallet operations"""
    
    def __init__(self):
        self.config = self.load_config()
        self.processor = BitcoinProcessor(self.config)
        
    def load_config(self) -> Dict:
        """Load wallet configuration"""
        return {
            'testnet': os.getenv('BITCOIN_TESTNET', 'true').lower() == 'true',
            'main_address': os.getenv('BITCOIN_ADDRESS', 'tb1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh'),
            'private_key': os.getenv('BITCOIN_PRIVATE_KEY'),
            'api_key': os.getenv('BLOCKCHAIN_API_KEY'),
            'webhook_secret': os.getenv('WEBHOOK_SECRET'),
            'min_confirmations': int(os.getenv('MIN_CONFIRMATIONS', '1')),
            'exchange_rate': float(os.getenv('BTC_TO_AITBC_RATE', '100000'))  # 1 BTC = 100,000 AITBC
        }
    
    def create_payment_request(self, user_id: str, aitbc_amount: float) -> Dict:
        """Create a new payment request"""
        btc_amount = aitbc_amount / self.config['exchange_rate']
        
        payment_request = {
            'user_id': user_id,
            'aitbc_amount': aitbc_amount,
            'btc_amount': btc_amount,
            'payment_address': self.processor.generate_payment_address(user_id, btc_amount),
            'created_at': int(time.time()),
            'status': 'pending',
            'expires_at': int(time.time()) + 3600  # 1 hour expiry
        }
        
        # Save payment request
        self.save_payment_request(payment_request)
        
        return payment_request
    
    def save_payment_request(self, request: Dict):
        """Save payment request to storage"""
        payments_file = 'payments.json'
        payments = []
        
        if os.path.exists(payments_file):
            with open(payments_file, 'r') as f:
                payments = json.load(f)
        
        payments.append(request)
        
        with open(payments_file, 'w') as f:
            json.dump(payments, f, indent=2)
    
    def get_payment_status(self, payment_id: str) -> Optional[Dict]:
        """Get payment status"""
        payments_file = 'payments.json'
        
        if not os.path.exists(payments_file):
            return None
        
        with open(payments_file, 'r') as f:
            payments = json.load(f)
        
        for payment in payments:
            if payment.get('payment_id') == payment_id:
                return payment
        
        return None
    
    def update_payment_status(self, payment_id: str, status: str, tx_hash: str = None):
        """Update payment status"""
        payments_file = 'payments.json'
        
        if not os.path.exists(payments_file):
            return False
        
        with open(payments_file, 'r') as f:
            payments = json.load(f)
        
        for payment in payments:
            if payment.get('payment_id') == payment_id:
                payment['status'] = status
                payment['updated_at'] = int(time.time())
                if tx_hash:
                    payment['tx_hash'] = tx_hash
                
                with open(payments_file, 'w') as f:
                    json.dump(payments, f, indent=2)
                return True
        
        return False

# Global wallet manager
wallet_manager = WalletManager()
