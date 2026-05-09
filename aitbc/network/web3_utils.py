"""
Web3 utilities for AITBC
Provides Ethereum blockchain interaction utilities using web3.py
"""

from typing import Any, Optional
from decimal import Decimal


class Web3Client:
    """Web3 client wrapper for blockchain operations"""
    
    def __init__(self, rpc_url: str, timeout: int = 30):
        """Initialize Web3 client with RPC URL"""
        try:
            from web3 import Web3
            from web3.middleware import geth_poa_middleware
            
            self.w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={'timeout': timeout}))
            
            # Add POA middleware for chains like Polygon, BSC, etc.
            self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)
            
            if not self.w3.is_connected():
                raise ConnectionError(f"Failed to connect to RPC URL: {rpc_url}")
        except ImportError:
            raise ImportError("web3 is required for blockchain operations. Install with: pip install web3")
        except Exception as e:
            raise ConnectionError(f"Failed to initialize Web3 client: {e}")
    
    def get_eth_balance(self, address: str) -> str:
        """Get ETH balance in wei"""
        try:
            balance_wei = self.w3.eth.get_balance(address)
            return str(balance_wei)
        except Exception as e:
            raise ValueError(f"Failed to get ETH balance: {e}")
    
    def get_token_balance(self, address: str, token_address: str) -> dict[str, Any]:
        """Get ERC-20 token balance"""
        try:
            # ERC-20 balanceOf function signature: 0x70a08231
            balance_of_signature = '0x70a08231'
            # Pad address to 32 bytes
            padded_address = address[2:].lower().zfill(64)
            call_data = balance_of_signature + padded_address
            
            result = self.w3.eth.call({
                'to': token_address,
                'data': f'0x{call_data}'
            })
            
            balance = int(result.hex(), 16)
            
            # Get token decimals
            decimals_signature = '0x313ce567'
            decimals_result = self.w3.eth.call({
                'to': token_address,
                'data': decimals_signature
            })
            decimals = int(decimals_result.hex(), 16)
            
            # Get token symbol (optional, may fail for some tokens)
            try:
                symbol_signature = '0x95d89b41'
                symbol_result = self.w3.eth.call({
                    'to': token_address,
                    'data': symbol_signature
                })
                symbol_bytes = bytes.fromhex(symbol_result.hex()[2:])
                symbol = symbol_bytes.rstrip(b'\x00').decode('utf-8')
            except:
                symbol = "TOKEN"
            
            return {
                "balance": str(balance),
                "decimals": decimals,
                "symbol": symbol
            }
        except Exception as e:
            raise ValueError(f"Failed to get token balance: {e}")
    
    def get_gas_price(self) -> int:
        """Get current gas price in wei"""
        try:
            gas_price = self.w3.eth.gas_price
            return gas_price
        except Exception as e:
            raise ValueError(f"Failed to get gas price: {e}")
    
    def get_gas_price_gwei(self) -> float:
        """Get current gas price in Gwei"""
        try:
            gas_price_wei = self.get_gas_price()
            return float(gas_price_wei) / 10**9
        except Exception as e:
            raise ValueError(f"Failed to get gas price in Gwei: {e}")
    
    def get_nonce(self, address: str) -> int:
        """Get transaction nonce for address"""
        try:
            nonce = self.w3.eth.get_transaction_count(address)
            return nonce
        except Exception as e:
            raise ValueError(f"Failed to get nonce: {e}")
    
    def send_raw_transaction(self, signed_transaction: str) -> str:
        """Send raw transaction to blockchain"""
        try:
            tx_hash = self.w3.eth.send_raw_transaction(signed_transaction)
            return tx_hash.hex()
        except Exception as e:
            raise ValueError(f"Failed to send raw transaction: {e}")
    
    def get_transaction_receipt(self, tx_hash: str) -> Optional[dict[str, Any]]:
        """Get transaction receipt"""
        try:
            receipt = self.w3.eth.get_transaction_receipt(tx_hash)
            if receipt is None:
                return None
            
            return {
                "status": receipt['status'],
                "blockNumber": hex(receipt['blockNumber']),
                "blockHash": receipt['blockHash'].hex(),
                "gasUsed": hex(receipt['gasUsed']),
                "effectiveGasPrice": hex(receipt['effectiveGasPrice']),
                "logs": receipt['logs'],
            }
        except Exception as e:
            raise ValueError(f"Failed to get transaction receipt: {e}")
    
    def get_transaction_by_hash(self, tx_hash: str) -> dict[str, Any]:
        """Get transaction by hash"""
        try:
            tx = self.w3.eth.get_transaction(tx_hash)
            return {
                "from": tx['from'],
                "to": tx['to'],
                "value": hex(tx['value']),
                "data": tx['input'].hex() if hasattr(tx['input'], 'hex') else tx['input'],
                "nonce": tx['nonce'],
                "gas": tx['gas'],
                "gasPrice": hex(tx['gasPrice']),
                "blockNumber": hex(tx['blockNumber']) if tx['blockNumber'] else None,
            }
        except Exception as e:
            raise ValueError(f"Failed to get transaction by hash: {e}")
    
    def estimate_gas(self, transaction: dict[str, Any]) -> int:
        """Estimate gas for transaction"""
        try:
            gas_estimate = self.w3.eth.estimate_gas(transaction)
            return gas_estimate
        except Exception as e:
            raise ValueError(f"Failed to estimate gas: {e}")
    
    def get_block_number(self) -> int:
        """Get current block number"""
        try:
            return self.w3.eth.block_number
        except Exception as e:
            raise ValueError(f"Failed to get block number: {e}")
    
    def get_wallet_transactions(self, address: str, limit: int = 100) -> list[dict[str, Any]]:
        """Get wallet transactions (simplified implementation)"""
        try:
            # This is a simplified version - in production you'd want to use
            # event logs or a blockchain explorer API for this
            transactions = []
            current_block = self.get_block_number()
            
            # Look back at recent blocks for transactions from/to this address
            start_block = max(0, current_block - 1000)
            
            for block_num in range(current_block, start_block, -1):
                if len(transactions) >= limit:
                    break
                
                try:
                    block = self.w3.eth.get_block(block_num, full_transactions=True)
                    for tx in block['transactions']:
                        if tx['from'].lower() == address.lower() or \
                           (tx['to'] and tx['to'].lower() == address.lower()):
                            transactions.append({
                                "hash": tx['hash'].hex(),
                                "from": tx['from'],
                                "to": tx['to'].hex() if tx['to'] else None,
                                "value": hex(tx['value']),
                                "blockNumber": hex(tx['blockNumber']),
                                "timestamp": block['timestamp'],
                                "gasUsed": hex(tx['gas']),
                            })
                            if len(transactions) >= limit:
                                break
                except:
                    continue
            
            return transactions
        except Exception as e:
            raise ValueError(f"Failed to get wallet transactions: {e}")


def create_web3_client(rpc_url: str, timeout: int = 30) -> Web3Client:
    """Factory function to create Web3 client"""
    return Web3Client(rpc_url, timeout)
