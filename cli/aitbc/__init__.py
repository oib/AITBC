"""Minimal aitbc package for CLI compatibility"""

from typing import Any

import requests


class NetworkError(Exception):
    """Network error for AITBC operations"""

    pass


class ValidationError(Exception):
    """Validation error for AITBC operations"""

    pass


class AITBCHTTPClient:
    """Simple HTTP client for AITBC blockchain RPC"""

    def __init__(self, base_url: str = "http://localhost:8202", timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.client = requests.Session()

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """GET request to blockchain RPC"""
        try:
            response = self.client.get(f"{self.base_url}{path}", params=params, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise NetworkError(f"HTTP error: {e}") from e

    def post(self, path: str, json_data: dict[str, Any] | None = None) -> dict[str, Any]:
        """POST request to blockchain RPC"""
        try:
            response = self.client.post(f"{self.base_url}{path}", json=json_data, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise NetworkError(f"HTTP error: {e}") from e

    def close(self):
        """Close the HTTP client"""
        self.client.close()


def get_logger(name: str):
    """Simple logger wrapper"""
    import logging

    return logging.getLogger(name)


# Constants
BLOCKCHAIN_RPC_PORT = 8202
KEYSTORE_DIR = "/var/lib/aitbc/keystore"


class BaseAITBCConfig:
    """Base configuration class"""

    pass
