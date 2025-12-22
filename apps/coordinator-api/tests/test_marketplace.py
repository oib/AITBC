import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, delete

from app.config import settings
from app.domain import MarketplaceOffer, OfferStatus, MarketplaceBid
from app.main import create_app
from app.services.marketplace import MarketplaceService
from app.storage.db import init_db, session_scope


@pytest.fixture(scope="module", autouse=True)
def _init_db(tmp_path_factory):
    db_file = tmp_path_factory.mktemp("data") / "marketplace.db"
    settings.database_url = f"sqlite:///{db_file}"
    init_db()
    yield


@pytest.fixture()
def session():
    with session_scope() as sess:
        sess.exec(delete(MarketplaceBid))
        sess.exec(delete(MarketplaceOffer))
        sess.commit()
        yield sess


@pytest.fixture()
def client():
    app = create_app()
    return TestClient(app)


def test_list_offers_filters_by_status(client: TestClient, session: Session):
    open_offer = MarketplaceOffer(provider="Alpha", capacity=250, price=12.5, sla="99.9%", status=OfferStatus.open)
    reserved_offer = MarketplaceOffer(provider="Beta", capacity=100, price=15.0, sla="99.5%", status=OfferStatus.reserved)
    session.add(open_offer)
    session.add(reserved_offer)
    session.commit()

    # All offers
    resp = client.get("/v1/marketplace/offers")
    assert resp.status_code == 200
    payload = resp.json()
    assert len(payload) == 2

    # Filter by status
    resp_open = client.get("/v1/marketplace/offers", params={"status": "open"})
    assert resp_open.status_code == 200
    open_payload = resp_open.json()
    assert len(open_payload) == 1
    assert open_payload[0]["provider"] == "Alpha"

    # Invalid status yields 400
    resp_invalid = client.get("/v1/marketplace/offers", params={"status": "invalid"})
    assert resp_invalid.status_code == 400


def test_marketplace_stats(client: TestClient, session: Session):
    session.add_all(
        [
            MarketplaceOffer(provider="Alpha", capacity=200, price=10.0, sla="99.9%", status=OfferStatus.open),
            MarketplaceOffer(provider="Beta", capacity=150, price=20.0, sla="99.5%", status=OfferStatus.open),
            MarketplaceOffer(provider="Gamma", capacity=90, price=12.0, sla="99.0%", status=OfferStatus.reserved),
        ]
    )
    session.commit()

    resp = client.get("/v1/marketplace/stats")
    assert resp.status_code == 200
    stats = resp.json()
    assert stats["totalOffers"] == 3
    assert stats["openCapacity"] == 350
    assert pytest.approx(stats["averagePrice"], rel=1e-3) == 15.0
    assert stats["activeBids"] == 0


def test_submit_bid_creates_record(client: TestClient, session: Session):
    payload = {
        "provider": "Alpha",
        "capacity": 120,
        "price": 13.5,
        "notes": "Need overnight capacity",
    }
    resp = client.post("/v1/marketplace/bids", json=payload)
    assert resp.status_code == 202
    response_payload = resp.json()
    assert "id" in response_payload

    bid = session.get(MarketplaceBid, response_payload["id"])
    assert bid is not None
    assert bid.provider == payload["provider"]
    assert bid.capacity == payload["capacity"]
    assert bid.price == payload["price"]
    assert bid.notes == payload["notes"]


def test_marketplace_service_list_offers_handles_limit_offset(session: Session):
    session.add_all(
        [
            MarketplaceOffer(provider="A", capacity=50, price=9.0, sla="99.0%", status=OfferStatus.open),
            MarketplaceOffer(provider="B", capacity=70, price=11.0, sla="99.0%", status=OfferStatus.open),
            MarketplaceOffer(provider="C", capacity=90, price=13.0, sla="99.0%", status=OfferStatus.open),
        ]
    )
    session.commit()

    service = MarketplaceService(session)
    limited = service.list_offers(limit=2, offset=1)
    assert len(limited) == 2
    # Offers ordered by created_at descending → last inserted first
    assert {offer.provider for offer in limited} == {"B", "A"}
