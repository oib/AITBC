from __future__ import annotations

from functools import lru_cache

from fastapi import Depends

from .keystore.service import KeystoreService
from .ledger_mock import SQLiteLedgerAdapter
from .keystore.persistent_service import PersistentKeystoreService
from .receipts.service import ReceiptVerifierService
from .settings import Settings, settings
# Temporarily disable multi-chain imports to test basic functionality
# from .chain.manager import ChainManager, chain_manager
# from .chain.multichain_ledger import MultiChainLedgerAdapter
# from .chain.chain_aware_wallet_service import ChainAwareWalletService


def get_settings() -> Settings:
    return settings


def get_receipt_service(config: Settings = Depends(get_settings)) -> ReceiptVerifierService:
    return ReceiptVerifierService(
        coordinator_url=config.coordinator_base_url,
        api_key=config.coordinator_api_key,
    )


@lru_cache
def get_keystore(config: Settings = Depends(get_settings)) -> PersistentKeystoreService:
    return PersistentKeystoreService(db_path=config.ledger_db_path.parent / "keystore.db")


def get_ledger(config: Settings = Depends(get_settings)) -> SQLiteLedgerAdapter:
    return SQLiteLedgerAdapter(config.ledger_db_path)

# Temporarily disable multi-chain dependency functions
# @lru_cache
# def get_chain_manager() -> ChainManager:
#     return chain_manager

# @lru_cache
# def get_multichain_ledger(chain_mgr: ChainManager = Depends(get_chain_manager)) -> MultiChainLedgerAdapter:
#     return MultiChainLedgerAdapter(chain_mgr)

# @lru_cache
# def get_chain_aware_wallet_service(
#     chain_mgr: ChainManager = Depends(get_chain_manager),
#     multichain_ledger: MultiChainLedgerAdapter = Depends(get_multichain_ledger)
# ) -> ChainAwareWalletService:
#     return ChainAwareWalletService(chain_mgr, multichain_ledger)
