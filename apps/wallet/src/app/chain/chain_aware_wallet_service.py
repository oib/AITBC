"""
Chain-Aware Wallet Service for Wallet Daemon

Multi-chain wallet operations with proper chain context,
isolation, and management across different blockchain networks.
"""

from typing import Dict, List, Optional, Any
from pathlib import Path
from datetime import datetime

from aitbc import get_logger
from .manager import ChainManager, ChainConfig, ChainStatus
from .multichain_ledger import MultiChainLedgerAdapter, ChainWalletMetadata
from ..keystore.persistent_service import PersistentKeystoreService
from ..security import wipe_buffer

logger = get_logger(__name__)


class ChainAwareWalletService:
    """Chain-aware wallet service with multi-chain support"""
    
    def __init__(self, chain_manager: ChainManager, multichain_ledger: MultiChainLedgerAdapter):
        self.chain_manager = chain_manager
        self.multichain_ledger = multichain_ledger
        
        # Chain-specific keystores
        self.chain_keystores: Dict[str, PersistentKeystoreService] = {}
        self._initialize_chain_keystores()
    
    def _initialize_chain_keystores(self):
        """Initialize keystore for each chain"""
        for chain in self.chain_manager.list_chains():
            self._init_chain_keystore(chain.chain_id)
    
    def _init_chain_keystore(self, chain_id: str):
        """Initialize keystore for a specific chain"""
        try:
            chain = self.chain_manager.get_chain(chain_id)
            if not chain:
                return
            
            keystore_path = chain.keystore_path or f"./data/keystore_{chain_id}"
            keystore = PersistentKeystoreService(keystore_path)
            self.chain_keystores[chain_id] = keystore
            
            logger.info(f"Initialized keystore for chain: {chain_id}")
        except Exception as e:
            logger.error(f"Failed to initialize keystore for chain {chain_id}: {e}")
    
    def _get_keystore(self, chain_id: str) -> Optional[PersistentKeystoreService]:
        """Get keystore for a specific chain"""
        if chain_id not in self.chain_keystores:
            self._init_chain_keystore(chain_id)
        
        return self.chain_keystores.get(chain_id)
    
    def create_wallet(self, chain_id: str, wallet_id: str, password: str, 
                     secret_key: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> Optional[ChainWalletMetadata]:
        """Create a wallet in a specific chain"""
        try:
            # Validate chain
            if not self.chain_manager.validate_chain_id(chain_id):
                logger.error(f"Invalid or inactive chain: {chain_id}")
                return None
            
            # Get keystore for chain
            keystore = self._get_keystore(chain_id)
            if not keystore:
                logger.error(f"Failed to get keystore for chain: {chain_id}")
                return None
            
            # Create wallet in keystore
            keystore_record = keystore.create_wallet(wallet_id, password, secret_key, metadata or {})
            
            # Create wallet in ledger
            success = self.multichain_ledger.create_wallet(
                chain_id, wallet_id, keystore_record.public_key, 
                metadata=keystore_record.metadata
            )
            
            if not success:
                # Rollback keystore creation
                try:
                    keystore.delete_wallet(wallet_id, password)
                except:
                    pass
                return None
            
            # Get wallet metadata
            wallet_metadata = self.multichain_ledger.get_wallet(chain_id, wallet_id)
            
            # Record creation event
            self.multichain_ledger.record_event(chain_id, wallet_id, "created", {
                "public_key": keystore_record.public_key,
                "chain_id": chain_id,
                "metadata": metadata or {}
            })
            
            logger.info(f"Created wallet {wallet_id} in chain {chain_id}")
            return wallet_metadata
            
        except Exception as e:
            logger.error(f"Failed to create wallet {wallet_id} in chain {chain_id}: {e}")
            return None
    
    def get_wallet(self, chain_id: str, wallet_id: str) -> Optional[ChainWalletMetadata]:
        """Get wallet metadata from a specific chain"""
        try:
            if not self.chain_manager.validate_chain_id(chain_id):
                return None
            
            return self.multichain_ledger.get_wallet(chain_id, wallet_id)
        except Exception as e:
            logger.error(f"Failed to get wallet {wallet_id} from chain {chain_id}: {e}")
            return None
    
    def list_wallets(self, chain_id: Optional[str] = None) -> List[ChainWalletMetadata]:
        """List wallets from a specific chain or all chains"""
        try:
            if chain_id:
                if not self.chain_manager.validate_chain_id(chain_id):
                    return []
                return self.multichain_ledger.list_wallets(chain_id)
            else:
                # List from all active chains
                all_wallets = []
                for chain in self.chain_manager.get_active_chains():
                    chain_wallets = self.multichain_ledger.list_wallets(chain.chain_id)
                    all_wallets.extend(chain_wallets)
                return all_wallets
        except Exception as e:
            logger.error(f"Failed to list wallets: {e}")
            return []
    
    def delete_wallet(self, chain_id: str, wallet_id: str, password: str) -> bool:
        """Delete a wallet from a specific chain"""
        try:
            if not self.chain_manager.validate_chain_id(chain_id):
                return False
            
            # Get keystore
            keystore = self._get_keystore(chain_id)
            if not keystore:
                return False
            
            # Delete from keystore
            keystore_success = keystore.delete_wallet(wallet_id, password)
            if not keystore_success:
                return False
            
            # Record deletion event
            self.multichain_ledger.record_event(chain_id, wallet_id, "deleted", {
                "chain_id": chain_id
            })
            
            # Note: We keep the wallet metadata in ledger for audit purposes
            logger.info(f"Deleted wallet {wallet_id} from chain {chain_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete wallet {wallet_id} from chain {chain_id}: {e}")
            return False
    
    def sign_message(self, chain_id: str, wallet_id: str, password: str, message: bytes, 
                    ip_address: Optional[str] = None) -> Optional[str]:
        """Sign a message with wallet private key in a specific chain"""
        try:
            if not self.chain_manager.validate_chain_id(chain_id):
                return None
            
            # Get keystore
            keystore = self._get_keystore(chain_id)
            if not keystore:
                return None
            
            # Sign message
            signature = keystore.sign_message(wallet_id, password, message, ip_address)
            
            if signature:
                # Record signing event
                self.multichain_ledger.record_event(chain_id, wallet_id, "signed", {
                    "message_length": len(message),
                    "ip_address": ip_address,
                    "chain_id": chain_id
                })
                
                logger.info(f"Signed message for wallet {wallet_id} in chain {chain_id}")
            
            return signature
            
        except Exception as e:
            logger.error(f"Failed to sign message for wallet {wallet_id} in chain {chain_id}: {e}")
            return None
    
    def unlock_wallet(self, chain_id: str, wallet_id: str, password: str) -> bool:
        """Unlock a wallet in a specific chain"""
        try:
            if not self.chain_manager.validate_chain_id(chain_id):
                return False
            
            # Get keystore
            keystore = self._get_keystore(chain_id)
            if not keystore:
                return False
            
            # Unlock wallet
            success = keystore.unlock_wallet(wallet_id, password)
            
            if success:
                # Record unlock event
                self.multichain_ledger.record_event(chain_id, wallet_id, "unlocked", {
                    "chain_id": chain_id
                })
                
                logger.info(f"Unlocked wallet {wallet_id} in chain {chain_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to unlock wallet {wallet_id} in chain {chain_id}: {e}")
            return False
    
    def lock_wallet(self, chain_id: str, wallet_id: str) -> bool:
        """Lock a wallet in a specific chain"""
        try:
            if not self.chain_manager.validate_chain_id(chain_id):
                return False
            
            # Get keystore
            keystore = self._get_keystore(chain_id)
            if not keystore:
                return False
            
            # Lock wallet
            success = keystore.lock_wallet(wallet_id)
            
            if success:
                # Record lock event
                self.multichain_ledger.record_event(chain_id, wallet_id, "locked", {
                    "chain_id": chain_id
                })
                
                logger.info(f"Locked wallet {wallet_id} in chain {chain_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to lock wallet {wallet_id} in chain {chain_id}: {e}")
            return False
    
    def get_wallet_events(self, chain_id: str, wallet_id: str, 
                        event_type: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Get events for a wallet in a specific chain"""
        try:
            if not self.chain_manager.validate_chain_id(chain_id):
                return []
            
            events = self.multichain_ledger.get_wallet_events(chain_id, wallet_id, event_type, limit)
            
            return [
                {
                    "chain_id": event.chain_id,
                    "wallet_id": event.wallet_id,
                    "event_type": event.event_type,
                    "timestamp": event.timestamp.isoformat(),
                    "data": event.data,
                    "success": event.success
                }
                for event in events
            ]
            
        except Exception as e:
            logger.error(f"Failed to get events for wallet {wallet_id} in chain {chain_id}: {e}")
            return []
    
    def get_chain_wallet_stats(self, chain_id: str) -> Dict[str, Any]:
        """Get wallet statistics for a specific chain"""
        try:
            if not self.chain_manager.validate_chain_id(chain_id):
                return {}
            
            # Get ledger stats
            ledger_stats = self.multichain_ledger.get_chain_stats(chain_id)
            
            # Get keystore stats
            keystore = self._get_keystore(chain_id)
            keystore_stats = {}
            if keystore:
                keystore_stats = {
                    "total_wallets": len(keystore.list_wallets()),
                    "unlocked_wallets": len([w for w in keystore.list_wallets() if w.get("unlocked", False)])
                }
            
            return {
                "chain_id": chain_id,
                "ledger_stats": ledger_stats,
                "keystore_stats": keystore_stats
            }
            
        except Exception as e:
            logger.error(f"Failed to get stats for chain {chain_id}: {e}")
            return {}
    
    def get_all_chain_wallet_stats(self) -> Dict[str, Any]:
        """Get wallet statistics for all chains"""
        stats = {
            "total_chains": 0,
            "total_wallets": 0,
            "chain_stats": {}
        }
        
        for chain in self.chain_manager.get_active_chains():
            chain_stats = self.get_chain_wallet_stats(chain.chain_id)
            if chain_stats:
                stats["chain_stats"][chain.chain_id] = chain_stats
                stats["total_wallets"] += chain_stats.get("ledger_stats", {}).get("wallet_count", 0)
                stats["total_chains"] += 1
        
        return stats
    
    def migrate_wallet_between_chains(self, source_chain_id: str, target_chain_id: str, 
                                   wallet_id: str, password: str, new_password: Optional[str] = None) -> bool:
        """Migrate a wallet from one chain to another"""
        try:
            # Validate both chains
            if not self.chain_manager.validate_chain_id(source_chain_id):
                logger.error(f"Invalid source chain: {source_chain_id}")
                return False
            
            if not self.chain_manager.validate_chain_id(target_chain_id):
                logger.error(f"Invalid target chain: {target_chain_id}")
                return False
            
            # Get source wallet
            source_wallet = self.get_wallet(source_chain_id, wallet_id)
            if not source_wallet:
                logger.error(f"Wallet {wallet_id} not found in source chain {source_chain_id}")
                return False
            
            # Check if wallet already exists in target chain
            target_wallet = self.get_wallet(target_chain_id, wallet_id)
            if target_wallet:
                logger.error(f"Wallet {wallet_id} already exists in target chain {target_chain_id}")
                return False
            
            # Get source keystore
            source_keystore = self._get_keystore(source_chain_id)
            target_keystore = self._get_keystore(target_chain_id)
            
            if not source_keystore or not target_keystore:
                logger.error("Failed to get keystores for migration")
                return False
            
            # Export wallet from source chain
            try:
                # This would require adding export/import methods to keystore
                # For now, we'll create a new wallet with the same keys
                source_keystore_record = source_keystore.get_wallet(wallet_id)
                if not source_keystore_record:
                    logger.error("Failed to get source wallet record")
                    return False
                
                # Create wallet in target chain with same keys
                target_wallet = self.create_wallet(
                    target_chain_id, wallet_id, new_password or password,
                    source_keystore_record.get("secret_key"), source_wallet.metadata
                )
                
                if target_wallet:
                    # Record migration events
                    self.multichain_ledger.record_event(source_chain_id, wallet_id, "migrated_from", {
                        "target_chain": target_chain_id,
                        "migration_timestamp": datetime.now().isoformat()
                    })
                    
                    self.multichain_ledger.record_event(target_chain_id, wallet_id, "migrated_to", {
                        "source_chain": source_chain_id,
                        "migration_timestamp": datetime.now().isoformat()
                    })
                    
                    logger.info(f"Migrated wallet {wallet_id} from {source_chain_id} to {target_chain_id}")
                    return True
                else:
                    logger.error("Failed to create wallet in target chain")
                    return False
                    
            except Exception as e:
                logger.error(f"Failed to migrate wallet {wallet_id}: {e}")
                return False
                
        except Exception as e:
            logger.error(f"Wallet migration failed: {e}")
            return False
    
    def cleanup(self):
        """Cleanup resources"""
        try:
            # Close all keystore connections
            for chain_id, keystore in self.chain_keystores.items():
                try:
                    keystore.close()
                    logger.info(f"Closed keystore for chain: {chain_id}")
                except Exception as e:
                    logger.error(f"Failed to close keystore for chain {chain_id}: {e}")
            
            self.chain_keystores.clear()
            
            # Close ledger connections
            self.multichain_ledger.close_all_connections()
            
        except Exception as e:
            logger.error(f"Failed to cleanup wallet service: {e}")
