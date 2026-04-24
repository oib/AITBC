"""Wallet Daemon Client for AITBC CLI

This module provides a client for communicating with the AITBC wallet daemon,
supporting both REST and JSON-RPC APIs for wallet operations.
"""

import json
import base64
from typing import Dict, Any, Optional, List
from pathlib import Path
from dataclasses import dataclass

from aitbc.http_client import AITBCHTTPClient
from aitbc.exceptions import NetworkError

from utils import error, success
from config import Config


@dataclass
class ChainInfo:
    """Chain information from daemon"""
    chain_id: str
    name: str
    status: str
    coordinator_url: str
    created_at: str
    updated_at: str
    wallet_count: int
    recent_activity: int


@dataclass
class WalletInfo:
    """Wallet information from daemon"""
    wallet_id: str
    chain_id: str
    public_key: str
    address: Optional[str] = None
    created_at: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class WalletBalance:
    """Wallet balance information"""
    wallet_id: str
    chain_id: str
    balance: float
    address: Optional[str] = None
    last_updated: Optional[str] = None


@dataclass
class WalletMigrationResult:
    """Result of wallet migration between chains"""
    success: bool
    source_wallet: WalletInfo
    target_wallet: WalletInfo
    migration_timestamp: str


class WalletDaemonClient:
    """Client for interacting with AITBC wallet daemon"""
    
    def __init__(self, config: Config):
        self.config = config
        self.base_url = config.wallet_url.rstrip('/')
        self.timeout = getattr(config, 'timeout', 30)
    
    def _get_http_client(self) -> AITBCHTTPClient:
        """Create HTTP client with appropriate settings"""
        return AITBCHTTPClient(
            base_url=self.base_url,
            timeout=self.timeout,
            headers={"Content-Type": "application/json"}
        )
    
    def is_available(self) -> bool:
        """Check if wallet daemon is available and responsive"""
        try:
            client = self._get_http_client()
            client.get("/health")
            return True
        except NetworkError:
            return False
        except Exception:
            return False
    
    def get_status(self) -> Dict[str, Any]:
        """Get wallet daemon status information"""
        try:
            client = self._get_http_client()
            return client.get("/health")
        except NetworkError as e:
            return {"status": "unavailable", "error": str(e)}
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    def create_wallet(self, wallet_id: str, password: str, metadata: Optional[Dict[str, Any]] = None) -> WalletInfo:
        """Create a new wallet in the daemon"""
        try:
            client = self._get_http_client()
            payload = {
                "wallet_id": wallet_id,
                "password": password,
                "metadata": metadata or {}
            }
            
            data = client.post("/v1/wallets", json=payload)
            return WalletInfo(
                wallet_id=data["wallet_id"],
                chain_id=data.get("chain_id", "default"),
                public_key=data["public_key"],
                address=data.get("address"),
                created_at=data.get("created_at"),
                metadata=data.get("metadata")
            )
        except NetworkError as e:
            error(f"Error creating wallet: {e}")
            raise
        except Exception as e:
            error(f"Error creating wallet: {str(e)}")
            raise
    
    def list_wallets(self) -> List[WalletInfo]:
        """List all wallets in the daemon"""
        try:
            client = self._get_http_client()
            data = client.get("/v1/wallets")
            wallets = []
            # Handle both "wallets" and "items" keys for compatibility
            wallet_list = data.get("wallets", data.get("items", []))
            for wallet_data in wallet_list:
                wallets.append(WalletInfo(
                    wallet_id=wallet_data.get("wallet_id", wallet_data.get("wallet_name", "")),
                    chain_id=wallet_data.get("chain_id", "default"),
                    public_key=wallet_data.get("public_key", ""),
                    address=wallet_data.get("address", ""),
                    created_at=wallet_data.get("created_at", ""),
                    metadata=wallet_data.get("metadata", {})
                ))
            return wallets
        except NetworkError as e:
            error(f"Failed to list daemon wallets: {str(e)}")
            raise
        except Exception as e:
            error(f"Error listing wallets: {str(e)}")
            raise
    
    def get_wallet_info(self, wallet_id: str) -> Optional[WalletInfo]:
        """Get information about a specific wallet"""
        try:
            client = self._get_http_client()
            data = client.get(f"/v1/wallets/{wallet_id}")
            return WalletInfo(
                wallet_id=data["wallet_id"],
                chain_id=data.get("chain_id", "default"),
                public_key=data["public_key"],
                address=data.get("address"),
                created_at=data.get("created_at"),
                metadata=data.get("metadata")
            )
        except NetworkError as e:
            error(f"Failed to get wallet info: {e}")
            return None
        except Exception as e:
            error(f"Error getting wallet info: {str(e)}")
            return None
    
    def get_wallet_balance(self, wallet_id: str) -> Optional[WalletBalance]:
        """Get wallet balance from daemon"""
        try:
            client = self._get_http_client()
            data = client.get(f"/v1/wallets/{wallet_id}/balance")
            return WalletBalance(
                wallet_id=wallet_id,
                chain_id=data.get("chain_id", "default"),
                balance=data["balance"],
                address=data.get("address"),
                last_updated=data.get("last_updated")
            )
        except NetworkError as e:
            error(f"Failed to get wallet balance: {e}")
            return None
        except Exception as e:
            error(f"Error getting wallet balance: {str(e)}")
            return None
    
    def sign_message(self, wallet_id: str, password: str, message: bytes) -> str:
        """Sign a message with wallet private key"""
        try:
            with self._get_http_client() as client:
                # Encode message as base64 for transmission
                message_b64 = base64.b64encode(message).decode()
                
                payload = {
                    "password": password,
                    "message": message_b64
                }
                
                response = client.post(f"/v1/wallets/{wallet_id}/sign", json=payload)
                if response.status_code == 200:
                    data = response.json()
                    return data["signature_base64"]
                else:
                    error(f"Failed to sign message: {response.text}")
                    raise Exception(f"HTTP {response.status_code}: {response.text}")
        except Exception as e:
            error(f"Error signing message: {str(e)}")
            raise
    
    def send_transaction(self, wallet_id: str, password: str, to_address: str, amount: float, 
                        description: Optional[str] = None) -> Dict[str, Any]:
        """Send a transaction via the daemon"""
        try:
            with self._get_http_client() as client:
                payload = {
                    "password": password,
                    "to_address": to_address,
                    "amount": amount,
                    "description": description or ""
                }
                
                response = client.post(f"/v1/wallets/{wallet_id}/send", json=payload)
                if response.status_code == 201:
                    return response.json()
                else:
                    error(f"Failed to send transaction: {response.text}")
                    raise Exception(f"HTTP {response.status_code}: {response.text}")
        except Exception as e:
            error(f"Error sending transaction: {str(e)}")
            raise
    
    def unlock_wallet(self, wallet_id: str, password: str) -> bool:
        """Unlock a wallet for operations"""
        try:
            with self._get_http_client() as client:
                payload = {"password": password}
                response = client.post(f"/v1/wallets/{wallet_id}/unlock", json=payload)
                return response.status_code == 200
        except Exception:
            return False
    
    def lock_wallet(self, wallet_id: str) -> bool:
        """Lock a wallet"""
        try:
            with self._get_http_client() as client:
                response = client.post(f"/v1/wallets/{wallet_id}/lock")
                return response.status_code == 200
        except Exception:
            return False
    
    def delete_wallet(self, wallet_id: str, password: str) -> bool:
        """Delete a wallet from daemon"""
        try:
            with self._get_http_client() as client:
                payload = {"password": password}
                response = client.delete(f"/v1/wallets/{wallet_id}", json=payload)
                return response.status_code == 200
        except Exception:
            return False
    
    def jsonrpc_call(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make a JSON-RPC call to the daemon"""
        try:
            with self._get_http_client() as client:
                payload = {
                    "jsonrpc": "2.0",
                    "method": method,
                    "params": params or {},
                    "id": 1
                }
                
                response = client.post("/rpc", json=payload)
                if response.status_code == 200:
                    return response.json()
                else:
                    error(f"JSON-RPC call failed: {response.text}")
                    raise Exception(f"HTTP {response.status_code}: {response.text}")
        except Exception as e:
            error(f"Error making JSON-RPC call: {str(e)}")
            raise

    # Multi-Chain Methods
    
    def list_chains(self) -> List[ChainInfo]:
        """List all blockchain chains"""
        try:
            with self._get_http_client() as client:
                response = client.get("/v1/chains")
                if response.status_code == 200:
                    data = response.json()
                    chains = []
                    for chain_data in data.get("chains", []):
                        chains.append(ChainInfo(
                            chain_id=chain_data["chain_id"],
                            name=chain_data["name"],
                            status=chain_data["status"],
                            coordinator_url=chain_data["coordinator_url"],
                            created_at=chain_data["created_at"],
                            updated_at=chain_data["updated_at"],
                            wallet_count=chain_data["wallet_count"],
                            recent_activity=chain_data["recent_activity"]
                        ))
                    return chains
                else:
                    error(f"Failed to list chains: {response.text}")
                    raise Exception(f"HTTP {response.status_code}: {response.text}")
        except Exception as e:
            error(f"Error listing chains: {str(e)}")
            raise
    
    def create_chain(self, chain_id: str, name: str, coordinator_url: str, 
                    coordinator_api_key: str, metadata: Optional[Dict[str, Any]] = None) -> ChainInfo:
        """Create a new blockchain chain"""
        try:
            with self._get_http_client() as client:
                payload = {
                    "chain_id": chain_id,
                    "name": name,
                    "coordinator_url": coordinator_url,
                    "coordinator_api_key": coordinator_api_key,
                    "metadata": metadata or {}
                }
                
                response = client.post("/v1/chains", json=payload)
                if response.status_code == 201:
                    data = response.json()
                    chain_data = data["chain"]
                    return ChainInfo(
                        chain_id=chain_data["chain_id"],
                        name=chain_data["name"],
                        status=chain_data["status"],
                        coordinator_url=chain_data["coordinator_url"],
                        created_at=chain_data["created_at"],
                        updated_at=chain_data["updated_at"],
                        wallet_count=chain_data["wallet_count"],
                        recent_activity=chain_data["recent_activity"]
                    )
                else:
                    error(f"Failed to create chain: {response.text}")
                    raise Exception(f"HTTP {response.status_code}: {response.text}")
        except Exception as e:
            error(f"Error creating chain: {str(e)}")
            raise
    
    def create_wallet(self, wallet_id: str, password: str, metadata: Optional[Dict[str, Any]] = None) -> WalletInfo:
        """Create a new wallet in the daemon"""
        try:
            client = self._get_http_client()
            payload = {
                "wallet_id": wallet_id,
                "password": password,
                "metadata": metadata or {}
            }
            
            data = client.post("/v1/wallets", json=payload)
            return WalletInfo(
                wallet_id=data["wallet_id"],
                public_key=data["public_key"],
                address=data.get("address"),
                created_at=data.get("created_at"),
                metadata=data.get("metadata")
            )
        except NetworkError as e:
            error(f"Failed to create wallet: {e}")
            raise
        except Exception as e:
            error(f"Error creating wallet: {str(e)}")
            raise
    
    def create_wallet_in_chain(self, chain_id: str, wallet_id: str, password: str,
                              metadata: Optional[Dict[str, Any]] = None) -> WalletInfo:
        """Create a wallet in a specific chain"""
        try:
            with self._get_http_client() as client:
                payload = {
                    "chain_id": chain_id,
                    "wallet_id": wallet_id,
                    "password": password,
                    "metadata": metadata or {}
                }
                
                response = client.post(f"/v1/chains/{chain_id}/wallets", json=payload)
                if response.status_code == 201:
                    data = response.json()
                    wallet_data = data["wallet"]
                    return WalletInfo(
                        wallet_id=wallet_data["wallet_id"],
                        chain_id=wallet_data["chain_id"],
                        public_key=wallet_data["public_key"],
                        address=wallet_data.get("address"),
                        created_at=wallet_data.get("created_at"),
                        metadata=wallet_data.get("metadata")
                    )
                else:
                    error(f"Failed to create wallet in chain {chain_id}: {response.text}")
                    raise Exception(f"HTTP {response.status_code}: {response.text}")
        except Exception as e:
            error(f"Error creating wallet in chain {chain_id}: {str(e)}")
            raise
    
    def list_wallets_in_chain(self, chain_id: str) -> List[WalletInfo]:
        """List wallets in a specific chain"""
        try:
            with self._get_http_client() as client:
                response = client.get(f"/v1/chains/{chain_id}/wallets")
                if response.status_code == 200:
                    data = response.json()
                    wallets = []
                    for wallet_data in data.get("items", []):
                        wallets.append(WalletInfo(
                            wallet_id=wallet_data["wallet_id"],
                            chain_id=wallet_data["chain_id"],
                            public_key=wallet_data["public_key"],
                            address=wallet_data.get("address"),
                            created_at=wallet_data.get("created_at"),
                            metadata=wallet_data.get("metadata")
                        ))
                    return wallets
                else:
                    error(f"Failed to list wallets in chain {chain_id}: {response.text}")
                    raise Exception(f"HTTP {response.status_code}: {response.text}")
        except Exception as e:
            error(f"Error listing wallets in chain {chain_id}: {str(e)}")
            raise
    
    def get_wallet_info_in_chain(self, chain_id: str, wallet_id: str) -> Optional[WalletInfo]:
        """Get wallet information from a specific chain"""
        try:
            wallets = self.list_wallets_in_chain(chain_id)
            for wallet in wallets:
                if wallet.wallet_id == wallet_id:
                    return wallet
            return None
        except Exception as e:
            error(f"Error getting wallet info from chain {chain_id}: {str(e)}")
            return None
    
    def unlock_wallet_in_chain(self, chain_id: str, wallet_id: str, password: str) -> bool:
        """Unlock a wallet in a specific chain"""
        try:
            with self._get_http_client() as client:
                payload = {"password": password}
                response = client.post(f"/v1/chains/{chain_id}/wallets/{wallet_id}/unlock", json=payload)
                return response.status_code == 200
        except Exception:
            return False
    
    def sign_message_in_chain(self, chain_id: str, wallet_id: str, password: str, message: bytes) -> Optional[str]:
        """Sign a message with a wallet in a specific chain"""
        try:
            with self._get_http_client() as client:
                payload = {
                    "password": password,
                    "message_base64": base64.b64encode(message).decode()
                }
                
                response = client.post(f"/v1/chains/{chain_id}/wallets/{wallet_id}/sign", json=payload)
                if response.status_code == 200:
                    data = response.json()
                    return data.get("signature_base64")
                else:
                    return None
        except Exception:
            return None
    
    def get_wallet_balance_in_chain(self, chain_id: str, wallet_id: str) -> Optional[WalletBalance]:
        """Get wallet balance in a specific chain"""
        try:
            # For now, return a placeholder balance
            # In a real implementation, this would call the chain-specific balance endpoint
            wallet_info = self.get_wallet_info_in_chain(chain_id, wallet_id)
            if wallet_info:
                return WalletBalance(
                    wallet_id=wallet_id,
                    chain_id=chain_id,
                    balance=0.0,  # Placeholder
                    address=wallet_info.address
                )
            return None
        except Exception as e:
            error(f"Error getting wallet balance in chain {chain_id}: {str(e)}")
            return None
    
    def migrate_wallet(self, source_chain_id: str, target_chain_id: str, wallet_id: str,
                      password: str, new_password: Optional[str] = None) -> Optional[WalletMigrationResult]:
        """Migrate a wallet from one chain to another"""
        try:
            with self._get_http_client() as client:
                payload = {
                    "source_chain_id": source_chain_id,
                    "target_chain_id": target_chain_id,
                    "wallet_id": wallet_id,
                    "password": password
                }
                if new_password:
                    payload["new_password"] = new_password
                
                response = client.post("/v1/wallets/migrate", json=payload)
                if response.status_code == 200:
                    data = response.json()
                    
                    source_wallet = WalletInfo(
                        wallet_id=data["source_wallet"]["wallet_id"],
                        chain_id=data["source_wallet"]["chain_id"],
                        public_key=data["source_wallet"]["public_key"],
                        address=data["source_wallet"].get("address"),
                        metadata=data["source_wallet"].get("metadata")
                    )
                    
                    target_wallet = WalletInfo(
                        wallet_id=data["target_wallet"]["wallet_id"],
                        chain_id=data["target_wallet"]["chain_id"],
                        public_key=data["target_wallet"]["public_key"],
                        address=data["target_wallet"].get("address"),
                        metadata=data["target_wallet"].get("metadata")
                    )
                    
                    return WalletMigrationResult(
                        success=data["success"],
                        source_wallet=source_wallet,
                        target_wallet=target_wallet,
                        migration_timestamp=data["migration_timestamp"]
                    )
                else:
                    error(f"Failed to migrate wallet: {response.text}")
                    return None
        except Exception as e:
            error(f"Error migrating wallet: {str(e)}")
            return None
    
    def get_chain_status(self) -> Dict[str, Any]:
        """Get overall chain status and statistics"""
        try:
            chains = self.list_chains()
            active_chains = [c for c in chains if c.status == "active"]
            
            return {
                "total_chains": len(chains),
                "active_chains": len(active_chains),
                "total_wallets": sum(c.wallet_count for c in chains),
                "chains": [
                    {
                        "chain_id": chain.chain_id,
                        "name": chain.name,
                        "status": chain.status,
                        "wallet_count": chain.wallet_count,
                        "recent_activity": chain.recent_activity
                    }
                    for chain in chains
                ]
            }
        except Exception as e:
            error(f"Error getting chain status: {str(e)}")
            return {"error": str(e)}
