"""PBFT observability for #2194 (quorum ``have=2`` with one validator down).

Purely additive: nothing here changes a vote, a quorum count or a wire message.

* ``pbft_intake_drop_total`` / ``pbft_intake_drop_<reason>_total`` — always on, one
  counter increment per message the intake drops silently.
* ``describe_quorum_gap`` — always on, used by the quorum-timeout warning to name who
  voted, who did not, and when each present vote arrived.
* ``PBFT-TRACE`` log lines — gated by ``pbft_vote_trace_enabled`` (default OFF);
  flag-off emits nothing.
"""

from __future__ import annotations

import time
from typing import Any

from aitbc.crypto.signature_recovery import canonical_address

from ..config import settings
from ..metrics import metrics_registry
from .pbft import logger


def trace_enabled() -> bool:
    return bool(getattr(settings, "pbft_vote_trace_enabled", False))


def trace(event: str, **fields: Any) -> None:
    """Emit one ``PBFT-TRACE`` line (no-op while the flag is off)."""
    if not trace_enabled():
        return
    body = " ".join(f"{k}={v}" for k, v in fields.items())
    logger.info("PBFT-TRACE %s %s ts=%.3f", event, body, time.time())


def _short(addr: Any) -> str:
    text = str(addr)
    return text[:10] if len(text) > 10 else text


def intake_drop(reason: str, message: Any = None, **extra: Any) -> None:
    """Count (always) and trace (flag) a message the intake dropped."""
    metrics_registry.increment("pbft_intake_drop_total")
    metrics_registry.increment(f"pbft_intake_drop_{reason}_total")
    if not trace_enabled():
        return
    fields: dict[str, Any] = {"reason": reason}
    if message is not None:
        mtype = getattr(getattr(message, "message_type", None), "value", None)
        if mtype is None and isinstance(message, dict):
            mtype = message.get("message_type")
            sender = message.get("sender")
            seq = message.get("sequence_number")
            view = message.get("view_number")
        else:
            sender = getattr(message, "sender", None)
            seq = getattr(message, "sequence_number", None)
            view = getattr(message, "view_number", None)
        fields.update(type=mtype, hr=f"{seq}:{view}", sender=_short(sender))
    fields.update(extra)
    trace("drop", **fields)


def stamp_rx(message: Any) -> None:
    """Record the local receive time on an incoming message (for lag figures)."""
    try:
        message._rx_ts = time.time()
    except AttributeError:  # slotted/frozen message: lag simply unavailable
        pass


def accepted(message: Any) -> None:
    """Trace an accepted vote with its sender timestamp and receive lag."""
    if not trace_enabled():
        return
    rx = getattr(message, "_rx_ts", None)
    ts = getattr(message, "timestamp", None)
    lag = f"{rx - ts:.3f}" if rx is not None and isinstance(ts, (int, float)) and ts else "na"
    trace(
        "accept",
        type=getattr(message.message_type, "value", message.message_type),
        hr=f"{message.sequence_number}:{message.view_number}",
        sender=_short(message.sender),
        msg_ts=ts,
        rx_ts=rx,
        lag=lag,
    )


def describe_quorum_gap(participants: list[str], votes: list[Any]) -> str:
    """``voted=[..] missing=[..]`` with each present vote's receive lag."""
    voted: dict[str, Any] = {canonical_address(v.sender): v for v in votes}
    parts = []
    for sender, vote in voted.items():
        rx = getattr(vote, "_rx_ts", None)
        ts = getattr(vote, "timestamp", None)
        lag = f"{rx - ts:.2f}s" if rx is not None and isinstance(ts, (int, float)) and ts else "na"
        parts.append(f"{_short(sender)}(lag={lag})")
    missing = [_short(a) for a in participants if canonical_address(a) not in voted]
    return f"voted=[{', '.join(parts)}] missing=[{', '.join(missing)}]"
