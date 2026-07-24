"""Pluggable yield-venue adapter registry for Agent B v0.13.0 B3."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import ClassVar


class YieldVenue(StrEnum):
    """Supported yield-venue categories."""

    STAKING = "staking"
    LIQUIDITY = "liquidity"
    LENDING = "lending"
    RESTAKING = "restaking"


@dataclass
class YieldPosition:
    """Simple yield position snapshot used by adapters."""

    venue: YieldVenue | str
    agent_id: str
    chain_id: str = "ait-hub"
    token: str = "AITBC"
    principal: Decimal = field(default_factory=lambda: Decimal("0"))
    rewards: Decimal = field(default_factory=lambda: Decimal("0"))

    def __post_init__(self) -> None:
        if isinstance(self.venue, str):
            self.venue = YieldVenue(self.venue)
        if self.principal < 0:
            raise ValueError("principal cannot be negative")
        if self.rewards < 0:
            raise ValueError("rewards cannot be negative")


class YieldAdapter(ABC):
    """Abstract base for yield-venue integrations."""

    name: ClassVar[str] = ""

    @abstractmethod
    def harvest(self, position: YieldPosition) -> Decimal:
        """Harvest available rewards and return the amount harvested."""
        ...

    @abstractmethod
    def estimate_apy(self, position: YieldPosition) -> Decimal:
        """Return the current estimated APY as a percent (0-100)."""
        ...


class _YieldRegistry:
    """In-memory registry of yield adapters."""

    def __init__(self) -> None:
        self._adapters: dict[str, type[YieldAdapter]] = {}

    def register(self, adapter_cls: type[YieldAdapter]) -> type[YieldAdapter]:
        """Register an adapter class by its ``name``."""
        if not adapter_cls.name:
            raise ValueError("adapter must define a name")
        self._adapters[adapter_cls.name] = adapter_cls
        return adapter_cls

    def get(self, name: str) -> type[YieldAdapter]:
        try:
            return self._adapters[name]
        except KeyError as exc:
            raise ValueError(f"unknown yield adapter {name}") from exc

    def list_adapters(self) -> list[str]:
        """Return names of registered adapters."""
        return list(self._adapters.keys())


yield_registry = _YieldRegistry()


class DemoStakingAdapter(YieldAdapter):
    """Demo staking adapter that compounds at a fixed APY."""

    name = "demo_staking"

    def __init__(self, apy: Decimal = Decimal("10")) -> None:
        if not (Decimal("0") <= apy <= Decimal("100")):
            raise ValueError("apy must be between 0 and 100")
        self.apy = apy

    def harvest(self, position: YieldPosition) -> Decimal:
        harvested = position.rewards
        position.rewards = Decimal("0")
        position.principal += harvested
        return harvested

    def estimate_apy(self, position: YieldPosition) -> Decimal:
        return self.apy


yield_registry.register(DemoStakingAdapter)


def register_adapter(adapter_cls: type[YieldAdapter]) -> type[YieldAdapter]:
    """Decorator/functional registration helper."""
    return yield_registry.register(adapter_cls)
