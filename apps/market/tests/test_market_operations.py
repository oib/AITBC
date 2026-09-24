"""Idempotency-Key adoption on the market service's mutating endpoints.

Replays return the originally recorded response; a key reused with a
different body conflicts. ``create_offer`` is non-adoptable — an abandoned
attempt goes ``uncertain`` rather than minting a duplicate offer.
"""

import pytest
from fastapi.testclient import TestClient

import market_service.main as market_main


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("MARKET_OPERATIONS_DB", str(tmp_path / "ops.db"))
    market_main._operations_ledger = None
    yield TestClient(market_main.app)
    market_main._operations_ledger = None


class TestCreateOfferIdempotency:
    BODY = {"provider": "0xprovider", "price": "1.5", "capacity": 4}

    def test_replay_returns_same_offer(self, client):
        r1 = client.post("/v1/market/offers", json=self.BODY, headers={"Idempotency-Key": "c1"})
        assert r1.status_code == 200
        offer_id = r1.json()["id"]
        r2 = client.post("/v1/market/offers", json=self.BODY, headers={"Idempotency-Key": "c1"})
        assert r2.status_code == 200
        assert r2.json()["id"] == offer_id

    def test_same_key_different_body_conflicts(self, client):
        client.post("/v1/market/offers", json=self.BODY, headers={"Idempotency-Key": "c2"})
        r = client.post("/v1/market/offers", json={**self.BODY, "price": "9"}, headers={"Idempotency-Key": "c2"})
        assert r.status_code == 409


class TestBookOfferIdempotency:
    def _offer(self, client) -> str:
        r = client.post("/v1/market/offers", json={"provider": "0xp"}, headers={"Idempotency-Key": "seed"})
        return r.json()["id"]

    def test_book_replays_after_success(self, client):
        offer_id = self._offer(client)
        body = {"wallet": "0xbuyer", "duration_hours": 1}
        r1 = client.post(f"/v1/market/offers/{offer_id}/book", json=body, headers={"Idempotency-Key": "b1"})
        assert r1.status_code == 200
        # The offer is now booked — a replay must return the recorded result,
        # not hit the "not available" state check.
        r2 = client.post(f"/v1/market/offers/{offer_id}/book", json=body, headers={"Idempotency-Key": "b1"})
        assert r2.status_code == 200
        assert r2.json() == r1.json()

    def test_book_rejection_is_memoized(self, client):
        r = client.post("/v1/market/offers/nonexistent/book", json={"wallet": "0xb"}, headers={"Idempotency-Key": "b2"})
        assert r.status_code == 404
        # Replay gets the recorded 404 verbatim.
        r2 = client.post("/v1/market/offers/nonexistent/book", json={"wallet": "0xb"}, headers={"Idempotency-Key": "b2"})
        assert r2.status_code == 404


class TestCancelOfferIdempotency:
    def test_cancel_replays(self, client):
        r = client.post("/v1/market/offers", json={"provider": "0xp"}, headers={"Idempotency-Key": "seed2"})
        offer_id = r.json()["id"]
        r1 = client.post(f"/v1/market/offers/{offer_id}/cancel", headers={"Idempotency-Key": "x1"})
        assert r1.status_code == 200
        # Replay returns the recorded cancellation even though the offer's
        # state now reads "cancelled" to a fresh request.
        r2 = client.post(f"/v1/market/offers/{offer_id}/cancel", headers={"Idempotency-Key": "x1"})
        assert r2.status_code == 200
        assert r2.json() == r1.json()


class TestMatchRequestIdempotency:
    """``POST /v1/market/match`` reserves an offer before the coordinator task
    is queued -- a replay must not reserve a second one."""

    BODY = {"requirements": {"gpu_model": "any"}, "max_price": "10"}

    def _seed_offer(self, client) -> None:
        r = client.post("/v1/market/offers", json={"provider": "0xp", "price": "1"}, headers={"Idempotency-Key": "m-seed"})
        assert r.status_code == 200

    def test_match_replays_verbatim(self, client):
        self._seed_offer(client)
        r1 = client.post("/v1/market/match", json=self.BODY, headers={"Idempotency-Key": "m1"})
        assert r1.status_code == 200
        r2 = client.post("/v1/market/match", json=self.BODY, headers={"Idempotency-Key": "m1"})
        assert r2.status_code == 200
        assert r2.json() == r1.json()

    def test_match_same_key_different_body_conflicts(self, client):
        self._seed_offer(client)
        client.post("/v1/market/match", json=self.BODY, headers={"Idempotency-Key": "m2"})
        r = client.post("/v1/market/match", json={**self.BODY, "max_price": "999"}, headers={"Idempotency-Key": "m2"})
        assert r.status_code == 409

    def test_match_no_match_result_is_memoized(self, client):
        """With no offers, ``no_match`` is the recorded outcome and replays."""
        r1 = client.post("/v1/market/match", json=self.BODY, headers={"Idempotency-Key": "m3"})
        assert r1.status_code == 200
        r2 = client.post("/v1/market/match", json=self.BODY, headers={"Idempotency-Key": "m3"})
        assert r2.status_code == 200
        assert r2.json() == r1.json()
