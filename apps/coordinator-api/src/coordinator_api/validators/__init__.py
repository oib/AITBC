"""Shared validators for Pydantic models."""

import re
from typing import Any
from pydantic import field_validator


# Ethereum address validator pattern
ETH_ADDRESS_PATTERN = re.compile(r"^0x[a-fA-F0-9]{40}$")

# Email validator pattern
EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

# URL validator pattern
URL_PATTERN = re.compile(r"^https?://[^\s/$.?#].[^\s]*$")

# Agent ID pattern (alphanumeric with hyphens and underscores)
AGENT_ID_PATTERN = re.compile(r"^[a-zA-Z0-9\-_]{1,128}$")


def validate_ethereum_address(v: str) -> str:
    """Validate Ethereum address format (0x followed by 40 hex chars)."""
    if not ETH_ADDRESS_PATTERN.match(v):
        raise ValueError("Invalid Ethereum address format (must be 0x followed by 40 hex characters)")
    return v.lower()


def validate_email(v: str) -> str:
    """Validate email format."""
    if not EMAIL_PATTERN.match(v):
        raise ValueError("Invalid email format")
    return v.lower()


def validate_url(v: str | None) -> str | None:
    """Validate URL format."""
    if v is None:
        return v
    if not URL_PATTERN.match(v):
        raise ValueError("Invalid URL format (must start with http:// or https://)")
    return v


def validate_agent_id(v: str) -> str:
    """Validate agent ID format."""
    if not AGENT_ID_PATTERN.match(v):
        raise ValueError("Invalid agent ID format (alphanumeric with hyphens/underscores, max 128 chars)")
    return v


def validate_positive_amount(v: float | int) -> float:
    """Validate that amount is positive."""
    if v <= 0:
        raise ValueError("Amount must be positive")
    return float(v)


def validate_positive_decimal(v: float) -> float:
    """Validate that decimal amount is positive."""
    if v <= 0:
        raise ValueError("Amount must be positive")
    return v


class ValidatorMixin:
    """Mixin class to add common validators to models."""

    @field_validator("*", mode="before")
    @classmethod
    def strip_strings(cls, v: Any) -> Any:
        """Strip whitespace from string fields."""
        if isinstance(v, str):
            return v.strip()
        return v
