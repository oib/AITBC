"""Lightweight SDK request/response shared types (v0.16.2 §A1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass
class SDKRequest:
    """Base SDK request envelope."""

    method: str = ""
    path: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    body: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class SDKResponse:
    """Base SDK response envelope."""

    status: int = 200
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class WalletBalance:
    """Wallet balance snapshot."""

    wallet_id: str = ""
    address: str = ""
    balance: Decimal = Decimal("0")
    asset: str = ""


@dataclass
class RegistryEntry:
    """Generic registry entry (developer, provider, agent, etc.)."""

    id: str = ""
    name: str = ""
    wallet_address: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class GrantSummary:
    """Summary of a grant proposal for SDK clients."""

    grant_id: str = ""
    title: str = ""
    status: str = ""
    requested_amount: Decimal = Decimal("0")
    approved_amount: Decimal = Decimal("0")
