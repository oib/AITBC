"""v24 state-transition rules gate (#1314).

Zero-dependency module so both ``database`` (session layer) and
``state.state_transition`` (apply layer) can share the activation context
without circular imports. The context is set only while applying blocks at
``block_version >= 24``; everywhere else v24 primitives behave exactly as if
they did not exist.
"""

from __future__ import annotations

import contextvars
from collections.abc import Generator
from contextlib import contextmanager

_v24_rules_active: contextvars.ContextVar[bool] = contextvars.ContextVar("aitbc_v24_rules_active", default=False)


@contextmanager
def v24_rules_active() -> Generator[None]:
    """Mark the current context as applying state-transition v24 rules."""
    token = _v24_rules_active.set(True)
    try:
        yield
    finally:
        _v24_rules_active.reset(token)


def v24_rules_is_active() -> bool:
    return _v24_rules_active.get()
