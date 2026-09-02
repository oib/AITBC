"""Tests for the ETH->AIT bridge monitor."""

from __future__ import annotations

from typing import Any

import pytest

BRIDGE_ADDRESS = "0x09362894C18f7CbCdb85b124ef4c8F63DEC09B32"
OTHER_ADDRESS = "0x1111111111111111111111111111111111111111"

DEPOSIT_TX = {
    "hash": "0x" + "aa" * 32,
    "from": "0x" + "bb" * 20,
    "to": BRIDGE_ADDRESS,
    "value": "0x100",
    "input": "0x",
}

OTHER_TX = {
    "hash": "0x" + "cc" * 32,
    "from": "0x" + "dd" * 20,
    "to": OTHER_ADDRESS,
    "value": "0x50",
    "input": "0x",
}


class FakeResponse:
    def __init__(self, data: Any) -> None:
        self._data = data

    def raise_for_status(self) -> None:
        pass

    def json(self) -> Any:
        return self._data


class FakeClient:
    @staticmethod
    async def post(url: str, **kwargs: Any) -> FakeResponse:
        raise NotImplementedError("Override post in the test")


def _block_for_number(bn: int, txs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "number": hex(bn),
        "hash": "0x" + f"{bn:064x}",
        "transactions": txs or [],
    }


@pytest.fixture
def monitor_env(tmp_path, monkeypatch):
    """Provide a fresh bridge monitor with an isolated fake HTTP client."""
    from wallet_app.bridge import bridge_monitor as monitor

    monkeypatch.setenv("ETH_RPC_URL", "http://test-rpc")
    monkeypatch.setenv("ETH_WALLET_ADDRESS", BRIDGE_ADDRESS)
    monkeypatch.setenv("BRIDGE_ETH_LOOKBACK_BLOCKS", "5")
    monkeypatch.setenv("BRIDGE_ETH_REORG_MARGIN", "2")
    monkeypatch.setattr(monitor, "_LAST_SCANNED_BLOCK", None)
    monkeypatch.setattr(monitor, "ETH_RPC_URL", "http://test-rpc")
    monkeypatch.setattr(monitor, "SharedHttpClient", FakeClient)

    yield monitor


class TestGetEthTransactions:
    @pytest.mark.asyncio
    async def test_first_poll_batches_lookback_window(self, monitor_env, monkeypatch):
        monitor = monitor_env
        calls: list[Any] = []

        async def fake_post(url: str, **kwargs: Any) -> FakeResponse:
            calls.append(kwargs.get("json"))
            request = kwargs.get("json")
            if isinstance(request, dict) and request.get("method") == "eth_blockNumber":
                return FakeResponse({"jsonrpc": "2.0", "id": 0, "result": "0x64"})
            if isinstance(request, list):
                results = []
                for payload in request:
                    bn = payload["id"]
                    txs = [DEPOSIT_TX, OTHER_TX] if bn == 100 else []
                    results.append({"jsonrpc": "2.0", "id": bn, "result": _block_for_number(bn, txs)})
                return FakeResponse(results)
            return FakeResponse({})

        monkeypatch.setattr(FakeClient, "post", staticmethod(fake_post))  # type: ignore[arg-type]

        txs = await monitor.get_eth_transactions(BRIDGE_ADDRESS)

        assert len(txs) == 1
        assert txs[0]["hash"] == DEPOSIT_TX["hash"]

        # One eth_blockNumber + one batched eth_getBlockByNumber.
        assert len(calls) == 2
        assert isinstance(calls[0], dict)
        assert calls[0].get("method") == "eth_blockNumber"
        assert isinstance(calls[1], list)
        assert len(calls[1]) == 5
        assert [p["id"] for p in calls[1]] == [96, 97, 98, 99, 100]

    @pytest.mark.asyncio
    async def test_steady_state_only_scans_new_and_reorg_margin(self, monitor_env, monkeypatch):
        monitor = monitor_env
        calls: list[Any] = []

        async def fake_post(url: str, **kwargs: Any) -> FakeResponse:
            request = kwargs.get("json")
            calls.append(request)
            if isinstance(request, dict) and request.get("method") == "eth_blockNumber":
                # First poll sees 100, second sees 102.
                if monitor._LAST_SCANNED_BLOCK is None:
                    return FakeResponse({"jsonrpc": "2.0", "id": 0, "result": "0x64"})
                return FakeResponse({"jsonrpc": "2.0", "id": 0, "result": "0x66"})
            if isinstance(request, list):
                results = []
                for payload in request:
                    bn = payload["id"]
                    txs = [DEPOSIT_TX] if bn == 102 else []
                    results.append({"jsonrpc": "2.0", "id": bn, "result": _block_for_number(bn, txs)})
                return FakeResponse(results)
            return FakeResponse({})

        monkeypatch.setattr(FakeClient, "post", staticmethod(fake_post))  # type: ignore[arg-type]

        # First poll: lookback window 96..100.
        first = await monitor.get_eth_transactions(BRIDGE_ADDRESS)
        assert len(first) == 0
        assert len(calls) == 2
        assert len(calls[1]) == 5

        # Second poll: reorg margin of 2 means start = 99, end = 102.
        second = await monitor.get_eth_transactions(BRIDGE_ADDRESS)
        assert len(second) == 1
        assert second[0]["hash"] == DEPOSIT_TX["hash"]

        assert len(calls) == 4
        assert isinstance(calls[2], dict)
        assert isinstance(calls[3], list)
        assert len(calls[3]) == 4  # 99, 100, 101, 102
        assert [p["id"] for p in calls[3]] == [99, 100, 101, 102]

    @pytest.mark.asyncio
    async def test_empty_range_updates_last_scanned_block(self, monitor_env, monkeypatch):
        monitor = monitor_env

        async def fake_post(url: str, **kwargs: Any) -> FakeResponse:
            request = kwargs.get("json")
            if isinstance(request, dict) and request.get("method") == "eth_blockNumber":
                return FakeResponse({"jsonrpc": "2.0", "id": 0, "result": "0x64"})
            return FakeResponse({})

        monkeypatch.setattr(FakeClient, "post", staticmethod(fake_post))  # type: ignore[arg-type]

        # Force an empty block range.
        monitor._LAST_SCANNED_BLOCK = 100
        txs = await monitor.get_eth_transactions(BRIDGE_ADDRESS)

        assert txs == []
        assert monitor._LAST_SCANNED_BLOCK == 100

    @pytest.mark.asyncio
    async def test_batch_error_does_not_advance_last_scanned(self, monitor_env, monkeypatch):
        monitor = monitor_env

        async def fake_post(url: str, **kwargs: Any) -> FakeResponse:
            request = kwargs.get("json")
            if isinstance(request, dict) and request.get("method") == "eth_blockNumber":
                return FakeResponse({"jsonrpc": "2.0", "id": 0, "result": "0x64"})
            if isinstance(request, list):
                return FakeResponse([{"jsonrpc": "2.0", "id": 96, "error": {"code": -32000, "message": "boom"}}])
            return FakeResponse({})

        monkeypatch.setattr(FakeClient, "post", staticmethod(fake_post))  # type: ignore[arg-type]

        txs = await monitor.get_eth_transactions(BRIDGE_ADDRESS)
        assert txs == []
        assert monitor._LAST_SCANNED_BLOCK is None

    @pytest.mark.asyncio
    async def test_uses_lookback_when_falling_behind(self, monitor_env, monkeypatch):
        monitor = monitor_env
        calls: list[Any] = []

        async def fake_post(url: str, **kwargs: Any) -> FakeResponse:
            request = kwargs.get("json")
            calls.append(request)
            if isinstance(request, dict) and request.get("method") == "eth_blockNumber":
                return FakeResponse({"jsonrpc": "2.0", "id": 0, "result": "0x6e"})
            if isinstance(request, list):
                results = []
                for payload in request:
                    bn = payload["id"]
                    results.append({"jsonrpc": "2.0", "id": bn, "result": _block_for_number(bn)})
                return FakeResponse(results)
            return FakeResponse({})

        monkeypatch.setattr(FakeClient, "post", staticmethod(fake_post))  # type: ignore[arg-type]

        # Last scanned was block 60, but the node is now at 110. The monitor must
        # not scan 50 blocks, only the configured lookback of 5.
        monitor._LAST_SCANNED_BLOCK = 60

        await monitor.get_eth_transactions(BRIDGE_ADDRESS)

        batch = calls[1]
        assert isinstance(batch, list)
        assert [p["id"] for p in batch] == [106, 107, 108, 109, 110]
