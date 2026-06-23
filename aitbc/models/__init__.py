"""Shared models for AITBC applications.

Moved from hermes_service.storage in v0.5.9 §1.
"""

from .coin_request import Base, CoinRequest, CoinRequestStatus

__all__ = ["Base", "CoinRequest", "CoinRequestStatus"]
