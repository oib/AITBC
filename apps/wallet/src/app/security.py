from __future__ import annotations

import re

from aitbc.security.rate_limiter import RateLimiter  # noqa: F401 — re-export for backward compat


def validate_password_rules(password: str) -> None:
    if len(password) < 12:
        raise ValueError("password must be at least 12 characters long")
    if not re.search(r"[A-Z]", password):
        raise ValueError("password must include at least one uppercase letter")
    if not re.search(r"[a-z]", password):
        raise ValueError("password must include at least one lowercase letter")
    if not re.search(r"\d", password):
        raise ValueError("password must include at least one digit")
    if not re.search(r"[^A-Za-z0-9]", password):
        raise ValueError("password must include at least one symbol")


def wipe_buffer(buffer: bytearray) -> None:
    for index in range(len(buffer)):
        buffer[index] = 0
