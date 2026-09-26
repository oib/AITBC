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

PROVIDER = "0x1111111111111111111111111111111111111111"
OTHER_SENDER = "0x2222222222222222222222222222222222222222"

GPU_REGISTER_TX = {
    "tx_hash": "0xgpureg",
    "block_height": 1647,
    "block_hash": "0xblock1647",
    "block_proposer": "0xPROPOSER",
    "created_at": "2026-09-16T08:00:00+00:00",
    # Transaction.timestamp is a string column — the endpoint emits it
    # verbatim, so confirmation must not assume epoch seconds.
    "timestamp": "2026-09-16T08:00:00+00:00",
    "payload": {"gpu_id": "gpu-live-05", "miner_id": "node0-miner"},
    "type": "GPU_REGISTER",
    "status": "confirmed",
}

SOFTWARE_OFFER_TX = {
    "tx_hash": "0xswoffer",
    "block_height": 21345,
    "block_hash": "0xblock21345",
    "block_proposer": "0xPROPOSER",
    "created_at": "2026-09-24T15:45:00+00:00",
    "timestamp": "2026-09-24T15:45:00+00:00",
    "payload": {"offer_id": "sw_offer_test", "service_type": "ipfs"},
    "sender": PROVIDER,
    "type": "GPU_MARKET",
    "status": "confirmed",
}


class StubRPC:
    def __init__(self, offers=None, txs=None, gpu_info=None):
        self._offers = offers or []
        self._txs = txs or {}
        self._gpu_info = gpu_info

    async def query_offers(self, **kwargs):
        return self._offers

    async def query_transactions(self, transaction_type=None, **kwargs):
        return self._txs.get(transaction_type, [])

    async def get_offer(self, gpu_id, chain_id=None):
        return self._gpu_info


@pytest.fixture
async def service() -> MarketService:
    # The negative-probe memo is class-level: clear between tests so one
    # test's "no anchor" result can't suppress another's live resolution.
    MarketService._anchor_negatives.clear()
    async with get_session_context() as session:
        yield MarketService(session)


@pytest.mark.asyncio
async def test_gpu_offer_confirmed_via_gpu_register(service: MarketService) -> None:
    service._rpc_client = StubRPC(  # type: ignore[assignment]
        offers=[
            {
                "gpu_id": "gpu-live-05",
                "price_per_hour": "0.001",
                "model": "RTX 4090",
                "status": "active",
                "miner_id": "node0-miner",
            }
        ],
        txs={"GPU_REGISTER": [GPU_REGISTER_TX]},
    )
    offers = await service.list_software_services()
    offer = next(o for o in offers if o["plugin_id"] == "gpu-live-05")
    assert offer["confirmed"] is True
    assert offer["block_height"] == 1647
    assert offer["tx_hash"] == "0xgpureg"
    assert offer["block_timestamp"] == "2026-09-16T08:00:00+00:00"


@pytest.mark.asyncio
async def test_local_offer_confirmed_via_software_tx(service: MarketService) -> None:
    async with get_session_context() as session:
        session.add(
            SoftwareService(
                plugin_id="test-ipfs",
                service_type="ipfs",
                offer_id="sw_offer_test",
                provider_address=PROVIDER,
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


@pytest.mark.asyncio
async def test_anchor_fills_block_metadata_and_registered(service: MarketService) -> None:
    """Confirmed offers render block hash/proposer and get registered_at
    from the sealing tx when the offer itself lacks one (GPU rows have none)."""
    service._rpc_client = StubRPC(  # type: ignore[assignment]
        offers=[
            {
                "gpu_id": "gpu-live-05",
                "price_per_hour": "0.001",
                "model": "RTX 4090",
                "status": "active",
                "miner_id": "node0-miner",
            }
        ],
        txs={"GPU_REGISTER": [GPU_REGISTER_TX]},
    )
    offers = await service.list_software_services()
    offer = next(o for o in offers if o["plugin_id"] == "gpu-live-05")
    assert offer["block_hash"] == "0xblock1647"
    assert offer["block_proposer"] == "0xPROPOSER"
    assert offer["registered_at"] == "2026-09-16T08:00:00+00:00"


@pytest.mark.asyncio
async def test_get_offer_detail_confirmed(service: MarketService) -> None:
    """The detail endpoint resolves anchors too — it must agree with the list."""
    async with get_session_context() as session:
        session.add(
            SoftwareService(
                plugin_id="test-detail",
                service_type="ipfs",
                offer_id="sw_offer_test",
                provider_address=PROVIDER,
                status="active",
            )
        )
        await session.commit()

    service._rpc_client = StubRPC(txs={"GPU_MARKET": [SOFTWARE_OFFER_TX]})  # type: ignore[assignment]
    detail = await service.get_software_service("test-detail")
    assert detail is not None
    assert detail["confirmed"] is True
    assert detail["block_height"] == 21345
    assert detail["tx_hash"] == "0xswoffer"
    assert detail["block_proposer"] == "0xPROPOSER"


@pytest.mark.asyncio
async def test_get_offer_detail_gpu_fallback(service: MarketService) -> None:
    """GPU offers exist only on-chain; the detail endpoint must fall back
    to /rpc/gpu/info/{gpu_id} instead of 404ing."""
    service._rpc_client = StubRPC(  # type: ignore[assignment]
        gpu_info={
            "gpu_id": "gpu-live-05",
            "price_per_hour": "0.001",
            "model": "RTX 4090",
            "status": "active",
            "miner_id": "node0-miner",
        },
        txs={"GPU_REGISTER": [GPU_REGISTER_TX]},
    )
    detail = await service.get_software_service("gpu-live-05")
    assert detail is not None
    assert detail["service_type"] == "gpu_market"
    assert detail["confirmed"] is True
    assert detail["block_height"] == 1647


@pytest.mark.asyncio
async def test_internal_endpoints_sanitized(service: MarketService) -> None:
    """Loopback endpoint/health_url values are internal routing data and
    must not leak through the serialized offer."""
    async with get_session_context() as session:
        session.add(
            SoftwareService(
                plugin_id="test-sanitize",
                service_type="whisper",
                endpoint="http://localhost:8110",
                health_url="http://127.0.0.1:8110/health",
                public_endpoint="https://node2.example/whisper",
                status="active",
            )
        )
        await session.commit()

    service._rpc_client = StubRPC()  # type: ignore[assignment]
    detail = await service.get_software_service("test-sanitize")
    assert detail is not None
    assert detail["endpoint"] is None
    assert detail["health_url"] is None
    assert detail["public_endpoint"] == "https://node2.example/whisper"


@pytest.mark.asyncio
async def test_software_offer_cannot_borrow_gpu_register_seal(service: MarketService) -> None:
    """A local offer squatting an existing gpu_id must not inherit the
    GPU_REGISTER seal: anchor lookups are namespaced per tx type, so a
    software offer only ever resolves market txs."""
    async with get_session_context() as session:
        session.add(
            SoftwareService(
                plugin_id="gpu-live-05",
                service_type="whisper",
                offer_id="gpu-live-05",
                provider_address=OTHER_SENDER,
                status="active",
            )
        )
        await session.commit()

    service._rpc_client = StubRPC(txs={"GPU_REGISTER": [GPU_REGISTER_TX]})  # type: ignore[assignment]
    detail = await service.get_software_service("gpu-live-05")
    assert detail is not None
    assert detail["confirmed"] is False
    assert detail["block_height"] is None


@pytest.mark.asyncio
async def test_foreign_newer_tx_does_not_take_over_anchor(service: MarketService) -> None:
    """A newer GPU_MARKET tx carrying a victim's offer_id but sealed by a
    different sender is skipped — the offer still anchors to its own older
    seal rather than displaying the foreign tx's block metadata."""
    async with get_session_context() as session:
        session.add(
            SoftwareService(
                plugin_id="test-takeover",
                service_type="ipfs",
                offer_id="sw_offer_test",
                provider_address=PROVIDER,
                status="active",
            )
        )
        await session.commit()

    foreign_newer = {
        **SOFTWARE_OFFER_TX,
        "tx_hash": "0xforeign",
        "sender": OTHER_SENDER,
        "block_height": 99999,
        "block_proposer": "0xATTACKER",
    }
    service._rpc_client = StubRPC(txs={"GPU_MARKET": [foreign_newer, SOFTWARE_OFFER_TX]})  # type: ignore[assignment]
    offers = await service.list_software_services()
    offer = next(o for o in offers if o["plugin_id"] == "test-takeover")
    assert offer["confirmed"] is True
    assert offer["tx_hash"] == "0xswoffer"
    assert offer["block_height"] == 21345


@pytest.mark.asyncio
async def test_gpu_offer_rejects_anchor_from_foreign_registrant(service: MarketService) -> None:
    """A GPU_REGISTER sealed by a different wallet must not anchor the offer:
    when /rpc/gpus supplies registered_by, the anchor binds the tx sender to
    the first registrant — miner_id alone (a signer-chosen label) is not
    enough. Covers the pre-v7 window where anyone could overwrite a gpu_id."""
    service._rpc_client = StubRPC(  # type: ignore[assignment]
        offers=[
            {
                "gpu_id": "gpu-live-05",
                "price_per_hour": "0.001",
                "model": "RTX 4090",
                "status": "active",
                "miner_id": "node0-miner",
                "registered_by": PROVIDER,
            }
        ],
        txs={"GPU_REGISTER": [{**GPU_REGISTER_TX, "sender": OTHER_SENDER}]},
    )
    offers = await service.list_software_services()
    offer = next(o for o in offers if o["plugin_id"] == "gpu-live-05")
    assert offer["confirmed"] is False
    assert offer["block_height"] is None


@pytest.mark.asyncio
async def test_gpu_offer_confirms_via_registered_by_sender(service: MarketService) -> None:
    """The strong path: sender == registered_by anchors even if payload
    miner_id were absent — the wallet binding, not the node label."""
    tx = {**GPU_REGISTER_TX, "sender": PROVIDER, "payload": {"gpu_id": "gpu-live-05", "miner_id": "anything"}}
    service._rpc_client = StubRPC(  # type: ignore[assignment]
        offers=[
            {
                "gpu_id": "gpu-live-05",
                "price_per_hour": "0.001",
                "model": "RTX 4090",
                "status": "active",
                "miner_id": "node0-miner",
                "registered_by": PROVIDER,
            }
        ],
        txs={"GPU_REGISTER": [tx]},
    )
    offers = await service.list_software_services()
    offer = next(o for o in offers if o["plugin_id"] == "gpu-live-05")
    assert offer["confirmed"] is True
    assert offer["block_height"] == 1647


class CountingRPC(StubRPC):
    """StubRPC that records query_transactions calls."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tx_queries: list = []

    async def query_transactions(self, transaction_type=None, **kwargs):
        self.tx_queries.append(transaction_type)
        return await super().query_transactions(transaction_type=transaction_type, **kwargs)


@pytest.mark.asyncio
async def test_confirmed_local_offer_persists_block_fields(service: MarketService) -> None:
    """Once a verified anchor resolves, the SoftwareService row stores the
    confirmation: a second listing reads block_* from the row and does not
    probe the chain again."""
    async with get_session_context() as session:
        session.add(
            SoftwareService(
                plugin_id="test-persist",
                service_type="ipfs",
                offer_id="sw_offer_test",
                provider_address=PROVIDER,
                status="active",
            )
        )
        await session.commit()

    rpc = CountingRPC(txs={"GPU_MARKET": [SOFTWARE_OFFER_TX]})
    service._rpc_client = rpc  # type: ignore[assignment]
    offers = await service.list_software_services()
    assert next(o for o in offers if o["plugin_id"] == "test-persist")["confirmed"] is True
    assert rpc.tx_queries  # first listing probed the chain

    rpc2 = CountingRPC(txs={})  # chain data "gone" — stored truth wins
    service._rpc_client = rpc2  # type: ignore[assignment]
    offers = await service.list_software_services()
    offer = next(o for o in offers if o["plugin_id"] == "test-persist")
    assert offer["confirmed"] is True
    assert offer["block_height"] == 21345
    assert rpc2.tx_queries == []


@pytest.mark.asyncio
async def test_stored_anchor_confirms_gpu_offer_without_chain_probe(service: MarketService) -> None:
    """On-chain GPU offers have no local row: their verified anchor lands in
    OfferAnchor and later listings confirm from the stored row — no probes."""
    from sqlalchemy import select

    from market_service.domain.market import OfferAnchor

    gpu_offer = {
        "gpu_id": "gpu-stored-01",
        "price_per_hour": "0.001",
        "model": "RTX 4090",
        "status": "active",
        "miner_id": "stored-miner",
    }
    register_tx = {
        **GPU_REGISTER_TX,
        "block_height": 2000,
        "payload": {"gpu_id": "gpu-stored-01", "miner_id": "stored-miner"},
    }
    rpc = CountingRPC(offers=[gpu_offer], txs={"GPU_REGISTER": [register_tx]})
    service._rpc_client = rpc  # type: ignore[assignment]
    offers = await service.list_software_services()
    assert next(o for o in offers if o["plugin_id"] == "gpu-stored-01")["confirmed"] is True
    assert rpc.tx_queries

    async with get_session_context() as session:
        row = (
            await session.execute(select(OfferAnchor).where(OfferAnchor.key == "gpu:gpu-stored-01"))
        ).scalar_one_or_none()
    assert row is not None
    assert row.block_height == 2000
    assert row.bound_provider == "stored-miner"

    rpc2 = CountingRPC(offers=[gpu_offer], txs={})
    service._rpc_client = rpc2  # type: ignore[assignment]
    offers = await service.list_software_services()
    offer = next(o for o in offers if o["plugin_id"] == "gpu-stored-01")
    assert offer["confirmed"] is True
    assert offer["block_height"] == 2000
    assert rpc2.tx_queries == []


@pytest.mark.asyncio
async def test_unanchored_offer_is_not_reprobed_within_ttl(service: MarketService) -> None:
    """An offer that resolves to nothing stays unconfirmed but must not cost
    three chain RPCs on every listing — the negative result is memoized."""
    async with get_session_context() as session:
        session.add(
            SoftwareService(
                plugin_id="test-negcache",
                service_type="ipfs",
                offer_id="sw_offer_never",
                provider_address=PROVIDER,
                status="active",
            )
        )
        await session.commit()

    rpc = CountingRPC(txs={"GPU_MARKET": [SOFTWARE_OFFER_TX]})
    service._rpc_client = rpc  # type: ignore[assignment]
    offers = await service.list_software_services()
    assert next(o for o in offers if o["plugin_id"] == "test-negcache")["confirmed"] is False
    first_count = len(rpc.tx_queries)
    assert first_count == 3

    offers = await service.list_software_services()
    assert next(o for o in offers if o["plugin_id"] == "test-negcache")["confirmed"] is False
    assert len(rpc.tx_queries) == first_count  # memoized — no new probes
