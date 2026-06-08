"""Simple HTTP client wrapper for AITBC CLI (replaces missing aitbc package)"""

import httpx
from typing import Any, Dict, Optional


class NetworkError(Exception):
    """Network error for AITBC operations"""
    pass


class AITBCHTTPClient:
    """Simple HTTP client for AITBC blockchain RPC"""
    
    def __init__(self, base_url: str = "http://localhost:8202", timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.client = httpx.Client(timeout=timeout)
    
    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """GET request to blockchain RPC"""
        try:
            response = self.client.get(f"{self.base_url}{path}", params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            raise NetworkError(f"HTTP error: {e}")
    
    def post(self, path: str, json_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """POST request to blockchain RPC"""
        try:
            response = self.client.post(f"{self.base_url}{path}", json=json_data)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            raise NetworkError(f"HTTP error: {e}")
    
    def close(self):
        """Close the HTTP client"""
        self.client.close()


def get_logger(name: str):
    """Simple logger wrapper"""
    import logging
    return logging.getLogger(name)


# Constants
KEYSTORE_DIR = "/var/lib/aitbc/keystore"
