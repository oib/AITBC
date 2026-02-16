import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, delete

from app.config import settings
from app.domain import MarketplaceOffer, MarketplaceBid
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
    open_offer = MarketplaceOffer(provider="Alpha", capacity=250, price=12.5, sla="99.9%", status="open")
    reserved_offer = MarketplaceOffer(provider="Beta", capacity=100, price=15.0, sla="99.5%", status="reserved")
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
            MarketplaceOffer(provider="A", capacity=50, price=9.0, sla="99.0%", status="open"),
            MarketplaceOffer(provider="B", capacity=70, price=11.0, sla="99.0%", status="open"),
            MarketplaceOffer(provider="C", capacity=90, price=13.0, sla="99.0%", status="open"),
        ]
    )
    session.commit()

    service = MarketplaceService(session)
    limited = service.list_offers(limit=2, offset=1)
    assert len(limited) == 2
    # Offers ordered by created_at descending → last inserted first
    assert {offer.provider for offer in limited} == {"B", "A"}


def test_submit_bid_creates_record(client: TestClient, session: Session):
    payload = {
        "provider": "TestProvider",
        "capacity": 150,
        "price": 0.075,
        "notes": "Test bid for GPU capacity"
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
    assert bid.status == "pending"


def test_list_bids_filters_by_status_and_provider(client: TestClient, session: Session):
    # Create test bids
    pending_bid = MarketplaceBid(provider="ProviderA", capacity=100, price=0.05, notes="Pending bid")
    accepted_bid = MarketplaceBid(provider="ProviderB", capacity=200, price=0.08, notes="Accepted bid", status="accepted")
    rejected_bid = MarketplaceBid(provider="ProviderA", capacity=150, price=0.06, notes="Rejected bid", status="rejected")
    
    session.add_all([pending_bid, accepted_bid, rejected_bid])
    session.commit()

    # List all bids
    resp = client.get("/v1/marketplace/bids")
    assert resp.status_code == 200
    payload = resp.json()
    assert len(payload) == 3

    # Filter by status
    resp_pending = client.get("/v1/marketplace/bids", params={"status": "pending"})
    assert resp_pending.status_code == 200
    pending_payload = resp_pending.json()
    assert len(pending_payload) == 1
    assert pending_payload[0]["provider"] == "ProviderA"
    assert pending_payload[0]["status"] == "pending"

    # Filter by provider
    resp_provider = client.get("/v1/marketplace/bids", params={"provider": "ProviderA"})
    assert resp_provider.status_code == 200
    provider_payload = resp_provider.json()
    assert len(provider_payload) == 2
    assert all(bid["provider"] == "ProviderA" for bid in provider_payload)

    # Filter by both status and provider
    resp_both = client.get("/v1/marketplace/bids", params={"status": "pending", "provider": "ProviderA"})
    assert resp_both.status_code == 200
    both_payload = resp_both.json()
    assert len(both_payload) == 1
    assert both_payload[0]["provider"] == "ProviderA"
    assert both_payload[0]["status"] == "pending"

    # Invalid status yields 400
    resp_invalid = client.get("/v1/marketplace/bids", params={"status": "invalid"})
    assert resp_invalid.status_code == 400


def test_get_bid_details(client: TestClient, session: Session):
    # Create a test bid
    bid = MarketplaceBid(
        provider="TestProvider",
        capacity=100,
        price=0.05,
        notes="Test bid details",
        status="pending"
    )
    session.add(bid)
    session.commit()
    session.refresh(bid)

    # Get bid details
    resp = client.get(f"/v1/marketplace/bids/{bid.id}")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["id"] == bid.id
    assert payload["provider"] == bid.provider
    assert payload["capacity"] == bid.capacity
    assert payload["price"] == bid.price
    assert payload["notes"] == bid.notes
    assert payload["status"] == bid.status
    assert "submitted_at" in payload

    # Non-existent bid yields 404
    resp_not_found = client.get("/v1/marketplace/bids/nonexistent")
    assert resp_not_found.status_code == 404


def test_marketplace_service_list_bids_handles_limit_offset(session: Session):
    session.add_all(
        [
            MarketplaceBid(provider="A", capacity=50, price=0.05, notes="Bid A"),
            MarketplaceBid(provider="B", capacity=70, price=0.07, notes="Bid B"),
            MarketplaceBid(provider="C", capacity=90, price=0.09, notes="Bid C"),
        ]
    )
    session.commit()

    service = MarketplaceService(session)
    limited = service.list_bids(limit=2, offset=1)
    assert len(limited) == 2
    # Bids ordered by submitted_at descending → last inserted first
    assert {bid.provider for bid in limited} == {"B", "A"}


def test_marketplace_stats_includes_bids(client: TestClient, session: Session):
    # Create offers and bids
    session.add_all(
        [
            MarketplaceOffer(provider="Alpha", capacity=200, price=10.0, sla="99.9%", status="open"),
            MarketplaceOffer(provider="Beta", capacity=150, price=20.0, sla="99.5%", status="reserved"),
            MarketplaceBid(provider="ProviderA", capacity=100, price=0.05, notes="Active bid 1"),
            MarketplaceBid(provider="ProviderB", capacity=200, price=0.08, notes="Active bid 2"),
            MarketplaceBid(provider="ProviderC", capacity=150, price=0.06, notes="Accepted bid", status="accepted"),
        ]
    )
    session.commit()

    resp = client.get("/v1/marketplace/stats")
    assert resp.status_code == 200
    stats = resp.json()
    assert stats["totalOffers"] == 2
    assert stats["openCapacity"] == 200  # Only open offers
    assert pytest.approx(stats["averagePrice"], rel=1e-3) == 10.0  # Only open offers
    assert stats["activeBids"] == 2  # Only pending bids


def test_bid_validation(client: TestClient):
    # Test invalid capacity (zero)
    resp_zero_capacity = client.post("/v1/marketplace/bids", json={
        "provider": "TestProvider",
        "capacity": 0,
        "price": 0.05
    })
    assert resp_zero_capacity.status_code == 400

    # Test invalid price (negative)
    resp_negative_price = client.post("/v1/marketplace/bids", json={
        "provider": "TestProvider", 
        "capacity": 100,
        "price": -0.05
    })
    assert resp_negative_price.status_code == 400

    # Test missing required field
    resp_missing_provider = client.post("/v1/marketplace/bids", json={
        "capacity": 100,
        "price": 0.05
    })
    assert resp_missing_provider.status_code == 422  # Validation error
