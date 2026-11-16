"""#1998 H4: read-only diagnostics for a ``seen=0`` attestation collect.

The first collect of the 15 Nov bc-2 halt ended ``counted=0 seen=0`` although
the redis SUBSCRIBE was live before the request and responses were relayed. The
node journals could not say whether the responses reached the node at all. Two
cheap, bounded pieces of evidence close that gap without changing behaviour:

- the persistent ``attest_response`` observer counts every response it sees per
  height (an independent subscription on the same topic), and
- the collect's transient subscription exposes frame/item/error counters.

When a collect ends ``seen=0`` the collector logs both, so the next 0/0 reads as
"never reached the node", "reached the observer but not the collector" or
"subscription died" from one line.
"""

from __future__ import annotations

from collections import OrderedDict

_MAX_HEIGHTS = 256
_observer_counts: OrderedDict[int, int] = OrderedDict()


def note_observer_response(height: int) -> None:
    """Count one ``attest_response`` the observer subscription received for ``height``."""
    _observer_counts[height] = _observer_counts.get(height, 0) + 1
    _observer_counts.move_to_end(height)
    while len(_observer_counts) > _MAX_HEIGHTS:
        _observer_counts.popitem(last=False)


def observer_count(height: int) -> int:
    """Responses the observer has seen for ``height`` (0 when none or aged out)."""
    return _observer_counts.get(height, 0)


def reset() -> None:
    _observer_counts.clear()
