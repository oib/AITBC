"""
Multi-Chain Support Module for Wallet Daemon

This module provides multi-chain capabilities for the wallet daemon,
including chain management, chain-specific storage, and chain-aware
wallet operations.
"""

from .manager import ChainManager, ChainConfig, ChainStatus, chain_manager
from .multichain_ledger import MultiChainLedgerAdapter, ChainLedgerRecord, ChainWalletMetadata
from .chain_aware_wallet_service import ChainAwareWalletService

__all__ = [
    "ChainManager",
    "ChainConfig", 
    "ChainStatus",
    "chain_manager",
    "MultiChainLedgerAdapter",
    "ChainLedgerRecord",
    "ChainWalletMetadata",
    "ChainAwareWalletService"
]
