from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, Request

from aitbc.auth import APIKeyAuthenticator

from .keystore.persistent_service import PersistentKeystoreService
from .ledger_mock import SQLiteLedgerAdapter
from .receipts.service import ReceiptVerifierService
from .settings import Settings, settings

# Temporarily disable multi-chain imports to test basic functionality
# from .chain.manager import ChainManager, chain_manager
# from .chain.multichain_ledger import MultiChainLedgerAdapter
# from .chain.chain_aware_wallet_service import ChainAwareWalletService


def get_settings() -> Settings:
    return settings


async def require_admin_api_key(
    request: Request,
    config: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    """Require an API key for admin/minting endpoints.

    ponytail: In production, set WALLET_API_KEY (or reuse COORDINATOR_API_KEY)
    and pass it as the X-API-Key header. The faucet is disabled by default.
    """
    authenticator = APIKeyAuthenticator(
        expected_key=config.api_key,
        auth_enabled=config.auth_enabled,
        header_name="X-API-Key",
        success_role="admin",
    )
    return await authenticator(request)


def get_receipt_service(config: Annotated[Settings, Depends(get_settings)]) -> ReceiptVerifierService:
    return ReceiptVerifierService(
        coordinator_url=config.coordinator_base_url,
        api_key=config.coordinator_api_key,
    )


def get_keystore(config: Annotated[Settings, Depends(get_settings)]) -> PersistentKeystoreService:
    return PersistentKeystoreService(db_path=config.ledger_db_path.parent / "keystore.db")


def get_ledger(config: Annotated[Settings, Depends(get_settings)]) -> SQLiteLedgerAdapter:
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
