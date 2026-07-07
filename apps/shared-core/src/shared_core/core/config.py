"""Shared configuration base for all AITBC services.

Re-exports the canonical DatabaseConfig and ServiceSettings from aitbc_shared.
"""

from aitbc_shared import DatabaseConfig, ServiceSettings

__all__ = ["DatabaseConfig", "ServiceSettings"]
