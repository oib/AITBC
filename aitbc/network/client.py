"""Canonical HTTP client for AITBC services."""

import json
from typing import Any

import requests

from ..exceptions import NetworkError


class AITBCHTTPClient:
    """Simple HTTP client that speaks JSON to AITBC services."""

    def __init__(self, base_url: str, timeout: int = 30, headers: dict[str, str] | None = None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.headers = headers or {}

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    def _merge_headers(self, extra: dict[str, str] | None) -> dict[str, str]:
        merged = dict(self.headers)
        if extra:
            merged.update(extra)
        return merged

    def get(self, path: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> Any:
        try:
            resp = requests.get(
                self._url(path),
                params=params,
                headers=self._merge_headers(headers),
                timeout=self.timeout,
            )
            resp.raise_for_status()
            if resp.text:
                return resp.json()
            return {}
        except requests.RequestException as exc:
            raise NetworkError(str(exc)) from exc
        except json.JSONDecodeError as exc:
            raise NetworkError(f"Invalid JSON from {path}: {exc}") from exc

    def post(self, path: str, json: Any | None = None, headers: dict[str, str] | None = None) -> Any:
        try:
            resp = requests.post(
                self._url(path),
                json=json,
                headers=self._merge_headers(headers),
                timeout=self.timeout,
            )
            resp.raise_for_status()
            if resp.text:
                return resp.json()
            return {}
        except requests.RequestException as exc:
            raise NetworkError(str(exc)) from exc
        except json.JSONDecodeError as exc:
            raise NetworkError(f"Invalid JSON from {path}: {exc}") from exc

    def put(self, path: str, json: Any | None = None, headers: dict[str, str] | None = None) -> Any:
        try:
            resp = requests.put(
                self._url(path),
                json=json,
                headers=self._merge_headers(headers),
                timeout=self.timeout,
            )
            resp.raise_for_status()
            if resp.text:
                return resp.json()
            return {}
        except requests.RequestException as exc:
            raise NetworkError(str(exc)) from exc
        except json.JSONDecodeError as exc:
            raise NetworkError(f"Invalid JSON from {path}: {exc}") from exc

    def delete(self, path: str, headers: dict[str, str] | None = None) -> Any:
        try:
            resp = requests.delete(
                self._url(path),
                headers=self._merge_headers(headers),
                timeout=self.timeout,
            )
            resp.raise_for_status()
            if resp.text:
                return resp.json()
            return {}
        except requests.RequestException as exc:
            raise NetworkError(str(exc)) from exc
        except json.JSONDecodeError as exc:
            raise NetworkError(f"Invalid JSON from {path}: {exc}") from exc
