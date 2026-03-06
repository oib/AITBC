"""Wallet Migration Service for AITBC CLI

This module provides utilities for migrating wallets between
file-based storage and daemon-based storage.
"""

import json
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

from .wallet_daemon_client import WalletDaemonClient, WalletInfo
from .dual_mode_wallet_adapter import DualModeWalletAdapter
from .config import Config
from .utils import error, success, output


class WalletMigrationService:
    """Service for migrating wallets between file-based and daemon storage"""
    
    def __init__(self, config: Config):
        self.config = config
        self.wallet_dir = Path.home() / ".aitbc" / "wallets"
        self.wallet_dir.mkdir(parents=True, exist_ok=True)
        
        # Create adapters for both modes
        self.file_adapter = DualModeWalletAdapter(config, use_daemon=False)
        self.daemon_adapter = DualModeWalletAdapter(config, use_daemon=True)
    
    def is_daemon_available(self) -> bool:
        """Check if wallet daemon is available"""
        return self.daemon_adapter.is_daemon_available()
    
    def list_file_wallets(self) -> List[Dict[str, Any]]:
        """List all file-based wallets"""
        return self.file_adapter.list_wallets()
    
    def list_daemon_wallets(self) -> List[Dict[str, Any]]:
        """List all daemon-based wallets"""
        if not self.is_daemon_available():
            return []
        return self.daemon_adapter.list_wallets()
    
    def migrate_to_daemon(self, wallet_name: str, password: Optional[str] = None, 
                         new_password: Optional[str] = None, force: bool = False) -> Dict[str, Any]:
        """Migrate a file-based wallet to daemon storage"""
        try:
            # Check if wallet exists in file storage
            file_wallet = self.file_adapter.get_wallet_info(wallet_name)
            if not file_wallet:
                error(f"File wallet '{wallet_name}' not found")
                raise Exception("Wallet not found")
            
            # Check if wallet already exists in daemon
            if self.is_daemon_available():
                daemon_wallet = self.daemon_adapter.get_wallet_info(wallet_name)
                if daemon_wallet and not force:
                    error(f"Wallet '{wallet_name}' already exists in daemon. Use --force to overwrite.")
                    raise Exception("Wallet exists in daemon")
            
            # Get wallet data from file
            wallet_path = self.wallet_dir / f"{wallet_name}.json"
            with open(wallet_path, 'r') as f:
                wallet_data = json.load(f)
            
            # Prepare metadata for daemon
            metadata = {
                "migrated_from": "file",
                "migration_date": datetime.now().isoformat(),
                "original_wallet_type": wallet_data.get("wallet_type", "hd"),
                "original_balance": wallet_data.get("balance", 0.0),
                "transaction_count": len(wallet_data.get("transactions", [])),
                "original_created_at": wallet_data.get("created_at")
            }
            
            # Use provided password or default
            migration_password = new_password or password or "migrate_123"
            
            # Create wallet in daemon
            if self.is_daemon_available():
                daemon_wallet_info = self.daemon_adapter.create_wallet(
                    wallet_name, migration_password, metadata=metadata
                )
                
                success(f"Migrated wallet '{wallet_name}' to daemon")
                
                return {
                    "wallet_name": wallet_name,
                    "source_mode": "file",
                    "target_mode": "daemon",
                    "migrated_at": datetime.now().isoformat(),
                    "original_balance": wallet_data.get("balance", 0.0),
                    "transaction_count": len(wallet_data.get("transactions", [])),
                    "daemon_wallet_id": daemon_wallet_info.get("wallet_id"),
                    "backup_file": str(wallet_path)
                }
            else:
                error("Wallet daemon is not available for migration")
                raise Exception("Daemon unavailable")
                
        except Exception as e:
            error(f"Failed to migrate wallet to daemon: {str(e)}")
            raise
    
    def migrate_to_file(self, wallet_name: str, password: Optional[str] = None,
                       new_password: Optional[str] = None, force: bool = False) -> Dict[str, Any]:
        """Migrate a daemon-based wallet to file storage"""
        try:
            if not self.is_daemon_available():
                error("Wallet daemon is not available")
                raise Exception("Daemon unavailable")
            
            # Check if wallet exists in daemon
            daemon_wallet = self.daemon_adapter.get_wallet_info(wallet_name)
            if not daemon_wallet:
                error(f"Daemon wallet '{wallet_name}' not found")
                raise Exception("Wallet not found")
            
            # Check if wallet already exists in file storage
            file_wallet = self.file_adapter.get_wallet_info(wallet_name)
            if file_wallet and not force:
                error(f"Wallet '{wallet_name}' already exists in file storage. Use --force to overwrite.")
                raise Exception("Wallet exists in file storage")
            
            # Get additional info from daemon
            balance_info = self.daemon_adapter.get_wallet_balance(wallet_name)
            
            # Create file wallet data
            wallet_data = {
                "name": wallet_name,
                "address": daemon_wallet.get("address") or f"aitbc1{wallet_name}_migrated",
                "balance": balance_info.balance if balance_info else 0.0,
                "encrypted": bool(new_password or password),
                "private_key": f"migrated_from_daemon_{wallet_name}_{datetime.now().isoformat()}",
                "transactions": [],
                "created_at": daemon_wallet.get("created_at") or datetime.now().isoformat(),
                "wallet_type": "hd",
                "migration_metadata": {
                    "migrated_from": "daemon",
                    "migration_date": datetime.now().isoformat(),
                    "original_wallet_id": daemon_wallet.get("wallet_id"),
                    "original_public_key": daemon_wallet.get("public_key"),
                    "daemon_metadata": daemon_wallet.get("metadata", {})
                }
            }
            
            # Save to file
            wallet_path = self.wallet_dir / f"{wallet_name}.json"
            with open(wallet_path, 'w') as f:
                json.dump(wallet_data, f, indent=2)
            
            success(f"Migrated wallet '{wallet_name}' to file storage")
            
            return {
                "wallet_name": wallet_name,
                "source_mode": "daemon",
                "target_mode": "file",
                "migrated_at": datetime.now().isoformat(),
                "balance": wallet_data["balance"],
                "wallet_file": str(wallet_path),
                "original_wallet_id": daemon_wallet.get("wallet_id")
            }
            
        except Exception as e:
            error(f"Failed to migrate wallet to file: {str(e)}")
            raise
    
    def sync_wallets(self, wallet_name: str, direction: str = "to_daemon") -> Dict[str, Any]:
        """Synchronize wallet data between file and daemon modes"""
        try:
            if direction == "to_daemon":
                return self._sync_to_daemon(wallet_name)
            elif direction == "to_file":
                return self._sync_to_file(wallet_name)
            else:
                error("Invalid sync direction. Use 'to_daemon' or 'to_file'")
                raise Exception("Invalid direction")
                
        except Exception as e:
            error(f"Failed to sync wallet: {str(e)}")
            raise
    
    def _sync_to_daemon(self, wallet_name: str) -> Dict[str, Any]:
        """Sync wallet data from file to daemon"""
        file_wallet = self.file_adapter.get_wallet_info(wallet_name)
        if not file_wallet:
            error(f"File wallet '{wallet_name}' not found")
            raise Exception("Wallet not found")
        
        if not self.is_daemon_available():
            error("Wallet daemon is not available")
            raise Exception("Daemon unavailable")
        
        daemon_wallet = self.daemon_adapter.get_wallet_info(wallet_name)
        if not daemon_wallet:
            error(f"Daemon wallet '{wallet_name}' not found")
            raise Exception("Wallet not found")
        
        # Compare and sync data
        file_balance = file_wallet.get("balance", 0.0)
        daemon_balance = self.daemon_adapter.get_wallet_balance(wallet_name) or 0.0
        
        sync_info = {
            "wallet_name": wallet_name,
            "sync_direction": "file_to_daemon",
            "sync_time": datetime.now().isoformat(),
            "file_balance": file_balance,
            "daemon_balance": daemon_balance,
            "balance_difference": abs(file_balance - daemon_balance),
            "sync_required": file_balance != daemon_balance
        }
        
        if sync_info["sync_required"]:
            success(f"Wallet '{wallet_name}' sync required: balance difference {sync_info['balance_difference']}")
        else:
            success(f"Wallet '{wallet_name}' already in sync")
        
        return sync_info
    
    def _sync_to_file(self, wallet_name: str) -> Dict[str, Any]:
        """Sync wallet data from daemon to file"""
        if not self.is_daemon_available():
            error("Wallet daemon is not available")
            raise Exception("Daemon unavailable")
        
        daemon_wallet = self.daemon_adapter.get_wallet_info(wallet_name)
        if not daemon_wallet:
            error(f"Daemon wallet '{wallet_name}' not found")
            raise Exception("Wallet not found")
        
        file_wallet = self.file_adapter.get_wallet_info(wallet_name)
        if not file_wallet:
            error(f"File wallet '{wallet_name}' not found")
            raise Exception("Wallet not found")
        
        # Compare and sync data
        file_balance = file_wallet.get("balance", 0.0)
        daemon_balance = self.daemon_adapter.get_wallet_balance(wallet_name) or 0.0
        
        sync_info = {
            "wallet_name": wallet_name,
            "sync_direction": "daemon_to_file",
            "sync_time": datetime.now().isoformat(),
            "file_balance": file_balance,
            "daemon_balance": daemon_balance,
            "balance_difference": abs(file_balance - daemon_balance),
            "sync_required": file_balance != daemon_balance
        }
        
        if sync_info["sync_required"]:
            success(f"Wallet '{wallet_name}' sync required: balance difference {sync_info['balance_difference']}")
        else:
            success(f"Wallet '{wallet_name}' already in sync")
        
        return sync_info
    
    def get_migration_status(self) -> Dict[str, Any]:
        """Get overall migration status"""
        try:
            file_wallets = self.list_file_wallets()
            daemon_wallets = self.list_daemon_wallets() if self.is_daemon_available() else []
            
            file_wallet_names = {w["wallet_name"] for w in file_wallets}
            daemon_wallet_names = {w["wallet_name"] for w in daemon_wallets}
            
            # Categorize wallets
            file_only = file_wallet_names - daemon_wallet_names
            daemon_only = daemon_wallet_names - file_wallet_names
            both_modes = file_wallet_names & daemon_wallet_names
            
            status = {
                "daemon_available": self.is_daemon_available(),
                "total_file_wallets": len(file_wallets),
                "total_daemon_wallets": len(daemon_wallets),
                "file_only_wallets": list(file_only),
                "daemon_only_wallets": list(daemon_only),
                "both_modes_wallets": list(both_modes),
                "migration_candidates": list(file_only),
                "sync_candidates": list(both_modes)
            }
            
            return status
            
        except Exception as e:
            error(f"Failed to get migration status: {str(e)}")
            return {
                "daemon_available": False,
                "error": str(e)
            }
    
    def backup_wallet(self, wallet_name: str, backup_path: Optional[str] = None) -> str:
        """Create a backup of a wallet file"""
        try:
            wallet_path = self.wallet_dir / f"{wallet_name}.json"
            
            if not wallet_path.exists():
                error(f"Wallet '{wallet_name}' not found")
                raise Exception("Wallet not found")
            
            if not backup_path:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_filename = f"{wallet_name}_backup_{timestamp}.json"
                backup_path = self.wallet_dir / "backups" / backup_filename
            
            # Create backup directory
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Copy wallet file
            shutil.copy2(wallet_path, backup_path)
            
            success(f"Wallet backup created: {backup_path}")
            return str(backup_path)
            
        except Exception as e:
            error(f"Failed to backup wallet: {str(e)}")
            raise
