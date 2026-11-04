"""Agent spend policy constants and permission checks (AGENT-SPEND-A-1)."""

from __future__ import annotations

PERM_WALLET_EXECUTE = "wallet.execute"
PERM_ESCROW_FUND = "escrow.fund"
PERM_TRANSFER_APPROVED = "transfer.approved"

ALLOWED_PERMISSIONS: frozenset[str] = frozenset({PERM_WALLET_EXECUTE, PERM_ESCROW_FUND, PERM_TRANSFER_APPROVED})


def operation_from_tx_data(data: dict | None) -> str:
    """Map transaction payload to a permission op (default wallet.execute)."""
    if not data:
        return PERM_WALLET_EXECUTE
    op = data.get("op")
    if op is None:
        return PERM_WALLET_EXECUTE
    if op not in ALLOWED_PERMISSIONS:
        raise ValueError(f"unsupported spend operation: {op}")
    return str(op)


def assert_wallet_permission(permissions: list[str], operation: str) -> None:
    """When permissions are configured, require the operation to be listed."""
    if operation not in ALLOWED_PERMISSIONS:
        raise ValueError(f"unsupported spend operation: {operation}")
    if not permissions:
        return
    if operation not in permissions:
        raise ValueError("Insufficient permissions for wallet execute")
