"""Authentication and credential compatibility for the AITBC CLI."""

from __future__ import annotations

import os
from typing import Dict, Optional

from ..utils import error, success, warning

_CREDENTIAL_STORE: dict[tuple[str, str], str] = {}


class AuthManager:
    """Lightweight credential manager used by the compatibility CLI surface."""

    SERVICE_NAME = "aitbc-cli"

    def __init__(self):
        self._store = _CREDENTIAL_STORE

    def store_credential(self, name: str, api_key: str, environment: str = "default"):
        key = (environment, name)
        self._store[key] = api_key
        success(f"Credential '{name}' stored for environment '{environment}'")

    def get_credential(self, name: str, environment: str = "default") -> Optional[str]:
        key = (environment, name)
        value = self._store.get(key)
        if value is None:
            warning(f"No stored credential found for '{name}' in '{environment}'")
        return value

    def delete_credential(self, name: str, environment: str = "default"):
        key = (environment, name)
        if key in self._store:
            del self._store[key]
            success(f"Credential '{name}' deleted for environment '{environment}'")
        else:
            warning(f"Credential '{name}' not found for environment '{environment}'")

    def list_credentials(self, environment: str = None) -> Dict[str, str]:
        envs = [environment] if environment else ["default", "dev", "staging", "prod"]
        names = ["client", "miner", "admin"]
        credentials = []

        for env in envs:
            for name in names:
                if self._store.get((env, name)):
                    credentials.append(f"{name}@{env}")

        return credentials

    def store_env_credential(self, name: str):
        env_var = f"{name.upper()}_API_KEY"
        api_key = os.getenv(env_var)
        if not api_key:
            error(f"Environment variable {env_var} not set")
            return False

        self.store_credential(name, api_key)
        return True


__all__ = ["AuthManager"]
