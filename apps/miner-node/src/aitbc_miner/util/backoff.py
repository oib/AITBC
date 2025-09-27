from __future__ import annotations

import asyncio
import random


def compute_backoff(base: float, factor: float, jitter_pct: float, max_seconds: float) -> float:
    backoff = min(base * factor, max_seconds)
    jitter = backoff * (jitter_pct / 100.0)
    return max(0.0, random.uniform(backoff - jitter, backoff + jitter))


def next_backoff(current: float, factor: float, jitter_pct: float, max_seconds: float) -> float:
    return compute_backoff(current, factor, jitter_pct, max_seconds)


async def sleep_with_backoff(delay: float, factor: float, jitter_pct: float, max_seconds: float) -> float:
    await asyncio.sleep(delay)
    return next_backoff(delay, factor, jitter_pct, max_seconds)
