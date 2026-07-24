"""Brand-agnostic configuration for white-label agent ecosystems."""

from __future__ import annotations

import dataclasses
import os
from typing import Self

_DEFAULT_BRAND = {
    "name": "AITBC",
    "token_symbol": "AITBC",
    "token_name": "AITBC Token",
    "network_name": "AITBC Network",
    "dao_name": "OpenClaw DAO",
    "wallet_name": "AITBC Wallet",
    "explorer_name": "AITBC Explorer",
}


def _env(key: str, default: str, overrides: dict[str, str]) -> str:
    return overrides.get(key, os.getenv(key, default))


@dataclasses.dataclass(frozen=True, slots=True)
class BrandSettings:
    """Runtime brand configuration consumed by apps, CLI, and contracts."""

    name: str
    token_symbol: str
    token_name: str
    network_name: str
    dao_name: str
    wallet_name: str
    explorer_name: str

    @classmethod
    def default(cls) -> Self:
        """Factory brand configuration matching current AITBC defaults."""
        return cls(**_DEFAULT_BRAND)

    @classmethod
    def from_env(
        cls,
        prefix: str = "AITBC_BRAND",
        overrides: dict[str, str] | None = None,
    ) -> Self:
        """Build brand settings from environment variables.

        Variable format: ``{PREFIX}_{FIELD_NAME}``.  For example,
        ``AITBC_BRAND_NAME`` overrides ``name``.
        """
        overrides = overrides or {}
        return cls(
            name=_env(f"{prefix}_NAME", _DEFAULT_BRAND["name"], overrides),
            token_symbol=_env(f"{prefix}_TOKEN_SYMBOL", _DEFAULT_BRAND["token_symbol"], overrides),
            token_name=_env(f"{prefix}_TOKEN_NAME", _DEFAULT_BRAND["token_name"], overrides),
            network_name=_env(f"{prefix}_NETWORK_NAME", _DEFAULT_BRAND["network_name"], overrides),
            dao_name=_env(f"{prefix}_DAO_NAME", _DEFAULT_BRAND["dao_name"], overrides),
            wallet_name=_env(f"{prefix}_WALLET_NAME", _DEFAULT_BRAND["wallet_name"], overrides),
            explorer_name=_env(f"{prefix}_EXPLORER_NAME", _DEFAULT_BRAND["explorer_name"], overrides),
        )
