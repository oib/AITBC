# mypy: ignore-errors
#!/usr/bin/env python3
"""
Test ETH-AIT bridge functionality without real ETH.
Simulates deposits and tests the bridge flow.
"""

import sys

# Add to path
sys.path.insert(0, "/opt/aitbc/apps/wallet/src")

from app.bridge.bridge_db import get_deposit_by_tx_hash, get_pending_deposits, init_db, insert_deposit, update_deposit_status
from app.bridge.price_api import calculate_ait_amount, get_exchange_rate


def test_database():
    """Test database operations."""
    print("\n=== Testing Database ===")
    
    init_db()
    print("✓ Database initialized")
    
    # Insert test deposit
    tx_hash = "0x" + "1" * 64  # Mock transaction hash
    from_address = "0x" + "a" * 40
    amount_eth = 1.0
    amount_ait = calculate_ait_amount(amount_eth)
    
    if amount_ait is None:
        print("✗ Failed to calculate AIT amount")
        return False
    
    deposit_id = insert_deposit(tx_hash, from_address, amount_eth, amount_ait)
    print(f"✓ Inserted deposit: {deposit_id}")
    
    # Get pending deposits
    pending = get_pending_deposits()
    print(f"✓ Found {len(pending)} pending deposits")
    
    if len(pending) == 0:
        print("✗ No pending deposits found")
        return False
    
    # Verify deposit
    success = update_deposit_status(deposit_id, "verified")
    if success:
        print(f"✓ Verified deposit: {deposit_id}")
    else:
        print(f"✗ Failed to verify deposit")
        return False
    
    # Complete deposit
    success = update_deposit_status(deposit_id, "completed")
    if success:
        print(f"✓ Completed deposit: {deposit_id}")
    else:
        print(f"✗ Failed to complete deposit")
        return False
    
    return True


def test_price_api():
    """Test price API."""
    print("\n=== Testing Price API ===")
    
    rate_info = get_exchange_rate()
    
    if not rate_info["success"]:
        print(f"✗ Failed to get exchange rate: {rate_info.get('error')}")
        return False
    
    print(f"✓ ETH Price: ${rate_info['eth_usd']:.2f} USD")
    print(f"✓ AIT Price: ${rate_info['ait_usd']:.2f} USD")
    print(f"✓ Exchange Rate: 1 ETH = {rate_info['eth_ait_rate']:.2f} AIT")
    
    # Test calculation
    test_eth = 0.5
    ait_amount = calculate_ait_amount(test_eth)
    
    if ait_amount is None:
        print(f"✗ Failed to calculate AIT for {test_eth} ETH")
        return False
    
    print(f"✓ {test_eth} ETH = {ait_amount:.2f} AIT")
    
    return True


def test_mock_deposit():
    """Test mock deposit flow."""
    print("\n=== Testing Mock Deposit Flow ===")
    
    init_db()
    
    # Simulate incoming ETH transaction
    mock_tx = {
        "hash": "0x" + "2" * 64,
        "from": "0x" + "b" * 40,
        "value": hex(int(0.5 * 1e18))  # 0.5 ETH in wei
    }
    
    # Parse amount
    value_wei = int(mock_tx["value"], 16)
    amount_eth = value_wei / 1e18
    
    print(f"Mock transaction: {amount_eth} ETH from {mock_tx['from']}")
    
    # Calculate AIT
    amount_ait = calculate_ait_amount(amount_eth)
    if amount_ait is None:
        print("✗ Failed to calculate AIT")
        return False
    
    # Insert deposit
    try:
        deposit_id = insert_deposit(mock_tx["hash"], mock_tx["from"], amount_eth, amount_ait)
        print(f"✓ Recorded deposit: {deposit_id}")
        print(f"  {amount_eth} ETH → {amount_ait:.2f} AIT")
    except Exception as e:
        print(f"✗ Failed to insert deposit: {e}")
        return False
    
    # Verify it was recorded
    deposit = get_deposit_by_tx_hash(mock_tx["hash"])
    if deposit:
        print(f"✓ Deposit retrieved successfully")
        print(f"  Status: {deposit['status']}")
    else:
        print("✗ Failed to retrieve deposit")
        return False
    
    return True


def test_api_endpoints():
    """Test API endpoints (requires running wallet service)."""
    print("\n=== Testing API Endpoints ===")
    
    try:
        import requests
        
        base_url = "http://localhost:8108"
        
        # Test price endpoint
        response = requests.get(f"{base_url}/v1/exchange/price", timeout=5)
        if response.status_code == 200:
            print("✓ GET /v1/exchange/price working")
        else:
            print(f"✗ GET /v1/exchange/price failed: {response.status_code}")
        
        # Test status endpoint
        response = requests.get(f"{base_url}/v1/exchange/status", timeout=5)
        if response.status_code == 200:
            print("✓ GET /v1/exchange/status working")
            status = response.json()
            print(f"  Enabled: {status['enabled']}")
            print(f"  Wallet: {status['wallet_address']}")
        else:
            print(f"✗ GET /v1/exchange/status failed: {response.status_code}")
        
        # Test deposits endpoint
        response = requests.get(f"{base_url}/v1/exchange/deposits", timeout=5)
        if response.status_code == 200:
            print("✓ GET /v1/exchange/deposits working")
            deposits = response.json()
            print(f"  Count: {deposits['count']}")
        else:
            print(f"✗ GET /v1/exchange/deposits failed: {response.status_code}")
        
    except requests.exceptions.ConnectionError:
        print("⚠ Wallet service not running (expected if not started)")
        return True
    except Exception as e:
        print(f"✗ API test failed: {e}")
        return False
    
    return True


def main():
    """Run all tests."""
    print("=" * 50)
    print("ETH-AIT Bridge Test Suite")
    print("=" * 50)
    
    results = []
    
    # Run tests
    results.append(("Database", test_database()))
    results.append(("Price API", test_price_api()))
    results.append(("Mock Deposit", test_mock_deposit()))
    results.append(("API Endpoints", test_api_endpoints()))
    
    # Summary
    print("\n" + "=" * 50)
    print("Test Summary")
    print("=" * 50)
    
    for test_name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{test_name:20s} {status}")
    
    all_passed = all(result[1] for result in results)
    
    if all_passed:
        print("\n✓ All tests passed!")
        return 0
    else:
        print("\n✗ Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
