"""Spend policy gate for wallet daemon signing (AGENT-SPEND-A-1 Phase A)."""

from __future__ import annotations

import os
from typing import Any

ALLOWED_OPS = frozenset({"wallet.execute", "escrow.fund", "transfer.approved"})


def spend_policy_enforced() -> bool:
    return os.getenv("AITBC_SPEND_POLICY_ENFORCE", "0").strip().lower() in ("1", "true", "yes")


def assert_transfer_allowed(amount: int, payload: dict[str, Any] | None) -> None:
    """Fail closed when enforcement is on: require payload with allowed op and optional max_amount."""
    if not spend_policy_enforced():
        return
    if not payload:
        raise ValueError(
            "spend policy: transaction payload required (set op, optional max_amount); "
            "disable with AITBC_SPEND_POLICY_ENFORCE=0"
        )
    op = str(payload.get("op") or "wallet.execute")
    if op not in ALLOWED_OPS:
        raise ValueError(f"spend policy: disallowed op {op!r}")
    max_amount = payload.get("max_amount")
    if max_amount is not None and amount > int(max_amount):
        raise ValueError("spend policy: amount exceeds payload max_amount")
