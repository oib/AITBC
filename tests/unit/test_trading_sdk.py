"""Unit tests for the aitbc.trading shared SDK (v0.8.0 §A4).

Covers:
- Trading types (InterChainTradeStatus, ChainStatus, TradingConfig,
  InterChainTradeData, ChainInfo, TradeMatchResult, TradeHistoryEntry,
  CreateTradeRequest, RegisterChainRequest)
- TradingClient init + async context manager + mocked REST methods
- TradingBridgeClient init + context manager + mocked BridgeClient methods

No real trading service or blockchain node required — all HTTP calls
are stubbed with AsyncMock.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx

from aitbc.trading import (
    ChainInfo,
    ChainStatus,
    CreateTradeRequest,
    InterChainTradeData,
    InterChainTradeStatus,
    RegisterChainRequest,
    TradeHistoryEntry,
    TradeMatchResult,
    TradingBridgeClient,
    TradingClient,
    TradingConfig,
)
from aitbc.trading.client import TradingClient as _TradingClient  # noqa: F401

RPC_URL = "http://localhost:8104"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _mock_response(
    status_code: int = 200,
    json_data: dict | list | None = None,
) -> MagicMock:
    """Create a mock httpx.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(f"HTTP {status_code}", request=MagicMock(), response=resp)
    return resp


def _sample_trade_data() -> InterChainTradeData:
    return InterChainTradeData(
        trade_id="trade_001",
        source_chain="ait-hub",
        dest_chain="ait-island1",
        sender="alice",
        recipient="bob",
        amount=1000,
        offer_id="sw_offer_001",
        price=0.02,
        quantity=500,
    )


def _sample_chain_info() -> ChainInfo:
    return ChainInfo(
        chain_id="ait-hub",
        endpoint="http://localhost:8202",
        status="active",
        block_height=12345,
        offers_count=42,
    )


# ---------------------------------------------------------------------------
# Types tests (A1)
# ---------------------------------------------------------------------------


class TestInterChainTradeStatus:
    def test_values(self) -> None:
        assert InterChainTradeStatus.PENDING.value == "pending"
        assert InterChainTradeStatus.MATCHED.value == "matched"
        assert InterChainTradeStatus.LOCKED.value == "locked"
        assert InterChainTradeStatus.CONFIRMED.value == "confirmed"
        assert InterChainTradeStatus.COMPLETED.value == "completed"
        assert InterChainTradeStatus.CANCELLED.value == "cancelled"
        assert InterChainTradeStatus.FAILED.value == "failed"

    def test_str_conversion(self) -> None:
        assert str(InterChainTradeStatus.PENDING) == "pending"


class TestChainStatus:
    def test_values(self) -> None:
        assert ChainStatus.ACTIVE.value == "active"
        assert ChainStatus.INACTIVE.value == "inactive"
        assert ChainStatus.SYNCING.value == "syncing"
        assert ChainStatus.DEGRADED.value == "degraded"


class TestTradingConfig:
    def test_defaults(self) -> None:
        cfg = TradingConfig()
        assert cfg.rpc_url == "http://localhost:8104"
        assert cfg.blockchain_rpc_url == "http://localhost:8202"
        assert cfg.bridge_rpc_url == "http://localhost:8202"
        assert cfg.chain_id == "ait-hub"
        assert cfg.matching_enabled is True
        assert cfg.execution_timeout == 300
        assert cfg.island_registry_sync_interval == 300
        assert cfg.timeout == 30

    def test_custom(self) -> None:
        cfg = TradingConfig(rpc_url="http://trade:9000", chain_id="ait-2")
        assert cfg.rpc_url == "http://trade:9000"
        assert cfg.chain_id == "ait-2"


class TestInterChainTradeData:
    def test_defaults(self) -> None:
        d = InterChainTradeData(
            trade_id="t1",
            source_chain="ait-hub",
            dest_chain="ait-2",
            sender="a",
            recipient="b",
            amount=100,
        )
        assert d.offer_id is None
        assert d.price == 0.0
        assert d.quantity == 0
        assert d.status == "pending"
        assert d.source_tx_hash is None
        assert d.dest_tx_hash is None
        assert d.chain_id == "ait-hub"

    def test_full(self) -> None:
        d = _sample_trade_data()
        assert d.trade_id == "trade_001"
        assert d.source_chain == "ait-hub"
        assert d.dest_chain == "ait-island1"
        assert d.amount == 1000
        assert d.offer_id == "sw_offer_001"
        assert d.price == 0.02


class TestChainInfo:
    def test_defaults(self) -> None:
        c = ChainInfo(chain_id="ait-hub", endpoint="http://localhost:8202")
        assert c.status == "active"
        assert c.block_height == 0
        assert c.offers_count == 0
        assert c.registered_at == ""
        assert c.last_sync == ""

    def test_full(self) -> None:
        c = _sample_chain_info()
        assert c.chain_id == "ait-hub"
        assert c.block_height == 12345
        assert c.offers_count == 42


class TestTradeMatchResult:
    def test_defaults(self) -> None:
        r = TradeMatchResult(trade_id="t1", matched=True)
        assert r.match_score == 0.0
        assert r.matched_chain == ""
        assert r.reason == ""

    def test_not_matched(self) -> None:
        r = TradeMatchResult(trade_id="t1", matched=False, reason="no offers")
        assert r.matched is False
        assert r.reason == "no offers"


class TestTradeHistoryEntry:
    def test_defaults(self) -> None:
        e = TradeHistoryEntry(trade_id="t1", source_chain="a", dest_chain="b", status="completed", amount=100)
        assert e.price == 0.0
        assert e.created_at == ""
        assert e.source_tx_hash is None


class TestCreateTradeRequest:
    def test_defaults(self) -> None:
        r = CreateTradeRequest(
            source_chain="ait-hub",
            dest_chain="ait-2",
            sender="a",
            recipient="b",
            amount=100,
        )
        assert r.offer_id is None
        assert r.price == 0.0
        assert r.quantity == 0
        assert r.chain_id == "ait-hub"


class TestRegisterChainRequest:
    def test_to_dict(self) -> None:
        r = RegisterChainRequest(chain_id="ait-2", endpoint="http://node2:8202")
        d = r.to_dict()
        assert d == {"chain_id": "ait-2", "endpoint": "http://node2:8202"}


# ---------------------------------------------------------------------------
# Client tests (A2)
# ---------------------------------------------------------------------------


class TestTradingClientInit:
    def test_default_config(self) -> None:
        c = TradingClient()
        assert c.config.rpc_url == "http://localhost:8104"
        assert c._client is None

    def test_custom_config(self) -> None:
        cfg = TradingConfig(rpc_url="http://custom:8000", timeout=10)
        c = TradingClient(cfg)
        assert c.config.rpc_url == "http://custom:8000"
        assert c.config.timeout == 10

    def test_config_property(self) -> None:
        c = TradingClient()
        assert isinstance(c.config, TradingConfig)


class TestTradingClientContextManager:
    async def test_aenter_creates_client(self) -> None:
        async with TradingClient() as c:
            assert c._client is not None
        assert c._client is None

    async def test_aexit_closes_client(self) -> None:
        c = TradingClient()
        await c.__aenter__()
        assert c._client is not None
        await c.__aexit__(None, None, None)
        assert c._client is None


class TestTradingClientMethods:
    async def test_create_trade(self) -> None:
        c = TradingClient()
        mock_resp = _mock_response(200, {"trade_id": "trade_001", "status": "pending"})
        c._client = MagicMock()
        c._client.post = AsyncMock(return_value=mock_resp)
        result = await c.create_trade({"source_chain": "ait-hub", "amount": 100})
        assert result["trade_id"] == "trade_001"
        c._client.post.assert_called_once()

    async def test_get_trade(self) -> None:
        c = TradingClient()
        mock_resp = _mock_response(200, {"trade_id": "trade_001", "status": "matched"})
        c._client = MagicMock()
        c._client.get = AsyncMock(return_value=mock_resp)
        result = await c.get_trade("trade_001")
        assert result["trade_id"] == "trade_001"

    async def test_list_trades_list_response(self) -> None:
        c = TradingClient()
        mock_resp = _mock_response(200, [{"trade_id": "t1"}, {"trade_id": "t2"}])
        c._client = MagicMock()
        c._client.get = AsyncMock(return_value=mock_resp)
        result = await c.list_trades()
        assert len(result) == 2

    async def test_list_trades_wrapped_response(self) -> None:
        c = TradingClient()
        mock_resp = _mock_response(200, {"trades": [{"trade_id": "t1"}]})
        c._client = MagicMock()
        c._client.get = AsyncMock(return_value=mock_resp)
        result = await c.list_trades(status="pending")
        assert len(result) == 1
        call_args = c._client.get.call_args
        assert call_args.kwargs["params"]["status"] == "pending"

    async def test_list_trades_empty_response(self) -> None:
        c = TradingClient()
        mock_resp = _mock_response(200, {"unexpected": "shape"})
        c._client = MagicMock()
        c._client.get = AsyncMock(return_value=mock_resp)
        result = await c.list_trades()
        assert result == []

    async def test_get_trade_status(self) -> None:
        c = TradingClient()
        mock_resp = _mock_response(200, {"trade_id": "t1", "status": "completed"})
        c._client = MagicMock()
        c._client.get = AsyncMock(return_value=mock_resp)
        result = await c.get_trade_status("t1")
        assert result["status"] == "completed"

    async def test_get_trade_history_list(self) -> None:
        c = TradingClient()
        mock_resp = _mock_response(200, [{"trade_id": "t1"}, {"trade_id": "t2"}])
        c._client = MagicMock()
        c._client.get = AsyncMock(return_value=mock_resp)
        result = await c.get_trade_history(source_chain="ait-hub")
        assert len(result) == 2

    async def test_get_trade_history_wrapped(self) -> None:
        c = TradingClient()
        mock_resp = _mock_response(200, {"history": [{"trade_id": "t1"}]})
        c._client = MagicMock()
        c._client.get = AsyncMock(return_value=mock_resp)
        result = await c.get_trade_history()
        assert len(result) == 1

    async def test_list_chains_list(self) -> None:
        c = TradingClient()
        mock_resp = _mock_response(200, [{"chain_id": "ait-hub"}, {"chain_id": "ait-2"}])
        c._client = MagicMock()
        c._client.get = AsyncMock(return_value=mock_resp)
        result = await c.list_chains()
        assert len(result) == 2

    async def test_list_chains_wrapped(self) -> None:
        c = TradingClient()
        mock_resp = _mock_response(200, {"chains": [{"chain_id": "ait-hub"}]})
        c._client = MagicMock()
        c._client.get = AsyncMock(return_value=mock_resp)
        result = await c.list_chains()
        assert len(result) == 1

    async def test_register_chain(self) -> None:
        c = TradingClient()
        mock_resp = _mock_response(200, {"chain_id": "ait-2", "status": "active"})
        c._client = MagicMock()
        c._client.post = AsyncMock(return_value=mock_resp)
        result = await c.register_chain("ait-2", "http://node2:8202")
        assert result["chain_id"] == "ait-2"

    async def test_get_chain_health(self) -> None:
        c = TradingClient()
        mock_resp = _mock_response(200, {"chain_id": "ait-hub", "status": "healthy"})
        c._client = MagicMock()
        c._client.get = AsyncMock(return_value=mock_resp)
        result = await c.get_chain_health("ait-hub")
        assert result["status"] == "healthy"

    async def test_health(self) -> None:
        c = TradingClient()
        mock_resp = _mock_response(200, {"status": "healthy"})
        c._client = MagicMock()
        c._client.get = AsyncMock(return_value=mock_resp)
        result = await c.health()
        assert result["status"] == "healthy"

    async def test_close(self) -> None:
        c = TradingClient()
        mock_client = MagicMock()
        mock_client.aclose = AsyncMock()
        c._client = mock_client
        await c.close()
        mock_client.aclose.assert_called_once()
        assert c._client is None

    async def test_close_when_not_open(self) -> None:
        c = TradingClient()
        await c.close()
        assert c._client is None

    async def test_ensure_client_creates_lazy(self) -> None:
        c = TradingClient()
        client = c._ensure_client()
        assert client is not None
        assert c._client is client
        client2 = c._ensure_client()
        assert client2 is client


# ---------------------------------------------------------------------------
# Bridge integration tests (A3)
# ---------------------------------------------------------------------------


class TestTradingBridgeClientInit:
    def test_default_config(self) -> None:
        c = TradingBridgeClient()
        assert c.bridge is not None

    def test_custom_config(self) -> None:
        cfg = TradingConfig(bridge_rpc_url="http://bridge:9000")
        c = TradingBridgeClient(cfg)
        assert c.bridge is not None

    def test_injected_bridge_client(self) -> None:
        mock_bridge = MagicMock(spec=TradingBridgeClient)
        c = TradingBridgeClient(bridge_client=mock_bridge)  # type: ignore[arg-type]
        assert c.bridge is mock_bridge


class TestTradingBridgeClientMethods:
    async def test_lock_escrow(self) -> None:
        mock_bridge = MagicMock()
        mock_bridge.lock = AsyncMock(return_value={"transfer_id": "tx_001", "status": "locked"})
        c = TradingBridgeClient(bridge_client=mock_bridge)
        result = await c.lock_escrow(
            source_chain="ait-hub",
            target_chain="ait-2",
            amount=1000,
            sender="alice",
            recipient="bob",
        )
        assert result["transfer_id"] == "tx_001"
        mock_bridge.lock.assert_called_once()

    async def test_get_transfer_status(self) -> None:
        mock_bridge = MagicMock()
        mock_bridge.get_transfer = AsyncMock(return_value={"transfer_id": "tx_001", "status": "confirmed"})
        c = TradingBridgeClient(bridge_client=mock_bridge)
        result = await c.get_transfer_status("tx_001")
        assert result["status"] == "confirmed"

    async def test_list_pending_transfers(self) -> None:
        mock_bridge = MagicMock()
        mock_bridge.list_pending = AsyncMock(return_value=[{"transfer_id": "tx_001"}])
        c = TradingBridgeClient(bridge_client=mock_bridge)
        result = await c.list_pending_transfers(chain_id="ait-hub")
        assert len(result) == 1

    async def test_get_chain_balance(self) -> None:
        mock_bridge = MagicMock()
        mock_bridge.get_balance = AsyncMock(return_value={"chain_id": "ait-hub", "balance": 5000})
        c = TradingBridgeClient(bridge_client=mock_bridge)
        result = await c.get_chain_balance("ait-hub")
        assert result["balance"] == 5000

    async def test_check_health(self) -> None:
        mock_bridge = MagicMock()
        mock_bridge.health = AsyncMock(return_value={"status": "healthy", "active_transfers": 3})
        c = TradingBridgeClient(bridge_client=mock_bridge)
        result = await c.check_health()
        assert result["status"] == "healthy"

    async def test_close(self) -> None:
        mock_bridge = MagicMock()
        mock_bridge.close = AsyncMock()
        c = TradingBridgeClient(bridge_client=mock_bridge)
        await c.close()
        mock_bridge.close.assert_called_once()


class TestTradingBridgeClientContextManager:
    async def test_context_manager(self) -> None:
        mock_bridge = MagicMock()
        mock_bridge.__aenter__ = AsyncMock(return_value=mock_bridge)
        mock_bridge.__aexit__ = AsyncMock(return_value=None)
        async with TradingBridgeClient(bridge_client=mock_bridge) as c:
            assert c.bridge is mock_bridge
        mock_bridge.__aenter__.assert_called_once()
        mock_bridge.__aexit__.assert_called_once()
