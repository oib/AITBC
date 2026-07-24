"""Marketplace protocols for white-label resource discovery and pricing."""

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any


class IPricingAPI(ABC):
    """Protocol for dynamic, brand-agnostic compute pricing."""

    @abstractmethod
    async def get_price(self, resource_type: str, duration_seconds: int) -> Decimal:
        """Return the current price for the requested resource and duration."""
        ...

    @abstractmethod
    async def submit_bid(
        self,
        consumer_id: str,
        max_price: Decimal,
        constraints: dict[str, Any],
    ) -> str:
        """Submit a consumer bid and return a bid identifier."""
        ...


class IResourceDiscovery(ABC):
    """Protocol for discovering compute, storage, and agent resources."""

    @abstractmethod
    async def list_resources(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Return resources matching the optional filters."""
        ...

    @abstractmethod
    async def register_resource(self, provider_id: str, resource_spec: dict[str, Any]) -> str:
        """Register a provider resource and return a resource identifier."""
        ...
