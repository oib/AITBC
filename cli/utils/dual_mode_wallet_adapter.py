"""Dual-Mode Wallet Adapter for AITBC CLI

This module provides an abstraction layer that supports both file-based
and daemon-based wallet operations, allowing seamless switching between modes.
"""

import json
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, List, Union
from datetime import datetime

from .wallet_daemon_client import WalletDaemonClient, WalletInfo, WalletBalance, ChainInfo, WalletMigrationResult
from config import Config
from utils import error, success, output


class DualModeWalletAdapter:
    """Adapter supporting both file-based and daemon-based wallet operations"""
    
    def __init__(self, config: Config, use_daemon: bool = False, chain_id: Optional[str] = None):
        self.config = config
        self.use_daemon = use_daemon
        self.chain_id = chain_id
        self.wallet_dir = Path.home() / ".aitbc" / "wallets"
        self.wallet_dir.mkdir(parents=True, exist_ok=True)
        
        # Auto-detect chain_id if not provided
        if not self.chain_id:
            from aitbc_cli.utils.chain_id import get_chain_id
            default_rpc_url = config.blockchain_rpc_url if hasattr(config, 'blockchain_rpc_url') else 'http://localhost:8006'
            self.chain_id = get_chain_id(default_rpc_url)
        
        if use_daemon:
            self.daemon_client = WalletDaemonClient(config)
        else:
            self.daemon_client = None
    
    def is_daemon_available(self) -> bool:
        """Check if daemon is available"""
        if not self.daemon_client:
            return False
        return self.daemon_client.is_available()
    
    def get_daemon_status(self) -> Dict[str, Any]:
        """Get daemon status"""
        if not self.daemon_client:
            return {"status": "disabled", "message": "Daemon mode not enabled"}
        return self.daemon_client.get_status()
    
    def create_wallet(self, wallet_name: str, password: str, wallet_type: str = "hd", 
                     metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Create a wallet using the appropriate mode"""
        if self.use_daemon:
            return self._create_wallet_daemon(wallet_name, password, metadata)
        else:
            return self._create_wallet_file(wallet_name, password, wallet_type)
    
    def _create_wallet_daemon(self, wallet_name: str, password: str, 
                            metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Create wallet using daemon"""
        try:
            if not self.is_daemon_available():
                error("Wallet daemon is not available")
                raise Exception("Daemon unavailable")
            
            wallet_info = self.daemon_client.create_wallet(wallet_name, password, metadata)
            
            success(f"Created daemon wallet: {wallet_name}")
            return {
                "mode": "daemon",
                "wallet_name": wallet_name,
                "wallet_id": wallet_info.wallet_id,
                "public_key": wallet_info.public_key,
                "address": wallet_info.address,
                "created_at": wallet_info.created_at,
                "metadata": wallet_info.metadata
            }
        except Exception as e:
            error(f"Failed to create daemon wallet: {str(e)}")
            raise
    
    def _create_wallet_file(self, wallet_name: str, password: str, wallet_type: str) -> Dict[str, Any]:
        """Create wallet using file-based storage"""
        from .commands.wallet import _save_wallet
        
        wallet_path = self.wallet_dir / f"{wallet_name}.json"
        
        if wallet_path.exists():
            error(f"Wallet '{wallet_name}' already exists")
            raise Exception("Wallet exists")
        
        # Generate wallet data
        if wallet_type == "simple":
            # Simple wallet with deterministic key for testing
            private_key = f"simple_key_{wallet_name}_{datetime.now().isoformat()}"
            address = f"aitbc1{wallet_name}_simple"
        else:
            # HD wallet (placeholder for real implementation)
            private_key = f"hd_key_{wallet_name}_{datetime.now().isoformat()}"
            address = f"aitbc1{wallet_name}_hd"
        
        wallet_data = {
            "name": wallet_name,
            "address": address,
            "balance": 0.0,
            "encrypted": bool(password),
            "private_key": private_key,
            "transactions": [],
            "created_at": datetime.now().isoformat(),
            "wallet_type": wallet_type
        }
        
        # Save wallet
        save_password = password if password else None
        _save_wallet(wallet_path, wallet_data, save_password)
        
        success(f"Created file wallet: {wallet_name}")
        return {
            "mode": "file",
            "wallet_name": wallet_name,
            "address": address,
            "balance": 0.0,
            "wallet_type": wallet_type,
            "created_at": wallet_data["created_at"]
        }
    
    def list_wallets(self) -> List[Dict[str, Any]]:
        """List wallets using the appropriate mode"""
        if self.use_daemon:
            return self._list_wallets_daemon()
        else:
            return self._list_wallets_file()
    
    def _list_wallets_daemon(self) -> List[Dict[str, Any]]:
        """List wallets using daemon"""
        try:
            if not self.is_daemon_available():
                error("Wallet daemon is not available")
                return []
            
            wallets = self.daemon_client.list_wallets()
            return [
                {
                    "mode": "daemon",
                    "wallet_name": w.wallet_id,
                    "wallet_id": w.wallet_id,
                    "public_key": w.public_key,
                    "address": w.address,
                    "created_at": w.created_at,
                    "metadata": w.metadata
                }
                for w in wallets
            ]
        except Exception as e:
            error(f"Failed to list daemon wallets: {str(e)}")
            return []
    
    def _list_wallets_file(self) -> List[Dict[str, Any]]:
        """List wallets using file-based storage"""
        wallets = []
        
        for wallet_file in self.wallet_dir.glob("*.json"):
            try:
                with open(wallet_file, 'r') as f:
                    wallet_data = json.load(f)
                
                wallets.append({
                    "mode": "file",
                    "wallet_name": wallet_data.get("name") or wallet_data.get("wallet_id") or wallet_file.stem,
                    "address": wallet_data.get("address"),
                    "balance": wallet_data.get("balance", 0.0),
                    "wallet_type": wallet_data.get("wallet_type", "hd"),
                    "created_at": wallet_data.get("created_at"),
                    "encrypted": wallet_data.get("encrypted", False)
                })
            except Exception as e:
                error(f"Error reading wallet file {wallet_file}: {str(e)}")
        
        return wallets
    
    def get_wallet_info(self, wallet_name: str) -> Optional[Dict[str, Any]]:
        """Get wallet information using the appropriate mode"""
        if self.use_daemon:
            return self._get_wallet_info_daemon(wallet_name)
        else:
            return self._get_wallet_info_file(wallet_name)
    
    def _get_wallet_info_daemon(self, wallet_name: str) -> Optional[Dict[str, Any]]:
        """Get wallet info using daemon"""
        try:
            if not self.is_daemon_available():
                return None
            
            wallet_info = self.daemon_client.get_wallet_info(wallet_name)
            if wallet_info:
                return {
                    "mode": "daemon",
                    "wallet_name": wallet_name,
                    "wallet_id": wallet_info.wallet_id,
                    "public_key": wallet_info.public_key,
                    "address": wallet_info.address,
                    "created_at": wallet_info.created_at,
                    "metadata": wallet_info.metadata
                }
            return None
        except Exception as e:
            error(f"Failed to get daemon wallet info: {str(e)}")
            return None
    
    def _get_wallet_info_file(self, wallet_name: str) -> Optional[Dict[str, Any]]:
        """Get wallet info using file-based storage"""
        from .commands.wallet import _load_wallet
        
        wallet_path = self.wallet_dir / f"{wallet_name}.json"
        
        if not wallet_path.exists():
            return None
        
        try:
            with open(wallet_path, 'r') as f:
                wallet_data = json.load(f)
            
            return {
                "mode": "file",
                "wallet_name": wallet_data.get("name") or wallet_data.get("wallet_id") or wallet_name,
                "address": wallet_data.get("address"),
                "balance": wallet_data.get("balance", 0.0),
                "wallet_type": wallet_data.get("wallet_type", "hd"),
                "created_at": wallet_data.get("created_at"),
                "encrypted": wallet_data.get("encrypted", False),
                "transactions": wallet_data.get("transactions", [])
            }
        except Exception as e:
            error(f"Failed to get file wallet info: {str(e)}")
            return None
    
    def get_wallet_balance(self, wallet_name: str) -> Optional[float]:
        """Get wallet balance using the appropriate mode"""
        if self.use_daemon:
            return self._get_wallet_balance_daemon(wallet_name)
        else:
            return self._get_wallet_balance_file(wallet_name)
    
    def _get_wallet_balance_daemon(self, wallet_name: str) -> Optional[float]:
        """Get wallet balance using daemon"""
        try:
            if not self.is_daemon_available():
                return None
            
            balance_info = self.daemon_client.get_wallet_balance(wallet_name)
            if balance_info:
                return balance_info.balance
            return None
        except Exception as e:
            error(f"Failed to get daemon wallet balance: {str(e)}")
            return None
    
    def _get_wallet_balance_file(self, wallet_name: str) -> Optional[float]:
        """Get wallet balance using file-based storage"""
        wallet_info = self._get_wallet_info_file(wallet_name)
        if wallet_info:
            return wallet_info.get("balance", 0.0)
        return None
    
    def send_transaction(self, wallet_name: str, password: str, to_address: str, 
                        amount: float, description: Optional[str] = None) -> Dict[str, Any]:
        """Send transaction using the appropriate mode"""
        if self.use_daemon:
            return self._send_transaction_daemon(wallet_name, password, to_address, amount, description)
        else:
            return self._send_transaction_file(wallet_name, password, to_address, amount, description)
    
    def _send_transaction_daemon(self, wallet_name: str, password: str, to_address: str, 
                              amount: float, description: Optional[str]) -> Dict[str, Any]:
        """Send transaction using daemon"""
        try:
            if not self.is_daemon_available():
                error("Wallet daemon is not available")
                raise Exception("Daemon unavailable")
            
            result = self.daemon_client.send_transaction(wallet_name, password, to_address, amount, description)
            
            success(f"Sent {amount} AITBC to {to_address} via daemon")
            return {
                "mode": "daemon",
                "wallet_name": wallet_name,
                "to_address": to_address,
                "amount": amount,
                "description": description,
                "tx_hash": result.get("tx_hash"),
                "timestamp": result.get("timestamp")
            }
        except Exception as e:
            error(f"Failed to send daemon transaction: {str(e)}")
            raise
    
    def _send_transaction_file(self, wallet_name: str, password: str, to_address: str, 
                             amount: float, description: Optional[str]) -> Dict[str, Any]:
        """Send transaction using file-based storage and blockchain RPC"""
        from .commands.wallet import _load_wallet, _save_wallet
        import httpx
        from .utils import error, success
        from datetime import datetime
        
        wallet_path = self.wallet_dir / f"{wallet_name}.json"
        
        if not wallet_path.exists():
            error(f"Wallet '{wallet_name}' not found")
            raise Exception("Wallet not found")
        
        wallet_data = _load_wallet(wallet_path, wallet_name)
        # Fetch current balance and nonce from blockchain
        from_address = wallet_data.get("address")
        if not from_address:
            error("Wallet does not have an address configured")
            raise Exception("Invalid wallet")
            
        rpc_url = self.config.blockchain_rpc_url
        try:
            resp = httpx.get(f"{rpc_url}/rpc/account/{from_address}?chain_id={self.chain_id}", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                chain_balance = data.get("balance", 0)
                nonce = data.get("nonce", 0)
            else:
                error(f"Failed to get balance from chain: {resp.text}")
                raise Exception("Chain error")
        except Exception as e:
            error(f"Failed to connect to blockchain RPC: {e}")
            raise

        if chain_balance < amount:
            error(f"Insufficient blockchain balance. Available: {chain_balance}, Required: {amount}")
            raise Exception("Insufficient balance")
            
        # Construct and send transaction
        tx_payload = {
            "type": "TRANSFER",
            "sender": from_address,
            "nonce": nonce,
            "fee": 0,
            "payload": {"to": to_address, "value": amount},
            "sig": "mock_signature" # Replace with real signature when implemented
        }
        
        try:
            resp = httpx.post(f"{rpc_url}/rpc/sendTx", json=tx_payload, timeout=5)
            if resp.status_code not in (200, 201):
                error(f"Failed to submit transaction to chain: {resp.text}")
                raise Exception("Chain submission failed")
            tx_hash = resp.json().get("tx_hash")
        except Exception as e:
            error(f"Failed to send transaction to RPC: {e}")
            raise

        # Add transaction to local history
        transaction = {
            "type": "send",
            "amount": -amount,
            "to_address": to_address,
            "description": description or "",
            "timestamp": datetime.now().isoformat(),
            "tx_hash": tx_hash,
            "status": "pending"
        }
        
        if "transactions" not in wallet_data:
            wallet_data["transactions"] = []
            
        wallet_data["transactions"].append(transaction)
        wallet_data["balance"] = chain_balance - amount
        
        # Save wallet - CRITICAL SECURITY FIX: Always use password if wallet is encrypted
        save_password = password if wallet_data.get("encrypted") else None
        if wallet_data.get("encrypted") and not save_password:
            error("❌ CRITICAL: Cannot save encrypted wallet without password")
            raise Exception("Password required for encrypted wallet")
        _save_wallet(wallet_path, wallet_data, save_password)
        
        success(f"Submitted transaction {tx_hash} to send {amount} AITBC to {to_address}")
        return {
            "mode": "file",
            "wallet_name": wallet_name,
            "to_address": to_address,
            "amount": amount,
            "description": description,
            "tx_hash": tx_hash,
            "timestamp": transaction["timestamp"]
        }
    
    def delete_wallet(self, wallet_name: str, password: str) -> bool:
        """Delete wallet using the appropriate mode"""
        if self.use_daemon:
            return self._delete_wallet_daemon(wallet_name, password)
        else:
            return self._delete_wallet_file(wallet_name, password)
    
    def _delete_wallet_daemon(self, wallet_name: str, password: str) -> bool:
        """Delete wallet using daemon"""
        try:
            if not self.is_daemon_available():
                return False
            
            return self.daemon_client.delete_wallet(wallet_name, password)
        except Exception as e:
            error(f"Failed to delete daemon wallet: {str(e)}")
            return False
    
    def _delete_wallet_file(self, wallet_name: str, password: str) -> bool:
        """Delete wallet using file-based storage"""
        wallet_path = self.wallet_dir / f"{wallet_name}.json"
        
        if not wallet_path.exists():
            error(f"Wallet '{wallet_name}' not found")
            return False
        
        try:
            wallet_path.unlink()
            success(f"Deleted wallet: {wallet_name}")
            return True
        except Exception as e:
            error(f"Failed to delete wallet: {str(e)}")
            return False

    # Multi-Chain Methods
    
    def list_chains(self) -> List[Dict[str, Any]]:
        """List all blockchain chains"""
        if not self.use_daemon or not self.is_daemon_available():
            error("Chain listing requires daemon mode")
            return []
        
        try:
            chains = self.daemon_client.list_chains()
            return [
                {
                    "chain_id": chain.chain_id,
                    "name": chain.name,
                    "status": chain.status,
                    "coordinator_url": chain.coordinator_url,
                    "created_at": chain.created_at,
                    "updated_at": chain.updated_at,
                    "wallet_count": chain.wallet_count,
                    "recent_activity": chain.recent_activity
                }
                for chain in chains
            ]
        except Exception as e:
            error(f"Failed to list chains: {str(e)}")
            return []
    
    def create_chain(self, chain_id: str, name: str, coordinator_url: str, 
                    coordinator_api_key: str, metadata: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Create a new blockchain chain"""
        if not self.use_daemon or not self.is_daemon_available():
            error("Chain creation requires daemon mode")
            return None
        
        try:
            chain = self.daemon_client.create_chain(chain_id, name, coordinator_url, coordinator_api_key, metadata)
            return {
                "chain_id": chain.chain_id,
                "name": chain.name,
                "status": chain.status,
                "coordinator_url": chain.coordinator_url,
                "created_at": chain.created_at,
                "updated_at": chain.updated_at,
                "wallet_count": chain.wallet_count,
                "recent_activity": chain.recent_activity
            }
        except Exception as e:
            error(f"Failed to create chain: {str(e)}")
            return None
    
    def create_wallet_in_chain(self, chain_id: str, wallet_name: str, password: str,
                              wallet_type: str = "hd", metadata: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Create a wallet in a specific chain"""
        if not self.use_daemon or not self.is_daemon_available():
            error("Chain-specific wallet creation requires daemon mode")
            return None
        
        try:
            wallet = self.daemon_client.create_wallet_in_chain(chain_id, wallet_name, password, metadata)
            return {
                "mode": "daemon",
                "chain_id": chain_id,
                "wallet_name": wallet.wallet_id,
                "public_key": wallet.public_key,
                "address": wallet.address,
                "created_at": wallet.created_at,
                "wallet_type": wallet_type,
                "metadata": wallet.metadata or {}
            }
        except Exception as e:
            error(f"Failed to create wallet in chain {chain_id}: {str(e)}")
            return None
    
    def list_wallets_in_chain(self, chain_id: str) -> List[Dict[str, Any]]:
        """List wallets in a specific chain"""
        if not self.use_daemon or not self.is_daemon_available():
            error("Chain-specific wallet listing requires daemon mode")
            return []
        
        try:
            wallets = self.daemon_client.list_wallets_in_chain(chain_id)
            return [
                {
                    "mode": "daemon",
                    "chain_id": chain_id,
                    "wallet_name": wallet.wallet_id,
                    "public_key": wallet.public_key,
                    "address": wallet.address,
                    "created_at": wallet.created_at,
                    "metadata": wallet.metadata or {}
                }
                for wallet in wallets
            ]
        except Exception as e:
            error(f"Failed to list wallets in chain {chain_id}: {str(e)}")
            return []
    
    def get_wallet_info_in_chain(self, chain_id: str, wallet_name: str) -> Optional[Dict[str, Any]]:
        """Get wallet information from a specific chain"""
        if not self.use_daemon or not self.is_daemon_available():
            error("Chain-specific wallet info requires daemon mode")
            return None
        
        try:
            wallet = self.daemon_client.get_wallet_info_in_chain(chain_id, wallet_name)
            if wallet:
                return {
                    "mode": "daemon",
                    "chain_id": chain_id,
                    "wallet_name": wallet.wallet_id,
                    "public_key": wallet.public_key,
                    "address": wallet.address,
                    "created_at": wallet.created_at,
                    "metadata": wallet.metadata or {}
                }
            return None
        except Exception as e:
            error(f"Failed to get wallet info from chain {chain_id}: {str(e)}")
            return None
    
    def get_wallet_balance_in_chain(self, chain_id: str, wallet_name: str) -> Optional[float]:
        """Get wallet balance in a specific chain"""
        if not self.use_daemon or not self.is_daemon_available():
            error("Chain-specific balance check requires daemon mode")
            return None
        
        try:
            balance = self.daemon_client.get_wallet_balance_in_chain(chain_id, wallet_name)
            return balance.balance if balance else None
        except Exception as e:
            error(f"Failed to get wallet balance in chain {chain_id}: {str(e)}")
            return None
    
    def unlock_wallet_in_chain(self, chain_id: str, wallet_name: str, password: str) -> bool:
        """Unlock a wallet in a specific chain"""
        if not self.use_daemon or not self.is_daemon_available():
            error("Chain-specific wallet unlock requires daemon mode")
            return False
        
        try:
            return self.daemon_client.unlock_wallet_in_chain(chain_id, wallet_name, password)
        except Exception as e:
            error(f"Failed to unlock wallet in chain {chain_id}: {str(e)}")
            return False
    
    def sign_message_in_chain(self, chain_id: str, wallet_name: str, password: str, message: bytes) -> Optional[str]:
        """Sign a message with a wallet in a specific chain"""
        if not self.use_daemon or not self.is_daemon_available():
            error("Chain-specific message signing requires daemon mode")
            return None
        
        try:
            return self.daemon_client.sign_message_in_chain(chain_id, wallet_name, password, message)
        except Exception as e:
            error(f"Failed to sign message in chain {chain_id}: {str(e)}")
            return None
    
    def migrate_wallet(self, source_chain_id: str, target_chain_id: str, wallet_name: str,
                      password: str, new_password: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Migrate a wallet from one chain to another"""
        if not self.use_daemon or not self.is_daemon_available():
            error("Wallet migration requires daemon mode")
            return None
        
        try:
            result = self.daemon_client.migrate_wallet(source_chain_id, target_chain_id, wallet_name, password, new_password)
            if result:
                return {
                    "success": result.success,
                    "source_wallet": {
                        "chain_id": result.source_wallet.chain_id,
                        "wallet_name": result.source_wallet.wallet_id,
                        "public_key": result.source_wallet.public_key,
                        "address": result.source_wallet.address
                    },
                    "target_wallet": {
                        "chain_id": result.target_wallet.chain_id,
                        "wallet_name": result.target_wallet.wallet_id,
                        "public_key": result.target_wallet.public_key,
                        "address": result.target_wallet.address
                    },
                    "migration_timestamp": result.migration_timestamp
                }
            return None
        except Exception as e:
            error(f"Failed to migrate wallet: {str(e)}")
            return None
    
    def get_chain_status(self) -> Dict[str, Any]:
        """Get overall chain status and statistics"""
        if not self.use_daemon or not self.is_daemon_available():
            return {"status": "disabled", "message": "Chain status requires daemon mode"}
        
        try:
            return self.daemon_client.get_chain_status()
        except Exception as e:
            error(f"Failed to get chain status: {str(e)}")
            return {"error": str(e)}
