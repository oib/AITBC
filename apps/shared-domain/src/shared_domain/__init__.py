"""Shared domain models for AITBC microservices.

This package re-exports the canonical domain types from ``aitbc`` so services do not
need to hand-roll their own copies of economic and identity primitives.
"""

from aitbc.agent_economics import (
    Budget,
    OnChainAction,
    OnChainActionType,
    RevenueRoute,
)

__all__ = [
    "Budget",
    "OnChainAction",
    "OnChainActionType",
    "RevenueRoute",
]
