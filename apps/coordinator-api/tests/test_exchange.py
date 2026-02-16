"""Tests for exchange API endpoints"""

import pytest
import time
import uuid
from fastapi.testclient import TestClient
from sqlmodel import Session, delete

from app.config import settings
from app.main import create_app
from app.routers.exchange import payments, BITCOIN_CONFIG


@pytest.fixture(scope="module", autouse=True)
def _init_db(tmp_path_factory):
    db_file = tmp_path_factory.mktemp("data") / "exchange.db"
    settings.database_url = f"sqlite:///{db_file}"
    # Initialize database if needed
    yield


@pytest.fixture()
def session():
    # For this test, we'll use in-memory storage
    yield None


@pytest.fixture()
def client():
    app = create_app()
    return TestClient(app)


@pytest.fixture(autouse=True)
def clear_payments():
    """Clear payments before each test"""
    payments.clear()
    yield
    payments.clear()


class TestExchangeRatesEndpoint:
    """Test exchange rates endpoint"""
    
    def test_get_exchange_rates_success(self, client: TestClient):
        """Test successful exchange rates retrieval"""
        response = client.get("/v1/exchange/rates")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "btc_to_aitbc" in data
        assert "aitbc_to_btc" in data
        assert "fee_percent" in data
        
        # Verify rates are reasonable
        assert data["btc_to_aitbc"] > 0
        assert data["aitbc_to_btc"] > 0
        assert data["fee_percent"] >= 0
        
        # Verify mathematical relationship
        expected_aitbc_to_btc = 1.0 / data["btc_to_aitbc"]
        assert abs(data["aitbc_to_btc"] - expected_aitbc_to_btc) < 0.00000001


class TestExchangeCreatePaymentEndpoint:
    """Test exchange create-payment endpoint"""
    
    def test_create_payment_success(self, client: TestClient):
        """Test successful payment creation"""
        payload = {
            "user_id": "test_user_123",
            "aitbc_amount": 1000,
            "btc_amount": 0.01
        }
        
        response = client.post("/v1/exchange/create-payment", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "payment_id" in data
        assert data["user_id"] == payload["user_id"]
        assert data["aitbc_amount"] == payload["aitbc_amount"]
        assert data["btc_amount"] == payload["btc_amount"]
        assert data["payment_address"] == BITCOIN_CONFIG['main_address']
        assert data["status"] == "pending"
        assert "created_at" in data
        assert "expires_at" in data
        
        # Verify payment was stored
        assert data["payment_id"] in payments
        stored_payment = payments[data["payment_id"]]
        assert stored_payment["user_id"] == payload["user_id"]
        assert stored_payment["aitbc_amount"] == payload["aitbc_amount"]
        assert stored_payment["btc_amount"] == payload["btc_amount"]
    
    def test_create_payment_invalid_amounts(self, client: TestClient):
        """Test payment creation with invalid amounts"""
        # Test zero AITBC amount
        payload1 = {
            "user_id": "test_user",
            "aitbc_amount": 0,
            "btc_amount": 0.01
        }
        response1 = client.post("/v1/exchange/create-payment", json=payload1)
        assert response1.status_code == 400
        assert "Invalid amount" in response1.json()["detail"]
        
        # Test negative BTC amount
        payload2 = {
            "user_id": "test_user",
            "aitbc_amount": 1000,
            "btc_amount": -0.01
        }
        response2 = client.post("/v1/exchange/create-payment", json=payload2)
        assert response2.status_code == 400
        assert "Invalid amount" in response2.json()["detail"]
    
    def test_create_payment_amount_mismatch(self, client: TestClient):
        """Test payment creation with amount mismatch"""
        payload = {
            "user_id": "test_user",
            "aitbc_amount": 1000,  # Should be 0.01 BTC at 100000 rate
            "btc_amount": 0.02     # This is double the expected amount
        }
        
        response = client.post("/v1/exchange/create-payment", json=payload)
        assert response.status_code == 400
        assert "Amount mismatch" in response.json()["detail"]
    
    def test_create_payment_rounding_tolerance(self, client: TestClient):
        """Test payment creation with small rounding differences"""
        payload = {
            "user_id": "test_user",
            "aitbc_amount": 1000,
            "btc_amount": 0.01000000001  # Very small difference should be allowed
        }
        
        response = client.post("/v1/exchange/create-payment", json=payload)
        assert response.status_code == 200


class TestExchangePaymentStatusEndpoint:
    """Test exchange payment-status endpoint"""
    
    def test_get_payment_status_success(self, client: TestClient):
        """Test successful payment status retrieval"""
        # First create a payment
        create_payload = {
            "user_id": "test_user",
            "aitbc_amount": 500,
            "btc_amount": 0.005
        }
        create_response = client.post("/v1/exchange/create-payment", json=create_payload)
        payment_id = create_response.json()["payment_id"]
        
        # Get payment status
        response = client.get(f"/v1/exchange/payment-status/{payment_id}")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["payment_id"] == payment_id
        assert data["user_id"] == create_payload["user_id"]
        assert data["aitbc_amount"] == create_payload["aitbc_amount"]
        assert data["btc_amount"] == create_payload["btc_amount"]
        assert data["status"] == "pending"
        assert data["confirmations"] == 0
        assert data["tx_hash"] is None
    
    def test_get_payment_status_not_found(self, client: TestClient):
        """Test payment status for non-existent payment"""
        fake_payment_id = "nonexistent_payment_id"
        response = client.get(f"/v1/exchange/payment-status/{fake_payment_id}")
        
        assert response.status_code == 404
        assert "Payment not found" in response.json()["detail"]
    
    def test_get_payment_status_expired(self, client: TestClient):
        """Test payment status for expired payment"""
        # Create a payment with expired timestamp
        payment_id = str(uuid.uuid4())
        expired_payment = {
            'payment_id': payment_id,
            'user_id': 'test_user',
            'aitbc_amount': 1000,
            'btc_amount': 0.01,
            'payment_address': BITCOIN_CONFIG['main_address'],
            'status': 'pending',
            'created_at': int(time.time()) - 7200,  # 2 hours ago
            'expires_at': int(time.time()) - 3600,  # 1 hour ago (expired)
            'confirmations': 0,
            'tx_hash': None
        }
        payments[payment_id] = expired_payment
        
        # Get payment status
        response = client.get(f"/v1/exchange/payment-status/{payment_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "expired"


class TestExchangeConfirmPaymentEndpoint:
    """Test exchange confirm-payment endpoint"""
    
    def test_confirm_payment_success(self, client: TestClient):
        """Test successful payment confirmation"""
        # First create a payment
        create_payload = {
            "user_id": "test_user",
            "aitbc_amount": 1000,
            "btc_amount": 0.01
        }
        create_response = client.post("/v1/exchange/create-payment", json=create_payload)
        payment_id = create_response.json()["payment_id"]
        
        # Confirm payment
        confirm_payload = {"tx_hash": "test_transaction_hash_123"}
        response = client.post(f"/v1/exchange/confirm-payment/{payment_id}", 
                              json=confirm_payload)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "ok"
        assert data["payment_id"] == payment_id
        assert data["aitbc_amount"] == create_payload["aitbc_amount"]
        
        # Verify payment was updated
        payment = payments[payment_id]
        assert payment["status"] == "confirmed"
        assert payment["tx_hash"] == confirm_payload["tx_hash"]
        assert "confirmed_at" in payment
    
    def test_confirm_payment_not_found(self, client: TestClient):
        """Test payment confirmation for non-existent payment"""
        fake_payment_id = "nonexistent_payment_id"
        confirm_payload = {"tx_hash": "test_tx_hash"}
        response = client.post(f"/v1/exchange/confirm-payment/{fake_payment_id}", 
                              json=confirm_payload)
        
        assert response.status_code == 404
        assert "Payment not found" in response.json()["detail"]
    
    def test_confirm_payment_not_pending(self, client: TestClient):
        """Test payment confirmation for non-pending payment"""
        # Create and confirm a payment
        create_payload = {
            "user_id": "test_user",
            "aitbc_amount": 1000,
            "btc_amount": 0.01
        }
        create_response = client.post("/v1/exchange/create-payment", json=create_payload)
        payment_id = create_response.json()["payment_id"]
        
        # First confirmation
        confirm_payload = {"tx_hash": "test_tx_hash_1"}
        client.post(f"/v1/exchange/confirm-payment/{payment_id}", json=confirm_payload)
        
        # Try to confirm again
        confirm_payload2 = {"tx_hash": "test_tx_hash_2"}
        response = client.post(f"/v1/exchange/confirm-payment/{payment_id}", 
                              json=confirm_payload2)
        
        assert response.status_code == 400
        assert "Payment not in pending state" in response.json()["detail"]


class TestExchangeMarketStatsEndpoint:
    """Test exchange market-stats endpoint"""
    
    def test_get_market_stats_empty(self, client: TestClient):
        """Test market stats with no payments"""
        response = client.get("/v1/exchange/market-stats")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "price" in data
        assert "price_change_24h" in data
        assert "daily_volume" in data
        assert "daily_volume_btc" in data
        assert "total_payments" in data
        assert "pending_payments" in data
        
        # With no payments, these should be 0
        assert data["daily_volume"] == 0
        assert data["daily_volume_btc"] == 0
        assert data["total_payments"] == 0
        assert data["pending_payments"] == 0
    
    def test_get_market_stats_with_payments(self, client: TestClient):
        """Test market stats with payments"""
        current_time = int(time.time())
        
        # Create some confirmed payments (within 24h)
        for i in range(3):
            payment_id = str(uuid.uuid4())
            payment = {
                'payment_id': payment_id,
                'user_id': f'user_{i}',
                'aitbc_amount': 1000 * (i + 1),
                'btc_amount': 0.01 * (i + 1),
                'payment_address': BITCOIN_CONFIG['main_address'],
                'status': 'confirmed',
                'created_at': current_time - 3600,  # 1 hour ago
                'expires_at': current_time + 3600,
                'confirmations': 1,
                'tx_hash': f'tx_hash_{i}',
                'confirmed_at': current_time - 1800  # 30 minutes ago
            }
            payments[payment_id] = payment
        
        # Create some pending payments
        for i in range(2):
            payment_id = str(uuid.uuid4())
            payment = {
                'payment_id': payment_id,
                'user_id': f'pending_user_{i}',
                'aitbc_amount': 500 * (i + 1),
                'btc_amount': 0.005 * (i + 1),
                'payment_address': BITCOIN_CONFIG['main_address'],
                'status': 'pending',
                'created_at': current_time - 1800,  # 30 minutes ago
                'expires_at': current_time + 1800,
                'confirmations': 0,
                'tx_hash': None
            }
            payments[payment_id] = payment
        
        # Create an old confirmed payment (older than 24h)
        old_payment_id = str(uuid.uuid4())
        old_payment = {
            'payment_id': old_payment_id,
            'user_id': 'old_user',
            'aitbc_amount': 2000,
            'btc_amount': 0.02,
            'payment_address': BITCOIN_CONFIG['main_address'],
            'status': 'confirmed',
            'created_at': current_time - 86400 - 3600,  # 25 hours ago
            'expires_at': current_time - 86400 + 3600,
            'confirmations': 1,
            'tx_hash': 'old_tx_hash',
            'confirmed_at': current_time - 86400  # 24 hours ago
        }
        payments[old_payment_id] = old_payment
        
        response = client.get("/v1/exchange/market-stats")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify calculations
        # Confirmed payments: 1000 + 2000 + 3000 = 6000 AITBC
        # Pending payments: 500 + 1000 = 1500 AITBC
        # Daily volume should only include recent confirmed payments
        expected_daily_volume = 1000 + 2000 + 3000  # 6000 AITBC
        expected_daily_volume_btc = expected_daily_volume / BITCOIN_CONFIG['exchange_rate']
        
        assert data["total_payments"] == 3  # Only confirmed payments
        assert data["pending_payments"] == 2
        assert data["daily_volume"] == expected_daily_volume
        assert abs(data["daily_volume_btc"] - expected_daily_volume_btc) < 0.00000001


class TestExchangeWalletEndpoints:
    """Test exchange wallet endpoints"""
    
    def test_wallet_balance_endpoint(self, client: TestClient):
        """Test wallet balance endpoint"""
        # This test may fail if bitcoin_wallet service is not available
        # We'll test the endpoint structure and error handling
        response = client.get("/v1/exchange/wallet/balance")
        
        # The endpoint should exist, but may return 500 if service is unavailable
        assert response.status_code in [200, 500]
        
        if response.status_code == 200:
            data = response.json()
            # Verify response structure if successful
            expected_fields = ["address", "balance", "unconfirmed_balance", 
                             "total_received", "total_sent"]
            for field in expected_fields:
                assert field in data
    
    def test_wallet_info_endpoint(self, client: TestClient):
        """Test wallet info endpoint"""
        response = client.get("/v1/exchange/wallet/info")
        
        # The endpoint should exist, but may return 500 if service is unavailable
        assert response.status_code in [200, 500]
        
        if response.status_code == 200:
            data = response.json()
            # Verify response structure if successful
            expected_fields = ["address", "balance", "unconfirmed_balance", 
                             "total_received", "total_sent", "transactions", 
                             "network", "block_height"]
            for field in expected_fields:
                assert field in data


class TestExchangeIntegration:
    """Test exchange integration scenarios"""
    
    def test_complete_payment_lifecycle(self, client: TestClient):
        """Test complete payment lifecycle: create → check status → confirm"""
        # Step 1: Create payment
        create_payload = {
            "user_id": "integration_user",
            "aitbc_amount": 1500,
            "btc_amount": 0.015
        }
        create_response = client.post("/v1/exchange/create-payment", json=create_payload)
        assert create_response.status_code == 200
        payment_id = create_response.json()["payment_id"]
        
        # Step 2: Check initial status
        status_response = client.get(f"/v1/exchange/payment-status/{payment_id}")
        assert status_response.status_code == 200
        status_data = status_response.json()
        assert status_data["status"] == "pending"
        assert status_data["confirmations"] == 0
        
        # Step 3: Confirm payment
        confirm_payload = {"tx_hash": "integration_tx_hash"}
        confirm_response = client.post(f"/v1/exchange/confirm-payment/{payment_id}", 
                                      json=confirm_payload)
        assert confirm_response.status_code == 200
        
        # Step 4: Check final status
        final_status_response = client.get(f"/v1/exchange/payment-status/{payment_id}")
        assert final_status_response.status_code == 200
        final_status_data = final_status_response.json()
        assert final_status_data["status"] == "confirmed"
        assert final_status_data["tx_hash"] == "integration_tx_hash"
        assert "confirmed_at" in final_status_data
    
    def test_market_stats_update_after_payment(self, client: TestClient):
        """Test that market stats update after payment confirmation"""
        # Get initial stats
        initial_stats_response = client.get("/v1/exchange/market-stats")
        assert initial_stats_response.status_code == 200
        initial_stats = initial_stats_response.json()
        initial_total = initial_stats["total_payments"]
        
        # Create and confirm payment
        create_payload = {
            "user_id": "stats_user",
            "aitbc_amount": 2000,
            "btc_amount": 0.02
        }
        create_response = client.post("/v1/exchange/create-payment", json=create_payload)
        payment_id = create_response.json()["payment_id"]
        
        confirm_payload = {"tx_hash": "stats_tx_hash"}
        client.post(f"/v1/exchange/confirm-payment/{payment_id}", json=confirm_payload)
        
        # Check updated stats
        updated_stats_response = client.get("/v1/exchange/market-stats")
        assert updated_stats_response.status_code == 200
        updated_stats = updated_stats_response.json()
        
        # Total payments should have increased
        assert updated_stats["total_payments"] == initial_total + 1
        assert updated_stats["daily_volume"] >= initial_stats["daily_volume"]
