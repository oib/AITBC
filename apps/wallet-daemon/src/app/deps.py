from __future__ import annotations

from functools import lru_cache

from fastapi import Depends

from .keystore.service import KeystoreService
from .ledger_mock import SQLiteLedgerAdapter
from .receipts.service import ReceiptVerifierService
from .settings import Settings, settings


@lru_cache
def get_settings() -> Settings:
    return settings


def get_receipt_service(config: Settings = Depends(get_settings)) -> ReceiptVerifierService:
    return ReceiptVerifierService(
        coordinator_url=config.coordinator_base_url,
        api_key=config.coordinator_api_key,
    )


@lru_cache
def get_keystore() -> KeystoreService:
    return KeystoreService()


@lru_cache
def get_ledger(config: Settings = Depends(get_settings)) -> SQLiteLedgerAdapter:
    return SQLiteLedgerAdapter(config.ledger_db_path)
