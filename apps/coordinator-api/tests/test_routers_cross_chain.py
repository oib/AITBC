"""Router tests for /v1/cross-chain/* (#1289 round 9 batch 6).

cross_chain_integration — AuthDep/AdminDep gated, real sqlite session,
SecureWalletService + chain adapters. Wallet creation needs
settings.wallet_encryption_password; chain calls resolve RPC URLs from
NetworkConfig and degrade honestly when absent. Covers auth floors,
validation, health/config/chain reads, and wallet ownership binding.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from aitbc.auth import create_access_token
from coordinator_api.contexts.cross_chain.domain.cross_chain_bridge import BridgeRequestStatus
from coordinator_api.contexts.cross_chain.routers import cross_chain_integration
from coordinator_api.contexts.cross_chain.services.cross_chain.bridge_client_adapter import (
    BridgeClientAdapter,
    BridgeHTLCRetired,
    BridgeProtocolRequired,
)
from coordinator_api.contexts.cross_chain.services.cross_chain.bridge_types import BridgeProtocol

BASE = "/v1/cross-chain"


def _headers(sub: str = "agent-1", role: str = "client") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(sub, role)}"}


class TestCrossChainAuth:
    def test_requires_auth(self, client: TestClient) -> None:
        # /health is public; gated endpoints require AuthDep
        assert client.get(f"{BASE}/health").status_code == 200
        assert client.post(
            f"{BASE}/wallets/create",
            params={"owner_address": "0x" + "22" * 20, "chain_id": 1, "security_config": {}},
            headers={"Authorization": "Bearer invalid"},
        ).status_code in (401, 403)
        assert client.get(f"{BASE}/wallets/0x{'11' * 20}/balance").status_code == 401

    def test_any_authenticated_role(self, client: TestClient) -> None:
        for role in ("client", "miner", "admin"):
            resp = client.get(f"{BASE}/health", headers=_headers("u", role))
            assert resp.status_code == 200, role


class TestCrossChainReads:
    def test_health_shape(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/health", headers=_headers())
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, dict)

    def test_config_shape(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/config", headers=_headers())
        assert resp.status_code == 200
        protocols = resp.json()["bridge_protocols"]
        assert "htlc" not in protocols
        assert "atomic_swap" in protocols
        assert "liquidity_pool" in protocols

    def test_supported_chains_empty_or_list(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/chains/supported", headers=_headers())
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_chain_info_unknown_404_or_error(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/chains/999999/info", headers=_headers())
        assert resp.status_code in (200, 400, 404, 503)

    def test_bridge_statistics_shape(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/bridge/statistics", headers=_headers())
        assert resp.status_code in (200, 503)

    def test_bridge_whitelist_shape(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/bridge/whitelist", headers=_headers())
        assert resp.status_code in (200, 503)


class TestWalletOwnership:
    def test_balance_unknown_wallet_404_or_403(self, client: TestClient) -> None:
        # _require_agent_wallet binds wallet_address to the caller's agent wallets
        resp = client.get(f"{BASE}/wallets/0x{'11' * 20}/balance", params={"chain_id": 1}, headers=_headers())
        assert resp.status_code in (403, 404)

    def test_verify_signature_validation(self, client: TestClient) -> None:
        resp = client.post(
            f"{BASE}/wallets/verify-signature",
            json={"message": "hello", "signature": "0x", "address": "0x" + "11" * 20},
            headers=_headers(),
        )
        # malformed signature must not verify — 200 with valid:false or a 4xx
        if resp.status_code == 200:
            assert resp.json().get("valid") is not True
        else:
            assert resp.status_code in (400, 422)

    def test_create_wallet_requires_encryption_config(self, client: TestClient) -> None:
        resp = client.post(
            f"{BASE}/wallets/create",
            params={"owner_address": "0x" + "22" * 20, "chain_id": 1, "security_config": {}},
            headers=_headers(),
        )
        # without WALLETS_ENCRYPTION_PASSWORD configured this is an honest 400;
        # with it configured the service may succeed — accept both, reject 500
        assert resp.status_code in (200, 400, 422, 503)


class _FakeTxManager:
    """Stand-in for ChainTransactionManager recording the history kwargs."""

    result: list[dict] = []
    error: Exception | None = None
    calls: list[dict] = []

    def __init__(self, session: object) -> None:
        pass

    async def initialize(self, chain_configs: dict) -> None:
        pass

    async def get_transaction_history(self, **kwargs: object) -> list[dict]:
        type(self).calls.append(kwargs)
        if type(self).error is not None:
            raise type(self).error
        return list(type(self).result)


@pytest.fixture
def fake_tx_manager(monkeypatch: pytest.MonkeyPatch) -> type[_FakeTxManager]:
    from coordinator_api.contexts.cross_chain.routers import cross_chain_integration

    _FakeTxManager.result = []
    _FakeTxManager.error = None
    _FakeTxManager.calls = []
    monkeypatch.setattr(cross_chain_integration, "ChainTransactionManager", _FakeTxManager)
    return _FakeTxManager


class TestTransactionHistory:
    """#2708 — no fabricated rows, caller-bound user_id, honest 502."""

    def test_requires_auth(self, client: TestClient) -> None:
        assert client.get(f"{BASE}/transactions/history").status_code in (401, 403)

    def test_empty_history_returns_empty_list(self, client: TestClient, fake_tx_manager: type[_FakeTxManager]) -> None:
        resp = client.get(f"{BASE}/transactions/history", headers=_headers())
        assert resp.status_code == 200
        assert resp.json() == []

    def test_non_admin_user_id_bound_to_caller(self, client: TestClient, fake_tx_manager: type[_FakeTxManager]) -> None:
        resp = client.get(f"{BASE}/transactions/history", headers=_headers("agent-1"))
        assert resp.status_code == 200
        assert fake_tx_manager.calls[-1]["user_id"] == "agent-1"

    def test_foreign_user_id_rejected_for_client(self, client: TestClient, fake_tx_manager: type[_FakeTxManager]) -> None:
        resp = client.get(
            f"{BASE}/transactions/history",
            params={"user_id": "victim-9"},
            headers=_headers("agent-1"),
        )
        assert resp.status_code == 403
        assert fake_tx_manager.calls == []

    def test_admin_may_read_other_user(self, client: TestClient, fake_tx_manager: type[_FakeTxManager]) -> None:
        resp = client.get(
            f"{BASE}/transactions/history",
            params={"user_id": "victim-9"},
            headers=_headers("root", "admin"),
        )
        assert resp.status_code == 200
        assert fake_tx_manager.calls[-1]["user_id"] == "victim-9"

    def test_backend_error_is_502_not_fixtures(self, client: TestClient, fake_tx_manager: type[_FakeTxManager]) -> None:
        fake_tx_manager.error = RuntimeError("db gone")
        resp = client.get(f"{BASE}/transactions/history", headers=_headers())
        assert resp.status_code == 502


class TestBridgeHTLCRetirement:
    """#2761 — HTLC bridge protocol retired.

    Explicit HTLC requests are refused with HTTP 410 before the adapter is
    constructed; a configured HTLC default requires an explicit supported
    protocol (HTTP 400); historical HTLC rows are skipped by dispatch but
    remain readable.
    """

    _CREATE_PARAMS = {
        "user_address": "0x" + "11" * 20,
        "source_chain_id": 1,
        "target_chain_id": 2,
        "amount": "100",
    }

    @staticmethod
    def _wallet() -> Any:
        wallet = MagicMock()
        wallet.validate_address = AsyncMock(return_value=True)
        return wallet

    @staticmethod
    def _protocol_config(protocol: BridgeProtocol) -> dict[str, Any]:
        return {
            "1": {
                "protocol": protocol,
                "enabled": True,
                "min_amount": "0",
                "max_amount": "1000000",
                "fee_rate": "0.01",
                "confirmation_blocks": 1,
            }
        }

    def _adapter(self, session: Any, protocol: BridgeProtocol) -> BridgeClientAdapter:
        adapter = BridgeClientAdapter(session=session)
        adapter.configure_allowed_transfers([(1, 2)])
        adapter.wallet_adapters[1] = self._wallet()
        adapter.wallet_adapters[2] = self._wallet()
        adapter.bridge_protocols = self._protocol_config(protocol)
        return adapter

    def test_explicit_htlc_is_410_before_adapter(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[object] = []

        def spy(*args: object, **kwargs: object) -> None:
            calls.append((args, kwargs))
            raise AssertionError("BridgeClientAdapter must not be constructed for retired HTLC")

        monkeypatch.setattr(cross_chain_integration, "BridgeClientAdapter", spy)
        resp = client.post(
            f"{BASE}/bridge/create-request",
            params={**self._CREATE_PARAMS, "protocol": "htlc"},
            headers=_headers(),
        )
        assert resp.status_code == 410
        assert resp.json()["detail"]["code"] == "htlc_retired"
        assert calls == []

    def test_configured_htlc_default_is_400(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        adapter = MagicMock()
        adapter.initialize_bridge = AsyncMock()
        adapter.create_bridge_request = AsyncMock(
            side_effect=BridgeProtocolRequired(
                "The configured HTLC default is retired; supply a supported protocol explicitly."
            )
        )
        monkeypatch.setattr(cross_chain_integration, "BridgeClientAdapter", MagicMock(return_value=adapter))
        resp = client.post(
            f"{BASE}/bridge/create-request",
            params=self._CREATE_PARAMS,
            headers=_headers(),
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "protocol_required"
        adapter.create_bridge_request.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_configured_htlc_default_rejected_without_session_or_wallet_work(self) -> None:
        session = MagicMock()
        adapter = self._adapter(session, BridgeProtocol.HTLC)

        with pytest.raises(BridgeProtocolRequired):
            await adapter.create_bridge_request(
                user_address="0x" + "11" * 20,
                source_chain_id=1,
                target_chain_id=2,
                amount=Decimal("100"),
            )

        session.add.assert_not_called()
        session.commit.assert_not_called()
        session.rollback.assert_not_called()
        adapter.wallet_adapters[1].validate_address.assert_not_awaited()
        adapter.wallet_adapters[2].validate_address.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_explicit_htlc_rejected_before_session_check(self) -> None:
        adapter = BridgeClientAdapter(session=None)

        with pytest.raises(BridgeHTLCRetired):
            await adapter.create_bridge_request(
                user_address="0x" + "11" * 20,
                source_chain_id=1,
                target_chain_id=2,
                amount=Decimal("100"),
                protocol=BridgeProtocol.HTLC,
            )

    @pytest.mark.asyncio
    async def test_supported_default_protocol_still_creates_request(self, monkeypatch: pytest.MonkeyPatch) -> None:
        session = MagicMock()
        adapter = self._adapter(session, BridgeProtocol.ATOMIC_SWAP)
        monkeypatch.setattr(adapter, "_estimate_network_fee", AsyncMock(return_value=Decimal("0.01")))
        dispatch = AsyncMock()
        monkeypatch.setattr(adapter, "_process_bridge_request", dispatch)

        result = await adapter.create_bridge_request(
            user_address="0x" + "11" * 20,
            source_chain_id=1,
            target_chain_id=2,
            amount=Decimal("100"),
        )

        session.add.assert_called_once()
        stored = session.add.call_args.args[0]
        assert stored.protocol == BridgeProtocol.ATOMIC_SWAP.value
        dispatch.assert_awaited_once()
        assert dispatch.await_args.args[0] == stored.id
        assert result["bridge_request_id"] == stored.id

    @pytest.mark.asyncio
    async def test_historical_htlc_request_skipped_by_dispatch_but_still_readable(self) -> None:
        session = MagicMock()
        stamp = datetime(2024, 1, 1, tzinfo=UTC)
        historical = SimpleNamespace(
            id="req-htlc-1",
            protocol=BridgeProtocol.HTLC.value,
            status=BridgeRequestStatus.PENDING,
            updated_at=stamp,
            lock_tx_hash=None,
            unlock_tx_hash=None,
            source_chain_id=1,
            target_chain_id=2,
            sender_address="0x" + "11" * 20,
            recipient_address="0x" + "11" * 20,
            amount=Decimal("100"),
            source_token="0x" + "0" * 40,
            target_token="0x" + "0" * 40,
            bridge_fee=Decimal("1"),
            total_amount=Decimal("101"),
            expires_at=stamp,
            created_at=stamp,
            completed_at=None,
        )
        session.execute.return_value.scalars.return_value.first.return_value = historical
        adapter = BridgeClientAdapter(session=session)

        await adapter._process_bridge_request("req-htlc-1")

        session.commit.assert_not_called()
        assert historical.status == BridgeRequestStatus.PENDING
        assert historical.updated_at == stamp

        status = await adapter.get_bridge_request_status("req-htlc-1")
        assert status["bridge_request_id"] == "req-htlc-1"
        assert status["protocol"] == "htlc"
        assert status["status"] == BridgeRequestStatus.PENDING.value
