"""Shared kernel — value objects, enums, and DTOs shared across bounded contexts.

This package holds cross-context value objects (enums, DTOs) that are intentionally
shared. Domain entities (SQLModel tables) should NOT live here — each context owns
its own domain models. The verification grep explicitly excludes `shared_kernel`
from the cross-context domain-import check.
"""
