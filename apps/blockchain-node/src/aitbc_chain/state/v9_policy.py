"""v9 transaction-authorization policy — one list, one rule, every path.

At ``state_transition_v9_height`` every user-originated transaction must
carry a valid sender signature at apply time. Only the internal types in
``V9_UNSIGNED_ALLOWED_TX_TYPES`` may appear unsigned, and each carries its
own authorization rule enforced elsewhere in the apply path:

- ``BRIDGE_LOCK`` — created by the bridge service after it debited the
  sender at request time. From v9 it carries the bridge authority's
  ``bridge_signature`` over its semantic fields (state/bridge_credit.py),
  the same rule as the credits — a forged lock was theft of the
  ``target_recipient`` credit on the target chain, so it cannot stay
  unsigned.
- ``BRIDGE_RELEASE`` / ``BRIDGE_REFUND`` — pseudo-senders authorized by
  the ``bridge_signature`` authority signature in the tx (checked at v5+,
  plus the v6 refund-lock binding). They are exempt only from the *sender*
  signature rule.

This list is shared by the sequential and parallel apply paths and by
remote attestation — the consensus rule must be one list, not three
copies that can drift.

While ``state_transition_v9_height`` is unset the same checks evaluate in
shadow mode: every would-reject logs and increments
``v9_would_reject_total`` plus ``v9_would_reject_<reason>[_<tx_type>]_total``
instead of rejecting, so a fleet can prove the allowlist is complete on
live traffic before the height is pinned.
"""

from __future__ import annotations

from typing import Any

from ..metrics import metrics_registry

V9_UNSIGNED_ALLOWED_TX_TYPES = frozenset(
    {
        "BRIDGE_LOCK",
        "BRIDGE_RELEASE",
        "BRIDGE_REFUND",
    }
)


def v9_signature_verdict(tx_data: dict[str, Any], tx_type: str) -> str | None:
    """Return the reason ``tx_data`` would be rejected under v9 rules, or
    ``None`` when it satisfies them.

    Only signature *presence* is judged here — an attached signature that
    fails verification is already rejected by the existing v7+ checks on
    every path, so its rejection is not v9-specific.
    """
    if tx_type in V9_UNSIGNED_ALLOWED_TX_TYPES:
        return None
    if tx_data.get("signature") or tx_data.get("sig"):
        return None
    return "missing_signature"


def count_v9_would_reject(reason: str, tx_type: str = "") -> None:
    """Count a v9 shadow-reject (or post-activation real reject).

    Emits the aggregate ``v9_would_reject_total`` and a per-reason (and
    per-type where known) detail counter — the metrics registry has no
    label support, so the reason/type are encoded in the name.
    """
    metrics_registry.increment("v9_would_reject_total")
    suffix = f"_{tx_type.lower()}" if tx_type else ""
    metrics_registry.increment(f"v9_would_reject_{reason}{suffix}_total")
