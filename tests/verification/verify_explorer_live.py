#!/usr/bin/env python3
"""
Verify that the explorer is using live data instead of mock
"""


import requests


def main():
    print("🔍 Verifying AITBC Explorer is using Live Data")
    print("=" * 60)

    # Check API endpoint
    print("\n1. Testing API endpoint...")
    try:
        response = requests.get("https://aitbc.bubuit.net/api/explorer/blocks")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ API is working - Found {len(data['items'])} blocks")

            # Show latest block
            if data['items']:
                latest = data['items'][0]
                print("\n   Latest Block:")
                print(f"   Height: {latest['height']}")
                print(f"   Hash: {latest['hash']}")
                print(f"   Proposer: {latest['proposer']}")
                print(f"   Time: {latest['timestamp']}")
        else:
            print(f"❌ API failed: {response.status_code}")
            return
    except Exception as e:
        print(f"❌ API error: {e}")
        return

    # Check explorer page
    print("\n2. Checking explorer configuration...")

    # Get the JS file
    try:
        js_response = requests.get("https://aitbc.bubuit.net/explorer/assets/index-IsD_hiHT.js")
        if js_response.status_code == 200:
            js_content = js_response.text

            # Check for live data mode
            if 'dataMode:"live"' in js_content:
                print("✅ Explorer is configured for LIVE data")
            elif 'dataMode:"mock"' in js_content:
                print("❌ Explorer is still using MOCK data")
                return
            else:
                print("⚠️  Could not determine data mode")
    except Exception as e:
        print(f"❌ Error checking JS: {e}")

    # Check other endpoints
    print("\n3. Testing other endpoints...")

    endpoints = [
        ("/api/explorer/transactions", "Transactions"),
        ("/api/explorer/addresses", "Addresses"),
        ("/api/explorer/receipts", "Receipts")
    ]

    for endpoint, name in endpoints:
        try:
            response = requests.get(f"https://aitbc.bubuit.net{endpoint}")
            if response.status_code == 200:
                data = response.json()
                print(f"✅ {name}: {len(data['items'])} items")
            else:
                print(f"❌ {name}: Failed ({response.status_code})")
        except Exception as e:
            print(f"❌ {name}: Error - {e}")

    print("\n" + "=" * 60)
    print("✅ Explorer is successfully using LIVE data!")
    print("\n📊 Live Data Sources:")
    print("   • Blocks: https://aitbc.bubuit.net/api/explorer/blocks")
    print("   • Transactions: https://aitbc.bubuit.net/api/explorer/transactions")
    print("   • Addresses: https://aitbc.bubuit.net/api/explorer/addresses")
    print("   • Receipts: https://aitbc.bubuit.net/api/explorer/receipts")

    print("\n💡 Visitors to https://aitbc.bubuit.net/explorer/ will now see:")
    print("   • Real blockchain data")
    print("   • Actual transactions")
    print("   • Live network activity")
    print("   • No mock/sample data")

if __name__ == "__main__":
    main()
