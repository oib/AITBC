"""AITBC Python SDK utilities."""

from __future__ import annotations

from importlib import import_module
from typing import Any

_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "AITBCClient": ("client", "AITBCClient"),
    "CoordinatorAPIClient": ("client", "CoordinatorAPIClient"),
    "CoordinatorReceiptClient": ("receipts", "CoordinatorReceiptClient"),
    "RegistryClient": ("client", "RegistryClient"),
    "WalletClient": ("client", "WalletClient"),
    "ReceiptPage": ("receipts", "ReceiptPage"),
    "ReceiptVerification": ("receipts", "ReceiptVerification"),
    "SignatureValidation": ("receipts", "SignatureValidation"),
    "verify_receipt": ("receipts", "verify_receipt"),
    "verify_receipts": ("receipts", "verify_receipts"),
    "AITBCError": ("errors", "AITBCError"),
    "AITBCConnectionError": ("errors", "AITBCConnectionError"),
    "AITBCRateLimitError": ("errors", "AITBCRateLimitError"),
    "with_backoff": ("retry", "with_backoff"),
}


def __getattr__(name: str) -> Any:
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute_name = _LAZY_EXPORTS[name]
    module = import_module(f".{module_name}", __name__)
    value = getattr(module, attribute_name)
    globals()[name] = value
    return value


__all__ = [*_LAZY_EXPORTS.keys()]
