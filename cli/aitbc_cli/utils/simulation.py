"""Deterministic helpers for CLI simulated fallbacks and simulation commands."""

from __future__ import annotations

import hashlib
import random
import time as _time
from datetime import datetime
from typing import Any, Protocol

DEFAULT_SIMULATION_SEED = 42
DEFAULT_SIMULATION_EPOCH = "2026-01-01T00:00:00+00:00"


def simulated_timestamp() -> str:
    """Return a fixed, deterministic timestamp for simulated output."""
    return DEFAULT_SIMULATION_EPOCH


def simulated_id(prefix: str, *parts: Any) -> str:
    """Return a deterministic identifier derived from ``prefix`` and ``parts``."""
    content = ":".join(str(p) for p in (prefix, *parts))
    digest = hashlib.sha256(content.encode()).hexdigest()
    return f"{prefix}_{digest[:16]}"


class _RNG(Protocol):
    """Common interface for live and simulated random sources."""

    def now(self) -> float: ...
    def sleep(self, seconds: float) -> None: ...
    def advance(self, step: float = 1.0) -> float: ...
    def getrandbits(self, k: int) -> int: ...
    def uniform(self, a: float, b: float) -> float: ...
    def randint(self, a: int, b: int) -> int: ...
    def choice(self, seq: list[Any]) -> Any: ...
    def sample(self, population: list[Any], k: int) -> list[Any]: ...
    def random(self) -> float: ...


class SimulatedRNG:
    """Deterministic random source and clock for reproducible simulations."""

    __slots__ = ("_rng", "_epoch", "_clock")

    def __init__(self, seed: int = DEFAULT_SIMULATION_SEED) -> None:
        self._rng = random.Random(seed)
        self._epoch = int(datetime.fromisoformat(DEFAULT_SIMULATION_EPOCH).timestamp())
        self._clock = float(self._epoch)

    def now(self) -> float:
        """Return the current simulated wall-clock time."""
        return self._clock

    def sleep(self, seconds: float) -> None:
        """No-op real-time sleep for deterministic runs."""
        # Deterministic simulations run as fast as possible; the clock is
        # advanced only through ``advance()`` so timestamps are reproducible.

    def advance(self, step: float = 1.0) -> float:
        """Advance the clock and return the new time."""
        self._clock += step
        return self._clock

    def getrandbits(self, k: int) -> int:
        return self._rng.getrandbits(k)

    def uniform(self, a: float, b: float) -> float:
        return self._rng.uniform(a, b)

    def randint(self, a: int, b: int) -> int:
        return self._rng.randint(a, b)

    def choice(self, seq: list[Any]) -> Any:
        return self._rng.choice(seq)

    def sample(self, population: list[Any], k: int) -> list[Any]:
        return self._rng.sample(population, k)

    def random(self) -> float:
        return self._rng.random()


class LiveRNG:
    """Live random source and clock for non-deterministic simulations."""

    __slots__ = ("_clock",)

    def __init__(self) -> None:
        self._clock = _time.time()

    def now(self) -> float:
        return self._clock

    def sleep(self, seconds: float) -> None:
        """Sleep in real time without changing the simulation clock."""
        _time.sleep(max(float(seconds), 0.0))

    def advance(self, step: float = 1.0) -> float:
        self._clock += step
        return self._clock

    def getrandbits(self, k: int) -> int:
        return random.getrandbits(k)

    def uniform(self, a: float, b: float) -> float:
        return random.uniform(a, b)

    def randint(self, a: int, b: int) -> int:
        return random.randint(a, b)

    def choice(self, seq: list[Any]) -> Any:
        return random.choice(seq)

    def sample(self, population: list[Any], k: int) -> list[Any]:
        return random.sample(population, k)

    def random(self) -> float:
        return random.random()


def make_rng(seed: int | None = DEFAULT_SIMULATION_SEED) -> tuple[_RNG, bool]:
    """Return an RNG and a flag for whether real sleeps should run.

    ``seed is None`` selects a live (non-deterministic) simulation.
    A concrete integer seed selects a deterministic, wall-clock-free simulation.
    """
    if seed is None:
        return LiveRNG(), True
    return SimulatedRNG(seed), False
