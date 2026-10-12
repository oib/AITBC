"""v13 (V-2) governance-binding shadow metrics.

Mirrors ``v9_policy``: while the v13 binding rules sit behind the
unreachable ``state_transition_v13_height`` sentinel, every
GOVERNANCE_PROPOSE / GOVERNANCE_EXECUTE evaluated in admission or block
verification is also scored by the post-gate rule. A case the new rules
would refuse surfaces as a ``v13_would_reject_<reason>_total`` counter and
a warning log — an operator-visible signal, never a rejection — so the
24h-plus shadow window before arming proves the rules only fire on what
they were built for.

``v13_shadow_checked_total`` (plus the per-type series) is the positive
control: a clean window is provably ``checked > 0 AND would_reject == 0``
instead of relying on the absence of a lazily-created series.

Reason tokens encode the direction: ``propose_*`` for GOVERNANCE_PROPOSE,
``execute_*`` for GOVERNANCE_EXECUTE — no separate type suffix is needed on
the would-reject series.
"""

from __future__ import annotations

from ..metrics import metrics_registry

# The transaction types the v13 binding rules evaluate.
GOVERNANCE_BIND_TX_TYPES: tuple[str, ...] = ("GOVERNANCE_PROPOSE", "GOVERNANCE_EXECUTE")


def _type_suffix(tx_type: str) -> str:
    t = (tx_type or "").upper()
    return "_" + t.lower() if t in GOVERNANCE_BIND_TX_TYPES else ""


def count_v13_shadow_checked(tx_type: str) -> None:
    """Positive control: every v13 verdict evaluated counts, pass or fail."""
    metrics_registry.increment("v13_shadow_checked_total")
    suffix = _type_suffix(tx_type)
    if suffix:
        metrics_registry.increment(f"v13_shadow_checked{suffix}_total")


def count_v13_would_reject(reason: str) -> None:
    """Count a v13 shadow-reject (or, post-activation, a real reject).

    Emits the aggregate ``v13_would_reject_total`` plus the per-reason
    detail counter — the metrics registry has no label support, so the
    reason is encoded in the series name. No type suffix: every reason
    token already carries its direction (``propose_*`` / ``execute_*``).
    """
    metrics_registry.increment("v13_would_reject_total")
    metrics_registry.increment(f"v13_would_reject_{reason}_total")


# Pre-create the window-judgement series like metrics.py's alert counters:
# an eager 0 is evidence the check ran; an absent series is not.
for _series in ("v13_shadow_checked_total", "v13_would_reject_total"):
    metrics_registry.increment(_series, 0.0)
