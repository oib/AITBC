"""
Chain-Aware Wallet Service for Wallet Daemon

Multi-chain wallet operations with proper chain context,
isolation, and management across different blockchain networks.
"""
from datetime import datetime
from typing import Any
from aitbc import get_logger
from ..keystore.persistent_service import PersistentKeystoreService
from .manager import ChainManager
from .multichain_ledger import ChainWalletMetadata, MultiChainLedgerAdapter
logger = get_logger(__name__)

class ChainAwareWalletService:
    """Chain-aware wallet service with multi-chain support"""

    def __init__(self, chain_manager: ChainManager, multichain_ledger: MultiChainLedgerAdapter):
        self.chain_manager = chain_manager
        self.multichain_ledger = multichain_ledger
        self.chain_keystores: dict[str, PersistentKeystoreService] = {}
        self._initialize_chain_keystores()

    def _initialize_chain_keystores(self) -> None:
        """Initialize keystore for each chain"""
        for chain in self.chain_manager.list_chains():
            self._init_chain_keystore(chain.chain_id)

    def _init_chain_keystore(self, chain_id: str) -> None:
        """Initialize keystore for a specific chain"""
        try:
            chain = self.chain_manager.get_chain(chain_id)
            if not chain:
                return
            keystore_path = chain.keystore_path or f'./data/keystore_{chain_id}'
            from pathlib import Path
            keystore = PersistentKeystoreService(Path(keystore_path))
            self.chain_keystores[chain_id] = keystore
            logger.info('Initialized keystore for chain: %s', chain_id)
        except Exception as e:
            logger.error('Failed to initialize keystore for chain %s: %s', chain_id, e)

    def _get_keystore(self, chain_id: str) -> PersistentKeystoreService | None:
        """Get keystore for a specific chain"""
        if chain_id not in self.chain_keystores:
            self._init_chain_keystore(chain_id)
        return self.chain_keystores.get(chain_id)

    def create_wallet(self, chain_id: str, wallet_id: str, password: str, secret_key: str | None=None, metadata: dict[str, Any] | None=None) -> ChainWalletMetadata | None:
        """Create a wallet in a specific chain"""
        try:
            if not self.chain_manager.validate_chain_id(chain_id):
                logger.error('Invalid or inactive chain: %s', chain_id)
                return None
            keystore = self._get_keystore(chain_id)
            if not keystore:
                logger.error('Failed to get keystore for chain: %s', chain_id)
                return None
            keystore_record = keystore.create_wallet(wallet_id, password, secret_key, metadata or {})  # type: ignore
            success = self.multichain_ledger.create_wallet(chain_id, wallet_id, keystore_record.public_key, metadata=keystore_record.metadata)
            if not success:
                try:
                    keystore.delete_wallet(wallet_id)
                except Exception:
                    pass
                return None
            wallet_metadata = self.multichain_ledger.get_wallet(chain_id, wallet_id)
            self.multichain_ledger.record_event(chain_id, wallet_id, 'created', {'public_key': keystore_record.public_key, 'chain_id': chain_id, 'metadata': metadata or {}})
            logger.info('Created wallet %s in chain %s', wallet_id, chain_id)
            return wallet_metadata
        except Exception as e:
            logger.error('Failed to create wallet %s in chain %s: %s', wallet_id, chain_id, e)
            return None

    def get_wallet(self, chain_id: str, wallet_id: str) -> ChainWalletMetadata | None:
        """Get wallet metadata from a specific chain"""
        try:
            if not self.chain_manager.validate_chain_id(chain_id):
                return None
            return self.multichain_ledger.get_wallet(chain_id, wallet_id)
        except Exception as e:
            logger.error('Failed to get wallet %s from chain %s: %s', wallet_id, chain_id, e)
            return None

    def list_wallets(self, chain_id: str | None=None) -> list[ChainWalletMetadata]:
        """List wallets from a specific chain or all chains"""
        try:
            if chain_id:
                if not self.chain_manager.validate_chain_id(chain_id):
                    return []
                return self.multichain_ledger.list_wallets(chain_id)
            else:
                all_wallets = []
                for chain in self.chain_manager.get_active_chains():
                    chain_wallets = self.multichain_ledger.list_wallets(chain.chain_id)
                    all_wallets.extend(chain_wallets)
                return all_wallets
        except Exception as e:
            logger.error('Failed to list wallets: %s', e)
            return []

    def delete_wallet(self, chain_id: str, wallet_id: str, password: str) -> bool:
        """Delete a wallet from a specific chain"""
        try:
            if not self.chain_manager.validate_chain_id(chain_id):
                return False
            keystore = self._get_keystore(chain_id)
            if not keystore:
                return False
            keystore_success = keystore.delete_wallet(wallet_id)
            if not keystore_success:
                return False
            self.multichain_ledger.record_event(chain_id, wallet_id, 'deleted', {'chain_id': chain_id})
            logger.info('Deleted wallet %s from chain %s', wallet_id, chain_id)
            return True
        except Exception as e:
            logger.error('Failed to delete wallet %s from chain %s: %s', wallet_id, chain_id, e)
            return False

    def sign_message(self, chain_id: str, wallet_id: str, password: str, message: bytes, ip_address: str | None=None) -> str | None:
        """Sign a message with wallet private key in a specific chain"""
        try:
            if not self.chain_manager.validate_chain_id(chain_id):
                return None
            keystore = self._get_keystore(chain_id)
            if not keystore:
                return None
            signature = keystore.sign_message(wallet_id, password, message, ip_address)
            if signature:
                self.multichain_ledger.record_event(chain_id, wallet_id, 'signed', {'message_length': len(message), 'ip_address': ip_address, 'chain_id': chain_id})
                logger.info('Signed message for wallet %s in chain %s', wallet_id, chain_id)
            return signature  # type: ignore[return-value]
        except Exception as e:
            logger.error('Failed to sign message for wallet %s in chain %s: %s', wallet_id, chain_id, e)
            return None

    def unlock_wallet(self, chain_id: str, wallet_id: str, password: str) -> bool:
        """Unlock a wallet in a specific chain"""
        try:
            if not self.chain_manager.validate_chain_id(chain_id):
                return False
            keystore = self._get_keystore(chain_id)
            if not keystore:
                return False
            success = keystore.unlock_wallet(wallet_id, password)
            if success:
                self.multichain_ledger.record_event(chain_id, wallet_id, 'unlocked', {'chain_id': chain_id})
                logger.info('Unlocked wallet %s in chain %s', wallet_id, chain_id)
            return success  # type: ignore[return-value]
        except Exception as e:
            logger.error('Failed to unlock wallet %s in chain %s: %s', wallet_id, chain_id, e)
            return False

    def lock_wallet(self, chain_id: str, wallet_id: str) -> bool:
        """Lock a wallet in a specific chain"""
        try:
            if not self.chain_manager.validate_chain_id(chain_id):
                return False
            keystore = self._get_keystore(chain_id)
            if not keystore:
                return False
            success = keystore.lock_wallet(wallet_id)  # type: ignore[attr-defined]
            if success:
                self.multichain_ledger.record_event(chain_id, wallet_id, 'locked', {'chain_id': chain_id})
                logger.info('Locked wallet %s in chain %s', wallet_id, chain_id)
            return success  # type: ignore[no-any-return]
        except Exception as e:
            logger.error('Failed to lock wallet %s in chain %s: %s', wallet_id, chain_id, e)
            return False

    def get_wallet_events(self, chain_id: str, wallet_id: str, event_type: str | None=None, limit: int=100) -> list[dict[str, Any]]:
        """Get events for a wallet in a specific chain"""
        try:
            if not self.chain_manager.validate_chain_id(chain_id):
                return []
            events = self.multichain_ledger.get_wallet_events(chain_id, wallet_id, event_type, limit)
            return [{'chain_id': event.chain_id, 'wallet_id': event.wallet_id, 'event_type': event.event_type, 'timestamp': event.timestamp.isoformat(), 'data': event.data, 'success': event.success} for event in events]
        except Exception as e:
            logger.error('Failed to get events for wallet %s in chain %s: %s', wallet_id, chain_id, e)
            return []

    def get_chain_wallet_stats(self, chain_id: str) -> dict[str, Any]:
        """Get wallet statistics for a specific chain"""
        try:
            if not self.chain_manager.validate_chain_id(chain_id):
                return {}
            ledger_stats = self.multichain_ledger.get_chain_stats(chain_id)
            keystore = self._get_keystore(chain_id)
            keystore_stats = {}
            if keystore:
                wallet_list = keystore.list_wallets()
                keystore_stats = {'total_wallets': len(wallet_list), 'unlocked_wallets': len(wallet_list)}
            return {'chain_id': chain_id, 'ledger_stats': ledger_stats, 'keystore_stats': keystore_stats}
        except Exception as e:
            logger.error('Failed to get stats for chain %s: %s', chain_id, e)
            return {}

    def get_all_chain_wallet_stats(self) -> dict[str, Any]:
        """Get wallet statistics for all chains"""
        stats: dict[str, Any] = {'total_chains': 0, 'total_wallets': 0, 'chain_stats': {}}
        for chain in self.chain_manager.get_active_chains():
            chain_stats = self.get_chain_wallet_stats(chain.chain_id)
            if chain_stats:
                stats['chain_stats'][chain.chain_id] = chain_stats
                stats['total_wallets'] += chain_stats.get('ledger_stats', {}).get('wallet_count', 0)
                stats['total_chains'] += 1
        return stats

    def migrate_wallet_between_chains(self, source_chain_id: str, target_chain_id: str, wallet_id: str, password: str, new_password: str | None=None) -> bool:
        """Migrate a wallet from one chain to another"""
        try:
            if not self.chain_manager.validate_chain_id(source_chain_id):
                logger.error('Invalid source chain: %s', source_chain_id)
                return False
            if not self.chain_manager.validate_chain_id(target_chain_id):
                logger.error('Invalid target chain: %s', target_chain_id)
                return False
            source_wallet = self.get_wallet(source_chain_id, wallet_id)
            if not source_wallet:
                logger.error('Wallet %s not found in source chain %s', wallet_id, source_chain_id)
                return False
            target_wallet = self.get_wallet(target_chain_id, wallet_id)
            if target_wallet:
                logger.error('Wallet %s already exists in target chain %s', wallet_id, target_chain_id)
                return False
            source_keystore = self._get_keystore(source_chain_id)
            target_keystore = self._get_keystore(target_chain_id)
            if not source_keystore or not target_keystore:
                logger.error('Failed to get keystores for migration')
                return False
            try:
                source_keystore_record = source_keystore.get_wallet(wallet_id)
                if not source_keystore_record:
                    logger.error('Failed to get source wallet record')
                    return False
                target_wallet = self.create_wallet(target_chain_id, wallet_id, new_password or password, source_keystore_record.get('secret_key'), source_wallet.metadata)  # type: ignore
                if target_wallet:
                    self.multichain_ledger.record_event(source_chain_id, wallet_id, 'migrated_from', {'target_chain': target_chain_id, 'migration_timestamp': datetime.now().isoformat()})
                    self.multichain_ledger.record_event(target_chain_id, wallet_id, 'migrated_to', {'source_chain': source_chain_id, 'migration_timestamp': datetime.now().isoformat()})
                    logger.info('Migrated wallet %s from %s to %s', wallet_id, source_chain_id, target_chain_id)
                    return True
                else:
                    logger.error('Failed to create wallet in target chain')
                    return False
            except Exception as e:
                logger.error('Failed to migrate wallet %s: %s', wallet_id, e)
                return False
        except Exception as e:
            logger.error('Wallet migration failed: %s', e)
            return False

    def cleanup(self) -> None:
        """Cleanup resources"""
        try:
            for chain_id, keystore in self.chain_keystores.items():
                try:
                    keystore.close()  # type: ignore[attr-defined]
                    logger.info('Closed keystore for chain: %s', chain_id)
                except Exception as e:
                    logger.error('Failed to close keystore for chain %s: %s', chain_id, e)
            self.chain_keystores.clear()
            self.multichain_ledger.close_all_connections()
        except Exception as e:
            logger.error('Failed to cleanup wallet service: %s', e)