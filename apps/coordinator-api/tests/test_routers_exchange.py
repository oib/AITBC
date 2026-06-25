"""Tests for exchange router with Redis-backed state."""

import pytest


@pytest.fixture
def exchange_client(client, monkeypatch):
    """Return the shared TestClient fixture with the payment-monitoring
    background task stubbed out.

    The real ``monitor_payment`` runs an infinite ``while True`` loop with
    ``asyncio.sleep(30)``. Under ``TestClient`` the background task shares the
    request event loop, so it hangs the client and causes test timeouts. We
    replace it with a no-op so payment creation returns immediately.
    """
    from app.contexts.infrastructure.routers import exchange as exchange_router

    async def _noop_monitor(_payment_id: str) -> None:
        return None

    monkeypatch.setattr(exchange_router, "monitor_payment", _noop_monitor)
    return client


def test_create_payment(exchange_client):
    """Test creating a Bitcoin payment request."""
    response = exchange_client.post(
        "/v1/exchange/create-payment",
        json={
            "user_id": "test-user-123",
            "aitbc_amount": 10000.0,
            "btc_amount": 0.1,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "pending"
    assert data["user_id"] == "test-user-123"
    assert "payment_id" in data
    assert "expires_at" in data


def test_create_payment_invalid_amount(exchange_client):
    """Test payment creation with an invalid (negative) amount.

    The ``ExchangePaymentRequest`` schema enforces ``gt=0`` on ``aitbc_amount``,
    so a negative value is rejected at the validation layer with 422 before the
    handler's own "Invalid amount" check is reached.
    """
    response = exchange_client.post(
        "/v1/exchange/create-payment",
        json={
            "user_id": "test-user-123",
            "aitbc_amount": -100,
            "btc_amount": 0.1,
        },
    )
    assert response.status_code == 422


def test_create_payment_amount_mismatch(exchange_client):
    """Test payment creation with a BTC amount that does not match the
    configured exchange rate. This exercises the handler-level 400 path.
    """
    response = exchange_client.post(
        "/v1/exchange/create-payment",
        json={
            "user_id": "test-user-123",
            "aitbc_amount": 10000.0,
            "btc_amount": 0.5,  # expected 0.1 at 100k AITBC/BTC
        },
    )
    assert response.status_code == 400
    assert "Amount mismatch" in response.json()["detail"]


def test_get_payment_status(exchange_client):
    """Test getting payment status."""
    # Create a payment first
    create_resp = exchange_client.post(
        "/v1/exchange/create-payment",
        json={
            "user_id": "test-user-123",
            "aitbc_amount": 10000.0,
            "btc_amount": 0.1,
        },
    )
    payment_id = create_resp.json()["payment_id"]

    # Get status
    status_resp = exchange_client.get(f"/v1/exchange/payment-status/{payment_id}")
    assert status_resp.status_code == 200
    data = status_resp.json()
    assert data["payment_id"] == payment_id
    assert data["status"] == "pending"


def test_get_payment_status_not_found(exchange_client):
    """Test getting status for non-existent payment."""
    response = exchange_client.get("/v1/exchange/payment-status/nonexistent-id")
    assert response.status_code == 404
    assert "Payment not found" in response.json()["detail"]


def test_confirm_payment(exchange_client):
    """Test confirming a payment."""
    # Create a payment first
    create_resp = exchange_client.post(
        "/v1/exchange/create-payment",
        json={
            "user_id": "test-user-123",
            "aitbc_amount": 10000.0,
            "btc_amount": 0.1,
        },
    )
    payment_id = create_resp.json()["payment_id"]

    # Confirm payment
    confirm_resp = exchange_client.post(f"/v1/exchange/confirm-payment/{payment_id}?tx_hash=abc123")
    assert confirm_resp.status_code == 200
    data = confirm_resp.json()
    assert data["status"] == "ok"
    assert data["payment_id"] == payment_id


def test_get_exchange_rates(exchange_client):
    """Test getting exchange rates."""
    response = exchange_client.get("/v1/exchange/rates")
    assert response.status_code == 200
    data = response.json()
    assert "btc_to_aitbc" in data
    assert "aitbc_to_btc" in data
    assert data["fee_percent"] == 0.5


def test_get_market_stats(exchange_client):
    """Test getting market statistics."""
    response = exchange_client.get("/v1/exchange/market-stats")
    assert response.status_code == 200
    data = response.json()
    assert "price" in data
    assert "daily_volume" in data
    assert "total_payments" in data
    assert "pending_payments" in data
