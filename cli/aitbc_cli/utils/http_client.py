"""Simple HTTP client wrapper for AITBC CLI (replaces missing aitbc package)"""

from typing import Any

import httpx


class NetworkError(Exception):
    """Network error for AITBC operations"""

    pass


class AITBCHTTPClient:
    """Simple HTTP client for AITBC blockchain RPC"""

    def __init__(self, base_url: str = "http://localhost:8202", timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.client = httpx.Client(timeout=timeout, follow_redirects=True)

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """GET request to blockchain RPC"""
        try:
            response = self.client.get(f"{self.base_url}{path}", params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            raise NetworkError(f"HTTP error: {e}") from e

    def post(
        self,
        path: str,
        json: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """POST request to blockchain RPC.

        Accepts the request body via either ``json`` (preferred, matches the
        httpx/aitbc.network convention used across the CLI commands) or the
        legacy ``json_data`` alias.
        """
        payload = json if json is not None else json_data
        try:
            response = self.client.post(f"{self.base_url}{path}", json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            raise NetworkError(f"HTTP error: {e}") from e

    def close(self):
        """Close the HTTP client"""
        self.client.close()


def get_logger(name: str):
    """Simple logger wrapper"""
    import logging

    return logging.getLogger(name)


# Constants
KEYSTORE_DIR = "/var/lib/aitbc/keystore"
