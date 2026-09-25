"""On-chain confirmation for merged marketplace offers.

list_software_services merges GPU offers from /rpc/gpus with local
SoftwareService rows, but neither source carries the sealing block. The
service resolves confirmation by joining offers to sealed GPU_REGISTER /
GPU_MARKET / GPU_MARKETPLACE transactions on payload.gpu_id /
payload.offer_id. These tests stub the RPC client and cover both link
shapes plus the unanchored and pre-confirmed cases.
"""

from __future__ import annotations

import pytest
from market_service.domain.market import SoftwareService
from market_service.services.market_service import MarketService
from market_service.storage import get_session_context

GPU_REGISTER_TX = {
    "tx_hash": "0xgpureg",
    "block_height": 1647,
    "timestamp": 1758000000.0,
    "payload": {"gpu_id": "gpu-live-05", "miner_id": "node0-miner"},
    "type": "GPU_REGISTER",
    "status": "confirmed",
}

SOFTWARE_OFFER_TX = {
    "tx_hash": "0xswoffer",
    "block_height": 21345,
    "timestamp": 1758740000.0,
    "payload": {"offer_id": "sw_offer_test", "service_type": "ipfs"},
    "type": "GPU_MARKET",
    "status": "confirmed",
}


class StubRPC:
    def __init__(self, offers=None, txs=None):
        self._offers = offers or []
        self._txs = txs or {}

    async def query_offers(self, **kwargs):
        return self._offers

    async def query_transactions(self, transaction_type=None, **kwargs):
        return self._txs.get(transaction_type, [])


@pytest.fixture
async def service() -> MarketService:
    async with get_session_context() as session:
        yield MarketService(session)


@pytest.mark.asyncio
async def test_gpu_offer_confirmed_via_gpu_register(service: MarketService) -> None:
    service._rpc_client = StubRPC(  # type: ignore[assignment]
        offers=[{"gpu_id": "gpu-live-05", "price_per_hour": "0.001", "model": "RTX 4090", "status": "active"}],
        txs={"GPU_REGISTER": [GPU_REGISTER_TX]},
    )
    offers = await service.list_software_services()
    offer = next(o for o in offers if o["plugin_id"] == "gpu-live-05")
    assert offer["confirmed"] is True
    assert offer["block_height"] == 1647
    assert offer["tx_hash"] == "0xgpureg"
    assert offer["block_timestamp"] is not None


@pytest.mark.asyncio
async def test_local_offer_confirmed_via_software_tx(service: MarketService) -> None:
    async with get_session_context() as session:
        session.add(
            SoftwareService(
                plugin_id="test-ipfs",
                service_type="ipfs",
                offer_id="sw_offer_test",
                status="active",
            )
        )
        await session.commit()

    service._rpc_client = StubRPC(txs={"GPU_MARKET": [SOFTWARE_OFFER_TX]})  # type: ignore[assignment]
    offers = await service.list_software_services()
    offer = next(o for o in offers if o["plugin_id"] == "test-ipfs")
    assert offer["confirmed"] is True
    assert offer["block_height"] == 21345
    assert offer["tx_hash"] == "0xswoffer"


@pytest.mark.asyncio
async def test_unanchored_offer_stays_unconfirmed(service: MarketService) -> None:
    async with get_session_context() as session:
        session.add(
            SoftwareService(
                plugin_id="test-noanchor",
                service_type="whisper",
                offer_id="sw_offer_missing",
                status="active",
            )
        )
        await session.commit()

    service._rpc_client = StubRPC(txs={"GPU_MARKET": [SOFTWARE_OFFER_TX]})  # type: ignore[assignment]
    offers = await service.list_software_services()
    offer = next(o for o in offers if o["plugin_id"] == "test-noanchor")
    assert offer["confirmed"] is False
    assert offer["block_height"] is None


@pytest.mark.asyncio
async def test_preconfirmed_offer_not_clobbered(service: MarketService) -> None:
    async with get_session_context() as session:
        session.add(
            SoftwareService(
                plugin_id="test-preconfirmed",
                service_type="ffmpeg",
                offer_id="sw_offer_old",
                status="active",
                block_height=99,
                tx_hash="0xstored",
            )
        )
        await session.commit()

    # A different tx anchors the same offer_id later; stored row data wins.
    service._rpc_client = StubRPC(  # type: ignore[assignment]
        txs={
            "GPU_MARKETPLACE": [
                {
                    **SOFTWARE_OFFER_TX,
                    "tx_hash": "0xother",
                    "block_height": 500,
                    "payload": {"offer_id": "sw_offer_old"},
                }
            ]
        }
    )
    offers = await service.list_software_services()
    offer = next(o for o in offers if o["plugin_id"] == "test-preconfirmed")
    assert offer["confirmed"] is True
    assert offer["block_height"] == 99
    assert offer["tx_hash"] == "0xstored"
