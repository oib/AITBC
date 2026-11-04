"""Spend policy gate for wallet daemon signing (AGENT-SPEND-A-1 Phase A)."""

from __future__ import annotations

import os
from typing import Any

ALLOWED_OPS = frozenset({"wallet.execute", "escrow.fund", "transfer.approved"})


def spend_policy_enforced() -> bool:
    return os.getenv("AITBC_SPEND_POLICY_ENFORCE", "0").strip().lower() in ("1", "true", "yes")


def assert_transfer_allowed(amount: int, payload: dict[str, Any] | None) -> None:
    """Fail closed when enforcement is on: require payload with allowed op and max_amount.

    This is a **shape gate** for the daemon signing path only; spend caps are enforced
    on the coordinator via spend sessions (see docs/account-abstraction/security.md).
    """
    if not spend_policy_enforced():
        return
    if not payload:
        raise ValueError(
            "spend policy: transaction payload required (set op and max_amount); disable with AITBC_SPEND_POLICY_ENFORCE=0"
        )
    op = str(payload.get("op") or "wallet.execute")
    if op not in ALLOWED_OPS:
        raise ValueError(f"spend policy: disallowed op {op!r}")
    if payload.get("max_amount") is None:
        raise ValueError("spend policy: max_amount required when enforcement is enabled")
    max_amount_raw = payload.get("max_amount")
    assert max_amount_raw is not None
    if amount > int(max_amount_raw):
        raise ValueError("spend policy: amount exceeds payload max_amount")
