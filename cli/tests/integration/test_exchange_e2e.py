#!/usr/bin/env python3
"""
Exchange End-to-End Test
Tests complete Bitcoin exchange workflow: rates → payment creation → monitoring → confirmation.
"""

import argparse
import sys
import time
from typing import Optional

import httpx

DEFAULT_COORDINATOR = "http://localhost:8000"
DEFAULT_API_KEY = "${CLIENT_API_KEY}"
DEFAULT_USER_ID = "e2e_test_user"
DEFAULT_AITBC_AMOUNT = 1000
DEFAULT_TIMEOUT = 300
POLL_INTERVAL = 10


def get_exchange_rates(client: httpx.Client, base_url: str) -> Optional[dict]:
    """Get current exchange rates"""
    response = client.get(
        f"{base_url}/v1/exchange/rates",
        timeout=10,
    )
    if response.status_code != 200:
        print(f"❌ Failed to get exchange rates: {response.status_code} {response.text}")
        return None
    return response.json()


def create_payment(client: httpx.Client, base_url: str, user_id: str, 
                  aitbc_amount: float, btc_amount: Optional[float] = None,
                  notes: Optional[str] = None) -> Optional[dict]:
    """Create a Bitcoin payment request"""
    if not btc_amount:
        # Get rates to calculate BTC amount
        rates = get_exchange_rates(client, base_url)
        if not rates:
            return None
        btc_amount = aitbc_amount / rates['btc_to_aitbc']
    
    payload = {
        "user_id": user_id,
        "aitbc_amount": aitbc_amount,
        "btc_amount": btc_amount
    }
    if notes:
        payload["notes"] = notes
    
    response = client.post(
        f"{base_url}/v1/exchange/create-payment",
        json=payload,
        timeout=10,
    )
    if response.status_code != 200:
        print(f"❌ Failed to create payment: {response.status_code} {response.text}")
        return None
    return response.json()


def get_payment_status(client: httpx.Client, base_url: str, payment_id: str) -> Optional[dict]:
    """Get payment status"""
    response = client.get(
        f"{base_url}/v1/exchange/payment-status/{payment_id}",
        timeout=10,
    )
    if response.status_code != 200:
        print(f"❌ Failed to get payment status: {response.status_code} {response.text}")
        return None
    return response.json()


def confirm_payment(client: httpx.Client, base_url: str, payment_id: str, 
                   tx_hash: str) -> Optional[dict]:
    """Confirm payment (simulating blockchain confirmation)"""
    response = client.post(
        f"{base_url}/v1/exchange/confirm-payment/{payment_id}",
        json={"tx_hash": tx_hash},
        timeout=10,
    )
    if response.status_code != 200:
        print(f"❌ Failed to confirm payment: {response.status_code} {response.text}")
        return None
    return response.json()


def get_market_stats(client: httpx.Client, base_url: str) -> Optional[dict]:
    """Get market statistics"""
    response = client.get(
        f"{base_url}/v1/exchange/market-stats",
        timeout=10,
    )
    if response.status_code != 200:
        print(f"❌ Failed to get market stats: {response.status_code} {response.text}")
        return None
    return response.json()


def get_wallet_balance(client: httpx.Client, base_url: str) -> Optional[dict]:
    """Get Bitcoin wallet balance"""
    response = client.get(
        f"{base_url}/v1/exchange/wallet/balance",
        timeout=10,
    )
    if response.status_code != 200:
        print(f"❌ Failed to get wallet balance: {response.status_code} {response.text}")
        return None
    return response.json()


def monitor_payment_confirmation(client: httpx.Client, base_url: str, 
                                payment_id: str, timeout: int) -> Optional[str]:
    """Monitor payment until confirmed or timeout"""
    deadline = time.time() + timeout
    
    while time.time() < deadline:
        status_data = get_payment_status(client, base_url, payment_id)
        if not status_data:
            return None
            
        status = status_data.get("status")
        print(f"⏳ Payment status: {status}")
        
        if status == "confirmed":
            return status
        elif status == "expired":
            print("❌ Payment expired")
            return status
        
        time.sleep(POLL_INTERVAL)
    
    print("❌ Payment monitoring timed out")
    return None


def test_basic_exchange_workflow(client: httpx.Client, base_url: str, user_id: str,
                                aitbc_amount: float) -> bool:
    """Test basic exchange workflow"""
    print("🧪 Testing basic exchange workflow...")
    
    # Step 1: Get exchange rates
    print("💱 Getting exchange rates...")
    rates = get_exchange_rates(client, base_url)
    if not rates:
        print("❌ Failed to get exchange rates")
        return False
    
    print(f"✅ Exchange rates: 1 BTC = {rates['btc_to_aitbc']:,} AITBC")
    print(f"   Fee: {rates['fee_percent']}%")
    
    # Step 2: Create payment
    print(f"💰 Creating payment for {aitbc_amount} AITBC...")
    payment = create_payment(client, base_url, user_id, aitbc_amount, 
                           notes="E2E test payment")
    if not payment:
        print("❌ Failed to create payment")
        return False
    
    print(f"✅ Payment created: {payment['payment_id']}")
    print(f"   Send {payment['btc_amount']:.8f} BTC to: {payment['payment_address']}")
    print(f"   Expires at: {payment['expires_at']}")
    
    # Step 3: Check initial payment status
    print("📋 Checking initial payment status...")
    status = get_payment_status(client, base_url, payment['payment_id'])
    if not status:
        print("❌ Failed to get payment status")
        return False
    
    print(f"✅ Initial status: {status['status']}")
    
    # Step 4: Simulate payment confirmation
    print("🔗 Simulating blockchain confirmation...")
    tx_hash = f"test_tx_{int(time.time())}"
    confirmation = confirm_payment(client, base_url, payment['payment_id'], tx_hash)
    if not confirmation:
        print("❌ Failed to confirm payment")
        return False
    
    print(f"✅ Payment confirmed with transaction: {tx_hash}")
    
    # Step 5: Verify final status
    print("📄 Verifying final payment status...")
    final_status = get_payment_status(client, base_url, payment['payment_id'])
    if not final_status:
        print("❌ Failed to get final payment status")
        return False
    
    if final_status['status'] != 'confirmed':
        print(f"❌ Expected confirmed status, got: {final_status['status']}")
        return False
    
    print(f"✅ Payment confirmed! AITBC amount: {final_status['aitbc_amount']}")
    
    return True


def test_market_statistics(client: httpx.Client, base_url: str) -> bool:
    """Test market statistics functionality"""
    print("🧪 Testing market statistics...")
    
    stats = get_market_stats(client, base_url)
    if not stats:
        print("❌ Failed to get market stats")
        return False
    
    print(f"📊 Market Statistics:")
    print(f"  Current price: ${stats['price']:.8f} per AITBC")
    print(f"  24h change: {stats['price_change_24h']:+.2f}%")
    print(f"  Daily volume: {stats['daily_volume']:,} AITBC")
    print(f"  Daily volume (BTC): {stats['daily_volume_btc']:.8f} BTC")
    print(f"  Total payments: {stats['total_payments']}")
    print(f"  Pending payments: {stats['pending_payments']}")
    
    return True


def test_wallet_operations(client: httpx.Client, base_url: str) -> bool:
    """Test wallet operations"""
    print("🧪 Testing wallet operations...")
    
    balance = get_wallet_balance(client, base_url)
    if not balance:
        print("❌ Failed to get wallet balance (service may be unavailable)")
        return True  # Don't fail test if wallet service is unavailable
    
    print(f"💰 Wallet Balance:")
    print(f"  Address: {balance['address']}")
    print(f"  Balance: {balance['balance']:.8f} BTC")
    print(f"  Unconfirmed: {balance['unconfirmed_balance']:.8f} BTC")
    print(f"  Total received: {balance['total_received']:.8f} BTC")
    print(f"  Total sent: {balance['total_sent']:.8f} BTC")
    
    return True


def test_multiple_payments_scenario(client: httpx.Client, base_url: str, 
                                  user_id: str) -> bool:
    """Test multiple payments scenario"""
    print("🧪 Testing multiple payments scenario...")
    
    # Create multiple payments
    payment_amounts = [500, 1000, 1500]
    payment_ids = []
    
    for i, amount in enumerate(payment_amounts):
        print(f"💰 Creating payment {i+1}: {amount} AITBC...")
        payment = create_payment(client, base_url, f"{user_id}_{i}", amount,
                               notes=f"Multi-payment test {i+1}")
        if not payment:
            print(f"❌ Failed to create payment {i+1}")
            return False
        
        payment_ids.append(payment['payment_id'])
        print(f"✅ Payment {i+1} created: {payment['payment_id']}")
        time.sleep(1)  # Small delay between payments
    
    # Confirm all payments
    for i, payment_id in enumerate(payment_ids):
        print(f"🔗 Confirming payment {i+1}...")
        tx_hash = f"multi_tx_{i}_{int(time.time())}"
        confirmation = confirm_payment(client, base_url, payment_id, tx_hash)
        if not confirmation:
            print(f"❌ Failed to confirm payment {i+1}")
            return False
        print(f"✅ Payment {i+1} confirmed")
        time.sleep(0.5)
    
    # Check updated market stats
    print("📊 Checking updated market statistics...")
    final_stats = get_market_stats(client, base_url)
    if final_stats:
        print(f"✅ Final stats: {final_stats['total_payments']} total payments")
    
    return True


def test_error_scenarios(client: httpx.Client, base_url: str) -> bool:
    """Test error handling scenarios"""
    print("🧪 Testing error scenarios...")
    
    # Test invalid payment creation
    print("❌ Testing invalid payment creation...")
    invalid_payment = create_payment(client, base_url, "test_user", -100)
    if invalid_payment:
        print("❌ Expected error for negative amount, but got success")
        return False
    print("✅ Correctly rejected negative amount")
    
    # Test non-existent payment status
    print("❌ Testing non-existent payment status...")
    fake_status = get_payment_status(client, base_url, "fake_payment_id")
    if fake_status:
        print("❌ Expected error for fake payment ID, but got success")
        return False
    print("✅ Correctly rejected fake payment ID")
    
    # Test invalid payment confirmation
    print("❌ Testing invalid payment confirmation...")
    fake_confirmation = confirm_payment(client, base_url, "fake_payment_id", "fake_tx")
    if fake_confirmation:
        print("❌ Expected error for fake payment confirmation, but got success")
        return False
    print("✅ Correctly rejected fake payment confirmation")
    
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Exchange end-to-end test")
    parser.add_argument("--url", default=DEFAULT_COORDINATOR, help="Coordinator base URL")
    parser.add_argument("--api-key", default=DEFAULT_API_KEY, help="Client API key")
    parser.add_argument("--user-id", default=DEFAULT_USER_ID, help="User ID for payments")
    parser.add_argument("--aitbc-amount", type=float, default=DEFAULT_AITBC_AMOUNT, help="AITBC amount for test payment")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="Timeout in seconds")
    parser.add_argument("--test", choices=["basic", "stats", "wallet", "multi", "errors", "all"], 
                       default="all", help="Test scenario to run")
    args = parser.parse_args()

    with httpx.Client() as client:
        print("🚀 Starting Exchange end-to-end test...")
        print(f"📍 Coordinator: {args.url}")
        print(f"🆔 User ID: {args.user_id}")
        print(f"💰 Test amount: {args.aitbc_amount} AITBC")
        print()
        
        success = True
        
        if args.test in ["basic", "all"]:
            success &= test_basic_exchange_workflow(client, args.url, args.user_id, args.aitbc_amount)
            print()
        
        if args.test in ["stats", "all"]:
            success &= test_market_statistics(client, args.url)
            print()
        
        if args.test in ["wallet", "all"]:
            success &= test_wallet_operations(client, args.url)
            print()
        
        if args.test in ["multi", "all"]:
            success &= test_multiple_payments_scenario(client, args.url, args.user_id)
            print()
        
        if args.test in ["errors", "all"]:
            success &= test_error_scenarios(client, args.url)
            print()
        
        if success:
            print("✅ All exchange tests completed successfully!")
            return 0
        else:
            print("❌ Some exchange tests failed!")
            return 1


if __name__ == "__main__":
    sys.exit(main())
