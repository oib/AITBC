"""High-level coordinator-api, wallet, and registry clients (v0.16.2 §A2)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from aitbc.exceptions import NetworkError, RateLimitError
from aitbc.network import AITBCHTTPClient
from aitbc.types import GrantSummary, RegistryEntry, SDKResponse, WalletBalance

from .errors import AITBCConnectionError, AITBCRateLimitError, AITBCError


def _str(value: Any) -> str:
    """Safely coerce a response value to a string."""
    return "" if value is None else str(value)


def _decimal(value: Any) -> Decimal:
    """Safely coerce a response value to Decimal."""
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


class _BaseClient:
    """Shared HTTP helpers for SDK clients."""

    def __init__(self, http: AITBCHTTPClient) -> None:
        self._http = http

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            return self._http.get(path, params=params)
        except RateLimitError as exc:
            raise AITBCRateLimitError(str(exc)) from exc
        except NetworkError as exc:
            raise AITBCConnectionError(str(exc)) from exc

    def _post(
        self,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            return self._http.post(path, json=json, params=params)
        except RateLimitError as exc:
            raise AITBCRateLimitError(str(exc)) from exc
        except NetworkError as exc:
            raise AITBCConnectionError(str(exc)) from exc


class WalletClient(_BaseClient):
    """Client for coordinator-api wallet operations."""

    def get_balance(self, wallet_id: str) -> WalletBalance:
        """Fetch the balance for a wallet."""
        payload = self._get(f"/v1/wallets/{wallet_id}/balance")
        return WalletBalance(
            wallet_id=_str(payload.get("wallet_id") or payload.get("id")),
            address=_str(payload.get("address")),
            balance=_decimal(payload.get("balance")),
            asset=_str(payload.get("asset")),
        )

    def send_payment(
        self,
        wallet_id: str,
        recipient_id: str,
        amount: str,
        asset: str = "",
    ) -> dict[str, Any]:
        """Submit a payment request."""
        return self._post(
            f"/v1/wallets/{wallet_id}/payments",
            json={
                "recipient_id": recipient_id,
                "amount": amount,
                "asset": asset,
            },
        )


class RegistryClient(_BaseClient):
    """Client for coordinator-api developer/provider registry operations."""

    def get_developer(self, address: str) -> RegistryEntry:
        """Fetch a single registry entry."""
        payload = self._get(f"/v1/developers/{address}")
        return _to_registry_entry(payload)

    def list_registry(
        self,
        *,
        role: str | None = None,
        limit: int = 100,
        cursor: str | None = None,
    ) -> list[RegistryEntry]:
        """List registry entries (deprecated alias for ``list_registry``)."""
        params: dict[str, Any] = {"limit": limit}
        if role:
            params["role"] = role
        if cursor:
            params["cursor"] = cursor
        payload = self._get("/v1/registry", params=params)
        items = payload.get("items") if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            return []
        return [_to_registry_entry(item) for item in items if isinstance(item, dict)]

    def list_grants(self) -> list[GrantSummary]:
        """List grant proposals from the coordinator API."""
        payload = self._get("/v1/grants")
        items = payload.get("items") if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            raise AITBCError("unexpected grants response format")
        return [
            GrantSummary(
                grant_id=_str(item.get("grant_id") or item.get("id")),
                title=_str(item.get("title")),
                status=_str(item.get("status")),
                requested_amount=_decimal(item.get("requested_amount")),
                approved_amount=_decimal(item.get("approved_amount")),
            )
            for item in items
            if isinstance(item, dict)
        ]


def _to_registry_entry(payload: dict[str, Any]) -> RegistryEntry:
    """Convert a JSON payload into a ``RegistryEntry``."""
    return RegistryEntry(
        id=_str(payload.get("id") or payload.get("entry_id")),
        name=_str(payload.get("name")),
        wallet_address=_str(payload.get("wallet_address") or payload.get("address")),
        metadata=payload.get("metadata") or {},
    )


class CoordinatorAPIClient:
    """High-level client for the AITBC coordinator API."""

    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        http = AITBCHTTPClient(
            base_url=base_url,
            timeout=timeout,
            headers={"X-Api-Key": api_key} if api_key else {},
            max_retries=max_retries,
        )
        self.wallet = WalletClient(http)
        self.registry = RegistryClient(http)
        self._http = http

    def close(self) -> None:
        """Release the underlying HTTP connection pool.

        The client owns an AITBCHTTPClient and hands it to the wallet and registry
        sub-clients, but exposed no way to release it, so callers had no correct way to
        shut one down.
        """
        self._http.close()

    def __enter__(self) -> CoordinatorAPIClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def health(self) -> SDKResponse:
        """Check coordinator-api health."""
        try:
            data = self._http.get("/health")
            return SDKResponse(status=200, data=data)
        except Exception as exc:  # noqa: BLE001
            return SDKResponse(status=503, error=str(exc))

    def get_grant_summary(self, grant_id: str) -> GrantSummary:
        """Fetch a grant summary."""
        payload = self._http.get(f"/v1/grants/{grant_id}/summary")
        return GrantSummary(
            grant_id=_str(payload.get("grant_id") or payload.get("id")),
            title=_str(payload.get("title")),
            status=_str(payload.get("status")),
            requested_amount=_decimal(payload.get("requested_amount")),
            approved_amount=_decimal(payload.get("approved_amount")),
        )


# Canonical aliases used in the builder documentation.
AITBCClient = CoordinatorAPIClient
CoordinatorClient = CoordinatorAPIClient
