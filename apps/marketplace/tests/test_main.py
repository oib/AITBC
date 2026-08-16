"""
Test Marketplace service main application

Tests cover all public API endpoints with correct paths and required query
parameters.

Fourteen of these used to assert ``status_code in (200, 500)``, on the reasoning that the
database might not be available — which meant they passed whether the endpoint worked or
threw an unhandled exception, and that is not a test. The database is available: the suite's
conftest builds this service's schema into a throwaway directory before the first test
(V23-73). Every one of those endpoints returns 200 against an empty database, so that is what
they assert now, with the response shape where there is a shape worth checking.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Add the marketplace src directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from marketplace_service.main import app


@pytest.fixture
def client():
    """Create test client for Marketplace service"""
    return TestClient(app)


# --- Health / readiness ---


def test_health_check(client):
    """Test health check endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "marketplace-service"


def test_ready_check(client):
    """Test readiness endpoint"""
    response = client.get("/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"


def test_live_check(client):
    """Test liveness endpoint"""
    response = client.get("/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "alive"


def test_metrics_endpoint(client):
    """Test Prometheus metrics endpoint"""
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers.get("content-type", "")


# --- Marketplace status (corrected path) ---


def test_marketplace_status(client):
    """Test marketplace status endpoint (correct path: /v1/marketplace/status)"""
    response = client.get("/v1/marketplace/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "operational"
    assert data["service"] == "marketplace-service"


# --- Offers (corrected: required query params) ---


def test_get_marketplace_offers_with_params(client):
    """Test get marketplace offers with required query params

    The status here used to be "active", which is not a marketplace offer status at all --
    it belongs to `SoftwareService`, a different table reached through the singular
    `/v1/marketplace/offer`. It returned 200 and an empty list, so the test passed and said
    nothing. `?status=` now names a real state or is rejected (V23-83).
    """
    response = client.get(
        "/v1/marketplace/offers",
        params={"status": "available", "region": "us-east", "gpu_model": "A100"},
    )
    assert response.status_code == 200
    assert response.json() == []


def test_get_marketplace_offers_missing_params(client):
    """Test get marketplace offers without params — all params optional (v0.6.6)"""
    response = client.get("/v1/marketplace/offers")
    # v0.6.6: all query params are now optional (status, region, gpu_model, chain_id)
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_marketplace_offers_partial_params(client):
    """Test get marketplace offers with only some params — all optional (v0.6.6)"""
    response = client.get("/v1/marketplace/offers", params={"status": "available"})
    # v0.6.6: all params optional, partial params accepted
    assert response.status_code == 200
    assert isinstance(response.json(), list)


# --- Marketplace overview ---


def test_marketplace_overview(client):
    """Test marketplace overview endpoint"""
    response = client.get("/v1/marketplace")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "operational"
    assert "total_offers" in data
    assert "active_offers" in data


# --- Analytics (corrected: required query param) ---


def test_get_marketplace_analytics_with_param(client):
    """Test get marketplace analytics with required period_type param"""
    response = client.get("/v1/marketplace/analytics", params={"period_type": "daily"})
    assert response.status_code == 200
    assert response.json()["period_type"] == "daily"


def test_get_marketplace_analytics_missing_param(client):
    """Test get marketplace analytics without required param returns 422"""
    response = client.get("/v1/marketplace/analytics")
    assert response.status_code == 422


# --- Performance ---


def test_marketplace_performance(client):
    """Test marketplace performance endpoint (requires period param)"""
    response = client.get("/v1/marketplace/performance", params={"period": "daily"})
    assert response.status_code == 200
    assert response.json()["period"] == "daily"


def test_marketplace_performance_missing_param(client):
    """Test marketplace performance without required period param returns 422"""
    response = client.get("/v1/marketplace/performance")
    assert response.status_code == 422


# --- Plugins ---


def test_get_plugins(client):
    """Test get plugins endpoint"""
    response = client.get("/v1/marketplace/plugins")
    assert response.status_code == 200
    assert isinstance(response.json()["plugins"], list)


# --- Offer by ID ---


def test_get_offer_by_id_not_found(client):
    """A GET for an offer that does not exist answers 404, in this service's error shape.

    It used to answer 200 with a body of `null`, because the route returned `get_offer`'s
    `None` straight through — so a client checking the status code was told the offer
    existed. The body is asserted too, not just the code: the point of the fix was that this
    route disagreed with the seven other "not found" paths in the same file, and a 404
    carrying some other shape would only have moved the disagreement (V23-76).
    """
    response = client.get("/v1/marketplace/offers/nonexistent-offer-id")
    assert response.status_code == 404
    assert response.json() == {"error": "Offer not found"}


# --- Booking ---


def test_book_offer_not_found(client):
    """Booking an offer that does not exist answers 404, not 500.

    `MarketplaceService.book_offer` raises `ValueError("Offer not found: ...")` and the route
    re-raised it, so a typo'd offer id produced `{"error": {"type": "internal_error", ...}}`
    with a 500 — a client retrying on 5xx would retry it forever, and an operator watching
    error rates would see the service failing rather than a caller asking for nothing (V23-81).
    """
    response = client.post("/v1/marketplace/offers/nonexistent-offer-id/book", json={"wallet": "aitbc1test"})
    assert response.status_code == 404
    assert response.json() == {"error": "Offer not found"}


def test_book_offer_that_is_not_available(client):
    """Booking an offer in the wrong state answers 400, and says which state.

    The other half of the same 500: `book_offer` raises `ValueError` for this too. 400 rather
    than 409 because the only 409 in this service means an optimistic-concurrency mismatch,
    which is a different thing, and because `cancel_offer` already answers 400 for the
    equivalent "wrong state" case over the same resource (V23-81).

    Booking twice is how the offer is moved out of `available` here, and it stays that way
    now that cancelling works (V23-83): a booked offer cannot be cancelled either, so the
    two-bookings route to this state is the only one.
    """
    created = client.post("/v1/marketplace/offers", json={"provider": "aitbc1provider", "capacity": 1})
    assert created.status_code == 200
    offer_id = created.json()["id"]

    first = client.post(f"/v1/marketplace/offers/{offer_id}/book", json={"wallet": "aitbc1test"})
    assert first.status_code == 200

    response = client.post(f"/v1/marketplace/offers/{offer_id}/book", json={"wallet": "aitbc1other"})
    assert response.status_code == 400
    assert response.json() == {"error": "Offer is not available (status=booked)"}


def test_book_offer_with_an_unparseable_duration(client):
    """Request fields that will not convert answer 400, not 500.

    `_create_bid` does `float(booking_data["duration_hours"])`, so a non-numeric duration
    raised `ValueError` out of the service and the route re-raised it — the same 500 as a
    missing offer, from bad input rather than a bad id. The `except ValueError` added in
    V23-81 covers both, which is why it is worth pinning that it covers this one too.
    """
    created = client.post("/v1/marketplace/offers", json={"provider": "aitbc1provider", "capacity": 1})
    assert created.status_code == 200
    offer_id = created.json()["id"]

    response = client.post(
        f"/v1/marketplace/offers/{offer_id}/book",
        json={"wallet": "aitbc1test", "duration_hours": "half a day"},
    )
    assert response.status_code == 400
    assert "error" in response.json()


# --- Cancellation ---


def _new_offer(client, **fields):
    """Create an offer and return its id. Defaults to a bookable one."""
    created = client.post("/v1/marketplace/offers", json={"provider": "aitbc1provider", "capacity": 1, **fields})
    assert created.status_code == 200, created.text
    return created.json()["id"]


def test_cancel_offer_not_found(client):
    """An offer id that is not there is 404, as it is on every other route over this resource."""
    response = client.post("/v1/marketplace/offers/nonexistent-offer-id/cancel")
    assert response.status_code == 404
    assert response.json() == {"error": "Offer not found"}


def test_cancel_offer_without_a_reason(client):
    """`?reason=` is optional, and this is the test that says so.

    `reason: str | None` with no default is a required query parameter to FastAPI — the
    published spec carried `"required": true` — so cancelling without one was a 422 before any
    of the cancellation logic ran. The handler has always defaulted it in the body
    (`reason or "user_requested"`), so the requirement was an accident of the signature and
    nothing agreed with it (V23-83).
    """
    response = client.post(f"/v1/marketplace/offers/{_new_offer(client)}/cancel")
    assert response.status_code == 200
    assert response.json()["reason"] == "user_requested"


def test_cancel_an_available_offer(client):
    """The finding: this answered 500 for every offer in the database.

    `cancel_offer` asks for the status `"cancelled"`, `update_offer_status` parsed it with
    `OfferFSM.from_string`, and `"cancelled"` is not one of the five `OfferStatus` members —
    so it raised `ValueError` for every offer that existed, the route had no handler, and the
    client got `{"error": {"type": "internal_error"}}` with a 500 (V23-83).
    """
    offer_id = _new_offer(client)

    response = client.post(f"/v1/marketplace/offers/{offer_id}/cancel", params={"reason": "listing withdrawn"})
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert response.json()["reason"] == "listing withdrawn"

    # And it stuck: the old code raised before the assignment, so nothing was ever written.
    assert client.get(f"/v1/marketplace/offers/{offer_id}").json()["status"] == "cancelled"


def test_cancel_an_offer_twice(client):
    """The second cancellation is 400, and reachable for the first time.

    The route has always had this branch; it could not be reached, because `"cancelled"` was
    never successfully written to any row.
    """
    offer_id = _new_offer(client)
    assert client.post(f"/v1/marketplace/offers/{offer_id}/cancel").status_code == 200

    response = client.post(f"/v1/marketplace/offers/{offer_id}/cancel")
    assert response.status_code == 400
    assert response.json() == {"error": "Offer already cancelled"}


def test_cancel_an_offer_stored_under_a_legacy_status(client):
    """An offer stored as "open" cancels, and that is the point of the alias map.

    One of the four offers in the deployed database has this status — coordinator-api's word
    for the same state. It failed a step earlier than the others: `OfferFSM.from_string` could
    not parse the *current* status either, so the offer was frozen in place, unbookable and
    uncancellable, with every route over it answering 500.
    """
    offer_id = _new_offer(client, status="open")

    response = client.post(f"/v1/marketplace/offers/{offer_id}/cancel")
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_cancel_a_booked_offer_is_refused(client):
    """400 and a reason, not a 500 and not a silent delisting.

    `RESERVED` transitions to `IN_USE`, back to `AVAILABLE`, or to `EXPIRED` — not to
    `DELISTED`. A provider cannot delist an offer out from under a buyer holding it. That rule
    is the FSM's and predates this change; what is new is that the service reaches it instead
    of failing to parse `"booked"` on the way in.
    """
    offer_id = _new_offer(client)
    assert client.post(f"/v1/marketplace/offers/{offer_id}/book", json={"wallet": "aitbc1buyer"}).status_code == 200

    response = client.post(f"/v1/marketplace/offers/{offer_id}/cancel")
    assert response.status_code == 400
    assert response.json() == {"error": "Offer cannot be cancelled while it is booked"}


def test_an_offer_cannot_be_created_in_a_status_the_service_does_not_have(client):
    """`create_offer` splats the request body into the model, `status` included.

    Which is how a row nothing could parse got into the deployed database. Rejecting the
    status on the way in is what makes "every stored status parses" an invariant rather than
    a hope — without it the alias map only covers the words this repo happens to write today.
    """
    created = client.post(
        "/v1/marketplace/offers",
        json={"provider": "aitbc1provider", "capacity": 1, "status": "mostly available"},
    )
    assert created.status_code == 400
    assert "Unknown offer status" in created.json()["error"]


def test_the_status_filter_matches_by_state_not_by_spelling(client):
    """`?status=available` finds the offer stored as "open", and vice versa.

    Two spellings of one state meant an offer was visible or invisible depending on which word
    the caller used, with nothing to say the other existed.
    """
    plain = _new_offer(client, region="filter-test")
    legacy = _new_offer(client, region="filter-test", status="open")

    for spelling in ("available", "open"):
        found = client.get("/v1/marketplace/offers", params={"status": spelling, "region": "filter-test"})
        assert found.status_code == 200
        assert {o["id"] for o in found.json()} == {plain, legacy}, spelling


def test_the_status_filter_rejects_a_state_that_does_not_exist(client):
    """400, rather than 200 and an empty list.

    An empty list is the same answer a real filter with no matches gives, so a typo — or the
    `SoftwareService` vocabulary, which is the confusion this endpoint actually attracts —
    read as "no offers are in that state".
    """
    response = client.get("/v1/marketplace/offers", params={"status": "inactive"})
    assert response.status_code == 400
    assert "Unknown offer status" in response.json()["error"]


def test_the_overview_counts_an_offer_stored_as_open_as_active(client):
    """`active_offers` compared against the literal "available" and missed it.

    The offer was in `total_offers` and not in `active_offers`, and its region and service type
    were left out of the lists the overview advertises: available, and invisible.
    """
    before = client.get("/v1/marketplace").json()["active_offers"]
    _new_offer(client, status="open")

    assert client.get("/v1/marketplace").json()["active_offers"] == before + 1


def test_an_offer_stored_as_open_can_be_booked(client):
    """The same comparison, in the route that turns an offer into money.

    `book_offer` checked `offer.status != "available"`, so the one offer in the deployed
    database stored under coordinator-api's word was refused with 400 — as unavailable, while
    being available.
    """
    offer_id = _new_offer(client, status="open")

    response = client.post(f"/v1/marketplace/offers/{offer_id}/book", json={"wallet": "aitbc1buyer"})
    assert response.status_code == 200
    assert client.get(f"/v1/marketplace/offers/{offer_id}").json()["status"] == "booked"


# --- Offer history ---


def test_get_offer_history_not_found(client):
    """Test get history for non-existent offer"""
    response = client.get("/v1/marketplace/offers/nonexistent-offer-id/history")
    assert response.status_code == 404


# --- Offer by plugin ID ---


def test_get_offer_by_plugin_id(client):
    """Test get offer by plugin ID"""
    response = client.get("/v1/marketplace/offer/test-plugin-id")
    assert response.status_code == 404


# --- Ratings ---


@pytest.fixture
def registered_service(client):
    """A registered software service, with any ratings it collects marked synced on teardown.

    `test_get_unsynced_ratings` asserts that the unsynced list is globally empty, and the
    whole module shares one database for the session — so a rating written here and left
    unsynced would fail that test whenever it happened to run second. Cleaning up after this
    fixture is cheaper than weakening an assertion that is doing real work.
    """
    plugin_id = "v23-81-registered-service"
    created = client.post(
        "/v1/marketplace/offer",
        json={"plugin_id": plugin_id, "service_type": "inference", "model": "test-model"},
    )
    assert created.status_code == 200

    yield plugin_id

    unsynced = client.get("/v1/marketplace/ratings/unsynced", params={"limit": 100}).json()["ratings"]
    stale = [rating["id"] for rating in unsynced if rating["service_id"] == plugin_id]
    if stale:
        client.post("/v1/marketplace/ratings/mark-synced", json=stale)


def test_get_ratings_by_service_id_not_found(client):
    """Ratings for a service that does not exist answer 404, not an empty list.

    This test used to assert 200 with `rating_count == 0` — it asserted the bug. The handler
    already looked the service up both ways round and already knew it was absent; it just
    answered anyway, with a body that a client cannot tell apart from a real service nobody
    has rated yet. "No such service" and "no ratings yet" are different answers and the caller
    needs different behaviour for each (V23-81).
    """
    response = client.get(
        "/v1/marketplace/offer/test-service-id/ratings",
        params={"limit": 10, "offset": 0},
    )
    assert response.status_code == 404
    assert response.json() == {"error": "Service not found"}


def test_get_ratings_for_a_registered_service(client, registered_service):
    """A service that exists but has no ratings still answers 200 with an empty list.

    The counterpart to the test above, and the reason the fix had to be a 404 rather than a
    different empty body: this is what "no ratings yet" is supposed to look like, and before
    V23-81 a missing service was indistinguishable from it.
    """
    response = client.get(
        f"/v1/marketplace/offer/{registered_service}/ratings",
        params={"limit": 10, "offset": 0},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["service_id"] == registered_service
    assert data["ratings"] == []
    assert data["service_info"] == {"avg_rating": 0.0, "rating_count": 0}


def test_rate_service_not_found(client):
    """Rating a service that does not exist answers 404 and writes nothing.

    It used to answer 200. `add_service_rating` never checked that the service existed, and
    the aggregate update it then called is guarded by `if service:` — so the rating row was
    written and no `avg_rating` anywhere was ever moved by it. The row is the part worth
    asserting: a 404 that still wrote would have fixed only the status code (V23-81).
    """
    response = client.post(
        "/v1/marketplace/offer/no-such-service/rate",
        json={"rating": 5.0, "reviewer_id": "aitbc1reviewer", "comment": "orphan"},
    )
    assert response.status_code == 404
    assert response.json() == {"error": "Service not found"}

    unsynced = client.get("/v1/marketplace/ratings/unsynced", params={"limit": 100}).json()["ratings"]
    assert [rating for rating in unsynced if rating["service_id"] == "no-such-service"] == []


def test_rate_a_registered_service(client, registered_service):
    """Rating a service that exists still works, and moves its aggregate.

    The existence check added in V23-81 sits in front of the happy path, so the happy path is
    worth pinning: the rating is stored and `rating_count` reflects it, which is exactly what
    the orphan rows never did.
    """
    response = client.post(
        f"/v1/marketplace/offer/{registered_service}/rate",
        json={"rating": 4.0, "reviewer_id": "aitbc1reviewer", "comment": "fine"},
    )
    assert response.status_code == 200
    assert response.json()["rating"]["service_id"] == registered_service

    ratings = client.get(
        f"/v1/marketplace/offer/{registered_service}/ratings",
        params={"limit": 10, "offset": 0},
    ).json()
    assert ratings["count"] == 1
    assert ratings["service_info"] == {"avg_rating": 4.0, "rating_count": 1}


def test_get_ratings_missing_params(client):
    """Test get ratings without required params returns 422"""
    response = client.get("/v1/marketplace/offer/test-service-id/ratings")
    assert response.status_code == 422


def test_get_unsynced_ratings(client):
    """Test get unsynced ratings (requires limit param)"""
    response = client.get("/v1/marketplace/ratings/unsynced", params={"limit": 10})
    assert response.status_code == 200
    assert response.json() == {"ratings": [], "count": 0}


def test_get_unsynced_ratings_missing_param(client):
    """Test get unsynced ratings without required limit param returns 422"""
    response = client.get("/v1/marketplace/ratings/unsynced")
    assert response.status_code == 422


# --- Offer query (plugin marketplace) ---


def test_get_offer_query(client):
    """Test offer query endpoint.

    This route asks the blockchain node for on-chain offers before reading the local table,
    but the call is wrapped in a `try`/`except` that logs a warning, so the answer is the same
    200 whether or not a node is listening on this machine.
    """
    response = client.get("/v1/marketplace/offer")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["offers"], list)
    assert data["total"] == len(data["offers"])


# --- Transactions ---


def test_get_transactions(client):
    """Test get transactions endpoint (requires query params)"""
    response = client.get(
        "/v1/transactions",
        params={
            "transaction_type": "marketplace",
            "action": "offer",
            "status": "active",
            "island_id": "test-island",
        },
    )
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_transactions_missing_params(client):
    """Test get transactions without required params returns 422"""
    response = client.get("/v1/transactions")
    assert response.status_code == 422
